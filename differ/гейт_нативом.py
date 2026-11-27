# -*- coding: utf-8 -*-
"""Натив-гейт «ВМ == C» [v0.10.0, раунд 11 QWEN].

Каждый СВИДЕТЕЛЬ-КЕЙС поддержанной числовой сделки корпуса исполняется
питон-ВМ и нативом (deal/kodogen_c.py, cc -O2), вердикты канонизируются и
сверяются. Нечисловые сделки и не поддержанные гейтом — пропускаются
(named). Канон-отказы кернела (деление_на_ноль, стой) сверяются именами;
контракт/хост-отказы (топливо, глубина, нет_имени…) судит только ВМ.

Прогон: python differ/гейт_нативом.py <korpus.json>
Без cc на хосте — честный пропуск (код 0, «cc нет — гейт пропущен»);
CI-ubuntu/macos прогоняет его систематически.
"""
import json
import os
import shutil
import sys

KOREN = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, KOREN)

from deal import vm as dvm  # noqa: E402
from deal import kodogen_c as dc  # noqa: E402


def kanonich(x):
    if isinstance(x, bool):
        return x
    if isinstance(x, int):
        return x
    if isinstance(x, float):
        if x != x or x in (float("inf"), float("-inf")):
            return None
        if x.is_integer() and abs(x) <= 1e15:
            return int(x)
        return round(x, 9)
    if isinstance(x, str):
        return x
    if isinstance(x, list):
        return [kanonich(y) for y in x]
    if isinstance(x, dict):
        return {k: kanonich(v) for k, v in x.items()}
    return None


def main():
    put_korpusa = sys.argv[1] if len(sys.argv) > 1 else os.path.join(
        KOREN, "differ", "korpus.json")
    with open(put_korpusa, encoding="utf-8") as fh:
        korpus = json.load(fh)

    # cc есть на хосте? нет — честный пропуск (натив-гейт уедет в CI)
    import subprocess
    try:
        subprocess.run(["cc", "--version"], capture_output=True, check=True)
    except (OSError, subprocess.CalledProcessError):
        print("cc нет на хосте — натив-гейт пропущен (CI-ubuntu прогонит)")
        return

    sdelki = {s["имя"]: s for s in korpus["сделки"]}
    podderzh = [im for im, s in sdelki.items() if dc.podderzhivaema(s, sdelki)]
    if not podderzh:
        print("натив-гейт: поддержанных сделок 0 — пропуск")
        return
    katalog = os.path.join(KOREN, "skorost", "deal_c_gate")
    shutil.rmtree(katalog, ignore_errors=True)
    ker = {im: sdelki[im] for im in podderzh}
    so, I = dc.sobrat(ker, katalog)
    lib = dc.zagruzit(so, ker, I)

    itog = []
    rassh = 0
    propush = 0
    ПРЕДЕЛ = 2 ** 53
    for im in podderzh:
        sdelka = sdelki[im]
        telo = sdelka.get("тело", [])
        for n, kz in enumerate(sdelka.get("свидетель", []), 1):
            vhod = kz.get("вход", {})
            argy = [vhod.get(v["имя"]) for v in sdelka.get("входы", [])]
            # [v0.10.1] тип-кейсы и >2^53: контракт типов и f64-канон судит
            # ВМ; натив такими аргументами не зовётся (named-пропуск)
            if not all(isinstance(a, (int, float))
                       and not isinstance(a, bool)
                       and abs(a) <= ПРЕДЕЛ for a in argy):
                propush += 1
                continue
            dvm._toplivo_sbrodit()
            try:
                r = dvm.vypolnit_telo(json.loads(json.dumps(telo)),
                                      json.loads(json.dumps(vhod)), sdelki)
                vm_itog = kanonich(r[1] if r else None)
            except dvm.DealOtkaz as otk:
                vm_itog = {"отказ": otk.imya}
            nativ = dc.zov(lib, sdelka, argy, I)
            c_itog = ({"отказ": nativ[1]} if nativ[0] == "отказ"
                      else kanonich(nativ[1]))
            soshlo = vm_itog == c_itog
            itog.append((im, n, soshlo, vm_itog, c_itog))
            rassh += 0 if soshlo else 1
    vsego = len(itog)
    if rassh:
        print("натив-гейт: %d/%d — РАСХОЖДЕНИЙ %d:" % (
            vsego - rassh, vsego, rassh))
        for im, n, ok, a, b in itog:
            if not ok:
                print("  %s/%s: ВМ %s ≠ C %s" % (im, n,
                                                 json.dumps(a, ensure_ascii=False),
                                                 json.dumps(b, ensure_ascii=False)))
        raise SystemExit(1)
    print("натив-гейт: %d/%d кейсов — ВМ и C сходятся "
          "(пропущено named: %d)" % (vsego, vsego, propush))
    shutil.rmtree(katalog, ignore_errors=True)


if __name__ == "__main__":
    main()
