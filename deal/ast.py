# -*- coding: utf-8 -*-
"""DEAL: канон-AST — загрузка, детерминированная сериализация, хеш, проекция.

Канон: JSON с сортировкой ключей и фиксированными разделителями —
два серийных хеша одного смысла обязаны совпадать байт-в-байт.
Проекция — детерминированная печать AST (единственный читаемый вид,
печатающийся из канона всегда: «декомпиляция» = печать, не реконструкция).
"""
import hashlib
import io
import json
import os

from deal import vm as _dvm  # vm не зовёт ast — цикла нет; нужен DealOtkaz


def zagruzit(put: str) -> dict:
    with io.open(put, encoding="utf-8") as fh:
        return json.load(fh)


def sdelki_s_vvozyami(ast: dict, papka: str, put_steka=None, kesh_heshey=None) -> dict:
    """Словарь сделок файла + ВВОЗЫ ПО ХЕШУ (ступень 2).

    Раздел файла: «ввозы»: [{договор, из, хеш}] — «из» — имя файла рядом
    (без расширения; пробуются .deal и .deal.json). Хеш канона ввозимого
    файла обязан совпасть заявленному БАЙТ-В-БАЙТ: договор приезжает ровно
    тот, что назван, не «похожий». Ввозимый файл может сам иметь ввозы.
    [v0.1.3, аудит: цикл судится ПО ПУТИ (стек), а не глобально — ромб
    A→{B,C}, B→D, C→D легален; повторный ввоз того же ХЕША дедуплицируется
    (кэш по хешу), расхождение хеша — нарушен_договор.] Отказы словами:
      полка_не_доступна — файла нет рядом;
      нарушен_договор   — хеш не совпал / имя занято местной сделкой / цикл по пути;
      нет_договора      — имени нет в ввозимом файле.
    """
    put_steka = [] if put_steka is None else put_steka
    kesh_heshey = {} if kesh_heshey is None else kesh_heshey
    sdelki = {s["имя"]: s for s in ast.get("сделки", [])}
    for vvoz in ast.get("ввозы", []):
        imya = vvoz.get("договор", "?")
        iz = vvoz.get("из", "?")
        put = None
        for rassh in (".deal", ".deal.json"):
            kandidat = os.path.join(papka, iz + rassh)
            if os.path.exists(kandidat):
                put = kandidat
                break
        if not put:
            raise _dvm.DealOtkaz("полка_не_доступна",
                                 "ввоз «%s»: файла «%s» нет рядом с %s" % (imya, iz, papka))
        if put in put_steka:
            raise _dvm.DealOtkaz("нарушен_договор",
                                 "ввоз «%s» из «%s»: цикл по пути ввозов" % (imya, iz))
        chuzhoj = None
        hesh_fakt = None
        # [v0.1.3] дедуп по содержанию: тот же файл в другой ветке — тот же договор
        kesh = kesh_heshey.get(put)
        if kesh is not None:
            hesh_fakt, chuzhoj = kesh
        else:
            chuzhoj = zagruzit(put)
            hesh_fakt = hesh(chuzhoj)
            kesh_heshey[put] = (hesh_fakt, chuzhoj)
        if hesh_fakt != vvoz.get("хеш"):
            raise _dvm.DealOtkaz("нарушен_договор",
                                 "ввоз «%s» из «%s»: хеш файла не совпал заявленному "
                                 "(%s… ≠ %s…) — договор изменился" % (imya, iz, hesh_fakt[:12],
                                                                      str(vvoz.get("хеш"))[:12]))
        if imya in sdelki and sdelki[imya] is not chuzhie[imya]:
            raise _dvm.DealOtkaz("нарушен_договор",
                                 "ввоз «%s»: имя занято местной сделкой" % imya)
        chuzhie = sdelki_s_vvozyami(chuzhoj, os.path.dirname(put),
                                    put_steka + [put], kesh_heshey)
        if imya not in chuzhie:
            raise _dvm.DealOtkaz("нет_договора",
                                 "ввоз «%s» из «%s»: сделки с таким именем нет (есть: %s)"
                                 % (imya, iz, ", ".join(sorted(chuzhie))))
        # [v0.1.3, аудит-ромб: ввоз привозит ВСЁ окружение ввозимого файла —
        # «удвои» из D нужен телу «четыре» из B; раньше в словарь попадала
        # только названная сделка, и её зовы падали нет_договора. Коллизия
        # имён между ветками — нарушен_договор, тот же объект — не трогаем.]
        for imya2, sdelka2 in chuzhie.items():
            if imya2 in sdelki:
                if sdelki[imya2] is sdelka2:
                    continue
                raise _dvm.DealOtkaz("нарушен_договор",
                                     "ввоз «%s» из «%s»: имя «%s» занято другим ввозом — "
                                     "переименуй" % (imya, iz, imya2))
            sdelki[imya2] = sdelka2
        sdelki[imya] = chuzhie[imya]
    return sdelki


def zagruzit(put: str) -> dict:
    # [v0.1.2, аудит: NaN/Infinity — невалидный JSON для строгих парсеров;
    # канон запрещает их на входе, не на выходе serialization]
    def _zapret(slovo):
        raise _dvm.DealOtkaz("типы_не_сошлись",
                             "константа «%s» запрещена каноном (невалидный JSON) — "
                             "замени числом" % slovo)
    with io.open(put, encoding="utf-8") as fh:
        return json.load(fh, parse_constant=_zapret)


def kanon(obj) -> str:
    """Единственный серийный вид AST: сортировка ключей, без пробелов, utf-8.
    [v0.1.2] allow_nan=False — NaN не сериализуется молча.]"""
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
                      allow_nan=False)
    """Единственный серийный вид AST: сортировка ключей, без пробелов, utf-8."""
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def hesh(obj) -> str:
    return hashlib.sha256(kanon(obj).encode("utf-8")).hexdigest()


def _tip(vyrazhenie) -> str:
    # проекция типа: из входа сделки
    return str(vyrazhenie)


def pecatat_vyrazhenie(expr) -> str:
    op = expr.get("оп")
    if op == "константа":
        zn = expr["значение"]
        return '"%s"' % zn if isinstance(zn, str) else str(zn)
    if op == "поле":
        return expr["имя"]
    if op == "сравнение":
        return "%s %s %s" % (pecatat_vyrazhenie(expr["лево"]), expr["чем"],
                             pecatat_vyrazhenie(expr["право"]))
    if op == "арифметика":
        return "%s %s %s" % (pecatat_vyrazhenie(expr["лево"]), expr["чем"],
                             pecatat_vyrazhenie(expr["право"]))
    if op == "зов":
        return "%s(%s)" % (expr["договор"],
                           ", ".join(pecatat_vyrazhenie(a) for a in expr["аргументы"]))
    if op == "полка-читай":
        return "полка.читай(%s)" % pecatat_vyrazhenie(expr["адрес"])
    if op == "полка-пиши":
        return "полка.пиши(%s, %s)" % (pecatat_vyrazhenie(expr["адрес"]),
                                       pecatat_vyrazhenie(expr["значение"]))
    return "<?%s?>" % op


def pecatat_telo(telo, otstup: str) -> list:
    stroki = []
    for st in telo:
        op = st.get("оп")
        if op == "присваивание":
            stroki.append("%s%s = %s" % (otstup, st["имя"],
                                         pecatat_vyrazhenie(st["что"])))
        elif op == "верни":
            stroki.append("%sверни %s" % (otstup, pecatat_vyrazhenie(st["что"])))
        elif op == "стой":
            stroki.append("%sстой отказ %s" % (otstup, st["отказ"]))
        elif op == "если":
            stroki.append("%sесли %s:" % (otstup, pecatat_vyrazhenie(st["условие"])))
            stroki.extend(pecatat_telo(st["то"], otstup + "  "))
            if st.get("иначе"):
                stroki.append("%sиначе:" % otstup)
                stroki.extend(pecatat_telo(st["иначе"], otstup + "  "))
        elif op == "для-каждого-до":
            stroki.append("%sдля-каждого-до(%s, до %s):" % (
                otstup, st["переменная"], pecatat_vyrazhenie(st["до"])))
            stroki.extend(pecatat_telo(st["тело"], otstup + "  "))
    return stroki


def projekciya(ast: dict) -> str:
    """Детерминированная печать канона в читаемый вид (русские ключевые слова)."""
    stroki = []
    for dog in ast.get("договоры", []):
        vhody = ", ".join("%s: %s" % (v["имя"], v["тип"]) for v in dog.get("входы", []))
        stroki.append("договор %s(%s) -> %s" % (dog["имя"], vhody, dog.get("выход", "число")))
        if dog.get("требует"):
            stroki.append("  требует  %s" % pecatat_vyrazhenie(dog["требует"]))
        if dog.get("даёт"):
            stroki.append("  даёт     %s" % pecatat_vyrazhenie(dog["даёт"]))
        for otk in dog.get("отказы", []):
            stroki.append("  отказ    %s" % otk)
        stroki.append("")
    for s in ast.get("сделки", []):
        vhody = ", ".join("%s: %s" % (v["имя"], v["тип"]) for v in s.get("входы", []))
        stroki.append("сделка %s(%s) -> %s" % (s["имя"], vhody, s.get("выход", "число")))
        stroki.append("  тело:")
        stroki.extend(pecatat_telo(s.get("тело", []), "    "))
        stroki.append("  свидетель:")
        for kz in s.get("свидетель", []):
            vhod = ", ".join("%s=%s" % (k, pecatat_vyrazhenie({"оп": "константа", "значение": v}))
                             for k, v in kz.get("вход", {}).items())
            if "выход" in kz:
                stroki.append("    %s -> %s" % (vhod, kz["выход"]))
            elif "отказ" in kz:
                stroki.append("    %s -> отказ %s" % (vhod, kz["отказ"]))
        stroki.append("")
    return "\n".join(stroki)
