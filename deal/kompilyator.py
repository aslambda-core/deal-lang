# -*- coding: utf-8 -*-
"""DEAL: компилятор — 8 стадий сделки (пилот ступени 1).

Стадии: 1 прим · 2 полнота · 3 выполнимость · 4 свидетели · 5 хеш ·
6 летопись · 7 реестр · 8 выдача. Отказ — всегда словами:
{стадия, виновник, причина, что_править}.
"""
import copy
import hashlib
import io
import json
import os
import sys
import time

# [v0.2.0, мина 3.14: каталог deal/ в sys.path затенял stdlib ast (наш
# ast.py) — цепочка concurrent.futures->logging->ast падала; каталог
# модуля из пути убирается, пакет резолвится только через корень]
_наш_каталог = os.path.dirname(os.path.abspath(__file__))
_корень = os.path.dirname(_наш_каталог)
sys.path[:] = [p for p in sys.path if os.path.abspath(p or ".") != _наш_каталог]
sys.path.insert(0, _корень)

from deal import ast as dast
from deal import kesh as dkesh
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
                "нет_договора", "нет_имени", "нет_операции", "полка_наружу",
                "типы_не_сошлись", "за_краем", "глубина",
                "топливо"}  # [v0.1.2: канон-список выровнен с ВМ]


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


def _parall_rabochiy(zadanie):
    """[v0.2.0] Воркер пула: гонит свидетелей одной сделки в своём процессе
    (обход GIL, изоляция падения). Отказ ВМ возвращается словами —
    в родителе поднимается теми же словами, что и при серийном прогоне."""
    sdelka, sdelki = zadanie
    try:
        return ("ok", dvm.gonit_svideteley(sdelka, sdelki))
    except dvm.DealOtkaz as otk:
        return ("otkaz", otk.imya, otk.prichina)


def _kanon_json(x) -> str:
    """Канон-строка для сверки вердиктов (сверка байт-в-байт по словам)."""
    return json.dumps(x, ensure_ascii=False, sort_keys=True)


def _izmena_v_reestr(klyuch: str, prichina: str):
    """[v0.2.1, аудит: кеш — ускоритель с проверкой; измена (подделка,
    порча, устаревание записи) не молчит — пишется в реестр словами.]"""
    zapis = {"kogda": time.time(), "kto": "kesh-izmena", "klyuch": klyuch,
             "prichina": prichina}
    try:
        with io.open(REESTR, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(zapis, ensure_ascii=False, sort_keys=True) + "\n")
    except OSError:
        pass


def _spot_proba(kesh_proba: int) -> bool:
    """True — это попадание кеша перепроверяется живым счётом.
    Выбор случайный на каждый прогон (os.urandom) — подделщик не может
    выбрать ключ, который никогда не проверяется. kesh_proba=1 — всегда,
    0 или меньше — никогда."""
    if not kesh_proba or kesh_proba < 1:
        return False
    return int.from_bytes(os.urandom(4), "big") % kesh_proba == 0


def _proba_odna(s: dict, env: dict, sdelki: dict, imya: str, kraj: int) -> dict:
    """Один краевой прогон: {tip, imya, beda}. Безымянный отказ и падение
    тела — Otkaz наружу (как и в свежем счёте), такие вердикты не кешируются."""
    try:
        dvm.vypolnit_telo(s.get("тело", []), dict(env), sdelki)
        return {"tip": "ok", "imya": "", "beda": ""}
    except dvm.DealOtkaz as otk:
        if otk.imya not in set(s.get("отказы", [])) | dvm.KANON_OTKAZY:
            raise Otkaz(4, "сделка %s" % s["имя"],
                        "скрытый край %s=%d упал отказом «%s», не названным "
                        "в договоре" % (imya, kraj, otk.imya),
                        "добавь отказ в договор или огради вход требует-ом")
        return {"tip": "otkaz", "imya": otk.imya, "beda": ""}
    except (TypeError, ValueError, ZeroDivisionError, KeyError) as beda:
        raise Otkaz(4, "сделка %s" % s["имя"],
                    "скрытый край %s=%d роняет тело: %s: %s"
                    % (imya, kraj, type(beda).__name__, str(beda)[:80]),
                    "огради вход требует-ом или обработай в теле")


def stadija_4(ast: dict, sdelki=None, parall: bool = False, kesh: bool = True,
              kesh_proba: int = 16) -> list:
    """Свидетели: исполнение в ВМ + скрытые края ступени 1.

    Для каждого числового входа компилятор подставляет край 0 и край
    1 000 000: сделка обязана ответить каноническим отказом (названным
    в договоре) либо осмысленным числом — непредсказуемый крах красит
    сделку [урок заданника: края обязательны в обеих половинах].

    [v0.2.0: вердикты чистых сделок кешируются в .deal_kesh/;
    --parall гонит сделки в пуле процессов.]
    [v0.2.1, шестой аудит: попадание кеша выборочно переисполняется
    (_spot_proba) — подделка/устаревание ловится, запись стирается,
    вердикт пересчитывается, измена пишется в реестр; полочные сделки
    в пул не идут — фиксатуры соседей по полке не перемежаются;
    проба края получает ВСЕ входы (нечисловые — из собственного кейса
    сделки, без кейса — нуль типа): раньше тело ловило нет_имени, а
    требует на нечисловое имя ронял пробу — легальная сделка не
    компилилась.]"""
    sdelki = sdelki if sdelki is not None else _sdelki_fayla(ast)
    sdelki_fayla = ast["сделки"]
    svody = [None] * len(sdelki_fayla)
    k_rabote = []
    for i, s in enumerate(sdelki_fayla):
        verd = None
        klyuch = None
        if kesh and dkesh.chistaya(s, sdelki):
            klyuch = dkesh.klyuch_svoda(s, sdelki)
            verd = dkesh.chitat(klyuch, ("svod",))
        if verd is not None and _spot_proba(kesh_proba):
            # попадание перепроверяется живым счётом
            try:
                zhivoy = dvm.gonit_svideteley(sdelki_fayla[i], sdelki)
            except dvm.DealOtkaz as otk:
                dkesh.udalit(klyuch)
                _izmena_v_reestr(klyuch, "живой счёт упал отказом «%s», "
                                         "запись кеша стёрта" % otk.imya)
                raise Otkaz(4, "сделка %s" % s["имя"],
                            "свидетель упал отказом «%s»: %s" % (otk.imya, otk.prichina),
                            "назови отказ в договоре или исправь тело/кейс")
            if _kanon_json(zhivoy) != _kanon_json(verd["svod"]):
                dkesh.udalit(klyuch)
                _izmena_v_reestr(klyuch, "переисполнение не сошлось с записью — "
                                         "запись стёрта, вердикт пересчитан")
            svody[i] = zhivoy
        elif verd is not None:
            svody[i] = verd["svod"]
        else:
            k_rabote.append(i)
    if k_rabote:
        # полочные сделки не идут в пул: их фиксатуры на полке не должны
        # перемежаться — порядок полочного счёта всегда серийный
        chistye_rabote = [i for i in k_rabote if dkesh.chistaya(sdelki_fayla[i], sdelki)]
        polochnye_rabote = [i for i in k_rabote if not dkesh.chistaya(sdelki_fayla[i], sdelki)]
        if parall and len(chistye_rabote) > 1:
            from concurrent.futures import ProcessPoolExecutor  # только при пуле
            with ProcessPoolExecutor(max_workers=max(1, (os.cpu_count() or 2) - 1)) as pul:
                for i, itog in zip(chistye_rabote,
                                   pul.map(_parall_rabochiy,
                                           [(sdelki_fayla[i], sdelki) for i in chistye_rabote])):
                    if itog[0] == "otkaz":
                        raise Otkaz(4, "сделка %s" % sdelki_fayla[i]["имя"],
                                    "свидетель упал отказом «%s»: %s" % (itog[1], itog[2]),
                                    "назови отказ в договоре или исправь тело/кейс")
                    svody[i] = itog[1]
        else:
            for i in chistye_rabote:
                try:
                    svody[i] = dvm.gonit_svideteley(sdelki_fayla[i], sdelki)
                except dvm.DealOtkaz as otk:
                    raise Otkaz(4, "сделка %s" % sdelki_fayla[i]["имя"],
                                "свидетель упал отказом «%s»: %s" % (otk.imya, otk.prichina),
                                "назови отказ в договоре или исправь тело/кейс")
        for i in polochnye_rabote:
            try:
                svody[i] = dvm.gonit_svideteley(sdelki_fayla[i], sdelki)
            except dvm.DealOtkaz as otk:
                raise Otkaz(4, "сделка %s" % sdelki_fayla[i]["имя"],
                            "свидетель упал отказом «%s»: %s" % (otk.imya, otk.prichina),
                            "назови отказ в договоре или исправь тело/кейс")
        if kesh:
            for i in k_rabote:
                if dkesh.chistaya(sdelki_fayla[i], sdelki):
                    dkesh.pisat(dkesh.klyuch_svoda(sdelki_fayla[i], sdelki), {"svod": svody[i]})
    for s in ast["сделки"]:
        chist = kesh and dkesh.chistaya(s, sdelki)
        baza = dkesh.klyuch_svoda(s, sdelki) if chist else None
        vhody = s.get("входы", [])
        chislennye = [v["имя"] for v in vhody if v.get("тип") == "число"]
        # [v0.2.1] нечисловые входы в пробе не выбрасываются: значение —
        # из собственного кейса сделки (кейсы зелёной сделки удовлетворяют
        # её требует), без кейса — нуль типа
        ne_chislennye = [v for v in vhody if v.get("тип") != "число"]
        nuli_tipov = {"строка": "", "список": [], "словарь": {}, "статус": False,
                      "файл": ""}
        iz_keysa = {}
        for kz in s.get("свидетель", []):
            for v in ne_chislennye:
                if v["имя"] not in iz_keysa and v["имя"] in kz.get("вход", {}):
                    iz_keysa[v["имя"]] = copy.deepcopy(kz["вход"][v["имя"]])
        for imya in chislennye:
            for kraj in (0, 1000000):
                env = {v["имя"]: (kraj if v["имя"] == imya else 1)
                       for v in vhody if v.get("тип") == "число"}
                for v in ne_chislennye:
                    env[v["имя"]] = iz_keysa.get(v["имя"],
                                                 nuli_tipov.get(v.get("тип"), ""))
                env_full = dict(env)
                trebuet = s.get("требует")
                if trebuet:
                    try:
                        ok_treb = dvm.vyzhit(trebuet, env_full, sdelki)
                    except dvm.DealOtkaz:
                        ok_treb = False  # требует не взялся на пробном env — край отсечён
                    if not ok_treb:
                        continue  # требует отсёк край — канонический отказ нарушен_договор
                # [v0.2.0, мина: проба края наследовала счётчик топлива после
                # свидетелей — вердикт зависел от порядка прогонов; дисциплина
                # ВМ «топливо сбрасывается на каждом кейсе» распространена на
                # пробы — вердикт пробы сам за себя]
                dvm._toplivo_sbrodit()
                verd = dkesh.chitat(dkesh.klyuch_kraya(baza, imya, kraj),
                                    ("tip", "imya", "beda")) if chist else None
                if verd is not None and _spot_proba(kesh_proba):
                    zhivoy = _proba_odna(s, env, sdelki, imya, kraj)
                    if _kanon_json(zhivoy) != _kanon_json(verd):
                        dkesh.udalit(dkesh.klyuch_kraya(baza, imya, kraj))
                        _izmena_v_reestr(dkesh.klyuch_kraya(baza, imya, kraj),
                                         "краевая проба не сошлась с записью — "
                                         "запись стёрта, вердикт пересчитан")
                    verd = zhivoy
                elif verd is None:
                    verd = _proba_odna(s, env, sdelki, imya, kraj)
                    if chist:
                        dkesh.pisat(dkesh.klyuch_kraya(baza, imya, kraj), verd)
                if verd["tip"] == "otkaz" and verd["imya"] not in set(s.get("отказы", [])) | dvm.KANON_OTKAZY:
                    raise Otkaz(4, "сделка %s" % s["имя"],
                                "скрытый край %s=%d упал отказом «%s», не названным "
                                "в договоре" % (imya, kraj, verd["imya"]),
                                "добавь отказ в договор или огради вход требует-ом")
                elif verd["tip"] == "beda":
                    raise Otkaz(4, "сделка %s" % s["имя"],
                                "скрытый край %s=%d роняет тело: %s"
                                % (imya, kraj, verd["beda"]),
                                "огради вход требует-ом или обработай в теле")
    return svody


def stadija_5(ast: dict) -> str:
    return dast.hesh(ast)


YAKOR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                     ".deal_letopis_golova")


class _Zamok:
    """Сторож-замок для append-журналов [v0.3.0]: лочится БАЙТ 0 ОТДЕЛЬНОГО
    сторож-файла <журнал>.zamok — один и тот же байт для всех писцов, на весь
    read-think-append. Две мины, пойманные пробой гонки v0.3.0:
    (1) замок только на write не спасает — два писца читают одну голову и
    второй рвёт хеш-цепочку: verify обязан быть ВНУТРИ замка;
    (2) лочить сам журнал нельзя: залоченный байт 0 запрещает и ЧТЕНИЕ
    другим процессам (PermissionError на verify), а байты у EOF у каждого
    писца свои — замки разъезжаются. Сторож никто не читает — только лочит.
    Замок не взялся — пишем без него (не роняем компиляцию)."""

    def __init__(self, put: str):
        self.put = put
        self.storozh = None
        self.zhurnal = None
        self.vzyat = False

    def __enter__(self):
        try:
            import msvcrt
            put_st = self.put + ".zamok"
            self.storozh = io.open(put_st, "ab")
            try:
                if os.path.getsize(put_st) == 0:
                    self.storozh.write(b"0")
                    self.storozh.flush()
                self.storozh.seek(0)
                msvcrt.locking(self.storozh.fileno(), msvcrt.LK_LOCK, 1)
                self.vzyat = True
            except OSError:
                self.vzyat = False
            self.zhurnal = io.open(self.put, "ab")
        except OSError:
            self.snyat()
        return self

    def pishi(self, stroka: str):
        stroka = stroka if stroka.endswith("\n") else stroka + "\n"
        if self.zhurnal is not None:
            try:
                self.zhurnal.write(stroka.encode("utf-8"))
                self.zhurnal.flush()
                return
            except OSError:
                pass
        with io.open(self.put, "a", encoding="utf-8") as fh:
            fh.write(stroka)

    def snyat(self):
        if self.storozh is not None and self.vzyat:
            try:
                import msvcrt
                self.storozh.seek(0)
                msvcrt.locking(self.storozh.fileno(), msvcrt.LK_UNLCK, 1)
            except OSError:
                pass
        for fh in (self.zhurnal, self.storozh):
            if fh is not None:
                try:
                    fh.close()
                except OSError:
                    pass
        self.zhurnal = None
        self.storozh = None

    def __exit__(self, *slovar):
        self.snyat()
        return False


def _dobavit_stroku(put: str, stroka: str):
    """Строка в append-журнал (reestr/letopis) под замком байта 0."""
    with _Zamok(put) as z:
        z.pishi(stroka)


def _chitat_yakor() -> str:
    try:
        with io.open(YAKOR, encoding="utf-8") as fh:
            return fh.read().strip()
    except OSError:
        return ""


def _pisat_yakor(golova: str):
    try:
        with io.open(YAKOR, "w", encoding="utf-8") as fh:
            fh.write(golova)
    except OSError:
        pass


def _proverit_letopis() -> str:
    """[v0.1.3: хеш-цепочка — каждая запись несёт хеш предыдущей.]
    [v0.2.1, аудит: цепочка ПИСАЛАСЬ, но не проверялась — хвостовое
    укорачивание с дописыванием самосогласовано, «нельзя укоротить»
    не enforced. Теперь две проверки при каждой компиляции:
    (1) каждая запись перепроверяется — хеш записи и связь с предыдущей;
    (2) голова сверяется с якорем прошлой компиляции
    (.deal_letopis_golova) — укорачивание хвоста обнаруживается.
    Возврат — голова цепи ("" для пустой летописи).]"""
    if not os.path.exists(LETOPIS):
        yakor = _chitat_yakor()
        if yakor:
            raise Otkaz(6, "летопись",
                        "файла letopis.jsonl нет, а якорь головы есть («%s…») — "
                        "летопись укорочена до нуля" % yakor[:16],
                        "восстанови letopis.jsonl из внешней копии или удали якорь "
                        ".deal_letopis_golova осознанно")
        return ""
    pred = ""
    golova = ""
    nomer = 0
    with io.open(LETOPIS, encoding="utf-8") as fh:
        for stroka in fh:
            stroka = stroka.strip()
            if not stroka:
                continue
            nomer += 1
            try:
                zapis = json.loads(stroka)
            except ValueError:
                raise Otkaz(6, "летопись",
                            "запись %d не разобралась как JSON" % nomer,
                            "летопись append-only — строка искажена; "
                            "восстанови из внешней копии")
            sohran = zapis.pop("hesh_zapisi", None)
            if not sohran or dast.hesh(json.dumps(zapis, ensure_ascii=False,
                                                  sort_keys=True)) != sohran:
                raise Otkaz(6, "летопись",
                            "запись %d: хеш записи не сходится" % nomer,
                            "летопись искажена — восстанови из внешней копии")
            if zapis.get("pred") != pred:
                raise Otkaz(6, "летопись",
                            "запись %d: связь с предыдущей порвана" % nomer,
                            "летопись укорочена или искажена — "
                            "восстанови из внешней копии")
            pred = sohran
    golova = pred
    yakor = _chitat_yakor()
    if yakor and yakor != golova:
        raise Otkaz(6, "летопись",
                    "голова цепи «%s…» не равна якорю прошлой компиляции «%s…» — "
                    "хвост укорочен" % (golova[:16], yakor[:16]),
                    "восстанови letopis.jsonl из внешней копии или удали якорь "
                    ".deal_letopis_golova осознанно")
    return golova


def _dopisat_letopis(zapis: dict) -> str:
    """Проверить цепь, дописать запись, обновить якорь — ВСЁ под одним
    замком (verify вне замка рвал цепь: два писца читали одну голову).
    Общая для компиляции сделки и сборки проекта [v0.3.0]."""
    with _Zamok(LETOPIS) as z:
        zapis["pred"] = _proverit_letopis()
        zapis["hesh_zapisi"] = dast.hesh(json.dumps(
            {k: v for k, v in zapis.items()}, ensure_ascii=False, sort_keys=True))
        z.pishi(json.dumps(zapis, ensure_ascii=False, sort_keys=True))
        _pisat_yakor(zapis["hesh_zapisi"])
    return zapis["hesh_zapisi"]


def stadija_6_7(ast: dict, hesh: str, svody: list, kto: str):
    """Летопись (нельзя укоротить — теперь и ПРОВЕРЯЕТСЯ) + реестр (хеш → компонент).
    [v0.1.3, аудит: хеш уже в реестре — лёгкая запись без полного AST;
    append-only реестр не раздувается дублями.]"""
    zapis = {"kogda": time.time(), "kto": kto, "hesh": hesh,
             "sdelki": [s["имя"] for s in ast.get("сделки", [])],
             "zelenye": sum(1 for s in svody if s["зелёная"]),
             "vsego": len(svody)}
    zapis["hesh_zapisi"] = _dopisat_letopis(zapis)
    uzh = False
    if os.path.exists(REESTR):
        with io.open(REESTR, encoding="utf-8") as fh:
            for stroka in fh:
                if '"hesh"' in stroka and ('"' + hesh + '"') in stroka:
                    uzh = True
                    break
    reestr_zapis = {**zapis}
    if uzh:
        reestr_zapis["tip"] = "povtor"
    else:
        reestr_zapis["ast"] = ast
    _dobavit_stroku(REESTR, json.dumps(reestr_zapis, ensure_ascii=False, sort_keys=True))


def _otkaz_v_reestr(stad, vinovnik, prichina, chto, put_fayla):
    """[v0.1.2, аудит: «РЕЕСТР — что отвергнуто» был словами; отказ
    компилятора пишется в реестр — отвергнутое не исчезает.]"""
    zapis = {"kogda": time.time(), "kto": "otkaz", "tip": "otkaz",
             "stad": stad, "vinovnik": vinovnik, "prichina": prichina,
             "chto": chto, "fajl": os.path.basename(put_fayla)}
    _dobavit_stroku(REESTR, json.dumps(zapis, ensure_ascii=False, sort_keys=True))


def sobrat(put_fayla: str, kto: str = "пилот", parall: bool = False,
           kesh: bool = True, kesh_proba: int = 16, pisat: bool = True) -> dict:
    """Полный цикл: файл .deal → суд всех стадий → реестр. Наружу — свод.
    [v0.2.0: kesh — вердикты чистых сделок из .deal_kesh/; parall — пул
    процессов на свидетелей. Верификация (ввозы по хешу, статика) не
    пропускается никогда — кешируется только исполнение.]
    [v0.2.1: kesh_proba — доля переисполнения попаданий кеша (1 из N;
    0 — выключить, 1 — проверять каждое попадание).]
    [v0.4.0: pisat=False — суд БЕЗ записи реестра/летописи (прогон «до» в
    суде превращения не мусорит хронику; отказы в реестр пишутся как были).]"""
    try:
        ast = dast.zagruzit(put_fayla)
        stadija_1_2(ast)
        sdelki = sdelki_dlya(ast, put_fayla)
        stadija_3(ast, sdelki)
        svody = stadija_4(ast, sdelki, parall=parall, kesh=kesh,
                          kesh_proba=kesh_proba)
        hesh = stadija_5(ast)
        if not all(s["зелёная"] for s in svody):
            ploho = [s for s in svody if not s["зелёная"]][0]
            raise Otkaz(4, "сделка %s" % ploho["сделка"],
                        "кейс не сошёлся: %s" % json.dumps(
                            [k for k in ploho["кейсы"] if not k["сошлось"]][0],
                            ensure_ascii=False),
                        "правь тело или кейс — исполни и сравни руками")
    except Otkaz as otk:
        _otkaz_v_reestr(otk.stad, otk.vinovnik, otk.prichina, otk.chto, put_fayla)
        raise
    except dvm.DealOtkaz as otk:
        _otkaz_v_reestr(0, "исполнение", otk.imya, otk.prichina, put_fayla)
        raise
    if pisat:
        stadija_6_7(ast, hesh, svody, kto)
    return {"hesh": hesh, "svody": svody, "proekciya": dast.projekciya(ast)}


if __name__ == "__main__":
    import sys
    argv = list(sys.argv[1:])
    parall = "--parall" in argv          # [v0.2.0] пул процессов на свидетелей
    kesh = "--bez-kesh" not in argv      # [v0.2.0] кеш вердиктов включён по умолчанию
    # [v0.2.1] доля переисполнения попаданий кеша: 1 из N (умолчание 16);
    # --kesh-proba 0 — никогда, --kesh-proba 1 — каждое попадание
    kesh_proba = 16
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "--kesh-proba" and i + 1 < len(argv):
            kesh_proba = int(argv[i + 1])
            del argv[i:i + 2]
        elif a.startswith("--kesh-proba="):
            kesh_proba = int(a.split("=", 1)[1])
            del argv[i]
        else:
            i += 1
    # [v0.4.0, №9] применение превращения: запрос JSON {файл, превращение, данные}
    if "--превратить" in argv:
        i = argv.index("--превратить")
        if i + 1 >= len(argv):
            print(json.dumps({"стадия": 4, "виновник": "превращение",
                              "причина": "не указан файл запроса",
                              "что_править": "зов: kompilyator.py --превратить "
                              "<zapros.json>"}, ensure_ascii=False))
            raise SystemExit(2)
        zapros_put = argv[i + 1]
        del argv[i:i + 2]
        from deal import prevrashenie
        try:
            with io.open(zapros_put, encoding="utf-8") as fh:
                zapros = json.load(fh)
            itog = prevrashenie.primenit_zapros(zapros, kto="ruki",
                                                kesh=kesh,
                                                kesh_proba=kesh_proba)
        except Exception as otk:   # [мина v0.3.0] суд по словам, не по классу
            if not hasattr(otk, "stad"):
                raise
            print(json.dumps({"стадия": otk.stad, "виновник": otk.vinovnik,
                              "причина": otk.prichina,
                              "что_править": otk.chto}, ensure_ascii=False))
            raise SystemExit(1)
        print(json.dumps(itog, ensure_ascii=False))
        raise SystemExit(0)
    # [v0.3.0, №10] сборка проекта: путь-файл не нужен, нужен путь-папка
    if "--собрать-проект" in argv:
        i = argv.index("--собрать-проект")
        if i + 1 >= len(argv):
            print(json.dumps({"стадия": 1, "виновник": "сборка проекта",
                              "причина": "не указана папка",
                              "что_править": "зов: kompilyator.py --собрать-проект <папка>"},
                             ensure_ascii=False))
            raise SystemExit(2)
        papka = argv[i + 1]
        del argv[i:i + 2]
        from deal import proekt
        try:
            svod = proekt.sobrat_proekt(papka, parall=parall, kesh=kesh,
                                        kesh_proba=kesh_proba)
        except Exception as otk:
            # [мина v0.3.0] скрипт живёт как __main__, а proekt импортирует
            # deal.kompilyator ВТОРОЙ копией — её Otkaz другого класса,
            # except по классу не ловит. Судим по словам (stad/vinovnik есть
            # — отказ компилятора словами; нет — честно роняем дальше).
            if not hasattr(otk, "stad"):
                raise
            print(json.dumps({"стадия": otk.stad, "виновник": otk.vinovnik,
                              "причина": otk.prichina, "что_править": otk.chto},
                             ensure_ascii=False))
            raise SystemExit(1)
        print(json.dumps(svod, ensure_ascii=False))
        raise SystemExit(0 if not svod.get("отказы_список") else 1)
    argv = [a for a in argv if not a.startswith("--")]
    if not argv:
        print("зов: python deal/kompilyator.py <файл.deal> [--parall] [--bez-kesh] "
              "[--kesh-proba N] | --собрать-проект <папка>")
        raise SystemExit(2)
    try:
        itog = sobrat(argv[0], kto="ruki", parall=parall, kesh=kesh,
                      kesh_proba=kesh_proba)
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