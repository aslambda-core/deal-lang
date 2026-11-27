# -*- coding: utf-8 -*-
"""DEAL: летопись и реестр [v0.4.1 — вынесено из kompilyator.py, норма 600].

Летопись append-only с хеш-цепочкой («нельзя укоротить» проверяемо):
каждая запись несёт хеш предыдущей; цепь ПРОВЕРЯЕТСЯ при каждой компиляции
(v0.2.1): хеш каждой записи + связь с предыдущей + якорь головы прошлой
компиляции (.deal_letopis_golova) — укорачивание хвоста и подшитый
самосогласованный хвост ловятся, отказ словами.

Записи идут под СТОРОЖ-ЗАМКОМ (v0.3.0): байт 0 отдельного файла
<журнал>.zamok, на весь read-think-append. Три мины, пойманные пробой
гонки v0.3.0: замок только на write рвал цепь (два писца читали одну
голову); лочить сам журнал нельзя — залоченный байт 0 запрещает и
ЧТЕНИЕ (PermissionError на verify); EOF-замки у каждого писца свои.
Сторож никто не читает — только лочит. Замок не взялся — пишем без
него (не роняем компиляцию).
"""
import io
import json
import os
import time

from deal import ast as dast

KOREN = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REESTR = os.path.join(KOREN, "reestr.jsonl")
LETOPIS = os.path.join(KOREN, "letopis.jsonl")
YAKOR = os.path.join(KOREN, ".deal_letopis_golova")


class _Zamok:
    """Сторож-замок для append-журналов: лочится БАЙТ 0 ОТДЕЛЬНОГО
    сторож-файла <журнал>.zamok — один и тот же байт для всех писцов,
    на весь read-think-append (см. докстринг модуля)."""

    def __init__(self, put: str):
        self.put = put
        self.storozh = None
        self.zhurnal = None
        self.vzyat = False

    def __enter__(self):
        try:
            import msvcrt
            put_st = self.put + ".zamok"
            self.storozh = io.open(put_st, "ab")
            try:
                if os.path.getsize(put_st) == 0:
                    self.storozh.write(b"0")
                    self.storozh.flush()
                self.storozh.seek(0)
                msvcrt.locking(self.storozh.fileno(), msvcrt.LK_LOCK, 1)
                self.vzyat = True
            except OSError:
                self.vzyat = False
            self.zhurnal = io.open(self.put, "ab")
        except OSError:
            self.snyat()
        return self

    def pishi(self, stroka: str):
        stroka = stroka if stroka.endswith("\n") else stroka + "\n"
        if self.zhurnal is not None:
            try:
                self.zhurnal.write(stroka.encode("utf-8"))
                self.zhurnal.flush()
                return
            except OSError:
                pass
        with io.open(self.put, "a", encoding="utf-8") as fh:
            fh.write(stroka)

    def snyat(self):
        if self.storozh is not None and self.vzyat:
            try:
                import msvcrt
                self.storozh.seek(0)
                msvcrt.locking(self.storozh.fileno(), msvcrt.LK_UNLCK, 1)
            except OSError:
                pass
        for fh in (self.zhurnal, self.storozh):
            if fh is not None:
                try:
                    fh.close()
                except OSError:
                    pass
        self.zhurnal = None
        self.storozh = None

    def __exit__(self, *slovar):
        self.snyat()
        return False


def _dobavit_stroku(put: str, stroka: str):
    """Строка в append-журнал (reestr/letopis) под замком байта 0."""
    with _Zamok(put) as z:
        z.pishi(stroka)


def _chitat_yakor() -> str:
    try:
        with io.open(YAKOR, encoding="utf-8") as fh:
            return fh.read().strip()
    except OSError:
        return ""


def _pisat_yakor(golova: str):
    try:
        with io.open(YAKOR, "w", encoding="utf-8") as fh:
            fh.write(golova)
    except OSError:
        pass


class LetopisBeda(Exception):
    """Отказ летописи словами [мина v0.4.1: lazy-import Otkaz из компилятора
    давал ЧУЖОЙ класс — скрипт живёт как __main__, except по классу не ловил.
    Летопись несёт свой класс с полями отказа; компилятор переводит его в
    свой Otkaz на границе (stadija_6_7).]"""

    def __init__(self, prichina: str, chto: str):
        self.stad = 6
        self.vinovnik = "летопись"
        self.prichina = prichina
        self.chto = chto
        super().__init__("[стадия 6] летопись: %s — %s" % (prichina, chto))


def beda_letopisi(prichina: str, chto: str) -> "LetopisBeda":
    return LetopisBeda(prichina, chto)


def _proverit_letopis() -> str:
    """[v0.2.1] Две проверки при каждой компиляции: (1) каждая запись
    перепроверяется — хеш записи и связь с предыдущей; (2) голова сверяется
    с якорем прошлой компиляции — укорачивание хвоста обнаруживается.
    Возврат — голова цепи ("" для пустой летописи)."""
    if not os.path.exists(LETOPIS):
        yakor = _chitat_yakor()
        if yakor:
            raise beda_letopisi(
                "файла letopis.jsonl нет, а якорь головы есть («%s…») — "
                "летопись укорочена до нуля" % yakor[:16],
                "восстанови letopis.jsonl из внешней копии или удали якорь "
                ".deal_letopis_golova осознанно")
        return ""
    pred = ""
    golova = ""
    nomer = 0
    with io.open(LETOPIS, encoding="utf-8") as fh:
        for stroka in fh:
            stroka = stroka.strip()
            if not stroka:
                continue
            nomer += 1
            try:
                zapis = json.loads(stroka)
            except ValueError:
                raise beda_letopisi("запись %d не разобралась как JSON" % nomer,
                                    "летопись append-only — строка "
                                    "искажена; восстанови из внешней копии")
            sohran = zapis.pop("hesh_zapisi", None)
            if not sohran or dast.hesh(json.dumps(zapis, ensure_ascii=False,
                                                  sort_keys=True)) != sohran:
                raise beda_letopisi("запись %d: хеш записи не сходится" % nomer,
                                    "летопись искажена — восстанови из "
                                    "внешней копии")
            if zapis.get("pred") != pred:
                raise beda_letopisi("запись %d: связь с предыдущей порвана"
                                    % nomer,
                                    "летопись укорочена или искажена — "
                                    "восстанови из внешней копии")
            pred = sohran
    golova = pred
    yakor = _chitat_yakor()
    if yakor and yakor != golova:
        raise beda_letopisi("голова цепи «%s…» не равна якорю прошлой "
                            "компиляции «%s…» — хвост укорочен"
                            % (golova[:16], yakor[:16]),
                            "восстанови letopis.jsonl из внешней копии или "
                            "удали якорь .deal_letopis_golova осознанно")
    return golova


def _dopisat_letopis(zapis: dict) -> str:
    """Проверить цепь, дописать запись, обновить якорь — ВСЁ под одним
    замком. Общая для компиляции сделки, сборки проекта и суда
    превращений [v0.3.0/v0.4.0]."""
    with _Zamok(LETOPIS) as z:
        zapis["pred"] = _proverit_letopis()
        zapis["hesh_zapisi"] = dast.hesh(json.dumps(
            {k: v for k, v in zapis.items()}, ensure_ascii=False, sort_keys=True))
        z.pishi(json.dumps(zapis, ensure_ascii=False, sort_keys=True))
        _pisat_yakor(zapis["hesh_zapisi"])
    return zapis["hesh_zapisi"]


def _otkaz_v_reestr(stad, vinovnik, prichina, chto, put_fayla):
    """[v0.1.2] «РЕЕСТР — что отвергнуто»: отказ компилятора пишется в
    реестр — отвергнутое не исчезает."""
    zapis = {"kogda": time.time(), "kto": "otkaz", "tip": "otkaz",
             "stad": stad, "vinovnik": vinovnik, "prichina": prichina,
             "chto": chto, "fajl": os.path.basename(put_fayla)}
    _dobavit_stroku(REESTR, json.dumps(zapis, ensure_ascii=False,
                                       sort_keys=True))
