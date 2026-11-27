# -*- coding: utf-8 -*-
"""Питон-прогон дифференциал-корпуса [v0.7.0, №14].

Каждый кейс исполняется штатной ВМ пакета (vypolnit_telo, боевой путь —
байткод-рубильник включён), результат канонизируется (дробные с целым
значением → целые, дробные → 9 знаков) и пишется JSON-ом.

Прогон: python differ/прогон_питоном.py <korpus.json> <itogi_python.json>
"""
import copy
import io
import json
import os
import sys

KOREN = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, KOREN)

from deal import vm as dvm  # noqa: E402


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
    put_korpusa = sys.argv[1]
    put_itogov = sys.argv[2]
    with io.open(put_korpusa, encoding="utf-8") as fh:
        korpus = json.load(fh)
    itogi = []
    nomer = 0
    for sdelka in korpus["сделки"]:
        sdelki = {s["имя"]: s for s in korpus["сделки"]}
        telo = sdelka.get("тело", [])
        for n, kz in enumerate(sdelka.get("свидетель", []), 1):
            nomer += 1
            dvm._toplivo_sbrodit()
            try:
                rez = dvm.vypolnit_telo(copy.deepcopy(telo),
                                        copy.deepcopy(kz.get("вход", {})),
                                        sdelki)
                itog = kanonich(rez[1] if rez else None)
            except dvm.DealOtkaz as otk:
                itog = {"отказ": otk.imya}
            itogi.append({"сделка": sdelka["имя"], "кейс": n,
                          "метка": kz.get("метка", ""), "итог": itog})
    with io.open(put_itogov, "w", encoding="utf-8", newline="\n") as fh:
        json.dump({"исполнитель": "python-vm", "кейсов": nomer,
                   "результаты": itogi}, fh, ensure_ascii=False, indent=1)
    print("питон: %d кейсов → %s" % (nomer, put_itogov))


if __name__ == "__main__":
    main()
