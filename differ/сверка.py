# -*- coding: utf-8 -*-
"""Сверка вердиктов двух исполнителей дифференциал-корпуса [v0.7.0, №14].

Сравнение структурное ПОСЛЕ канонизации (оба прогона нормализуют числа
одинаково: целозначные дробные → целые, дробные → 9 знаков): каждый кейс —
значение или {"отказ": канон-имя}. Причина отказа словами не сверяется —
хост-формулировки (граница названа).

Прогон: python differ/сверка.py <itogi_python.json> <itogi_js.json>
Наружу: «N/N кейсов, расхождений 0» и код 0 — либо список расхождений, код 1.
"""
import io
import json
import sys


def ravno(a, b):
    if isinstance(a, bool) or isinstance(b, bool):
        return isinstance(a, bool) and isinstance(b, bool) and a == b
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return a == b
    if type(a) is not type(b):
        return False
    if isinstance(a, list):
        return len(a) == len(b) and all(ravno(x, y) for x, y in zip(a, b))
    if isinstance(a, dict):
        return set(a) == set(b) and all(ravno(a[k], b[k]) for k in a)
    return a == b


def main():
    with io.open(sys.argv[1], encoding="utf-8") as fh:
        py = json.load(fh)
    with io.open(sys.argv[2], encoding="utf-8") as fh:
        js = json.load(fh)
    if py["кейсов"] != js["кейсов"]:
        print("ЧИСЛО КЕЙСОВ разошлось: %s против %s" % (py["кейсов"],
                                                        js["кейсов"]))
        raise SystemExit(1)
    rasshozhdeniya = []
    for p, j in zip(py["результаты"], js["результаты"]):
        if p["сделка"] != j["сделка"] or p["кейс"] != j["кейс"]:
            print("ПОРЯДОК разошёлся: %s/%s против %s/%s"
                  % (p["сделка"], p["кейс"], j["сделка"], j["кейс"]))
            raise SystemExit(1)
        if not ravno(p["итог"], j["итог"]):
            rasshozhdeniya.append({
                "сделка": p["сделка"], "кейс": p["кейс"], "метка": p["метка"],
                "питон": p["итог"], "js": j["итог"]})
    vsego = py["кейсов"]
    if rasshozhdeniya:
        print("%d/%d кейсов сошлись, РАСХОЖДЕНИЙ %d:" % (
            vsego - len(rasshozhdeniya), vsego, len(rasshozhdeniya)))
        for r in rasshozhdeniya:
            print("  %s/%s (%s): питон %s ≠ js %s" % (
                r["сделка"], r["кейс"], r["метка"],
                json.dumps(r["питон"], ensure_ascii=False),
                json.dumps(r["js"], ensure_ascii=False)))
        raise SystemExit(1)
    print("%d/%d кейсов, расхождений 0 — веб-интерпретатор и пилот сходятся"
          % (vsego, vsego))
    raise SystemExit(0)


if __name__ == "__main__":
    main()
