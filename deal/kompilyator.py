# -*- coding: utf-8 -*-
"""DEAL: компилятор — 8 стадий сделки (пилот ступени 1).

Стадии: 1 прим · 2 полнота · 3 выполнимость · 4 свидетели · 5 хеш ·
6 летопись · 7 реестр · 8 выдача. Отказ — всегда словами:
{стадия, виновник, причина, что_править}.
"""
import hashlib
import io
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from deal import ast as dast
from deal import vm as dvm

REESTR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                      "reestr.jsonl")
LETOPIS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       "letopis.jsonl")


class Otkaz(Exception):
    """Отказ компилятора словами: виновник, причина, что править."""

    def __init__(self, stad: int, vinovnik: str, prichina: str, chto: str):
        super().__init__("[стадия %d] %s: %s — %s" % (stad, vinovnik, prichina, chto))
        self.stad = stad
        self.vinovnik = vinovnik
        self.prichina = prichina
        self.chto = chto


KANON_OTKAZY = {"деление_на_ноль", "нарушен_договор", "полка_не_доступна",
                "нет_договора", "нет_имени", "нет_операции", "полка_наружу"}


def _sdelki_fayla(ast: dict) -> dict:
    return {s["имя"]: s for s in ast.get("сделки", [])}


def _sud_vyrazheniya(expr, imya_sdelki, izvestnye, stad, obyavleno, sdelki):
    """Суд выражения: поле объявлено, зов существует (примитивник или сделка файла)."""
    op = expr.get("оп")
    if op in ("константа",):
        return
    if op == "поле":
        if expr["имя"] not in obyavleno:
            raise Otkaz(stad, "поле «%s» в %s" % (expr["имя"], imya_sdelki),
                        "поле не объявлено во входах и не присваивалось до использования",
                        "объяви входом или присваиванием до первого использования")
        return
    # [ступень 2: мина — ВМ исполняет и/или/не, а суд молча браковал живые
    # выражения; найдено при постройке DEAL-двойника (sud_vypolnimost.py)]
    if op in ("сравнение", "арифметика", "и", "или"):
        _sud_vyrazheniya(expr["лево"], imya_sdelki, izvestnye, stad, obyavleno, sdelki)
        _sud_vyrazheniya(expr["право"], imya_sdelki, izvestnye, stad, obyavleno, sdelki)
        return
    if op == "не":
        _sud_vyrazheniya(expr["что"], imya_sdelki, izvestnye, stad, obyavleno, sdelki)
        return
    if op == "зов":
        imya = expr["договор"]
        if imya not in sdelki and imya not in dvm.PRIMITIVY:
            raise Otkaz(stad, "зов «%s» в %s" % (imya, imya_sdelki),
                        "договора нет в файле и нет в примитивнике",
                        "добавь сделку или используй примитивник")
        for a in expr.get("аргументы", []):
            _sud_vyrazheniya(a, imya_sdelki, izvestnye, stad, obyavleno, sdelki)
        return
    if op in ("полка-читай", "полка-пиши"):
        _sud_vyrazheniya(expr.get("адрес", {"оп": "константа", "значение": ""}),
                         imya_sdelki, izvestnye, stad, obyavleno, sdelki)
        if "значение" in expr:
            _sud_vyrazheniya(expr["значение"], imya_sdelki, izvestnye, stad, obyavleno, sdelki)
        return
    raise Otkaz(stad, "выражение «%s» в %s" % (op, imya_sdelki),
                "операция неизвестна языку", "используй операции канона")


def _proverit_telo(telo, imya_sdelki, izvestnye, stad, obyavleno, sdelki):
    """Статический суд тела: зовы резолвятся, стой — в отказах, поля объявлялись ДО использования."""
    for st in telo:
        op = st.get("оп")
        if op == "присваивание":
            _sud_vyrazheniya(st["что"], imya_sdelki, izvestnye, stad, obyavleno, sdelki)
            obyavleno.add(st["имя"])
        elif op == "верни":
            _sud_vyrazheniya(st["что"], imya_sdelki, izvestnye, stad, obyavleno, sdelki)
        elif op == "стой":
            if st["отказ"] not in izvestnye and st["отказ"] not in KANON_OTKAZY:
                raise Otkaz(stad, "стой в %s" % imya_sdelki,
                            "отказ «%s» не назван в договоре сделки" % st["отказ"],
                            "добавь отказ в договор или используй канонический")
        elif op == "если":
            _sud_vyrazheniya(st["условие"], imya_sdelki, izvestnye, stad, obyavleno, sdelki)
            _proverit_telo(st["то"], imya_sdelki, izvestnye, stad, obyavleno, sdelki)
            _proverit_telo(st.get("иначе", []), imya_sdelki, izvestnye, stad, obyavleno, sdelki)
        elif op == "для-каждого-до":
            _sud_vyrazheniya(st["до"], imya_sdelki, izvestnye, stad, obyavleno, sdelki)
            obyavleno.add(st["переменная"])
            _proverit_telo(st["тело"], imya_sdelki, izvestnye, stad, obyavleno, sdelki)
        elif op == "присоединить":
            # присоединить ОБЪЯВЛЯЕТ имя: первый элемент создаёт список
            _sud_vyrazheniya(st["что"], imya_sdelki, izvestnye, stad, obyavleno, sdelki)
            obyavleno.add(st["имя"])
        elif op == "полка-пиши":
            _sud_vyrazheniya(st["адрес"], imya_sdelki, izvestnye, stad, obyavleno, sdelki)
            _sud_vyrazheniya(st["значение"], imya_sdelki, izvestnye, stad, obyavleno, sdelki)


def stadija_1_2(ast: dict):
    """Прим + полнота (стадия 1 судит и ФОРМУ ввозов)."""
    if not isinstance(ast, dict) or "сделки" not in ast:
        raise Otkaz(1, "файл", "нет ключа «сделки» — это не .deal AST",
                    "верни JSON с ключом «сделки»")
    vvozy = ast.get("ввозы", [])
    if not isinstance(vvozy, list):
        raise Otkaz(1, "файл", "«ввозы» не список",
                    "оформи ввозы списком {договор, из, хеш}")
    for vvoz in vvozy:
        for pole in ("договор", "из", "хеш"):
            if not isinstance(vvoz, dict) or pole not in vvoz:
                raise Otkaz(1, "ввоз из «%s»" % (vvoz.get("из", "?") if isinstance(vvoz, dict) else "?"),
                            "нет поля «%s» — ввоз не оформлен" % pole,
                            "оформи ввоз {договор, из, хеш}: хеш канона ввозимого файла")
    for s in ast["сделки"]:
        for pole in ("имя", "входы", "тело", "свидетель"):
            if pole not in s:
                raise Otkaz(2, "сделка %s" % s.get("имя", "?"),
                            "нет поля «%s» — договор неполон" % pole,
                            "дополни поле по канону (часть 2 §1 записки)")
        minimum = 2 if s.get("входы") else 1
        # нулевые сделки (без входов) доказываются одним кейсом: входного
        # пространства нет, краёв не бывает
        if len(s["свидетель"]) < minimum:
            raise Otkaz(2, "сделка %s" % s["имя"],
                        "свидетелей %d < %d — сделка не доказана"
                        % (len(s["свидетель"]), minimum),
                        "добавь кейсы, включая край (ноль, пусто, максимум)")


def sdelki_dlya(ast: dict, put_fajla: str) -> dict:
    """Сделки файла + ввозы по хешу (ступень 2). Без ввозов — быстрый путь.
    Отказ сборщика (хеш/имя/файл) переводится в слова компилятора."""
    if not ast.get("ввозы"):
        return _sdelki_fayla(ast)
    try:
        return dast.sdelki_s_vvozyami(ast, os.path.dirname(os.path.abspath(put_fajla)))
    except dvm.DealOtkaz as otk:
        raise Otkaz(1, "ввозы файла «%s»" % ast.get("файл", "?"), otk.prichina,
                    "правь раздел «ввозы» или обнови хеш ввозимого файла")


def stadija_3(ast: dict, sdelki=None):
    """Выполнимость: зовы резолвятся (в т.ч. ввозы), стой в отказах,
    поля объявлялись до использования."""
    sdelki = sdelki if sdelki is not None else _sdelki_fayla(ast)
    for s in ast["сделки"]:
        izvestnye = set(s.get("отказы", []))
        obyavleno = {v["имя"] for v in s.get("входы", [])}
        _proverit_telo(s.get("тело", []), s["имя"], izvestnye, 3, obyavleno, sdelki)


def stadija_4(ast: dict, sdelki=None) -> list:
    """Свидетели: исполнение в ВМ + скрытые края ступени 1.

    Для каждого числового входа компилятор подставляет край 0 и край
    1 000 000: сделка обязана ответить каноническим отказом (названным
    в договоре) либо осмысленным числом — непредсказуемый крах красит
    сделку [урок заданника: края обязательны в обеих половинах]."""
    sdelki = sdelki if sdelki is not None else _sdelki_fayla(ast)
    svody = []
    for s in ast["сделки"]:
        try:
            svody.append(dvm.gonit_svideteley(s, sdelki))
        except dvm.DealOtkaz as otk:
            raise Otkaz(4, "сделка %s" % s["имя"],
                        "свидетель упал отказом «%s»: %s" % (otk.imya, otk.prichina),
                        "назови отказ в договоре или исправь тело/кейс")
    for s in ast["сделки"]:
        chislennye = [v["имя"] for v in s.get("входы", []) if v.get("тип") == "число"]
        for imya in chislennye:
            for kraj in (0, 1000000):
                env = {v["имя"]: (kraj if v["имя"] == imya else 1)
                       for v in s.get("входы", []) if v.get("тип") == "число"}
                env_full = dict(env)
                trebuet = s.get("требует")
                if trebuet and not dvm.vyzhit(trebuet, env_full, sdelki):
                    continue  # требует отсёк край — канонический отказ нарушен_договор
                try:
                    dvm.vypolnit_telo(s.get("тело", []), dict(env), sdelki)
                except dvm.DealOtkaz as otk:
                    if otk.imya not in set(s.get("отказы", [])) | dvm.KANON_OTKAZY:
                        raise Otkaz(4, "сделка %s" % s["имя"],
                                    "скрытый край %s=%d упал отказом «%s», не названным "
                                    "в договоре" % (imya, kraj, otk.imya),
                                    "добавь отказ в договор или огради вход требует-ом")
                except (TypeError, ValueError, ZeroDivisionError, KeyError) as beda:
                    raise Otkaz(4, "сделка %s" % s["имя"],
                                "скрытый край %s=%d роняет тело: %s: %s"
                                % (imya, kraj, type(beda).__name__, str(beda)[:80]),
                                "огради вход требует-ом или обработай в теле")
    return svody


def stadija_5(ast: dict) -> str:
    return dast.hesh(ast)


def stadija_6_7(ast: dict, hesh: str, svody: list, kto: str):
    """Летопись (нельзя укоротить) + реестр (хеш → компонент)."""
    zapis = {"kogda": time.time(), "kto": kto, "hesh": hesh,
             "sdelki": [s["имя"] for s in ast.get("сделки", [])],
             "zelenye": sum(1 for s in svody if s["зелёная"]),
             "vsego": len(svody)}
    for put, obekt in ((LETOPIS, zapis), (REESTR, {**zapis, "ast": ast})):
        with io.open(put, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(obekt, ensure_ascii=False, sort_keys=True) + "\n")


def sobrat(put_fayla: str, kto: str = "пилот") -> dict:
    """Полный цикл: файл .deal → суд всех стадий → реестр. Наружу — свод."""
    ast = dast.zagruzit(put_fayla)
    stadija_1_2(ast)
    sdelki = sdelki_dlya(ast, put_fayla)
    stadija_3(ast, sdelki)
    svody = stadija_4(ast, sdelki)
    hesh = stadija_5(ast)
    if not all(s["зелёная"] for s in svody):
        ploho = [s for s in svody if not s["зелёная"]][0]
        raise Otkaz(4, "сделка %s" % ploho["сделка"],
                    "кейс не сошёлся: %s" % json.dumps(
                        [k for k in ploho["кейсы"] if not k["сошлось"]][0],
                        ensure_ascii=False),
                    "правь тело или кейс — исполни и сравни руками")
    stadija_6_7(ast, hesh, svody, kto)
    return {"hesh": hesh, "svody": svody, "proekciya": dast.projekciya(ast)}


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("зов: python deal/kompilyator.py <файл.deal>")
        raise SystemExit(2)
    try:
        itog = sobrat(sys.argv[1], kto="ruki")
    except Otkaz as otk:
        # отказ компилятора — словами, а не traceback: виновник, причина, что править
        print(json.dumps({"стадия": otk.stad, "виновник": otk.vinovnik,
                          "причина": otk.prichina, "что_править": otk.chto},
                         ensure_ascii=False))
        raise SystemExit(1)
    except dvm.DealOtkaz as otk:
        print(json.dumps({"стадия": 4, "виновник": "исполнение свидетеля",
                          "причина": otk.imya + (" — " + otk.prichina if otk.prichina else ""),
                          "что_править": "назови отказ в договоре или исправь тело/кейс"},
                         ensure_ascii=False))
        raise SystemExit(1)
    print(json.dumps({"hesh": itog["hesh"][:16],
                      "sdelki": [(s["сделка"], s["зелёная"]) for s in itog["svody"]]},
                     ensure_ascii=False))
