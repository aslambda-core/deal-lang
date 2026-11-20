# -*- coding: utf-8 -*-
"""DEAL 2.0, П3: БАЙТКОД — канон-AST компилируется в ПЛОСКИЙ стековый код.

Всё выражение разворачивается в основной поток инструкций: операнды кладутся
на стек слева направо, операция снимает их оттуда. Исполнитель — ОДИН цикл
по ip, без рекурсии (рекурсия только через зов сделки, где контракт глубины).

Опкоды: PUSH · LOAD · STORE · APPEND · CALL(имя, n) · CMP(чем) · ARITH(чем) ·
AND · OR · NOT · PCHITAI · PISHI · RETURN · STOP(имя, причина) · JUMP · JF ·
FOR_INIT(имя) · FOR_TEST(конец) · FOR_NEXT(тест) · KONETS.

Канон не тронут (AST — источник); семантика и отказы те же байт-в-байт:
LOAD не объявленного — нет_имени; CALL чужого — нет_договора; CMP/ARITH на
чужих типах — типы_не_сошлись; примитивник — через те же обёртки П2; арность
и глубина — тем же контрактом zov_sdelki. Компиляция ленива (кэш по id тела)
и детерминированна. Выключатель — vm.РЕЖИМ["байткод"] (выкл = интерпретатор).
"""
import copy
import io
import json
import os

from deal import vm as dvm
from deal.vm import DealOtkaz, PRIMITIVY, zov_sdelki, _арифметика, _имя_типа, _polka_put

from deal.vm import _топливо as _топливо_schetchik, _ТОПЛИВО_ЛИМИТ

# [v0.1.2] топливо живёт в vm (один счётчик на расчёт); исполнитель байткода
# подращивает его по ссылке через vm-переменную
import deal.vm as _dvm_mod

_КАШ_ТЕЛ = {}
_КАШ_ВЫР = {}


def telo_kod(telo):
    """Компиляция тела (кэш по id; сильная ссылка держит id стабильным)."""
    klyuch = id(telo)
    if klyuch not in _КАШ_ТЕЛ:
        kod = []
        _komp_statji(telo, kod)
        kod.append(("KONETS", None))
        _КАШ_ТЕЛ[klyuch] = (telo, kod)
    return _КАШ_ТЕЛ[klyuch][1]


def vyrazh_kod(expr):
    klyuch = id(expr)
    if klyuch not in _КАШ_ВЫР:
        kod = []
        _komp_vyrazh(expr, kod)
        kod.append(("KONETS", None))
        _КАШ_ВЫР[klyuch] = (expr, kod)
    return _КАШ_ВЫР[klyuch][1]


# ═══════════════════ КОМПИЛЯТОР (плоский) ═══════════════════

def _komp_telo(telo):
    kod = []
    _komp_statji(telo, kod)
    return kod


def _komp_statji(telo, kod):
    for st in telo:
        op = st.get("оп")
        if op == "присваивание":
            if "имя" not in st:
                raise DealOtkaz("нет_операции", "присваивание без «имя» — правь тело")
            _komp_vyrazh(st["что"], kod)
            kod.append(("STORE", st["имя"]))
        elif op == "верни":
            _komp_vyrazh(st["что"], kod)
            kod.append(("RETURN", None))
        elif op == "стой":
            if "отказ" not in st:
                raise DealOtkaz("нет_операции", "стой без имени отказа — назови отказ")
            kod.append(("STOP", (st["отказ"], st.get("причина"))))
        elif op == "присоединить":
            if "имя" not in st:
                raise DealOtkaz("нет_операции", "присоединить без «имя» — правь тело")
            _komp_vyrazh(st["что"], kod)
            kod.append(("APPEND", st["имя"]))
        elif op == "полка-пиши":
            _komp_vyrazh(st["адрес"], kod)
            _komp_vyrazh(st["значение"], kod)
            kod.append(("PISHI", None))
        elif op == "если":
            _komp_vyrazh(st["условие"], kod)
            jf = len(kod)
            kod.append(("JF", None))
            _komp_statji(st.get("то", []), kod)
            jend = len(kod)
            kod.append(("JUMP", None))
            kod[jf] = ("JF", len(kod))
            _komp_statji(st.get("иначе", []), kod)
            kod[jend] = ("JUMP", len(kod))
        elif op == "для-каждого-до":
            if "переменная" not in st:
                raise DealOtkaz("нет_операции", "цикл без переменной — правь тело")
            _komp_vyrazh(st["до"], kod)
            kod.append(("FOR_INIT", st["переменная"]))
            ft = len(kod)
            kod.append(("FOR_TEST", None))
            _komp_statji(st.get("тело", []), kod)
            kod.append(("FOR_NEXT", ft))
            kod[ft] = ("FOR_TEST", len(kod))
        else:
            raise DealOtkaz("нет_операции", "тело: неизвестная операция «%s»" % op)


def _komp_vyrazh(expr, kod):
    """Разворот выражения в основной поток: операнды слева направо, потом
    операция. Один стек, без подпрограмм."""
    op = expr.get("оп")
    if op == "константа":
        kod.append(("PUSH", expr["значение"]))
    elif op == "поле":
        kod.append(("LOAD", expr["имя"]))
    elif op == "зов":
        imya = expr["договор"]
        argy = expr.get("аргументы", [])
        for a in argy:
            _komp_vyrazh(a, kod)
        kod.append(("CALL", (imya, len(argy))))
    elif op == "сравнение":
        _komp_vyrazh(expr["лево"], kod)
        _komp_vyrazh(expr["право"], kod)
        kod.append(("CMP", expr["чем"]))
    elif op == "арифметика":
        _komp_vyrazh(expr["лево"], kod)
        _komp_vyrazh(expr["право"], kod)
        kod.append(("ARITH", expr["чем"]))
    elif op in ("и", "или"):
        _komp_vyrazh(expr["лево"], kod)
        _komp_vyrazh(expr["право"], kod)
        kod.append(("AND" if op == "и" else "OR", None))
    elif op == "не":
        _komp_vyrazh(expr["что"], kod)
        kod.append(("NOT", None))
    elif op == "полка-читай":
        _komp_vyrazh(expr["адрес"], kod)
        kod.append(("PCHITAI", None))
    elif op == "полка-пиши":
        _komp_vyrazh(expr["адрес"], kod)
        _komp_vyrazh(expr["значение"], kod)
        kod.append(("PISHI", None))
    else:
        raise DealOtkaz("нет_операции", "выражение с неизвестной операцией «%s»" % op)


# ═══════════════════ ИСПОЛНИТЕЛЬ (один цикл) ═══════════════════

def _polka_zapis(adres, znach):
    put = _polka_put(adres)
    os.makedirs(os.path.dirname(put), exist_ok=True)
    tmp = put + ".tmp"
    with io.open(tmp, "w", encoding="utf-8") as fh:
        json.dump(znach, fh, ensure_ascii=False, sort_keys=True)
    os.replace(tmp, put)
    return znach


def ispolnit(kod, env, sdelki, stack=None):
    """Плоский цикл по ip. Выражение оставляет значение на стеке (передай
    свой stack через vyrazh_znach); тело — ("верни", значение) или None.
    Отказы — те же канонические."""
    stack = [] if stack is None else stack
    cikly = []
    ip = 0
    while True:
        if ip >= len(kod):
            return None
        op, arg = kod[ip]
        # [v0.1.2, аудит: топливо — каждый шаг инструкции считает; расчёт
        # без выхода получает канон-отказ «топливо», не вечный цикл]
        _dvm_mod._топливо += 1
        if _dvm_mod._топливо > _dvm_mod._ТОПЛИВО_ЛИМИТ:
            raise DealOtkaz("топливо",
                            "расчёт израсходовал %d шагов — проверь границы циклов"
                            % _dvm_mod._ТОПЛИВО_ЛИМИТ)
        if op == "PUSH":
            # [v0.1.2, аудит: мутируемый литерал — копия, как в интерпретаторе]
            stack.append(copy.deepcopy(arg) if isinstance(arg, (list, dict)) else arg)
        elif op == "LOAD":
            if arg not in env:
                raise DealOtkaz("нет_имени",
                                "поле «%s» не объявлено во входах/пусть" % arg)
            stack.append(env[arg])
        elif op == "STORE":
            env[arg] = stack.pop()
        elif op == "APPEND":
            spisok = env.get(arg)
            if not isinstance(spisok, list):
                spisok = []
                env[arg] = spisok
            spisok.append(stack.pop())
        elif op == "CALL":
            imya, n = arg
            argy = stack[len(stack) - n:] if n else []
            if n:
                del stack[len(stack) - n:]
            if imya in PRIMITIVY:
                stack.append(PRIMITIVY[imya](argy))
            elif imya in sdelki:
                stack.append(zov_sdelki(sdelki[imya], argy, sdelki))
            else:
                raise DealOtkaz("нет_договора", "зов «%s»: договора нет в файле" % imya)
        elif op == "CMP":
            prav = stack.pop()
            lev = stack.pop()
            try:
                if arg == "==":
                    shod = lev == prav
                elif arg == "!=":
                    shod = lev != prav
                elif arg == "<":
                    shod = lev < prav
                elif arg == ">":
                    shod = lev > prav
                elif arg == "<=":
                    shod = lev <= prav
                else:
                    shod = lev >= prav
            except TypeError:
                raise DealOtkaz("типы_не_сошлись",
                                "сравнение «%s»: %s с %s не сравнить — приведи типы"
                                % (arg, _имя_типа(lev), _имя_типа(prav)))
            stack.append(shod)
        elif op == "ARITH":
            prav = stack.pop()
            lev = stack.pop()
            try:
                stack.append(_арифметика(lev, arg, prav))
            except DealOtkaz:
                raise
            except TypeError:
                raise DealOtkaz("типы_не_сошлись",
                                "арифметика «%s»: %s с %s не считать — приведи типы"
                                % (arg, _имя_типа(lev), _имя_типа(prav)))
        elif op in ("AND", "OR"):
            prav = stack.pop()
            lev = stack.pop()
            stack.append((bool(lev) and bool(prav)) if op == "AND" else (bool(lev) or bool(prav)))
        elif op == "NOT":
            stack.append(not bool(stack.pop()))
        elif op == "PCHITAI":
            stack.append(dvm._polka_chitai_kanon(stack.pop()))
        elif op == "PISHI":
            znach = stack.pop()
            stack.append(dvm._polka_zapis_kanon(stack.pop(), znach))
        elif op == "RETURN":
            return ("верни", stack.pop())
        elif op == "STOP":
            imya, prichina = arg
            raise DealOtkaz(imya, prichina or "стой по договору сделки")
        elif op == "JUMP":
            ip = arg
            continue
        elif op == "JF":
            if not stack.pop():
                ip = arg
                continue
        elif op == "FOR_INIT":
            do = stack.pop()
            try:
                do = int(do)
            except (TypeError, ValueError):
                raise DealOtkaz("типы_не_сошлись",
                                "«до» цикла ждёт целое число — проверь границу")
            cikly.append([arg, 0, do])
            env[arg] = 0
        elif op == "FOR_TEST":
            imya, schet, do = cikly[-1]
            if schet >= do:
                cikly.pop()
                ip = arg
                continue
            env[imya] = schet
        elif op == "FOR_NEXT":
            imya, schet, do = cikly[-1]
            schet += 1
            cikly[-1][1] = schet
            env[imya] = schet
            ip = arg
            continue
        elif op == "KONETS":
            return None
        else:
            raise DealOtkaz("нет_операции", "неизвестный опкод «%s»" % op)
        ip += 1


def telo_rezultat(telo, env, sdelki):
    """Совместимый с vypolnit_telo итог: ("верни", значение) или None."""
    return ispolnit(telo_kod(telo), env, sdelki)


def vyrazh_znach(expr, env, sdelki):
    """Совместимый с vyzhit итог: значение выражения."""
    stack = []
    ispolnit(vyrazh_kod(expr), env, sdelki, stack)
    return stack.pop()
