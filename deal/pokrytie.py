# -*- coding: utf-8 -*-
"""DEAL: покрытие ветвей/циклов канон-честно [v0.5.0, №11 доски — З3].

СОВЕТ, не отказ: компилятор не краснеет от непокрытого канала — отчёт
называет каналы словами, строгость — флаг --покрытие-отказ [--покрытие-
порог N] (решение советом раунда 8; владелец выбирает режим при запуске).

Канон-честные каналы (ничего выдуманного):
  - «если» несёт пару каналов «то»/«иначе» — покрыт, если хоть один
    свидетель-кейс взял эту ветвь;
  - «для-каждого-до» несёт пару «0 витков»/«≥1 виток» — покрыт, если есть
    кейс с пустым циклом и кейс с непустым.
Вложенные узлы канализируются по своим путям (тело[i].то[j]…).

Кейсы исполняет ТРАССИРОВЩИК — зеркало vm._telo_syr: те же операции, тот
же порядок, то же топливо; отличается только записью попаданий. Выражения
исполняет сам vm.vyzhit (та же семантика, дифференциал 300/300). Отказ
кейса — тоже след: ветви, взятые до отказа, считаются. Фиксатуры полки
применяются перед кейсом, как у свидетелей.

Границы честно: недетерминированные ветви («время») — снимок одного
прогона; полноту по ВСЕМ путям статически не доказываем — мерим ровно
канон-узлы на кейсах сделки.
"""
import copy
import os

from deal import ast as dast
from deal import vm as dvm


def _kanaly_tela(telo, put, kanaly):
    """Статический сбор каналов: (путь-узла, канал) по всему дереву тела."""
    for i, st in enumerate(telo):
        kluch = "%s[%d]" % (put, i)
        op = st.get("оп")
        if op == "если":
            kanaly.add((kluch, "то"))
            kanaly.add((kluch, "иначе"))
            _kanaly_tela(st.get("то", []), kluch + ".то", kanaly)
            _kanaly_tela(st.get("иначе", []), kluch + ".иначе", kanaly)
        elif op == "для-каждого-до":
            kanaly.add((kluch, "ноль"))
            kanaly.add((kluch, "витки"))
            _kanaly_tela(st.get("тело", []), kluch + ".тело", kanaly)
    return kanaly


_SRYV = (TypeError, ValueError, KeyError, AttributeError, IndexError,
         OverflowError)


def _hod_telo(telo, env, sdelki, put, popad):
    """Трассировщик тела: зеркало vm._telo_syr (те же семантики; отличает
    только popad). Возвращает ("верни", значение) или None — как ВМ."""
    for i, st in enumerate(telo):
        dvm._shag()
        kluch = "%s[%d]" % (put, i)
        op = st.get("оп")
        if op == "присваивание":
            if "имя" not in st:
                raise dvm.DealOtkaz("нет_операции", "присваивание без «имя»")
            env[st["имя"]] = dvm.vyzhit(st["что"], env, sdelki)
        elif op == "верни":
            return ("верни", dvm.vyzhit(st["что"], env, sdelki))
        elif op == "стой":
            if "отказ" not in st:
                raise dvm.DealOtkaz("нет_операции", "стой без имени отказа")
            raise dvm.DealOtkaz(st["отказ"],
                                st.get("причина") or "стой по договору сделки")
        elif op == "присоединить":
            if "имя" not in st:
                raise dvm.DealOtkaz("нет_операции", "присоединить без «имя»")
            spisok = env.get(st["имя"])
            if not isinstance(spisok, list):
                spisok = []
                env[st["имя"]] = spisok
            spisok.append(dvm.vyzhit(st["что"], env, sdelki))
        elif op == "полка-пиши":
            dvm._polka_zapis_kanon(dvm.vyzhit(st["адрес"], env, sdelki),
                                   dvm.vyzhit(st["значение"], env, sdelki))
        elif op == "если":
            pravda = bool(dvm.vyzhit(st.get("условие", {"оп": "константа",
                                                        "значение": True}),
                                     env, sdelki))
            popad((kluch, "то" if pravda else "иначе"))
            itog = _hod_telo(st.get("то" if pravda else "иначе", []),
                             env, sdelki,
                             kluch + (".то" if pravda else ".иначе"), popad)
            if itog:
                return itog
        elif op == "для-каждого-до":
            if "переменная" not in st:
                raise dvm.DealOtkaz("нет_операции", "цикл без переменной")
            try:
                do = int(dvm.vyzhit(st["до"], env, sdelki))
            except dvm.DealOtkaz:
                raise
            except (TypeError, ValueError):
                raise dvm.DealOtkaz("типы_не_сошлись",
                                    "«до» цикла ждёт целое число")
            vitki = 0
            for j in range(do):
                vitki += 1
                env[st["переменная"]] = j
                itog = _hod_telo(st.get("тело", []), env, sdelki,
                                 kluch + ".тело", popad)
                if itog:
                    return itog
            popad((kluch, "ноль" if vitki == 0 else "витки"))
        else:
            raise dvm.DealOtkaz("нет_операции",
                                "тело: неизвестная операция «%s»" % op)
    return None


def _pokryt_kasey(kz, telo, sdelki):
    """Прогон одного кейса трассировщиком. Отказ/сырое исключение — не беда
    совета: след до места падения честно посчитан; судить кейс — работа
    компилятора, не покрытия."""
    if kz.get("фиксатура"):
        for adres, znach in kz["фиксатура"].items():
            dvm._polka_zapis_kanon(adres, znach)
    popavshie = set()
    env = copy.deepcopy(kz.get("вход", {}))
    dvm._toplivo_sbrodit()
    try:
        _hod_telo(telo, env, sdelki, "тело", popavshie.add)
    except dvm.DealOtkaz:
        pass
    except RecursionError:
        pass
    except _SRYV:
        pass
    return popavshie


def _slovami(kanal):
    kluch, imya = kanal
    slovo = {"то": "ветвь «то»", "иначе": "ветвь «иначе»",
             "ноль": "случай «0 витков»", "витки": "случай «≥1 виток»"}[imya]
    return "если %s — %s" % (kluch, slovo) if imya in ("то", "иначе") \
        else "для %s — %s" % (kluch, slovo)


def pokrytie_sdelki(sdelka, sdelki) -> dict:
    kanaly = _kanaly_tela(sdelka.get("тело", []), "тело", set())
    popalo = set()
    telo = sdelka.get("тело", [])
    for kz in sdelka.get("свидетель", []):
        popalo |= _pokryt_kasey(kz, telo, sdelki)
    return {"сделка": sdelka["имя"],
            "каналов": len(kanaly),
            "покрыто": len(kanaly & popalo),
            "непокрытые": [_slovami(k) for k in sorted(kanaly - popalo)]}


def pokrytie_fajla(put_fajla: str) -> dict:
    """Свод по файлу: каналы, покрытие, непокрытые — словами. Ввозы по хешу
    резолвятся (зовы в ветвях должны исполняться живьём)."""
    try:
        ast = dast.zagruzit(put_fajla)
    except OSError as beda:
        otk = dvm.DealOtkaz("полка_не_доступна",
                            "полка_не_доступна — файла нет: %s" % beda)
        otk.stad = 1
        otk.vinovnik = "покрытие"
        otk.chto = "укажи существующий .deal файл"
        raise otk
    try:
        sdelki = dast.sdelki_s_vvozyami(
            ast, os.path.dirname(os.path.abspath(put_fajla)))
    except dvm.DealOtkaz as otk:
        otk.stad = 1
        otk.vinovnik = "ввозы файла"
        otk.prichina = "%s — %s" % (otk.imya, otk.prichina)
        otk.chto = "правь раздел «ввозы» или обнови хеш ввозимого"
        raise
    svody = [pokrytie_sdelki(s, sdelki) for s in ast.get("сделки", [])]
    vsego = sum(s["каналов"] for s in svody)
    pokryto = sum(s["покрыто"] for s in svody)
    return {"файл": os.path.basename(put_fajla), "сделки": svody,
            "каналов": vsego, "покрыто": pokryto,
            "процент": (100 * pokryto // vsego) if vsego else 100}


def iz_consolei(argv) -> int:
    """CLI: --покрытие <файл.deal> [--покрытие-отказ] [--покрытие-порог N].
    СОВЕТ: код 0 всегда, кроме строгого режима ниже порога (код 1)."""
    import json
    i = argv.index("--покрытие")
    if i + 1 >= len(argv):
        print(json.dumps({"стадия": 1, "виновник": "покрытие",
                          "причина": "не указан файл",
                          "что_править": "зов: kompilyator.py --покрытие "
                          "<файл.deal> [--покрытие-отказ] "
                          "[--покрытие-порог N]"}, ensure_ascii=False))
        return 2
    put = argv[i + 1]
    otkaz = "--покрытие-отказ" in argv
    porog = 100
    j = 0
    while j < len(argv):
        a = argv[j]
        if a == "--покрытие-порог" and j + 1 < len(argv):
            porog = int(argv[j + 1])
            del argv[j:j + 2]
        elif a.startswith("--покрытие-порог="):
            porog = int(a.split("=", 1)[1])
            del argv[j]
        else:
            j += 1
    try:
        svod = pokrytie_fajla(put)
    except Exception as otk:
        if hasattr(otk, "imya") and not hasattr(otk, "vinovnik"):
            print(json.dumps({"стадия": 1, "виновник": "покрытие",
                              "причина": "%s — %s" % (otk.imya, otk.prichina),
                              "что_править": getattr(otk, "chto",
                                                     "правь файл")},
                             ensure_ascii=False))
            return 1
        if not hasattr(otk, "stad"):
            raise
        print(json.dumps({"стадия": otk.stad, "виновник": otk.vinovnik,
                          "причина": otk.prichina, "что_править": otk.chto},
                         ensure_ascii=False))
        return 1
    if otkaz and svod["процент"] < porog:
        print(json.dumps({"стадия": 4, "виновник": "покрытие",
                          "причина": "покрытие %d%% ниже порога %d%% — "
                                     "каналы не покрыты кейсами"
                                     % (svod["процент"], porog),
                          "что_править": "добавь кейсы на названные каналы",
                          "свод": svod}, ensure_ascii=False))
        return 1
    print(json.dumps(svod, ensure_ascii=False))
    return 0
