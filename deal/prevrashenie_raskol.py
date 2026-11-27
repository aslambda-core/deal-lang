# -*- coding: utf-8 -*-
"""DEAL: расколоть-по-шву — проектное превращение [v0.4.2, №9 ступень 3].

Сделка A режется по шву (после N-го стейта) на ГОЛОВУ (новая сделка: блок
до шва + верни словарь ЖИВЫХ переменных) и ХВОСТ (та же A: зов головы +
распаковка + блок после шва). Живые = присвоенные в блоке до шва ∩ читаемые
после шва (тело, «даёт», свойства кейсов) — мёртвое через шов не едет.

Свидетели ПЕРЕГОНЯЮТСЯ механически: блок до шва исполняется ВМ на каждом
кейсе A (фиксатуры применяются) — завершился → кейс головы ожидает словарь
живых значений; отказался → кейс головы ожидает тот же отказ (стой в блоке
до шва — легален, отказ честно едет через зов). Кейс-свойство не перегоняется
(свойство о результате головы не эквивалентно) — остаётся только у хвоста.

Суд — на СТЕНДЕ (как все проектные): хвост обязан остаться зелёным под тем
же именем и с теми же кейсами («две сделки в сумме эквивалентны» на
доказательной базе свидетелей A), голова обязана быть зелёной на
перегнанных кейсах.
"""
import copy
import json
import os

from deal import ast as dast
from deal import vm as dvm
from deal import kompilyator as dkom


def _chitaet(x, mnozh):
    """Имена переменных, читаемые в дереве (узлы «поле»; строки-имена отказов
    и договоров зова — не узлы, мимо)."""
    if isinstance(x, dict):
        if x.get("оп") == "поле":
            mnozh.add(x["имя"])
        for k in sorted(x):
            _chitaet(x[k], mnozh)
    elif isinstance(x, list):
        for y in x:
            _chitaet(y, mnozh)


def _pripisano(telo, mnozh):
    """Имена, присваиваемые в теле (присваивание, присоединить, переменная
    цикла) — рекурсивно по ветвям если и телам циклов."""
    for st in telo:
        op = st.get("оп")
        if op in ("присваивание", "присоединить"):
            mnozh.add(st["имя"])
        elif op == "для-каждого-до":
            mnozh.add(st["переменная"])
            _pripisano(st.get("тело", []), mnozh)
        elif op == "если":
            _pripisano(st.get("то", []), mnozh)
            _pripisano(st.get("иначе", []), mnozh)


def _est_verni(telo):
    for st in telo:
        op = st.get("оп")
        if op == "верни":
            return True
        if op == "если" and (_est_verni(st.get("то", []))
                             or _est_verni(st.get("иначе", []))):
            return True
        if op == "для-каждого-до" and _est_verni(st.get("тело", [])):
            return True
    return False


def _otkaz(prichina: str, chto: str):
    return dkom.Otkaz(4, "расколоть-по-шву", prichina, chto)


def _peregonka_kasa(kz, blok1, okruzhenie, zhivye, nomer):
    """Перегонка одного кейса: прогон блока до шва → кейс головы.
    Фиксатура применяется до прогона и едет в кейс головы (голове нужна та
    же полка). Отказ блока — канонический кейс «отказ» головы (имя легально:
    голова наследует отказы A, канон-отказы названы всегда)."""
    kaset = {"вход": copy.deepcopy(kz.get("вход", {}))}
    if kz.get("фиксатура"):
        kaset["фиксатура"] = copy.deepcopy(kz["фиксатура"])
        for adres, znach in kz["фиксатура"].items():
            dvm._polka_zapis_kanon(adres, copy.deepcopy(znach))
    env = copy.deepcopy(kaset["вход"])
    dvm._toplivo_sbrodit()
    try:
        dvm.vypolnit_telo(copy.deepcopy(blok1), env, okruzhenie)
    except dvm.DealOtkaz as otk:
        kaset["отказ"] = otk.imya
        return kaset
    ozhid = {}
    for im in zhivye:
        if im not in env:
            raise _otkaz("переменная «%s» не определена на кейсе %d после "
                         "блока до шва" % (im, nomer),
                         "живая переменная живёт не на всех путях — сдвинь шов")
        ozhid[im] = env[im]
    kaset["выход"] = ozhid
    return kaset


def _p_raskol(papka: str, fayly: list, asty: dict, dannye: dict):
    """Применение в памяти. Возврат (тронутые файлы, относительный путь
    нового файла, AST нового файла) — стенд, суд и запись делает
    primenit_proektnoe (prevrashenie_proekt.py)."""
    imya_a = dannye.get("сделка")
    imya_golovy = dannye.get("имя_головы")
    shov = dannye.get("шов")
    if not imya_a or not imya_golovy or not isinstance(shov, int):
        raise _otkaz("нужны «сделка», «шов» (номер стейта, после которого "
                     "режем) и «имя_головы»", "дополни данные")
    put_a = None
    s_a = None
    for put in fayly:
        dlya = [s for s in asty[put].get("сделки", [])
                if s.get("имя") == imya_a]
        if dlya:
            if put_a is not None:
                raise _otkaz("сделка «%s» определена в нескольких файлах"
                             % imya_a, "расколот исполняет однозначное имя")
            put_a = put
            s_a = dlya[0]
    if put_a is None:
        raise _otkaz("сделки «%s» нет ни в одном файле проекта" % imya_a,
                     "укажи имя определённой в проекте сделки")
    telo = s_a.get("тело", [])
    if shov < 1 or shov > len(telo) - 1:
        raise _otkaz("шов %s за краем: тело из %d стейтов, обе половины "
                     "обязаны быть непусты" % (shov, len(telo)),
                     "шов — число от 1 до длина-1")
    blok1, blok2 = telo[:shov], telo[shov:]
    if _est_verni(blok1):
        raise _otkaz("шов режет «верни»: возврат в блоке до шва уйдёт из "
                     "головы мимо словаря", "сдвинь шов ниже возврата")

    # имя головы: свободно везде (сделки, ввозы), не примитивник [мина: зов
    # в ВМ резолвится примитивником ПЕРВЫМ — голова «сумма» звала бы sum]
    if imya_golovy == imya_a:
        raise _otkaz("имя головы совпадает с именем расщепляемой сделки",
                     "выбери другое имя головы")
    if imya_golovy in dvm.PRIMITIVY:
        raise _otkaz("имя головы «%s» — имя примитивника" % imya_golovy,
                     "зов головы резолвился бы примитивником — выбери другое")
    for put in fayly:
        imena = {s.get("имя") for s in asty[put].get("сделки", [])}
        if imya_golovy in imena:
            raise _otkaz("имя головы «%s» занято сделкой в %s"
                         % (imya_golovy, os.path.basename(put)),
                         "выбери свободное имя")
        for v in asty[put].get("ввозы", []):
            if v.get("договор") == imya_golovy:
                raise _otkaz("имя головы «%s» занято ввозом в %s"
                             % (imya_golovy, os.path.basename(put)),
                             "выбери свободное имя")
    put_golovy = os.path.normpath(os.path.join(
        os.path.dirname(put_a), imya_golovy + ".deal"))
    if os.path.exists(put_golovy) or put_golovy in asty:
        raise _otkaz("файл %s уже есть рядом со сделкой"
                     % os.path.basename(put_golovy),
                     "выбери другое имя головы")

    # живые переменные: присвоено до шва ∩ читается после (тело, «даёт»,
    # свойства кейсов — их env переживает тело)
    prip1 = set()
    _pripisano(blok1, prip1)
    chit2 = set()
    _chitaet(blok2, chit2)
    if s_a.get("даёт"):
        _chitaet(s_a["даёт"], chit2)
    for kz in s_a.get("свидетель", []):
        if kz.get("свойство"):
            _chitaet(kz["свойство"], chit2)
    zhivye = prip1 & chit2
    if not zhivye:
        raise _otkaz("через шов не идут живые переменные — голова вернула бы "
                     "пустой словарь", "шов не несёт ничего, не раскалывай")

    # перегонка свидетелей: прогон блока до шва на каждом кейсе
    okruzhenie = dkom.sdelki_dlya(asty[put_a], put_a)
    peregnannye = []
    svoistva = 0
    for n, kz in enumerate(s_a.get("свидетель", []), 1):
        if "свойство" in kz and "отказ" not in kz:
            svoistva += 1   # свойство о результате головы не эквивалентно
            continue
        peregnannye.append(_peregonka_kasa(kz, blok1, okruzhenie, zhivye, n))
    minimum = 2 if s_a.get("входы") else 1
    if len(peregnannye) < minimum:
        raise _otkaz("свидетелей головы после перегонки %d < %d "
                     "(кейс-свойства не перегоняются: %d)"
                     % (len(peregnannye), minimum, svoistva),
                     "сдвинь шов или добавь кейсы с ожиданием значения")

    # уникальное имя переменной шва — свежее против всего именного в A
    imena_a = set()
    for v in s_a.get("входы", []):
        imena_a.add(v["имя"])
    _pripisano(telo, imena_a)
    _chitaet(telo, imena_a)
    shv = imya_golovy + "_итог"
    while shv in imena_a:
        shv = shv + "_"

    # голова: та же сделка-обвязка (входы, требует, отказы), выход — словарь
    golova = {"имя": imya_golovy,
              "входы": copy.deepcopy(s_a.get("входы", [])),
              "выход": "словарь",
              "тело": copy.deepcopy(blok1)}
    if s_a.get("отказы"):
        golova["отказы"] = list(s_a["отказы"])
    if s_a.get("требует") is not None:
        golova["требует"] = copy.deepcopy(s_a["требует"])
    golova["тело"].append({"оп": "присваивание", "имя": shv,
                           "что": {"оп": "зов", "договор": "словарь",
                                   "аргументы": []}})
    for im in sorted(zhivye):
        golova["тело"].append({"оп": "присваивание", "имя": shv,
                               "что": {"оп": "зов", "договор": "поле-записать",
                                       "аргументы": [
                                           {"оп": "поле", "имя": shv},
                                           {"оп": "константа", "значение": im},
                                           {"оп": "поле", "имя": im}]}})
    golova["тело"].append({"оп": "верни", "что": {"оп": "поле", "имя": shv}})
    golova["свидетель"] = peregnannye

    # хвост: зов головы со ВСЕМИ входами A + распаковка живых + блок после
    argy = [{"оп": "поле", "имя": v["имя"]}
            for v in s_a.get("входы", [])]
    s_a["тело"] = [{"оп": "присваивание", "имя": shv,
                    "что": {"оп": "зов", "договор": imya_golovy,
                            "аргументы": argy}}]
    for im in sorted(zhivye):
        s_a["тело"].append({"оп": "присваивание", "имя": im,
                            "что": {"оп": "зов", "договор": "поле-из-или",
                                    "аргументы": [
                                        {"оп": "поле", "имя": shv},
                                        {"оп": "константа", "значение": im},
                                        {"оп": "константа", "значение": None}]}})
    s_a["тело"].extend(blok2)
    asty[put_a].setdefault("ввозы", []).append(
        {"договор": imya_golovy, "из": imya_golovy, "хеш": ""})

    novy_rel = os.path.relpath(put_golovy, papka)
    novy_ast = {"сделки": [golova]}
    return [put_a], novy_rel, novy_ast
