# -*- coding: utf-8 -*-
"""SELFHOST S2a: ФОРМАТ ПРОГРАММЫ СЕМЕНИ + ЭТАЛОННЫЙ ИСПОЛНИТЕЛЬ ФОРМАТА.

Скомпилированный байткод (telo_kod) сериализуется в ТЕКСТОВУЮ программу —
формат, который будет читать C-семя (S2b):

    .полка <корень>
    .сделка <имя> <вход1,вход2>       (входы — арность, контракт зова)
    <OP> <json-арг>                   (OP без аргумента — строка одна)
    .конец

Эталонный исполнитель (ispolnit_programmu) — самостоятельный плоский цикл по
программе (НЕ bajtkod.ispolnit): он повторяет тот путь, который ляжет в C
(кадр зова = свой стек + локальный env; арность и глубина — те же контракты).
Примитивники — таблица vm (спека семени), полка — канон-хелперы vm.
"""
import json
import time

from deal import vm as dvm
from deal.vm import DealOtkaz, PRIMITIVY, _арифметика, _имя_типа


# ═══════════════════ СЕРИАЛИЗАТОР ═══════════════════

def _stroka_instrukcii(op, arg):
    if arg is None:
        return op
    return op + " " + json.dumps(arg, ensure_ascii=False)


def sostavit_programmu(sdelki_programmy, polka):
    """sdelki_programmy: {имя: (имена-входов-список, kod)}; наружу — текст."""
    stroki = [".полка " + polka]
    for imya in sorted(sdelki_programmy):
        vkhody, kod = sdelki_programmy[imya]
        stroki.append(".сделка %s %s" % (imya, ",".join(vkhody)))
        for op, arg in kod:
            stroki.append(_stroka_instrukcii(op, arg))
        stroki.append(".конец")
    return "\n".join(stroki)


def razobrat_programmu(tekst):
    """Текст -> (polka, {имя: (входы-имена, kod)})."""
    polka, programma, tekushaya = "", {}, None
    for stroka in tekst.split("\n"):
        if not stroka:
            continue
        if stroka.startswith("."):
            if stroka.startswith(".полка "):
                polka = stroka[len(".полка "):]
            elif stroka.startswith(".сделка "):
                chasti = stroka[len(".сделка "):].split(" ", 1)
                tekushaya = chasti[0]
                vkhody = chasti[1].split(",") if len(chasti) > 1 and chasti[1] else []
                programma[tekushaya] = [vkhody, []]
            continue
        if tekushaya is None:
            raise DealOtkaz("нет_операции", "инструкция вне .сделка: " + stroka[:60])
        chasti = stroka.split(" ", 1)
        op = chasti[0]
        arg = json.loads(chasti[1]) if len(chasti) > 1 else None
        programma[tekushaya][1].append((op, arg))
    return polka, programma


# ═══════════════════ ЭТАЛОННЫЙ ИСПОЛНИТЕЛЬ ФОРМАТА ═══════════════════

def ispolnit_programmu(tekst, entry, vkhody):
    """Исполнить задачу программы. vkhody — словарь входов; значения ложатся
    в кадр в ПОРЯДКЕ входов сделки. Наружу — значение (или None)."""
    _polka, programma = razobrat_programmu(tekst)
    if entry not in programma:
        raise DealOtkaz("нет_договора", "задачи «%s» в программе нет" % entry)
    vkh_imena = programma[entry][0]
    argy = []
    for imya in vkh_imena:
        if imya not in vkhody:
            raise DealOtkaz("нет_имени",
                            "поле «%s» не объявлено во входах/пусть" % imya)
        argy.append(vkhody[imya])
    itog = _vj(programma, entry, argy, [], [], {"stek": 0})
    return itog[1] if itog else None


def _vj(programma, imya, argy, stack, cikly, pamyat):
    """Кадр зова: свой стек и свой локальный env (имена входов из программы);
    арность — контракт; глубина — контракт 300."""
    vkhody_imena, kod = programma[imya]
    if len(argy) != len(vkhody_imena):
        raise DealOtkaz("нарушен_договор",
                        "зов «%s»: у сделки %d вход(ов), а подали %d — согласуй аргументы"
                        % (imya, len(vkhody_imena), len(argy)))
    pamyat["stek"] += 1
    try:
        if pamyat["stek"] > 300:
            raise DealOtkaz("глубина",
                            "рекурсия глубже 300: сделка «%s» зовёт себя без остановки"
                            % imya)
        env = dict(zip(vkhody_imena, argy))
        stack = []
        cikly = []
        ip = 0
        while True:
            if ip >= len(kod):
                return None
            op, arg = kod[ip]
            if op == "PUSH":
                stack.append(arg)
            elif op == "LOAD":
                if arg not in env:
                    raise DealOtkaz("нет_имени",
                                    "поле «%s» не объявлено во входах/пусть" % arg)
                stack.append(env[arg])
            elif op == "STORE":
                env[arg] = stack.pop()
            elif op == "APPEND":
                sp = env.get(arg)
                if not isinstance(sp, list):
                    sp = []
                    env[arg] = sp
                sp.append(stack.pop())
            elif op == "CALL":
                imya_z, n = arg
                argy_z = stack[len(stack) - n:] if n else []
                if n:
                    del stack[len(stack) - n:]
                if imya_z in PRIMITIVY:
                    stack.append(PRIMITIVY[imya_z](argy_z))
                elif imya_z in programma:
                    itog_z = _vj(programma, imya_z, argy_z, [], [], pamyat)
                    stack.append(itog_z[1] if itog_z else None)
                else:
                    raise DealOtkaz("нет_договора",
                                    "зов «%s»: договора нет в программе" % imya_z)
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
                stack.append((bool(lev) and bool(prav)) if op == "AND"
                              else (bool(lev) or bool(prav)))
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
                imya_o, prichina = arg
                raise DealOtkaz(imya_o, prichina or "стой по договору сделки")
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
                imya_c, schet, do = cikly[-1]
                if schet >= do:
                    cikly.pop()
                    ip = arg
                    continue
                env[imya_c] = schet
            elif op == "FOR_NEXT":
                imya_c, schet, do = cikly[-1]
                schet += 1
                cikly[-1][1] = schet
                env[imya_c] = schet
                ip = arg
                continue
            elif op == "KONETS":
                return None
            else:
                raise DealOtkaz("нет_операции", "неизвестный опкод «%s»" % op)
            ip += 1
    finally:
        pamyat["stek"] -= 1
