# -*- coding: utf-8 -*-
"""DEAL: ПРОЕКТНЫЕ превращения [v0.4.1, №9 ступень 2 — поверх --собрать-проекта].

Переименовать-с-переносом-зовущих · влить-сделки · удвоить-компонент-с-
вариацией. Запрос несёт «папка»: суд до/после идёт по ВСЕМ файлам проекта,
изменения каскадируются на объявленные хеши ввозов (топологически — патч
ввоза меняет содержимое самого файла, хеш фиксируется после своих ввозов).
Суд «после» гоняет СТЕНД: всю папку в <папка>.prev.tmp (диск ещё старый);
принято — атомарная запись изменённых файлов, стенд стирается; отвергнуто —
стенд стирается, живое дерево не тронуто.
"""
import copy
import io
import json
import os
import shutil
import time

from deal import ast as dast
from deal import vm as dvm
from deal import kompilyator as dkom

NABOR_PROEKT = {"переименовать-с-переносом-зовущих", "влить-сделки",
                "удвоить-компонент-с-вариацией"}


# ════════ проектные превращения [v0.4.1] — поверх --собрать-проекта ════════

def _proektnye_fajly(papka: str) -> list:
    rez = []
    for koren, _, fayly in os.walk(papka):
        for f in sorted(fayly):
            if f.endswith(".deal"):
                rez.append(os.path.abspath(os.path.join(koren, f)))
    return sorted(rez)


def _zamenit_zovy_vsem(x, staroe: str, novoje: str) -> int:
    """Зовы договора во всём дереве (тела, требует, даёт, свойства).
    Имена сделок — не узлы, замене не подлежат."""
    n = 0
    if isinstance(x, dict):
        if x.get("оп") == "зов" and x.get("договор") == staroe:
            x["договор"] = novoje
            n += 1
        for k in sorted(x):
            n += _zamenit_zovy_vsem(x[k], staroe, novoje)
    elif isinstance(x, list):
        for y in x:
            n += _zamenit_zovy_vsem(y, staroe, novoje)
    return n


def _zamenit_pola(x, podstanovka: dict) -> tuple:
    """Поля входов → выражения (подстановка тела вливаемой). (дерево, счёт)"""
    n = 0
    if isinstance(x, dict):
        if x.get("оп") == "поле" and x.get("имя") in podstanovka:
            return copy.deepcopy(podstanovka[x["имя"]]), 1
        for k in sorted(x):
            x[k], c = _zamenit_pola(x[k], podstanovka)
            n += c
    elif isinstance(x, list):
        for i, y in enumerate(x):
            x[i], c = _zamenit_pola(y, podstanovka)
            n += c
    return x, n


def _kaskad_heshey(fayly: list, asty: dict) -> list:
    """Объявленные хеши ввозов на фактические — в ТОПОЛОГИЧЕСКОМ порядке
    (ввозимые раньше): патч ввоза меняет содержимое самого файла, поэтому
    его собственный хеш фиксируется ПОСЛЕ своих ввозов; иначе зависимые
    получают ещё-не-финальный хеш [мина пробы v0.4.1: каскад в один проход
    рвал цепочку arith→cena→otchet на среднем звене]. Возврат — файлы, чьи
    ввозы патчились (их надо перезаписать, даже если зовы не менялись)."""
    def put_vvoza(put, iz):
        papka = os.path.dirname(put)
        for rassh in (".deal", ".deal.json"):
            kandidat = os.path.normpath(os.path.join(papka, str(iz) + rassh))
            if kandidat in asty:
                return kandidat
        return None

    sost = {}
    poryadok = []

    def obhod(put):
        if sost.get(put):
            return
        sost[put] = 1
        for v in asty[put].get("ввозы", []):
            pv = put_vvoza(put, v.get("из", ""))
            if pv:
                obhod(pv)
        sost[put] = 2
        poryadok.append(put)

    for put in fayly:
        obhod(put)

    izmenennye = []
    fakt = {}
    for put in poryadok:
        patch = False
        for v in asty[put].get("ввозы", []):
            pv = put_vvoza(put, v.get("из", ""))
            if pv is not None and pv in fakt:
                if str(v.get("хеш")) != fakt[pv]:
                    v["хеш"] = fakt[pv]
                    patch = True
        fakt[put] = dast.hesh(asty[put])   # хеш фиксируется ПОСЛЕ своих ввозов
        if patch and put not in izmenennye:
            izmenennye.append(put)
    return izmenennye


def _sud_proekta(fayly: list, koren_suda: str, zel_do: set,
                 peresadka: dict, kesh: bool, kesh_proba: int) -> None:
    """Прогон «после» по всем файлам стенда: не-ухудшение. zel_do —
    (путь-от-корня, имя) зелёных «до»; peresadka — {(путь, старое_имя):
    новое_имя|None}: переименованная сделка обязана быть зелёной под новым
    именем, влитая (None) — честно исчезла, её поведение живёт в зовущей."""
    for put in fayly:
        try:
            itog = dkom.sobrat(put, kto="суд-превращения", kesh=kesh,
                               kesh_proba=kesh_proba, pisat=False)
        except dkom.Otkaz as otk:
            raise dkom.Otkaz(4, "суд после (проект)",
                             os.path.basename(put) + ": " + otk.prichina,
                             otk.chto + " — или отмени превращение")
        rel = os.path.relpath(put, koren_suda)
        zel_posle = {s["сделка"] for s in itog["svody"] if s["зелёная"]}
        star_imena = {im for (r, im) in zel_do if r == rel}
        renezany = {star: novo for (r, star), novo in peresadka.items()
                    if r == rel}
        potery = star_imena - zel_posle - set(renezany)
        if potery:
            raise dkom.Otkaz(4, "суд после (проект)",
                             os.path.basename(put) + ": зелёные покраснели: "
                             + ", ".join(sorted(potery)),
                             "превращение не имеет права ухудшать")
        poteryanek = [star for star, novo in renezany.items()
                      if novo is not None and novo not in zel_posle]
        if poteryanek:
            raise dkom.Otkaz(4, "суд после (проект)",
                             os.path.basename(put) + ": переименованные не "
                             "зелёные: " + ", ".join(sorted(poteryanek)),
                             "переименование обязано сохранить зелёность")


def _zapishi_atomarno(put: str, ast: dict):
    tmp = put + ".prev.tmp"
    with io.open(tmp, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps(ast, ensure_ascii=False, sort_keys=True,
                            separators=(",", ":")))
    os.replace(tmp, put)


def _p_rereimenovat(fayly, asty, dannye):
    staroe = dannye.get("сделка")
    novoje = dannye.get("новое_имя")
    if not staroe or not novoje:
        raise dkom.Otkaz(4, "переименовать-с-переносом-зовущих",
                         "нужны «сделка» и «новое_имя»", "дополни данные")
    put_def = None
    for put in fayly:
        for s in asty[put].get("сделки", []):
            if s.get("имя") == staroe:
                put_def = put
    if put_def is None:
        raise dkom.Otkaz(4, "переименовать-с-переносом-зовущих",
                         "сделки «%s» нет ни в одном файле проекта" % staroe,
                         "укажи имя определённой в проекте сделки")
    for put in fayly:
        for s in asty[put].get("сделки", []):
            if s.get("имя") == novoje:
                raise dkom.Otkaz(4, "переименовать-с-переносом-зовущих",
                                 "новое имя «%s» занято сделкой в %s"
                                 % (novoje, os.path.basename(put)),
                                 "выбери свободное имя")
        for v in asty[put].get("ввозы", []):
            if v.get("договор") == novoje:
                raise dkom.Otkaz(4, "переименовать-с-переносом-зовущих",
                                 "новое имя «%s» занято ввозом в %s"
                                 % (novoje, os.path.basename(put)),
                                 "выбери свободное имя")
    tronuto = []
    for put in fayly:
        zovy = 0
        vvoz_ok = 0
        if put == put_def:
            for s in asty[put]["сделки"]:
                if s.get("имя") == staroe:
                    s["имя"] = novoje
        zovy = _zamenit_zovy_vsem(asty[put], staroe, novoje)
        # ввоз договорённости тоже переносятся: ввоз, ведущий к файлу
        # определения и названный старым именем, теперь носит новое
        for v in asty[put].get("ввозы", []):
            if v.get("договор") == staroe:
                papka = os.path.dirname(put)
                for rassh in (".deal", ".deal.json"):
                    put_v = os.path.normpath(os.path.join(
                        papka, str(v.get("из", "")) + rassh))
                    if os.path.normpath(put_def) == put_v:
                        v["договор"] = novoje
                        vvoz_ok += 1
                        break
        if put == put_def or zovy or vvoz_ok:
            tronuto.append(put)
    rel_def = os.path.relpath(put_def, os.path.commonpath(fayly) if len(fayly) > 1 else os.path.dirname(put_def))
    return tronuto, {(rel_def, staroe): novoje}


def _p_vlit(fayly, asty, dannye):
    imya_a = dannye.get("сделка")
    imya_b = dannye.get("вливаемая")
    if not imya_a or not imya_b:
        raise dkom.Otkaz(4, "влить-сделки",
                         "нужны «сделка» (зовущая) и «вливаемая»",
                         "дополни данные")
    put_ab = None
    sa = sb = None
    for put in fayly:
        imena = {s.get("имя") for s in asty[put].get("сделки", [])}
        if imya_a in imena and imya_b in imena:
            put_ab = put
            sa = next(s for s in asty[put]["сделки"]
                      if s.get("имя") == imya_a)
            sb = next(s for s in asty[put]["сделки"]
                      if s.get("имя") == imya_b)
    if put_ab is None:
        raise dkom.Otkaz(4, "влить-сделки",
                         "обе сделки («%s», «%s») должны лежать в одном файле"
                         % (imya_a, imya_b),
                         "влей в границах файла (ввоз — отдельная ступень)")
    telo_a = sa.get("тело", [])
    if not (len(telo_a) == 1 and telo_a[0].get("оп") == "верни"
            and telo_a[0]["что"].get("оп") == "зов"
            and telo_a[0]["что"].get("договор") == imya_b):
        raise dkom.Otkaz(4, "влить-сделки",
                         "тело «%s» — не единственный зов «%s»" % (imya_a,
                                                                   imya_b),
                         "узы канона: зовущая сводится к одному зову")
    argy = telo_a[0]["что"].get("аргументы", [])
    vhody_b = [v["имя"] for v in sb.get("входы", [])]
    if len(argy) != len(vhody_b):
        raise dkom.Otkaz(4, "влить-сделки",
                         "аргументов %d, а у «%s» входов %d"
                         % (len(argy), imya_b, len(vhody_b)),
                         "согласуй аргументы зова со входами вливаемой")
    # узы: B зовётся ТОЛЬКО из A (остальные сделки — во всех файлах), и не
    # ввозится чужими файлами; сам верни A — легальный единственный зов
    for put in fayly:
        for s in asty[put].get("сделки", []):
            if s is sa:
                continue
            if _zamenit_zovy_vsem(copy.deepcopy(s), imya_b, "\0") > 0:
                gde = os.path.basename(put)
                raise dkom.Otkaz(4, "влить-сделки",
                                 "«%s» зовётся сделкой «%s» (%s) — узы нарушены"
                                 % (imya_b, s.get("имя"), gde),
                                 "сначала переведи зовущих на «%s»" % imya_a)
        if put != put_ab:
            for v in asty[put].get("ввозы", []):
                if v.get("договор") == imya_b:
                    raise dkom.Otkaz(4, "влить-сделки",
                                     "«%s» ввозится из %s — узы нарушены"
                                     % (imya_b, os.path.basename(put)),
                                     "сливай в границах ввозящих")
    podstanovka = dict(zip(vhody_b, argy))
    telo_b, _ = _zamenit_pola(copy.deepcopy(sb.get("тело", [])),
                              podstanovka)
    sa["тело"] = telo_b
    asty[put_ab]["сделки"] = [s for s in asty[put_ab]["сделки"]
                              if s.get("имя") != imya_b]
    rel_ab = os.path.relpath(put_ab, os.path.commonpath(fayly))
    return [put_ab], {(rel_ab, imya_b): None}


def _p_udvoit(papka: str, fayly: list, asty: dict, dannye: dict):
    """Возврат (относительный путь нового файла, его AST) — запись на стенд
    делает вызывающий; на живое дерево файл ложится только после суда."""
    put = os.path.abspath(os.path.join(papka, dannye.get("файл", "")))
    if put not in asty:
        raise dkom.Otkaz(4, "удвоить-компонент-с-вариацией",
                         "файла %s нет в проекте" % dannye.get("файл"),
                         "укажи компонент проекта")
    suff = dannye.get("суффикс", "_вар")
    rel_novy = os.path.relpath(put, papka)[:-5] + suff + ".deal"
    ast = copy.deepcopy(asty[put])
    vnutr = {s.get("имя") for s in ast.get("сделки", [])}
    for s in ast["сделки"]:
        s["имя"] = s["имя"] + suff
    # зовы на внутренние имена — с суффиксом; зовы на ввозные — как были
    for imya in vnutr:
        _zamenit_zovy_vsem(ast, imya, imya + suff)
    return rel_novy, ast


def _vremya() -> float:
    return time.time()


def primenit_proektnoe(zapros: dict, kto: str = "пилот",
                       kesh: bool = True, kesh_proba: int = 16) -> dict:
    """Проектное превращение: «папка» + превращение из NABOR_PROEKT.
    Суд: прогон «до» всех живых файлов → применение в памяти → каскад
    хешей ввозов → СТЕНД (вся папка в <папка>.prev.tmp — суд «после» обязан
    гонять будущее дерево, диск ещё старый) → не-ухудшение → атомарная
    запись изменённых файлов на живое дерево, стенд стирается."""
    papka = os.path.abspath(zapros.get("папка", ""))
    prevrashenie = zapros.get("превращение")
    dannye = zapros.get("данные", {})
    if not papka or prevrashenie not in NABOR_PROEKT:
        raise dkom.Otkaz(4, "проектное превращение",
                         "нужны «папка» и имя из набора: %s"
                         % ", ".join(sorted(NABOR_PROEKT)),
                         "дополни запрос")
    fayly = _proektnye_fajly(papka)
    if not fayly:
        raise dkom.Otkaz(4, "проектное превращение",
                         "в папке нет .deal файлов", "укажи папку проекта")
    asty = {p: dast.zagruzit(p) for p in fayly}
    zel_do = set()
    for p in fayly:
        try:
            itog = dkom.sobrat(p, kto="суд-превращения", kesh=kesh,
                               kesh_proba=kesh_proba, pisat=False)
        except dkom.Otkaz as otk:
            raise dkom.Otkaz(4, "суд до (проект)",
                             os.path.basename(p) + ": " + otk.prichina,
                             "проект обязан собираться зелёным ДО превращения")
        zel_do |= {(os.path.relpath(p, papka), s["сделка"])
                   for s in itog["svody"] if s["зелёная"]}
    hesh_do = dast.hesh({os.path.basename(p): dast.hesh(a)
                         for p, a in sorted(asty.items())})

    tronuto = []
    peresadka = {}
    novy_rel = None
    if prevrashenie == "переименовать-с-переносом-зовущих":
        tronuto, peresadka = _p_rereimenovat(fayly, asty, dannye)
        tronuto = sorted(set(tronuto) | set(_kaskad_heshey(fayly, asty)))
    elif prevrashenie == "влить-сделки":
        tronuto, peresadka = _p_vlit(fayly, asty, dannye)
        tronuto = sorted(set(tronuto) | set(_kaskad_heshey(fayly, asty)))
    elif prevrashenie == "удвоить-компонент-с-вариацией":
        novy_rel, novy_ast = _p_udvoit(papka, fayly, asty, dannye)
        if os.path.exists(os.path.join(papka, novy_rel)):
            raise dkom.Otkaz(4, "удвоить-компонент-с-вариацией",
                             "файл %s уже есть" % novy_rel,
                             "укажи другой суффикс")
        tronuto = [os.path.join(papka, novy_rel)]

    # ── стенд: будущее дерево целиком — суд «после» гоняет его ──
    stazh = papka + ".prev.tmp"
    shutil.rmtree(stazh, ignore_errors=True)
    try:
        for p in fayly:
            rel = os.path.relpath(p, papka)
            dst = os.path.join(stazh, rel)
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            with io.open(dst, "w", encoding="utf-8", newline="\n") as fh:
                fh.write(json.dumps(asty[p], ensure_ascii=False,
                                    sort_keys=True, separators=(",", ":")))
        if novy_rel:
            dst = os.path.join(stazh, novy_rel)
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            with io.open(dst, "w", encoding="utf-8", newline="\n") as fh:
                fh.write(json.dumps(novy_ast, ensure_ascii=False,
                                    sort_keys=True, separators=(",", ":")))
        stazh_fayly = [os.path.join(stazh, os.path.relpath(p, papka))
                       for p in fayly]
        if novy_rel:
            stazh_fayly.append(os.path.join(stazh, novy_rel))
        _sud_proekta(stazh_fayly, stazh, zel_do, peresadka, kesh, kesh_proba)

        # суд пройден — живое дерево получает изменения атомарно
        for put in tronuto:
            if put == os.path.join(papka, novy_rel or ""):
                _zapishi_atomarno(put, novy_ast)
            elif put in asty:
                _zapishi_atomarno(put, asty[put])
    finally:
        shutil.rmtree(stazh, ignore_errors=True)

    hesh_posle = dast.hesh({os.path.basename(p): dast.hesh(dast.zagruzit(p))
                            for p in sorted(fayly)})
    dkom._dopisat_letopis({"kogda": _vremya(), "kto": kto,
                           "tip": "prevrashenie", "папка": papka,
                           "превращение": prevrashenie,
                           "hesh_do": hesh_do, "hesh_posle": hesh_posle,
                           "файлов_тронуто": len(tronuto),
                           "вердикт": "принято"})
    dkom._dobavit_stroku(dkom.REESTR, json.dumps(
        {"kogda": _vremya(), "kto": kto, "tip": "prevrashenie",
         "папка": os.path.basename(papka), "превращение": prevrashenie,
         "файлов_тронуто": len(tronuto), "вердикт": "принято"},
        ensure_ascii=False, sort_keys=True))
    return {"папка": papka, "превращение": prevrashenie,
            "вердикт": "принято", "файлов_тронуто": len(tronuto),
            "hesh_do": hesh_do, "hesh_posle": hesh_posle}
