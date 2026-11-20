# -*- coding: utf-8 -*-
"""DEAL: виртуальная машина — исполнение сделки против свидетель-кейсов.

ПРОЕКТ-ПИЛОТ (ступень 1, питон-ВМ, «дровосек»): медленно нарочно —
скорость меряет skorost/bench.py, натив — ступень 4.

Границы пилота (честно):
  - зовы резолвятся ВНУТРИ файла (ввозы по хешу между файлами — вне пилота);
  - «даёт» договора печатается, но не enforced (лимитация названа);
  - скрытые кейсы не генерируются (суд краёв руками корпуса).
Файлы полки исполняются ТОЛЬКО под E:\\DEAL_PILOT\\polka — наружу нельзя.
"""
import hashlib
import io
import json
import os
import sys
import time

POLKA = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "polka")


#: Канонические отказы ВМ: названы всегда, сделки не обязаны объявлять.
KANON_OTKAZY = {"деление_на_ноль", "нарушен_договор", "полка_не_доступна",
                "нет_договора", "нет_имени", "нет_операции", "полка_наружу",
                # [2.0 П2: отказ-канон полный — ни одна операция ВМ не падает
                # питон-исключением; три канона назвали то, что раньше роняло]
                "типы_не_сошлись", "за_краем", "глубина"}


class DealOtkaz(Exception):
    """Канонический отказ сделки: имя из договора + причина словами."""

    def __init__(self, imya: str, prichina: str = ""):
        self.imya = imya
        self.prichina = prichina
        super().__init__("%s: %s" % (imya, prichina) if prichina else imya)


def _имя_типа(x):
    return {int: "число", float: "число", str: "строка", list: "список",
            dict: "словарь", bool: "статус"}.get(type(x), "статус")


# ── примитивник: замороженный набор операций ВМ (ИИ его не пишет) ──

def _okrugleno(args):
    # [вопрос QWEN 14.11: правило половин] ПИЛОТ-КАНОН: половина вверх
    # (математическое). Питон-round — банковское (2,5 -> 2) и молча бы
    # считал по-другому; фиксируем правило в ВМ нарочно.
    import math
    x, n = float(args[0]), int(args[1])
    koeff = 10 ** n
    if x >= 0:
        return math.floor(x * koeff + 0.5) / koeff
    return -math.floor(-x * koeff + 0.5) / koeff


def _summa(args):
    return sum(args[0])


def _hash(args):
    return hashlib.sha256(str(args[0]).encode("utf-8")).hexdigest()


def _polka_chitaj_ili(args):
    """Чтение с умолчанием [П4]: через кэш полки; файла нет/не разобрался —
    умолчание, не отказ."""
    adres, umolchanie = args[0], args[1]
    return _polka_chitai_ili_kanon(adres, umolchanie)


def _element_bezopasno(args):
    """[2.0 П2] элемент: край и тип — канон-отказ, не IndexError."""
    sp, i = args[0], args[1]
    if not isinstance(sp, (list, str)):
        raise DealOtkaz("типы_не_сошлись",
                        "элемент ждёт список, а получил %s — проверь тип"
                        % _имя_типа(sp))
    try:
        nomer = int(i)
    except (TypeError, ValueError):
        raise DealOtkaz("типы_не_сошлись",
                        "элемент ждёт номер, а получил «%r» — приведи к числу" % (i,))
    if nomer < 0 or nomer >= len(sp):
        raise DealOtkaz("за_краем",
                        "элемент(список, %d): за краем — длина %d, номера от 0 до %d"
                        % (nomer, len(sp), len(sp) - 1))
    return sp[nomer]


def _bezopasno(imya, funk):
    """Обёртка примитивника [2.0 П2]: сырое исключение = канон-отказ словами
    с именем примитивника и правкой. DealOtkaz проходит насквозь."""
    def bezopasno(args):
        try:
            return funk(args)
        except DealOtkaz:
            raise
        except (TypeError, ValueError, ZeroDivisionError, AttributeError,
                IndexError, KeyError, OverflowError) as beda:
            raise DealOtkaz("типы_не_сошлись",
                            "примитив «%s» не взял аргументы: %s: %s — проверь типы и края"
                            % (imya, type(beda).__name__, str(beda)[:90]))
    return bezopasno


PRIMITIVY = {
    "округлено": _okrugleno,
    "хеш": _hash,
    "сумма": lambda a: sum(a[0]),
    "длина": lambda a: len(a[0]),
    "максимум": lambda a: max(a[0]),
    "минимум": lambda a: min(a[0]),
    "склейка": lambda a: a[2].join(str(x) for x in a[0]),
    "нижний-регистр": lambda a: str(a[0]).lower(),
    "полка-читай-или": _polka_chitaj_ili,
    "время": lambda a: time.time(),
    "логарифм": lambda a: __import__("math").log(a[0]),
    # [ступень 2: код судит код] примитивники хождения по данным
    "поле-из-или": lambda a: a[0].get(a[1], a[2]) if isinstance(a[0], dict) else a[2],
    "элемент": _element_bezopasno,
    "тип-из": lambda a: _имя_типа(a[0]),
    # [ступень 2: суд_выполнимости споткнулся — новым списком язык не умел
    # строить: константа-[] — общий мутабельный объект AST, автосоздание
    # живёт только в присоединить. Конструктор: список() -> [], список(а,б) -> [а,б]]
    "список": lambda a: list(a),
    # [ступень 2, саммит: применитель превращений строит AST — языку нужны
    # словари: пустой конструктор, список ключей, запись по ключу]
    "словарь": lambda a: {},
    "ключи": lambda a: list(a[0].keys()),
    "поле-записать": lambda a: (a[0].__setitem__(a[1], a[2]), a[0])[1],
    # [2.0 S1: компилятор байткода на DEAL патчит прыжки по индексу —
    # запись элемента списка по номеру]
    "поставить": lambda a: (a[0].__setitem__(int(a[1]), a[2]), a[0])[1],
}

# [2.0 П2] отказ-канон полный: каждый примитивник в безопасной обёртке —
# сырое исключение поднимается канон-отказом «типы_не_сошлись» с правкой
PRIMITIVY = {imya: _bezopasno(imya, funk) for imya, funk in PRIMITIVY.items()}


# ── исполнение выражений ──

#: [2.0 П3] рубильник пути исполнения: байткод = канон-AST компилируется в
#: стековый код (deal/bajtkod.py); кодоген = тело компилируется в питон-
#: функцию (deal/kodogen.py); оба выкл = интерпретатор AST (мерка сравнения)
РЕЖИМ = {"байткод": True, "кодоген": False}

_ОПЫ_ВЫР = {"константа", "поле", "зов", "сравнение", "арифметика",
            "и", "или", "не", "полка-читай", "полка-пиши"}


def _арифметика(lev, chem, prav):
    """Чистая арифметика: деление на ноль — канон, прочее — вверх на TypeError
    (сеть vyzhit переводит в «типы_не_сошлись» с типами)."""
    if chem == "+":
        return lev + prav
    if chem == "-":
        return lev - prav
    if chem == "*":
        return lev * prav
    if chem == "/":
        if prav == 0:
            raise DealOtkaz("деление_на_ноль", "правая часть равна 0")
        return lev / prav
    if chem == "%":
        if prav == 0:
            raise DealOtkaz("деление_на_ноль", "модуль по нулю")
        return lev % prav
    raise DealOtkaz("нет_операции", "неизвестная арифметика «%s»" % chem)


_СЫРЬЕ = (TypeError, ValueError, KeyError, AttributeError, IndexError, OverflowError)


def vyzhit(expr, env, sdelki):
    """Сеть [2.0 П2]: сырое исключение кривого узла = канон-отказ словами.
    [П3] рубильник РЕЖИМ["байткод"]: исполнение через стековый код."""
    op0 = expr.get("оп") if isinstance(expr, dict) else None
    if РЕЖИМ["байткод"] and op0 in _ОПЫ_ВЫР:
        try:
            from deal import bajtkod as dbk
            return dbk.vyrazh_znach(expr, env, sdelki)
        except DealOtkaz:
            raise
        except RecursionError:
            raise DealOtkaz("глубина", "выражение ушло в глубину — проверь рекурсию")
        except _СЫРЬЕ as beda:
            raise DealOtkaz("нет_операции",
                            "кривой узел выражения: %s: %s — правь AST по канону"
                            % (type(beda).__name__, str(beda)[:90]))
    try:
        return _vyzhit_syr(expr, env, sdelki)
    except DealOtkaz:
        raise
    except RecursionError:
        raise DealOtkaz("глубина", "выражение ушло в глубину — проверь рекурсию")
    except _СЫРЬЕ as beda:
        raise DealOtkaz("нет_операции",
                        "кривой узел выражения: %s: %s — правь AST по канону"
                        % (type(beda).__name__, str(beda)[:90]))


def _vyzhit_syr(expr, env, sdelki):
    op = expr.get("оп")
    if op == "константа":
        return expr["значение"]
    if op == "поле":
        imya = expr["имя"]
        if imya not in env:
            raise DealOtkaz("нет_имени", "поле «%s» не объявлено во входах/пусть" % imya)
        return env[imya]
    if op == "и":
        return bool(vyzhit(expr["лево"], env, sdelki)) and             bool(vyzhit(expr["право"], env, sdelki))
    if op == "или":
        return bool(vyzhit(expr["лево"], env, sdelki)) or             bool(vyzhit(expr["право"], env, sdelki))
    if op == "не":
        return not bool(vyzhit(expr["что"], env, sdelki))
    if op == "сравнение":
        lev = vyzhit(expr["лево"], env, sdelki)
        prav = vyzhit(expr["право"], env, sdelki)
        chem = expr["чем"]
        # ЛЕНИВО: только названный оператор исполняется (жадный словарь
        # сравнивал все разом и падал на неупорядочимых типах)
        try:
            if chem == "==":
                return lev == prav
            if chem == "!=":
                return lev != prav
            if chem == "<":
                return lev < prav
            if chem == ">":
                return lev > prav
            if chem == "<=":
                return lev <= prav
            return lev >= prav
        except TypeError:
            raise DealOtkaz("типы_не_сошлись",
                            "сравнение «%s»: %s с %s не сравнить — приведи типы"
                            % (chem, _имя_типа(lev), _имя_типа(prav)))
    if op == "арифметика":
        lev = vyzhit(expr["лево"], env, sdelki)
        prav = vyzhit(expr["право"], env, sdelki)
        chem = expr["чем"]
        try:
            return _арифметика(lev, chem, prav)
        except DealOtkaz:
            raise
        except TypeError:
            raise DealOtkaz("типы_не_сошлись",
                            "арифметика «%s»: %s с %s не считать — приведи типы"
                            % (chem, _имя_типа(lev), _имя_типа(prav)))
    if op == "зов":
        imya = expr["договор"]
        if imya in PRIMITIVY:
            return PRIMITIVY[imya]([vyzhit(a, env, sdelki) for a in expr["аргументы"]])
        if imya not in sdelki:
            raise DealOtkaz("нет_договора",
                            "зов «%s»: договора нет в файле" % imya)
        argy = [vyzhit(a, env, sdelki) for a in expr["аргументы"]]
        return zov_sdelki(sdelki[imya], argy, sdelki)
    if op == "полка-читай":
        return _polka_chitai_kanon(vyzhit(expr["адрес"], env, sdelki))
    if op == "полка-пиши":
        adres = vyzhit(expr["адрес"], env, sdelki)
        znach = vyzhit(expr["значение"], env, sdelki)
        return _polka_zapis_kanon(adres, znach)   # атомарная запись дома
    raise DealOtkaz("нет_операции", "выражение с неизвестной операцией «%s»" % op)


def _polka_put(adres: str) -> str:
    """Файлы полки живут ТОЛЬКО под polka/ — наружу нельзя (граница пилота)."""
    put = os.path.normpath(os.path.join(POLKA, str(adres)))
    if not put.startswith(os.path.normpath(POLKA)):
        raise DealOtkaz("полка_наружу", "адрес полки вылез за границу песка")
    return put


# [2.0 П4] кэш полки: {путь: (mtime, размер, значение)} — массовые чтения
# (цикл по полке, свидетели) не переоткрывают файл; mtime+размер валидируют
# наружные изменения; запись обновляет кэш сама
_ПОЛКА_КАШ = {}


def _polka_chitai_kanon(adres):
    """полка-читай: файла нет / не JSON — полка_не_доступна (канон)."""
    put = _polka_put(adres)
    try:
        st = os.stat(put)
        otpechat = (st.st_mtime_ns, st.st_size)
    except OSError:
        _ПОЛКА_КАШ.pop(put, None)
        raise DealOtkaz("полка_не_доступна", "файла нет на полке")
    zap = _ПОЛКА_КАШ.get(put)
    if zap and zap[0] == otpechat:
        return zap[1]
    try:
        with io.open(put, encoding="utf-8") as fh:
            znach = json.load(fh)
    except ValueError:
        raise DealOtkaz("полка_не_доступна", "файл полки не разобрался как JSON")
    _ПОЛКА_КАШ[put] = (otpechat, znach)
    return znach


def _polka_zapis_kanon(adres, znach):
    """полка-пиши: tmp+replace (атомарно) + кэш обновляется сам."""
    put = _polka_put(adres)
    os.makedirs(os.path.dirname(put), exist_ok=True)
    tmp = put + ".tmp"
    with io.open(tmp, "w", encoding="utf-8") as fh:
        json.dump(znach, fh, ensure_ascii=False, sort_keys=True)
    os.replace(tmp, put)
    st = os.stat(put)
    _ПОЛКА_КАШ[put] = ((st.st_mtime_ns, st.st_size), znach)
    return znach


def _polka_chitai_ili_kanon(adres, umolchanie):
    """полка-читай-или: файла нет / не разобрался — умолчание, не отказ."""
    try:
        return _polka_chitai_kanon(adres)
    except DealOtkaz as otk:
        if otk.imya == "полка_не_доступна":
            return umolchanie
        raise


# ── исполнение тела ──

_ГЛУБИНА_ПОТОЛОК = 300   # [2.0 П2] рекурсия зова — под контрактом, не RecursionError
# запас стека питона поднят, чтобы граница срабатывала КОНТРАКТОМ (счётчик
# на 300), а спасательной сетью
sys.setrecursionlimit(3000)
_глубина = 0


def vypolnit_telo(telo, env, sdelki):
    """Возвращает ("верни", значение) или None. Сеть [2.0 П2]: кривой узел
    тела = канон-отказ словами, не KeyError. [П3] рубильники РЕЖИМ:
    «кодоген» > «байткод» > интерпретатор."""
    if РЕЖИМ.get("кодоген") and telo and isinstance(telo[0], dict):
        try:
            from deal import kodogen as dkg
            return dkg.telo_rezultat(telo, env, sdelki)
        except DealOtkaz:
            raise
        except RecursionError:
            raise DealOtkaz("глубина", "тело ушло в глубину — цикл или рекурсия без выхода")
        except _СЫРЬЕ as beda:
            raise DealOtkaz("нет_операции",
                            "кривой узел тела: %s: %s — правь AST по канону"
                            % (type(beda).__name__, str(beda)[:90]))
    if РЕЖИМ["байткод"] and telo and isinstance(telo[0], dict) \
            and telo[0].get("оп") in ("присваивание", "верни", "стой", "присоединить",
                                       "полка-пиши", "если", "для-каждого-до"):
        try:
            from deal import bajtkod as dbk
            return dbk.telo_rezultat(telo, env, sdelki)
        except DealOtkaz:
            raise
        except RecursionError:
            raise DealOtkaz("глубина", "тело ушло в глубину — цикл или рекурсия без выхода")
        except _СЫРЬЕ as beda:
            raise DealOtkaz("нет_операции",
                            "кривой узел тела: %s: %s — правь AST по канону"
                            % (type(beda).__name__, str(beda)[:90]))
    try:
        return _telo_syr(telo, env, sdelki)
    except DealOtkaz:
        raise
    except RecursionError:
        raise DealOtkaz("глубина", "тело ушло в глубину — цикл или рекурсия без выхода")
    except _СЫРЬЕ as beda:
        raise DealOtkaz("нет_операции",
                        "кривой узел тела: %s: %s — правь AST по канону"
                        % (type(beda).__name__, str(beda)[:90]))


def _telo_syr(telo, env, sdelki):
    for st in telo:
        op = st.get("оп")
        if op == "присваивание":
            if "имя" not in st:
                raise DealOtkaz("нет_операции", "присваивание без «имя» — правь тело")
            env[st["имя"]] = vyzhit(st["что"], env, sdelki)
        elif op == "верни":
            return ("верни", vyzhit(st["что"], env, sdelki))
        elif op == "стой":
            if "отказ" not in st:
                raise DealOtkaz("нет_операции", "стой без имени отказа — назови отказ")
            # [2.0 П2] стой несёт причину структурой: st["причина"] — строка
            raise DealOtkaz(st["отказ"],
                            st.get("причина") or "стой по договору сделки")
        elif op == "присоединить":
            # [найдено A/B-тестом ступени 1: сверка полок требует сбора
            # списков — «только отсутствующее» без сбора не выразить]
            if "имя" not in st:
                raise DealOtkaz("нет_операции", "присоединить без «имя» — правь тело")
            spisok = env.get(st["имя"])
            if not isinstance(spisok, list):
                spisok = []
                env[st["имя"]] = spisok  # автосоздание: первый элемент создаёт список
            spisok.append(vyzhit(st["что"], env, sdelki))
        elif op == "полка-пиши":
            _polka_zapis_kanon(vyzhit(st["адрес"], env, sdelki),
                               vyzhit(st["значение"], env, sdelki))
        elif op == "если":
            vetv = st.get("то", []) if vyzhit(st.get("условие", {"оп": "константа",
                                                                  "значение": True}),
                                               env, sdelki) else st.get("иначе", [])
            itog = vypolnit_telo(vetv, env, sdelki)
            if itog:
                return itog
        elif op == "для-каждого-до":
            if "переменная" not in st:
                raise DealOtkaz("нет_операции", "цикл без переменной — правь тело")
            try:
                do = int(vyzhit(st["до"], env, sdelki))
            except DealOtkaz:
                raise
            except (TypeError, ValueError):
                raise DealOtkaz("типы_не_сошлись",
                                "«до» цикла ждёт целое число — проверь границу")
            for i in range(do):
                env[st["переменная"]] = i
                itog = vypolnit_telo(st.get("тело", []), env, sdelki)
                if itog:
                    return itog
        else:
            raise DealOtkaz("нет_операции", "тело: неизвестная операция «%s»" % op)
    return None


def zov_sdelki(sdelka, argy, sdelki):
    global _глубина
    vhody = sdelka.get("входы", [])
    # [2.0 П2] молча-обрезающий zip заменён контрактом: число аргументов —
    # часть договора
    if len(argy) != len(vhody):
        raise DealOtkaz("нарушен_договор",
                        "зов «%s»: у сделки %d вход(ов), а подали %d — согласуй аргументы"
                        % (sdelka.get("имя", "?"), len(vhody), len(argy)))
    _глубина += 1
    try:
        if _глубина > _ГЛУБИНА_ПОТОЛОК:
            raise DealOtkaz("глубина",
                            "рекурсия глубже %d: сделка «%s» зовёт себя без остановки"
                            % (_ГЛУБИНА_ПОТОЛОК, sdelka.get("имя", "?")))
        env = {}
        for vhod, znach in zip(vhody, argy):
            env[vhod["имя"]] = znach
        trebuet = sdelka.get("требует")
        if trebuet and not vyzhit(trebuet, env, sdelki):
            raise DealOtkaz("нарушен_договор", "требует не выполнено: %s"
                            % json.dumps(trebuet, ensure_ascii=False))
        itog = vypolnit_telo(sdelka.get("тело", []), env, sdelki)
        return itog[1] if itog else None
    finally:
        _глубина -= 1


# ── свидетели ──

def _sravnit(polucheno, ozhidaemoe) -> bool:
    if isinstance(ozhidaemoe, (int, float)) and isinstance(polucheno, (int, float)):
        return abs(float(polucheno) - float(ozhidaemoe)) < 1e-9
    return polucheno == ozhidaemoe


def gonit_svideteley(sdelka, sdelki) -> dict:
    """Исполнить все кейсы свидетеля сделки. Наружу — свод.

    Ступень 1: постусловие «даёт» договора исполняется на КАЖДОМ кейсе
    после тела — несходство красит сделку, даже если кейс сошёлся
    (двойной суд: тело и договор)."""
    itogi = []
    daet = sdelka.get("даёт")
    for n, kz in enumerate(sdelka.get("свидетель", []), 1):
        env = dict(kz.get("вход", {}))
        # ФИКСАТУРА [мина ступени 1: свидетели с состоянием не идемпотентны —
        # зелёный счётчик стоял на ручном сбросе]. Верификатор сам ставит
        # полку в заявленное состояние ПЕРЕД исполнением кейса.
        if kz.get("фиксатура"):
            for адрес, znach in kz["фиксатура"].items():
                _polka_zapis_kanon(адрес, znach)   # [П4] и кэш обновляется
        daet_ok = True
        try:
            rez = vypolnit_telo(sdelka.get("тело", []), env, sdelki)
            polucheno = rez[1] if rez else None
            if daet and not isinstance(polucheno, tuple):
                env["это"] = polucheno
                daet_ok = bool(vyzhit(daet, env, sdelki))
        except DealOtkaz as otk:
            polucheno = ("отказ", otk.imya)
        if "отказ" in kz:
            shoditsya = isinstance(polucheno, tuple) and polucheno[0] == "отказ" \
                and polucheno[1] == kz["отказ"]
            itogi.append({"кейс": n, "ожидали": "отказ %s" % kz["отказ"],
                          "сошлось": shoditsya})
        elif "свойство" in kz:
            # кейс-свойство: результат подаётся в выражение как «это» —
            # для значений, которые нельзя зафиксировать числом (время, хеш)
            env["это"] = polucheno
            shoditsya = (not isinstance(polucheno, tuple)) and \
                bool(vyzhit(kz["свойство"], env, sdelki)) and daet_ok
            itogi.append({"кейс": n, "ожидали": "свойство", "получили": polucheno,
                          "сошлось": shoditsya})
        else:
            shoditsya = not isinstance(polucheno, tuple) and \
                _sravnit(polucheno, kz.get("выход")) and daet_ok
            itogi.append({"кейс": n, "ожидали": kz.get("выход"),
                          "получили": polucheno, "сошлось": shoditsya,
                          "даёт": daet_ok})
    vsyo = all(i["сошлось"] for i in itogi)
    return {"сделка": sdelka["имя"], "кейсы": itogi, "зелёная": vsyo}
