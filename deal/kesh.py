# -*- coding: utf-8 -*-
"""DEAL: кеш вердиктов свидетелей [v0.2.0].

Производственный ускоритель, НЕ часть дисциплины: летопись и реестр
append-only живут своей жизнью, кеш их не читает и не пишет.

Правила честности:
  - кешируются только сделки БЕЗ полка-операций в транзитивном замыкании
    зова: вердикт полочной сделки зависит от файлов полки (вне AST),
    закешированный вердикт промолчал бы их изменение;
  - ключ = sha256 канона {схема, хеш_ВМ, сделка, контекст сделок} —
    смена ВМ или ввозов инвалидирует сама (хеш vm.py входит в ключ);
  - запись атомарная (tmp + os.replace): обрыв не портит кеш;
  - кеш лежит в .deal_kesh/ рядом с reestr.jsonl; недоступная папка не
    роняет компиляцию — компилятор просто тише работает без кеша.
"""
import hashlib
import io
import json
import os

from deal import ast as dast

# схема кеша: смена формата вердикта инвалидирует все записи
SHEMA = "kesh-verdikov-v1"

_KAT_ALOG = None  # ленивая инициализация; False = кеш недоступен
_HESH_VM = None   # memo: хеш семантики ВМ


def _hesh_vm() -> str:
    """Хеш исходников ВМ + кеша: смена семантики инвалидирует кеш сама."""
    global _HESH_VM
    if _HESH_VM is None:
        zerno = b""
        for imya in ("vm.py", "kesh.py"):
            put = os.path.join(os.path.dirname(os.path.abspath(__file__)), imya)
            with io.open(put, "rb") as fh:
                zerno += fh.read()
        _HESH_VM = hashlib.sha256(zerno).hexdigest()
    return _HESH_VM


def koren() -> str:
    """Корень пакета (рядом с reestr.jsonl)."""
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _katalog():
    """Папка кеша; None — кеш недоступен (не роняем компиляцию)."""
    global _KAT_ALOG
    if _KAT_ALOG is None:
        put = os.path.join(koren(), ".deal_kesh")
        try:
            os.makedirs(put, exist_ok=True)
            _KAT_ALOG = put
        except OSError:
            _KAT_ALOG = False
    return _KAT_ALOG or None


# ── предикат чистоты: нет полка-операций в транзитивном замыкании ──

_POLKA_OPS = {"полка-читай", "полка-пиши", "полка-читай-или"}


def _skan(x, sdelki, videl):
    """Есть ли полка-оп в дереве или в достижимых зову сделках."""
    if isinstance(x, dict):
        op = x.get("оп")
        if op in _POLKA_OPS:
            return False
        if op == "зов" and x.get("договор") in _POLKA_OPS:
            return False
        if op == "зов":
            imya = x.get("договор")
            if imya in sdelki and imya not in videl:
                videl.add(imya)
                if not _skan(sdelki[imya], sdelki, videl):
                    return False
        return all(_skan(v, sdelki, videl) for v in x.values())
    if isinstance(x, list):
        return all(_skan(v, sdelki, videl) for v in x)
    return True


def polka_chistaya(sdelka: dict, sdelki: dict) -> bool:
    """True — сделка и всё, чего она зовёт, не касаются полки.
    Такой вердикт зависит только от AST и ВМ — можно кешировать."""
    videl = {sdelka["имя"]}
    return _skan(sdelka, sdelki, videl)


# ── ключи ──

def klyuch_svoda(sdelka: dict, sdelki: dict) -> str:
    """Ключ вердикта сделки: сделка + весь контекст сделок + семантика ВМ."""
    return dast.hesh({"shema": SHEMA, "vm": _hesh_vm(),
                      "sdelka": sdelka, "sdelki": sdelki})


def klyuch_kraya(baza: str, imya: str, kraj: int) -> str:
    """Ключ краевой пробы (край входа 0 / 1000000) поверх ключа сделки."""
    return dast.hesh({"shema": SHEMA, "baza": baza, "imya": imya, "kraj": kraj})


# ── чтение/запись ──

def chitat(klyuch: str, polya: tuple):
    """Вердикт из кеша; None — нет/брак/кеш недоступен."""
    kat = _katalog()
    if not kat:
        return None
    put = os.path.join(kat, klyuch + ".json")
    try:
        with io.open(put, encoding="utf-8") as fh:
            verdikt = json.load(fh)
    except (OSError, ValueError):
        return None
    if not isinstance(verdikt, dict) or verdikt.get("shema") != SHEMA:
        return None
    if any(p not in verdikt for p in polya):
        return None
    return verdikt


def pisat(klyuch: str, verdikt: dict) -> None:
    """Атомарно: tmp + os.replace — обрыв не оставляет полузаписи."""
    kat = _katalog()
    if not kat:
        return
    put = os.path.join(kat, klyuch + ".json")
    tmp = put + ".tmp"
    try:
        with io.open(tmp, "w", encoding="utf-8") as fh:
            json.dump(dict(verdikt, shema=SHEMA), fh, ensure_ascii=False, sort_keys=True)
        os.replace(tmp, put)
    except OSError:
        try:
            os.remove(tmp)
        except OSError:
            pass
