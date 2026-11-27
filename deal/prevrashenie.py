# -*- coding: utf-8 -*-
"""DEAL: протокол превращений [v0.4.0, №9 доски СОВЕТ_DEAL, спека З1 с правками].

Канон §5 (DEAL_YAZYK): ИИ не редактирует AST руками — подаёт превращения
из закрытого набора; каждое атомарно (принято целиком или отвергнуто
словами), судится компилятором, попадает в летопись.

Запрос (JSON-файл для CLI --превратить):
  {"файл": "komponenty/cena.deal", "превращение": "заменить-тело",
   "данные": {...}}

Конвейер суда:
  1. форма — имя превращения из набора, «данные» соответствуют;
  2. прогон «до» (sobrat pisat=False — хронику не мусорим);
  3. применение к AST в памяти (чистая функция, отказ — словами);
  4. канон-запись во временный файл рядом (ввозы разрешаются в той же
     папке) и прогон «после» (pisat=False);
  5. НЕ-УХУДШЕНИЕ: все сделки после зелёные И ни одна зелёная до не
     покраснела (суд после и так исполняет все старые кейсы и края —
     этого достаточно: свидетели остаются в файле);
  6. принятие: os.replace(tmp, файл) — атомарно; летопись (одна запись,
     под сторож-замком) + сводная запись реестра (tip: prevrashenie).
  Отвергнуто: tmp стирается, файл не тронут, отказ словами.

Реализованные (8) — канон-однозначные на одном файле:
  ввести-сделку · заменить-тело · добавить-кейс-свидетель · убрать-кейс ·
  сузить-требует · расширить-даёт · добавить-отказ · заменить-зов.
Нереализованные, честно: ввести-договор (пилот-AST не различает договор
и сделку — канон-шов назван); переименовать-с-переносом-зовущих ·
расколоть-по-шву · влить-сделки · удвоить-компонент-с-вариацией (проектные,
поверх --собрать-проекта — следующая ступень); пометить-карантин ·
ввести-тип (форма маркера не в пилот-каноне); вынести-в-примитивник
(СМЕНА КАНОНА — слово владельца).

Сужение/расширение данные несут ДОБАВКУ: компилятор сам строит конъюнкцию
и(старое, добавка) — новое условие гарантированно сильнее старого
(предусловие канона «сильнее» исполнено по построению).
"""
import copy
import io
import json
import os

from deal import ast as dast
from deal import kompilyator as dkom

NABOR = {"ввести-сделку", "заменить-тело", "добавить-кейс-свидетель",
         "убрать-кейс", "сузить-требует", "расширить-даёт",
         "добавить-отказ", "заменить-зов"}


def _sdelka(ast: dict, imya, prichina):
    for s in ast.get("сделки", []):
        if s.get("имя") == imya:
            return s
    raise dkom.Otkaz(4, "превращение", "сделки «%s» нет в файле" % imya,
                     "укажи имя существующей сделки")


def _kanon(x) -> str:
    return json.dumps(x, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"))


def _zamenit_pervoe(telo, staroe_kanon: str, novoe):
    """Первое точное совпадение поддерева (обход: список по порядку,
    словарь по sorted ключам). Возврат (новое дерево, заменено 0/1)."""
    if _kanon(telo) == staroe_kanon:
        return copy.deepcopy(novoe), 1
    if isinstance(telo, list):
        for i, x in enumerate(telo):
            y, n = _zamenit_pervoe(x, staroe_kanon, novoe)
            if n:
                telo[i] = y
                return telo, 1
    elif isinstance(telo, dict):
        for k in sorted(telo):
            y, n = _zamenit_pervoe(telo[k], staroe_kanon, novoe)
            if n:
                telo[k] = y
                return telo, 1
    return telo, 0


def _primenit(ast: dict, prevrashenie: str, dannye: dict) -> dict:
    """Чистое применение превращения к AST (in-place по копии вызывающего).
    Отказ — Otkaz словами."""
    ast = copy.deepcopy(ast)
    if prevrashenie not in NABOR:   # имя судится ПЕРВЫМ — до разбора данных
        raise dkom.Otkaz(4, "превращение «%s»" % prevrashenie,
                         "превращение не в наборе v0.4.0 (набор: %s)"
                         % ", ".join(sorted(NABOR)),
                         "используй превращение из набора или жди следующую "
                         "ступень (проектные — поверх --собрать-проекта)")
    if not isinstance(dannye, dict):
        raise dkom.Otkaz(4, "превращение «%s»" % prevrashenie,
                         "«данные» не словарь", "оформи данные объектом")
    imya = dannye.get("сделка")
    if prevrashenie != "ввести-сделку" and not imya:
        raise dkom.Otkaz(4, "превращение «%s»" % prevrashenie,
                         "в данных нет «сделка»", "укажи имя сделки")

    if prevrashenie == "ввести-сделку":
        novaya = dannye.get("сделка_новая") or dannye.get("сделка")
        if not isinstance(novaya, dict):
            raise dkom.Otkaz(4, "превращение «ввести-сделку»",
                             "в данных нет новой сделки",
                             "поле «сделка_новая» — полная сделка канона")
        imya = novaya.get("имя", "?")
        zanyato = any(s.get("имя") == imya for s in ast.get("сделки", []))
        zanyato = zanyato or any(v.get("договор") == imya
                                 for v in ast.get("ввозы", []))
        if zanyato:
            raise dkom.Otkaz(4, "превращение «ввести-сделку»",
                             "имя «%s» уже занято" % imya,
                             "выбери свободное имя")
        ast.setdefault("сделки", []).append(copy.deepcopy(novaya))
        return ast

    s = _sdelka(ast, imya, prevrashenie)

    if prevrashenie == "заменить-тело":
        telo = dannye.get("тело")
        if not isinstance(telo, list):
            raise dkom.Otkaz(4, "превращение «заменить-тело» в %s" % imya,
                             "«тело» не список", "подай тело списком операций")
        s["тело"] = copy.deepcopy(telo)
        return ast

    if prevrashenie == "добавить-кейс-свидетель":
        keys = dannye.get("кейс")
        if not isinstance(keys, dict):
            raise dkom.Otkaz(4, "превращение «добавить-кейс-свидетель» в %s"
                             % imya, "в данных нет «кейс»",
                             "подай кейс {вход, выход|отказ|свойство}")
        if any(_kanon(k) == _kanon(keys) for k in s.get("свидетель", [])):
            raise dkom.Otkaz(4,
                             "превращение «добавить-кейс-свидетель» в %s" % imya,
                             "кейс — дубль существующего",
                             "сделай кейс отличным (значения или край)")
        s.setdefault("свидетель", []).append(copy.deepcopy(keys))
        return ast

    if prevrashenie == "убрать-кейс":
        nomer = dannye.get("номер")
        sv = s.get("свидетель", [])
        if not isinstance(nomer, int) or nomer < 1 or nomer > len(sv):
            raise dkom.Otkaz(4, "превращение «убрать-кейс» в %s" % imya,
                             "номер %r вне 1..%d" % (nomer, len(sv)),
                             "укажи номер кейса (1-основа)")
        ostanetsya = len(sv) - 1
        minimum = 2 if s.get("входы") else 1
        if ostanetsya < minimum:
            raise dkom.Otkaz(4, "превращение «убрать-кейс» в %s" % imya,
                             "останется %d свидетелей < %d" % (ostanetsya,
                                                               minimum),
                             "сначала добавь кейсы, потом убирай")
        del sv[nomer - 1]
        return ast

    if prevrashenie == "сузить-требует":
        dobavka = dannye.get("добавка")
        if not isinstance(dobavka, dict):
            raise dkom.Otkaz(4, "превращение «сузить-требует» в %s" % imya,
                             "в данных нет «добавка»",
                             "подай выражение-добавку; новое требует = "
                             "и(старое, добавка)")
        staroe = s.get("требует")
        s["требует"] = copy.deepcopy(dobavka) if staroe is None else \
            {"оп": "и", "лево": copy.deepcopy(staroe),
             "право": copy.deepcopy(dobavka)}
        return ast

    if prevrashenie == "расширить-даёт":
        dobavka = dannye.get("добавка")
        if not isinstance(dobavka, dict):
            raise dkom.Otkaz(4, "превращение «расширить-даёт» в %s" % imya,
                             "в данных нет «добавка»",
                             "подай выражение-добавку; новое даёт = "
                             "и(старое, добавка)")
        staroe = s.get("даёт")
        s["даёт"] = copy.deepcopy(dobavka) if staroe is None else \
            {"оп": "и", "лево": copy.deepcopy(staroe),
             "право": copy.deepcopy(dobavka)}
        return ast

    if prevrashenie == "добавить-отказ":
        ot = dannye.get("отказ")
        if not isinstance(ot, str) or not ot:
            raise dkom.Otkaz(4, "превращение «добавить-отказ» в %s" % imya,
                             "в данных нет «отказ» (имя)",
                             "подай имя отказа")
        if ot in s.get("отказы", []):
            raise dkom.Otkaz(4, "превращение «добавить-отказ» в %s" % imya,
                             "отказ «%s» уже объявлен" % ot,
                             "дублировать нельзя")
        s.setdefault("отказы", []).append(ot)
        return ast

    if prevrashenie == "заменить-зов":
        staroe = dannye.get("старый")
        novoe = dannye.get("новый")
        if not isinstance(staroe, dict) or not isinstance(novoe, dict):
            raise dkom.Otkaz(4, "превращение «заменить-зов» в %s" % imya,
                             "нужны «старый» и «новый» (выражения канона)",
                             "подай оба поддерева")
        telo, n = _zamenit_pervoe(s.get("тело", []), _kanon(staroe), novoe)
        if not n:
            raise dkom.Otkaz(4, "превращение «заменить-зов» в %s" % imya,
                             "точного совпадения со «старый» в теле нет",
                             "подай старый зов байт-в-байт по канону")
        s["тело"] = telo
        return ast

    raise dkom.Otkaz(4, "превращение «%s»" % prevrashenie,
                     "превращение не реализовано в v0.4.0", "см. набор")


def primenit_zapros(zapros: dict, kto: str = "пилот",
                    kesh: bool = True, kesh_proba: int = 16) -> dict:
    """Суд и применение одного превращения. Наружу — вердикт словами."""
    if not isinstance(zapros, dict):
        raise dkom.Otkaz(4, "превращение", "запрос не словарь",
                         "подай {файл, превращение, данные}")
    put = zapros.get("файл")
    prevrashenie = zapros.get("превращение")
    dannye = zapros.get("данные", {})
    if not put or not prevrashenie:
        raise dkom.Otkaz(4, "превращение", "в запросе нет «файл»/«превращение»",
                         "подай {файл, превращение, данные}")
    ast_do = dast.zagruzit(put)
    hesh_do = dast.hesh(ast_do)

    # прогон «до»: хронику не пишем; зелёность запоминаем ПО СДЕЛКАМ
    itog_do = dkom.sobrat(put, kto="суд-превращения", kesh=kesh,
                          kesh_proba=kesh_proba, pisat=False)
    zel_do = {s["сделка"] for s in itog_do["svody"] if s["зелёная"]}

    ast_posle = _primenit(ast_do, prevrashenie, dannye)
    tmp = put + ("" if put.endswith(".deal") else "") + ".prev.tmp"
    if tmp == put:
        tmp = put + ".prev.tmp"
    with io.open(tmp, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps(ast_posle, ensure_ascii=False, sort_keys=True,
                            separators=(",", ":")))
    try:
        try:
            itog_posle = dkom.sobrat(tmp, kto="суд-превращения", kesh=kesh,
                                     kesh_proba=kesh_proba, pisat=False)
        except dkom.Otkaz as otk:
            # sobrat сам поднимает отказ при красных — помечаем превращением,
            # чтобы слова говорили, ЧЬЙ суд отверг
            raise dkom.Otkaz(4, "превращение «%s»: суд после" % prevrashenie,
                             otk.prichina,
                             (otk.chto + " — или отмени превращение: старые "
                              "свидетели и края обязаны сходиться (не-ухудшение)"))
        sv_posle = itog_posle["svody"]
        krasnye = [s["сделка"] for s in sv_posle if not s["зелёная"]]
        if krasnye:
            ploho = next(s for s in sv_posle if not s["зелёная"])
            raise dkom.Otkaz(
                4, "превращение «%s»" % prevrashenie,
                "после: сделки красные: %s; первый несошедшийся кейс: %s"
                % (", ".join(krasnye),
                   json.dumps([k for k in ploho["кейсы"]
                               if not k["сошлось"]][0], ensure_ascii=False)),
                "правь превращение: старые свидетели и края обязаны "
                "сходиться (не-ухудшение)")
        zel_posle = {s["сделка"] for s in sv_posle if s["зелёная"]}
        potery = sorted(zel_do - zel_posle)
        if potery:
            raise dkom.Otkaz(4, "превращение «%s»" % prevrashenie,
                             "зелёные до превращения покраснели: %s"
                             % ", ".join(potery),
                             "превращение не имеет права ухудшать "
                             "(не-ухудшение)")
        os.replace(tmp, put)   # атомарно: либо целиком новое, либо старое
    except BaseException:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise

    hesh_posle = dast.hesh(ast_posle)
    dkom._dopisat_letopis({"kogda": _vremya(), "kto": kto,
                           "tip": "prevrashenie", "файл": put,
                           "превращение": prevrashenie,
                           "hesh_do": hesh_do, "hesh_posle": hesh_posle,
                           "вердикт": "принято"})
    dkom._dobavit_stroku(dkom.REESTR, json.dumps(
        {"kogda": _vremya(), "kto": kto, "tip": "prevrashenie",
         "файл": os.path.basename(put), "превращение": prevrashenie,
         "hesh_do": hesh_do, "hesh_posle": hesh_posle,
         "вердикт": "принято"}, ensure_ascii=False, sort_keys=True))
    return {"файл": put, "превращение": prevrashenie,
            "вердикт": "принято", "hesh_do": hesh_do,
            "hesh_posle": hesh_posle}


def _vremya() -> float:
    import time
    return time.time()
