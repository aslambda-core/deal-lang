# -*- coding: utf-8 -*-
"""DEAL 2.0, П3б: КОДОГЕН — тело (доказанное статсудом) компилируется в
настоящую питон-функцию и исполняется питоном, а не интерпретатором.

Честные границы:
  * применим только к телам, прошедшим стадию 3 (поля доказаны, зовы есть) —
    прямой env["имя"] законен доказательством; KeyError (если env кривой)
    перехватывается сетью в честный «нет_имени»;
  * арифметика через vm._арифметика (деление_на_ноль — канон, TypeError —
    сеть «типы_не_сошлись»); примитивники — те же обёртки П2; зов сделки —
    через zov_sdelki (арность и глубина — те же контракты);
  * полка/время — те же границы.

Выключатель: vm.РЕЖИМ["кодоген"] (по умолчанию выкл; мерка сравнивает пути).
Честная граница имён: переменные/поля не должны носить служебные имена
генератора (env, _sk, _sp, _pr, _a, _pz, _pc) — канон-печать их не запрещает,
генератор пока не проверяет (названо).
"""
import json
import re

from deal import vm as dvm
from deal.vm import DealOtkaz, PRIMITIVY, zov_sdelki, _арифметика, _polka_put
import io
import os

_КАШ = {}


def funkciya(telo):
    """Питон-функция _f(env, _sk) для тела; кэш по id (сильная ссылка)."""
    klyuch = id(telo)
    if klyuch not in _КАШ:
        stroki = ["def _f(env, _sk):"]
        stroki.append("    try:")
        _gen_telo(telo, "        ", stroki)
        stroki.append("        return None")
        stroki.append("    except DealOtkaz:")
        stroki.append("        raise")
        stroki.append("    except RecursionError:")
        stroki.append('        raise DealOtkaz("глубина", "тело ушло в глубину — проверь рекурсию")')
        stroki.append("    except KeyError as beda:")
        stroki.append('        raise DealOtkaz("нет_имени", "поле %s не объявлено во входах/пусть" % str(beda))')
        stroki.append("    except (TypeError, ValueError, AttributeError, IndexError, OverflowError) as beda:")
        stroki.append('        raise DealOtkaz("типы_не_сошлись", "в кодоген-теле: %s: %s — проверь типы и края" % (type(beda).__name__, str(beda)[:80]))')
        prostor = {"DealOtkaz": DealOtkaz, "_pr": PRIMITIVY, "_zv": zov_sdelki,
                    "_a": _арифметика, "_pz": _polka_zapis, "_pc": _polka_chitai,
                    "_sf": dvm._shag}   # [v0.1.3] топливо в кодогене
        exec(compile("\n".join(stroki), "<kodogen>", "exec"), prostor)
        _КАШ[klyuch] = (telo, prostor["_f"])
    return _КАШ[klyuch][1]


def _polka_chitai(adres):
    """[П4] через канон-хелпер с кэшем полки."""
    return dvm._polka_chitai_kanon(adres)


def _polka_zapis(adres, znach):
    """[П4] через канон-хелпер с кэшем полки."""
    return dvm._polka_zapis_kanon(adres, znach)


def _lit(zn):
    """Литерал значения: repr питон-литералов канона."""
    if zn is True:
        return "True"
    if zn is False:
        return "False"
    if zn is None:
        return "None"
    return repr(zn)


def _vyr(expr):
    """Питон-выражение для узла канона."""
    op = expr.get("оп")
    if op == "константа":
        return _lit(expr["значение"])
    if op == "поле":
        return "env[%s]" % repr(expr["имя"])
    if op == "зов":
        imya = expr["договор"]
        argy = ", ".join(_vyr(a) for a in expr.get("аргументы", []))
        if imya in PRIMITIVY:
            return "_pr[%r]([%s])" % (imya, argy)
        return "_zv(_sk[%r], [%s], _sk)" % (imya, argy)
    if op == "сравнение":
        return "((%s) %s (%s))" % (_vyr(expr["лево"]), expr["чем"], _vyr(expr["право"]))
    if op == "арифметика":
        # [v0.10.0, раунд 11 QWEN P1: «+»/«-» — чистые операторы питона,
        # TypeError ловит та же сеть; «*»/«/»/«%» остаются через _а — там
        # канон-ветки (запрет строк/булевых в «*», floor-mod, деление_на_ноль)]
        if expr["чем"] in ("+", "-"):
            return "((%s) %s (%s))" % (_vyr(expr["лево"]), expr["чем"],
                                       _vyr(expr["право"]))
        return "_a((%s), %r, (%s))" % (_vyr(expr["лево"]), expr["чем"], _vyr(expr["право"]))
    if op == "и":
        return "(bool(%s) and bool(%s))" % (_vyr(expr["лево"]), _vyr(expr["право"]))
    if op == "или":
        return "(bool(%s) or bool(%s))" % (_vyr(expr["лево"]), _vyr(expr["право"]))
    if op == "не":
        return "(not bool(%s))" % _vyr(expr["что"])
    if op == "полка-читай":
        return "_pc(%s)" % _vyr(expr["адрес"])
    if op == "полка-пиши":
        return "_pz(%s, %s)" % (_vyr(expr["адрес"]), _vyr(expr["значение"]))
    raise DealOtkaz("нет_операции", "выражение с неизвестной операцией «%s»" % op)


_IDEN = re.compile(r"^[A-Za-zА-яЁё_][A-Za-z0-9А-яЁё_]*$")


def _iden_ok(imya):
    """[v0.1.2, аудит CWE-94: имя переменной вставляется в генерируемый
    питон-код сырым — легальные имена канона (латиница/кириллица/цифры/_)
    проходят, кривые дают канон-отказ, а не SyntaxError наружу.]"""
    return bool(_IDEN.match(imya or ""))


def _gen_telo(telo, otstup, stroki):
    """Генерация тела; пустой блок канона = pass (питон требует непустой).
    [v0.9.0, раунд 10 QWEN: ЕДИНЫЙ канон топлива] _sf() перед КАЖДЫМ
    оператором (шаг = оператор тела DEAL, как в AST); прежний счёт
    «раз на виток цикла» давал вердикт, зависящий от рубильника. Операторы
    тела цикла генерируются ВНУТРИ python-for — их _sf() исполняется на
    каждой итерации, сам «для» считается один раз."""
    bilo = len(stroki)
    for st in telo:
        op = st.get("оп")
        stroki.append("%s_sf()" % otstup)
        if op == "присваивание":
            stroki.append("%senv[%s] = %s" % (otstup, repr(st["имя"]), _vyr(st["что"])))
        elif op == "верни":
            stroki.append("%sreturn %s" % (otstup, _vyr(st["что"])))
        elif op == "стой":
            prichina = _lit(st.get("причина")) if "причина" in st \
                else '"стой по договору сделки"'
            stroki.append('%sraise DealOtkaz(%r, %s)' % (otstup, st["отказ"], prichina))
        elif op == "присоединить":
            stroki.append("%s_sp = env.get(%r)" % (otstup, st["имя"]))
            stroki.append("%sif not isinstance(_sp, list):" % otstup)
            stroki.append("%s    _sp = []" % otstup)
            stroki.append("%s    env[%s] = _sp" % (otstup, repr(st["имя"])))
            stroki.append("%s_sp.append(%s)" % (otstup, _vyr(st["что"])))
        elif op == "полка-пиши":
            stroki.append("%s_pz(%s, %s)" % (otstup, _vyr(st["адрес"]), _vyr(st["значение"])))
        elif op == "если":
            stroki.append("%sif %s:" % (otstup, _vyr(st["условие"])))
            _gen_telo(st.get("то", []), otstup + "    ", stroki)
            if "иначе" in st or st.get("иначе"):
                stroki.append("%selse:" % otstup)
                _gen_telo(st.get("иначе", []), otstup + "    ", stroki)
        elif op == "для-каждого-до":
            perem = st["переменная"]
            if not _iden_ok(perem):
                raise DealOtkaz("нарушен_договор",
                                "имя переменной цикла «%s» — не идентификатор канона "
                                "(латиница/кириллица/цифры/_ без кавычек и черточек)" % perem)
            stroki.append("%sfor %s in range(int(%s)):" % (otstup, perem, _vyr(st["до"])))
            stroki.append("%s    env[%s] = %s" % (otstup, repr(perem), perem))
            _gen_telo(st.get("тело", []), otstup + "    ", stroki)
        else:
            raise DealOtkaz("нет_операции", "тело: неизвестная операция «%s»" % op)
    if len(stroki) == bilo:
        stroki.append("%spass" % otstup)


def telo_rezultat(telo, env, sdelki):
    """Совместимый с vypolnit_telo итог: ("верни", значение) или None.
    «верни None» неотличим от «нет верни» — результат одинаков (None)."""
    rez = funkciya(telo)(env, sdelki)
    return None if rez is None else ("верни", rez)
