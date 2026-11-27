# -*- coding: utf-8 -*-
"""DEAL: публикуемый бенчмарк интерпретатора [v0.8.0, раунд 9 QWEN P3].

Закрывает вопрос воспроизводимости: три задачи сайта (сумма-цикл, массовый
зов деления, полка 300 чтений-записей) × три пути исполнения, питон-
базлайн — чистый цикл/файл (не NumPy), машина и режим в выводе, медиана 5.
Перед замером результаты DEAL и питона СВЕРЯЮТСЯ — гонки меряют одно и то
же. Результат — skorost/rezultat.json рядом с пакетом.

Прогон: python skorost/bench.py [аст|байткод|кодоген|все]   (умолчание все)
"""
import copy
import io
import json
import os
import platform
import statistics
import sys
import time

KOREN = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, KOREN)

from deal import vm as dvm  # noqa: E402

N = 20000
POLKA_ADRES = "skorost_bench_tmp.json"


def pole(i):
    return {"оп": "поле", "имя": i}


def kst(z):
    return {"оп": "константа", "значение": z}


def ar(c, l, p):
    return {"оп": "арифметика", "чем": c, "лево": l, "право": p}


def sr(c, l, p):
    return {"оп": "сравнение", "чем": c, "лево": l, "право": p}


def zov(i, *a):
    return {"оп": "зов", "договор": i, "аргументы": list(a)}


SUM = [{"оп": "присваивание", "имя": "с", "что": kst(0)},
       {"оп": "для-каждого-до", "переменная": "и", "до": pole("н"),
        "тело": [{"оп": "присваивание", "имя": "с",
                  "что": ar("+", pole("с"), pole("и"))}]},
       {"оп": "верни", "что": pole("с")}]

DIV = {"имя": "деление",
       "входы": [{"имя": "а", "тип": "число"}, {"имя": "б", "тип": "число"}],
       "тело": [{"оп": "если", "условие": sr("==", pole("б"), kst(0)),
                 "то": [{"оп": "стой", "отказ": "деление_на_ноль"}],
                 "иначе": []},
                {"оп": "верни", "что": ar("/", pole("а"), pole("б"))}]}

CALLS = [{"оп": "присваивание", "имя": "р", "что": kst(0)},
         {"оп": "для-каждого-до", "переменная": "и", "до": pole("н"),
          "тело": [{"оп": "присваивание", "имя": "р",
                    "что": zov("деление", kst(100000), kst(4))}]},
         {"оп": "верни", "что": pole("р")}]

SHELF = [{"оп": "для-каждого-до", "переменная": "и", "до": kst(300),
          "тело": [{"оп": "полка-пиши", "адрес": kst(POLKA_ADRES),
                    "значение": pole("и")},
                   {"оп": "присваивание", "имя": "х",
                    "что": {"оп": "полка-читай", "адрес": kst(POLKA_ADRES)}}]},
         {"оп": "верни", "что": pole("х")}]

SD = {"деление": DIV}


def deal(t, e, s):
    dvm._toplivo_sbrodit()
    return dvm.vypolnit_telo(copy.deepcopy(t), copy.deepcopy(e), s)


def py_sum(n):
    s = 0
    for i in range(n):
        s = s + i
    return s


def py_calls(n):
    r = 0.0
    for i in range(n):
        r = 100000 / 4
    return r


def py_shelf():
    put = os.path.join(KOREN, "polka", POLKA_ADRES)
    x = None
    for i in range(300):
        with io.open(put, "w", encoding="utf-8") as fh:
            json.dump(i, fh)
        with io.open(put, encoding="utf-8") as fh:
            x = json.load(fh)
    return x


def med(f, reps=5):
    ts = []
    for _ in range(reps):
        t0 = time.perf_counter()
        f()
        ts.append((time.perf_counter() - t0) * 1000)
    return round(statistics.median(ts), 2)


def main():
    arg = sys.argv[1] if len(sys.argv) > 1 else "все"
    rezhimy = ["аст", "байткод", "кодоген"] if arg == "все" else [arg]
    for r in rezhimy:
        if r not in ("аст", "байткод", "кодоген"):
            print("режимы: аст | байткод | кодоген | все")
            raise SystemExit(2)
    py = {"сумма": med(lambda: py_sum(N)), "зовы": med(lambda: py_calls(N)),
          "полка": med(py_shelf)}
    print("машина:", platform.platform(), "| Python",
          platform.python_version())
    print("питон (мс):", py)
    itog = {"машина": platform.platform(),
            "python": platform.python_version(),
            "задач": N, "питон": py, "deal": {}}
    for r in rezhimy:
        dvm.РЕЖИМ.update(байткод=(r == "байткод"), кодоген=(r == "кодоген"))
        # сверка результатов ДО замера: гонки меряют одно и то же
        s1 = deal(SUM, {"н": N}, {})[1]
        s2 = deal(CALLS, {"н": N}, SD)[1]
        s3 = deal(SHELF, {}, {})[1]
        assert s1 == py_sum(N) and s2 == py_calls(N) and s3 == 299, \
            "результаты разошлись: %r %r %r" % (s1, s2, s3)
        d = {"сумма": med(lambda: deal(SUM, {"н": N}, {})),
             "зовы": med(lambda: deal(CALLS, {"н": N}, SD)),
             "полка": med(lambda: deal(SHELF, {}, {}))}
        itog["deal"][r] = d
        print("%-8s сумма %8.2f (×%.1f) | зовы %8.2f (×%.1f) | полка %8.2f (×%.2f)"
              % (r, d["сумма"], d["сумма"] / py["сумма"],
                 d["зовы"], d["зовы"] / py["зовы"],
                 d["полка"], d["полка"] / py["полка"]))
    papka = os.path.join(KOREN, "skorost")
    os.makedirs(papka, exist_ok=True)
    with io.open(os.path.join(papka, "rezultat.json"), "w",
                 encoding="utf-8", newline="\n") as fh:
        json.dump(itog, fh, ensure_ascii=False, indent=1)
    print("итог → skorost/rezultat.json")


if __name__ == "__main__":
    main()
