# -*- coding: utf-8 -*-
"""DEAL: сборка проекта [v0.3.0, задание З2 / №10 доски СОВЕТ_DEAL].

--собрать-проект <папка>: все *.deal под папкой компилируются в порядке,
выведенном ИЗ AST-ОВ (ввозы; цикл по пути — отказ словами). Постоянных
боковых файлов графа нет — порядок живёт один запуск [вердикт раунда 7].

Правило пропуска честное [правка спеки QWEN раунда 8]: файл пропускается
только если совпадают его собственный хеш (зелёная запись реестра) И хеши
ВСЕХ транзитивных ввозов на диске с объявленными. Спека «суд ввозов для
пропущенного не нужен» — дыра: изменился только файл ввоза → собственный
хеш ввозителя не меняется → пропуск дал бы зовы в стухшее. У пересобираемых
суд ввозов обязателен всегда (байт-в-байт, v0.1.3).

Каскад отказов: упал базовый файл — зависимые получают отказ словами
«базовый файл X не собрался», независимые продолжают — все отказы за один
проход. Одна запись летописи на сборку (цепь + якорь, как у компиляции).
Подсказка мёртвого ввоза: файла нет рядом, но хеш совпадает с соседним
файлом — отказ называет нового соседа [мини-аудит QWEN].
"""
import io
import json
import os
import time

from deal import ast as dast
from deal import vm as dvm
from deal import kompilyator as dkom


def _dealfajly(papka: str) -> list:
    rez = []
    for koren, _, fayly in os.walk(papka):
        for f in sorted(fayly):
            if f.endswith(".deal"):
                rez.append(os.path.normpath(os.path.join(koren, f)))
    return sorted(rez)


def _put_vvoza(put_fayla: str, iz: str):
    """Файл ввоза рядом с ввозителем (как dast.sdelki_s_vvozyami).
    normpath ОБЯЗАТЕЛЕН: «из» несёт слэш («std/arith») — join даёт смесь
    разделителей, ключи графа разъезжаются [мина пробы v0.3.0: каскад молчал]."""
    papka = os.path.dirname(os.path.abspath(put_fayla))
    for rassh in (".deal", ".deal.json"):
        kandidat = os.path.normpath(os.path.join(papka, iz + rassh))
        if os.path.exists(kandidat):
            return kandidat
    return None


def _podskazka_mertvogo(put_fayla: str, iz: str, hesh: str):
    """Файла ввоза нет — сканируем ПАПКУ ВВОЗА (где файл был бы) по хешу:
    переименованный файл узнаётся по содержанию [мини-аудит QWEN, раунд 8]."""
    ozhidaemy = os.path.join(os.path.dirname(os.path.abspath(put_fayla)),
                             iz + ".deal")
    papka = os.path.dirname(ozhidaemy)
    stary = iz + ".deal"
    if not os.path.isdir(papka):
        return None
    for imya in sorted(os.listdir(papka)):
        if not imya.endswith((".deal", ".deal.json")) or imya == stary:
            continue
        kandidat = os.path.join(papka, imya)
        try:
            if dast.hesh(dast.zagruzit(kandidat)) == hesh:
                return kandidat
        except (OSError, dvm.DealOtkaz):
            continue
    return None


def _proverka_vvozov(fayly: list, asty: dict) -> list:
    """[дискавери] Все ввозы резолвятся в файлы на диске; мёртвый ввоз —
    отказ с подсказкой, если сосед узнаётся по хешу."""
    otkazy = []
    for put in fayly:
        for vvoz in asty[put].get("ввозы", []):
            iz = str(vvoz.get("из", ""))
            if _put_vvoza(put, iz) is None:
                prichina = "файла нет рядом"
                podsk = _podskazka_mertvogo(put, iz, str(vvoz.get("хеш")))
                if podsk:
                    prichina += (" — хеш совпадает с %s: обнови «из» в ввозах"
                                 % os.path.basename(podsk))
                otkazy.append({"файл": put, "стадия": 1,
                               "виновник": "ввоз из «%s» в %s"
                                           % (iz, os.path.basename(put)),
                               "причина": prichina,
                               "что_править": "правь раздел «ввозы» или обнови "
                                              "хеш ввозимого файла"})
    return otkazy


def _poryadok(fayly: list, asty: dict):
    """Топологический порядок из AST-ов: ввозимые раньше ввозителей.
    Цикл по пути — отказ словами. Возврат (порядок, граф внутри проекта)."""
    graf = {}
    for put in fayly:
        vnutr = set()
        for vvoz in asty[put].get("ввозы", []):
            put_v = _put_vvoza(put, str(vvoz.get("из", "")))
            if put_v in asty:
                vnutr.add(put_v)
        graf[put] = vnutr
    poryadok = []
    sost = {}

    def obhod(put, stek):
        s = sost.get(put, 0)
        if s == 2:
            return
        if s == 1:
            koltso = stek[stek.index(put):] + [put]
            raise dkom.Otkaz(1, "ввозы проекта",
                             "цикл по пути ввозов: "
                             + " → ".join(os.path.basename(x) for x in koltso),
                             "разорви цикл (расколоть-по-шву) или обнови ввозы")
        sost[put] = 1
        for zav in sorted(graf[put]):
            obhod(zav, stek + [put])
        sost[put] = 2
        poryadok.append(put)

    for put in fayly:
        obhod(put, [])
    return poryadok, graf


def _zelenye_heshey(reestr_put: str) -> set:
    """Хеши зелёных записей реестра (zelenye == vsego)."""
    heshey = set()
    try:
        with io.open(reestr_put, encoding="utf-8") as fh:
            for stroka in fh:
                try:
                    z = json.loads(stroka)
                except ValueError:
                    continue
                if z.get("hesh") and z.get("vsego") is not None \
                        and z.get("zelenye") == z.get("vsego"):
                    heshey.add(z["hesh"])
    except OSError:
        pass
    return heshey


def _propustit(put: str, ast: dict, zelenye: set) -> bool:
    """Правило пропуска [правка спеки QWEN раунда 8]: свой хеш зелёный
    в реестре И хеши ВСЕХ транзитивных ввозов на диске совпадают с
    объявленными — иначе стухший ввоз дал бы зовы в старое."""
    if dast.hesh(ast) not in zelenye:
        return False
    stek = [(put, ast)]
    videl = {put}
    while stek:
        p, a = stek.pop()
        for vvoz in a.get("ввозы", []):
            put_v = _put_vvoza(p, str(vvoz.get("из", "")))
            if put_v is None:
                return False
            try:
                ast_v = dast.zagruzit(put_v)
            except (OSError, dvm.DealOtkaz):
                return False
            if dast.hesh(ast_v) != str(vvoz.get("хеш")):
                return False   # ввоз изменился — пересборка с судом ввозов
            if put_v not in videl:
                videl.add(put_v)
                stek.append((put_v, ast_v))
    return True


def sobrat_proekt(papka: str, parall: bool = False, kesh: bool = True,
                  kesh_proba: int = 16) -> dict:
    """Полный проход сборки. Отказы собираются за один проход; наружу —
    свод словами. Код выхода решает вызывающий (отказов > 0 → 1)."""
    nacalo = time.time()
    # пути ВСЕГДА абсолютные: граф/ввозы сравниваются по os.path, а walk от
    # относительной папки дал бы смесь ключей (мина, пойманная пробой v0.3.0:
    # цикл не детектился — рёбра уезжали в абсолют, узлы оставались в относительных)
    fayly = [os.path.abspath(x) for x in _dealfajly(papka)]
    if not fayly:
        raise dkom.Otkaz(1, "сборка проекта", "в папке нет .deal файлов",
                         "укажи папку с компонентами")
    asty = {}
    for put in fayly:
        try:
            asty[put] = dast.zagruzit(put)
        except dvm.DealOtkaz as otk:
            raise dkom.Otkaz(1, "файл " + os.path.basename(put),
                             otk.imya + " — " + (otk.prichina or "файл не разобрался"),
                             "правь канон файла")
    otkazy = _proverka_vvozov(fayly, asty)
    mertvye = {o["файл"] for o in otkazy}
    poryadok, graf = _poryadok(fayly, asty)
    zelenye = _zelenye_heshey(dkom.REESTR)

    sost = {}
    for put in poryadok:
        if put in sost:
            continue
        if put in mertvye:
            sost[put] = "otkaz"   # свой отказ уже в списке
            continue
        upal_baza = None
        for zav in sorted(graf[put]):
            if sost.get(zav) == "otkaz":
                upal_baza = zav
                break
        if upal_baza is not None:
            prichina = "базовый файл %s не собрался" % os.path.basename(upal_baza)
            dkom._otkaz_v_reestr(1, "файл " + os.path.basename(put),
                                 prichina, "сначала исправьте базовый", put)
            otkazy.append({"файл": put, "стадия": 1,
                           "виновник": "файл " + os.path.basename(put),
                           "причина": prichina,
                           "что_править": "сначала исправьте %s"
                                          % os.path.basename(upal_baza)})
            sost[put] = "otkaz"
            continue
        if kesh and _propustit(put, asty[put], zelenye):
            sost[put] = "propushen"
            continue
        try:
            dkom.sobrat(put, kto="сборка-проекта", parall=parall,
                        kesh=kesh, kesh_proba=kesh_proba)
            sost[put] = "ok"
        except dkom.Otkaz as otk:
            otkazy.append({"файл": put, "стадия": otk.stad,
                           "виновник": otk.vinovnik, "причина": otk.prichina,
                           "что_править": otk.chto})
            sost[put] = "otkaz"
        except dvm.DealOtkaz as otk:
            otkazy.append({"файл": put, "стадия": 4,
                           "виновник": "исполнение свидетеля",
                           "причина": otk.imya + (" — " + otk.prichina
                                                  if otk.prichina else ""),
                           "что_править": "назови отказ в договоре или "
                                          "исправь тело/кейс"})
            sost[put] = "otkaz"

    peresobrano = sum(1 for v in sost.values() if v == "ok")
    propusheno = sum(1 for v in sost.values() if v == "propushen")
    golova = dkom._dopisat_letopis({
        "kogda": time.time(), "kto": "сборка-проекта", "папка": papka,
        "всего": len(fayly), "пересобрано": peresobrano,
        "пропущено": propusheno, "отказов": len(otkazy)})
    return {"папка": papka, "всего_файлов": len(fayly),
            "пересобрано": peresobrano, "пропущено": propusheno,
            "отказов": len(otkazy),
            "отказы_список": otkazy,
            "пересобрано_список": [os.path.basename(p) for p, v in sorted(sost.items())
                                   if v == "ok"],
            "время_с": round(time.time() - nacalo, 2),
            "хеш_головы_летописи": golova}
