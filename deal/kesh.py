# -*- coding: utf-8 -*-
"""DEAL: кеш вердиктов свидетелей [v0.2.1].

Производственный ускоритель, НЕ источник истины: вердикт всегда СЧИТАН
компилятором, кеш лишь экономит повторный счёт. Три зуба честности
[шестой раунд аудита, 21.11]:

  - кешируются только ЧИСТЫЕ сделки: без полка-операций и без
    недетерминированных примитивников («время» вердикт берёт у часов)
    в транзитивном замыкании зова — вердикт чистой сделки зависит
    только от AST и тракта исполнения;
  - запись ПОДПИСАНА: HMAC-SHA256 секретом инстанса (.deal_kesh_slovo
    рядом с reestr.jsonl, вне папки кеша — перенос .deal_kesh на чужую
    машину записи не оживляет). Чужая запись из общего CI-кеша или от
    соседа по машине подписи не проходит и неотличима от отсутствия;
  - попадание ВЫБОРОЧНО переисполняется (по умолчанию 1 из 16, флаг
    --kesh-proba N; N=0 — никогда, N=1 — всегда): живой счёт сверяется
    с записью байт-в-байт — подделка, порча и недетерминизм ловятся,
    запись стирается, вердикт пересчитывается, измена пишется в реестр.

Ключ = sha256 канона {схема, хеш_тракта, сделка, контекст сделок}, где
хеш_тракта покрывает КАЖДЫЙ .py пакета deal/ (vm, bajtkod — дефолтный
исполнитель, kodogen, ast, proekciya, s2_format, kesh, kompilyator) —
смена любого байта семантики инвалидирует сама. Запись атомарная
(tmp с pid+случаем + os.replace — гонка двух писцов закрыта). Кеш лежит
в .deal_kesh/ рядом с reestr.jsonl; недоступная папка или недоступный
секрет не роняют компиляцию — компилятор просто считает без кеша.
"""
import hashlib
import hmac as _hmac
import io
import json
import os

from deal import ast as dast

# схема кеша: смена формата/гарантий инвалидирует все записи v1
SHEMA = "kesh-verdikov-v2"

_KAT_ALOG = None    # ленивая инициализация; False = кеш недоступен
_HESH_TRAKT = None  # memo: хеш всех исходников тракта
_SEKRET = None      # None = ещё не читали; False = секрета нет — кеш выключен

# предикат чистоты: полка и недетерминированные примитивники
_POLKA_OPS = {"полка-читай", "полка-пиши", "полка-читай-или"}
_NEDET_OPS = {"время"}


def _hesh_trakta() -> str:
    """Хеш ВСЕГО исполняющего тракта: каждый .py пакета deal/ входит в ключ.
    [v0.2.1, аудит: раньше хешировались только vm.py+kesh.py — правка
    bajtkod.py (дефолтный исполнитель при РЕЖИМ['байткод']) давала
    устаревший зелёный вердикт из кеша при красном живом счёте.]"""
    global _HESH_TRAKT
    if _HESH_TRAKT is None:
        kat = os.path.dirname(os.path.abspath(__file__))
        zerno = b""
        for imya in sorted(f for f in os.listdir(kat) if f.endswith(".py")):
            with io.open(os.path.join(kat, imya), "rb") as fh:
                zerno += imya.encode("utf-8") + b"\0" + fh.read() + b"\0"
        _HESH_TRAKT = hashlib.sha256(zerno).hexdigest()
    return _HESH_TRAKT


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


def _slovo():
    """Секрет инстанса для подписи записей: bytes; None — кеш выключен.
    Файл .deal_kesh_slovo живёт рядом с reestr.jsonl (НЕ в папке кеша):
    скопированный на чужую машину .deal_kesh без секрета не проходит
    проверку подписи — записи пересчитываются."""
    global _SEKRET
    if _SEKRET is None:
        put = os.path.join(koren(), ".deal_kesh_slovo")
        slovo = b""
        try:
            with io.open(put, "rb") as fh:
                slovo = fh.read().strip()
        except OSError:
            pass
        if not slovo:
            # секрета нет — рождаем один раз; без подписи записи не пишутся
            try:
                slovo = os.urandom(32)
                fd = os.open(put, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                with os.fdopen(fd, "wb") as fh:
                    fh.write(slovo)
            except OSError:
                slovo = b""
        _SEKRET = slovo if slovo else False
    return _SEKRET if _SEKRET else None


def podpis(klyuch: str, verdikt: dict) -> str:
    """HMAC-SHA256 секрета инстанса над {klyuch, verdikt} в каноне."""
    telo = json.dumps({"klyuch": klyuch, "verdikt": verdikt},
                      ensure_ascii=False, sort_keys=True).encode("utf-8")
    return _hmac.new(_slovo(), telo, hashlib.sha256).hexdigest()


def _skan(x, sdelki, videl):
    """Есть ли полка-оп или недетерминированный зов в дереве или в
    достижимых зову сделках."""
    if isinstance(x, dict):
        op = x.get("оп")
        if op in _POLKA_OPS:
            return False
        if op == "зов":
            imya = x.get("договор")
            if imya in _POLKA_OPS or imya in _NEDET_OPS:
                return False
            if imya in sdelki and imya not in videl:
                videl.add(imya)
                if not _skan(sdelki[imya], sdelki, videl):
                    return False
        return all(_skan(v, sdelki, videl) for v in x.values())
    if isinstance(x, list):
        return all(_skan(v, sdelki, videl) for v in x)
    return True


def chistaya(sdelka: dict, sdelki: dict) -> bool:
    """True — сделка и всё, чего она зовёт, не касаются полки и
    недетерминированных примитивников («время»). Такой вердикт зависит
    только от AST и тракта — можно кешировать."""
    videl = {sdelka["имя"]}
    return _skan(sdelka, sdelki, videl)


# ── ключи ──

def klyuch_svoda(sdelka: dict, sdelki: dict) -> str:
    """Ключ вердикта сделки: сделка + весь контекст сделок + хеш тракта."""
    return dast.hesh({"shema": SHEMA, "trakt": _hesh_trakta(),
                      "sdelka": sdelka, "sdelki": sdelki})


def klyuch_kraya(baza: str, imya: str, kraj: int) -> str:
    """Ключ краевой пробы (край входа 0 / 1000000) поверх ключа сделки."""
    return dast.hesh({"shema": SHEMA, "baza": baza, "imya": imya, "kraj": kraj})


# ── чтение/запись ──

def chitat(klyuch: str, polya: tuple):
    """Вердикт из кеша; None — нет/брак/подпись не сошлась/кеш недоступен.
    Запись верится только под своей подписью: чужая, искажённая или
    неподписанная запись неотличима от отсутствия — счёт пойдёт заново."""
    kat = _katalog()
    if not kat or not _slovo():
        return None
    put = os.path.join(kat, klyuch + ".json")
    try:
        with io.open(put, encoding="utf-8") as fh:
            zap = json.load(fh)
    except (OSError, ValueError):
        return None
    if not isinstance(zap, dict) or zap.get("shema") != SHEMA \
            or zap.get("klyuch") != klyuch:
        return None
    verdikt = zap.get("verdikt")
    if not isinstance(verdikt, dict) or not isinstance(zap.get("podpis"), str):
        return None
    if any(p not in verdikt for p in polya):
        return None
    if not _hmac.compare_digest(zap["podpis"], podpis(klyuch, verdikt)):
        return None
    return verdikt


def pisat(klyuch: str, verdikt: dict) -> None:
    """Атомарно: tmp + os.replace — обрыв не портит кеш.
    [v0.2.1, аудит: фиксированное имя .tmp — гонка двух писцов одного
    ключа; tmp уникален (pid+случай), как в полке с v0.1.3.]"""
    kat = _katalog()
    if not kat or not _slovo():
        return
    put = os.path.join(kat, klyuch + ".json")
    tmp = "%s.tmp.%d.%s" % (put, os.getpid(), os.urandom(4).hex())
    try:
        with io.open(tmp, "w", encoding="utf-8") as fh:
            json.dump({"shema": SHEMA, "klyuch": klyuch, "verdikt": verdikt,
                       "podpis": podpis(klyuch, verdikt)},
                      fh, ensure_ascii=False, sort_keys=True)
        os.replace(tmp, put)
    except OSError:
        try:
            os.remove(tmp)
        except OSError:
            pass


def udalit(klyuch: str) -> None:
    """Стереть запись: измена поймана — запись больше не верится,
    вердикт будет считан заново."""
    kat = _katalog()
    if not kat:
        return
    try:
        os.remove(os.path.join(kat, klyuch + ".json"))
    except OSError:
        pass
