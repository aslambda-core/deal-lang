# -*- coding: utf-8 -*-
"""DEAL: натив-бэкенд C-эмиссией — ПРОТОТИП ступени 4 [v0.10.0, раунд 11
QWEN: его черновик, наши ГРАНИЦЫ-гейты поверх].

Канон числа кернела — f64 (ВМ-верный): «/» float, «%» floor-mod, ноль →
деление_на_ноль; отказы именами через deal_last_otkaz() (setjmp/longjmp).
Сборка cc -O2 -shared -fPIC -lm; ctypes наружу.

ГРАНИЦЫ-ГАТЫ (наши, жёсткие — в нативе НЕТ топлива и границы глубины,
незатактный расчёт = вечное зависание или падение стека):
  - рекурсия: цикл в графе зову → отказ на входе (стек C без контракта);
  - «для-каждого-до»: только КОНСТАНТА ≤ 2^53 (переменная граница не
    доказывает завершение, double-счётчик врёт выше 2^53);
  - присвоение до чтения [v0.10.1]: чтение локала до его присваивания
    на любом пути → не поддержана (в ВМ это отказ «нет_имени», натив
    молчал бы от 0.0 — гейт ловит расхождение ДО эмиссии);
  - только числовые кернелы (входы число, опы кернела — _podderzhivaema);
  - статсуд остаётся в компиляторе: натив эмитит доказанные тела.

ЭМИТТЕР (доска СОВЕТ_DEAL): натив — твоя ступень 4; прототип лежит в
deal/ — твой вердикт жду на доске (реестр «один файл — один дежурный»).
"""
import ctypes
import os
import subprocess
import tempfile

_TR = {'а': 'a', 'б': 'b', 'в': 'v', 'г': 'g', 'д': 'd', 'е': 'e', 'ё': 'e',
       'ж': 'zh', 'з': 'z', 'и': 'i', 'й': 'y', 'к': 'k', 'л': 'l', 'м': 'm',
       'н': 'n', 'о': 'o', 'п': 'p', 'р': 'r', 'с': 's', 'т': 't', 'у': 'u',
       'ф': 'f', 'х': 'h', 'ц': 'ts', 'ч': 'ch', 'ш': 'sh', 'щ': 'sch',
       'ъ': '', 'ы': 'y', 'ь': '', 'э': 'e', 'ю': 'yu', 'я': 'ya'}
_OPS = {"константа", "поле", "арифметика", "сравнение", "если",
        "для-каждого-до", "присваивание", "верни", "зов", "стой"}
_EXOPS = {"константа", "поле", "арифметика", "сравнение", "зов"}
ПРЕДЕЛ = 2 ** 53


class ГейтОтказ(Exception):
    """Натив-гейт не пропустил: причина словами (не канон-отказ сделки)."""


class Imena:
    def __init__(self):
        self.m = {}
        self.used = set()

    def __call__(self, s):
        if s in self.m:
            return self.m[s]
        base = "".join(_TR.get(c, c) for c in s) or "id"
        base = "".join(c if (c.isalnum() or c == "_") else "_" for c in base)
        if base[0].isdigit():
            base = "_" + base
        n = base
        k = 2
        while n in self.used:
            n = "%s_%d" % (base, k)
            k += 1
        self.used.add(n)
        self.m[s] = n
        return n


def _podderzh(x, sdelki, videl):
    """Обход ВСЕГО дерева: каждый оп — в кернеле, зовы — в числовые сделки
    без рекурсивных циклов (гейт: стек C без границы глубины)."""
    if isinstance(x, dict):
        op = x.get("оп")
        if op is not None and op not in _OPS and op not in _EXOPS:
            return False
        if op == "зов":
            im = x.get("договор")
            if im not in sdelki:
                return False
            if any(v.get("тип") != "число" for v in sdelki[im].get("входы", [])):
                return False
            if len(x.get("аргументы", [])) != len(sdelki[im].get("входы", [])):
                return False
            if im not in videl:
                videl.add(im)
                if not _podderzh(sdelki[im]["тело"], sdelki, videl):
                    return False
        if op == "константа":
            zn = x.get("значение")
            if not isinstance(zn, (int, float)):
                return False
            if isinstance(zn, bool) or abs(zn) > ПРЕДЕЛ:
                return False  # [v0.10.1] f64-канон: > 2^53 теряет точность
        return all(_podderzh(v, sdelki, videl) for v in x.values())
    if isinstance(x, list):
        return all(_podderzh(v, sdelki, videl) for v in x)
    return True


def _cikly_zovov(sdelki, videl):
    """[наш гейт] цикл в графе зову поддержанных сделок → True (рекурсия в
    нативе запрещена: стек C без контракта глубины)."""
    sost = {}

    def obhod(im, stek):
        if im in stek:
            return True
        if sost.get(im):
            return False
        sost[im] = 1
        stek = stek | {im}

        def hod(x):
            if isinstance(x, dict):
                if x.get("оп") == "зов" and x.get("договор") in sdelki \
                        and obhod(x["договор"], stek):
                    return True
                return any(hod(v) for v in x.values())
            if isinstance(x, list):
                return any(hod(v) for v in x)
            return False

        return hod(sdelki[im].get("тело", []))

    return any(obhod(im, set()) for im in sdelki if im in videl)


def _chteniya(e, acc):
    """Имена, читаемые в выражении (поля-локалы, аргументы зовов)."""
    if isinstance(e, dict):
        if e.get("оп") == "поле":
            acc.add(e.get("имя"))
        for v in e.values():
            _chteniya(v, acc)
    elif isinstance(e, list):
        for v in e:
            _chteniya(v, acc)
    return acc


def _smotri_chteniya(e, est):
    """[наш гейт 4] любое чтение в выражении — из присвоенных имён."""
    for im in _chteniya(e, set()):
        if im not in est:
            raise ГейтОтказ(
                "натив-гейт: чтение «%s» до присваивания — в ВМ это отказ "
                "«нет_имени», натив молчал бы от 0.0" % im)


def _pripisano_do_chteniya(telo, est):
    """[наш гейт 4] «присвоение до чтения»: каждое чтение локала — после
    присваивания на ВСЕХ путях (консервативно: если-ветки — пересечение,
    присвоения из тела цикла наружу не выходят). Возвращает множество
    имён, присвоенных на всех путях к концу тела."""
    for st in telo:
        op = st.get("оп")
        if op == "присваивание":
            _smotri_chteniya(st.get("что", {}), est)
            est = est | {st["имя"]}
        elif op == "верни":
            _smotri_chteniya(st.get("что", {}), est)
        elif op == "если":
            _smotri_chteniya(st.get("условие", {}), est)
            d_to = _pripisano_do_chteniya(st.get("то", []), set(est))
            d_iz = _pripisano_do_chteniya(st.get("иначе", []), set(est))
            est = d_to & d_iz
        elif op == "для-каждого-до":
            _smotri_chteniya(st.get("до", {}), est)
            _pripisano_do_chteniya(st.get("тело", []),
                                   est | {st.get("переменная")})
    return est


def _granitsy(telo):
    """[наш гейт] «до» цикла — только константа ≤ 2^53 (переменная граница
    не доказывает завершение; double-счётчик врёт выше 2^53)."""
    for st in telo:
        op = st.get("оп")
        if op == "для-каждого-до":
            do = st.get("до", {})
            if do.get("оп") != "константа" \
                    or not isinstance(do.get("значение"), (int, float)) \
                    or abs(do["значение"]) > ПРЕДЕЛ:
                raise ГейтОтказ(
                    "натив-гейт: «до» цикла — только константа ≤ 2^53 "
                    "(в нативе нет топлива; переменная граница не доказывает "
                    "завершение)")
        if op == "если":
            _granitsy(st.get("то", []))
            _granitsy(st.get("иначе", []))
        elif op == "для-каждого-до":
            _granitsy(st.get("тело", []))


def podderzhivaema(sdelka, sdelki):
    """True — сделка проезжает натив-гейты целиком (число-входы, кернел-опы,
    без рекурсивных циклов зову, циклы с константными границами ≤ 2^53,
    присвоение до чтения на всех путях)."""
    if any(v.get("тип") != "число" for v in sdelka.get("входы", [])):
        return False
    videl = {sdelka["имя"]}
    telo = sdelka.get("тело", [])
    if not _podderzh(telo, sdelki, videl):
        return False
    if _cikly_zovov(sdelki, videl):
        return False
    try:
        for im in videl:
            t = sdelki[im]
            vhod_imena = {v["имя"] for v in t.get("входы", [])}
            _pripisano_do_chteniya(t.get("тело", []), vhod_imena)
            _granitsy(t.get("тело", []))
    except ГейтОтказ:
        return False
    return True


def _ex(e, I):
    op = e["оп"]
    if op == "константа":
        return repr(float(e["значение"]))
    if op == "поле":
        return I(e["имя"])
    if op == "арифметика":
        l, r, c = _ex(e["лево"], I), _ex(e["право"], I), e["чем"]
        if c == "/":
            return "deal_div(%s,%s)" % (l, r)
        if c == "%":
            return "deal_mod(%s,%s)" % (l, r)
        return "(%s %s %s)" % (l, c, r)
    if op == "сравнение":
        return "(%s %s %s)" % (_ex(e["лево"], I), e["чем"], _ex(e["право"], I))
    if op == "зов":
        return I(e["договор"]) + "(" + ", ".join(_ex(a, I) for a in e["аргументы"]) + ")"
    raise ValueError("оп " + op)


def _assigned(t, acc):
    for st in t:
        if st["оп"] == "присваивание":
            acc.add(st["имя"])
        if st["оп"] == "если":
            _assigned(st["то"], acc)
            _assigned(st.get("иначе", []), acc)
        if st["оп"] == "для-каждого-до":
            _assigned(st["тело"], acc)
    return acc


def _body(t, out, ind, I):
    for st in t:
        op = st["оп"]
        if op == "присваивание":
            out.append("%s%s = %s;" % (ind, I(st["имя"]), _ex(st["что"], I)))
        elif op == "верни":
            out.append("%sreturn %s;" % (ind, _ex(st["что"], I)))
        elif op == "стой":
            out.append('%sdeal_refusal("%s");' % (ind, st["отказ"]))
        elif op == "если":
            out.append("%sif (%s) {" % (ind, _ex(st["условие"], I)))
            _body(st["то"], out, ind + "  ", I)
            out.append("%s} else {" % ind)
            _body(st.get("иначе", []), out, ind + "  ", I)
            out.append("%s}" % ind)
        elif op == "для-каждого-до":
            v = I(st["переменная"])
            out.append("%sfor (double %s=0; %s<%s; ++%s) {" % (
                ind, v, v, _ex(st["до"], I), v))
            _body(st["тело"], out, ind + "  ", I)
            out.append("%s}" % ind)


def emit(sdelki):
    I = Imena()
    src = ['#include <stdint.h>', '#include <stddef.h>', '#include <math.h>',
           '#include <setjmp.h>',
           'static jmp_buf deal_jmp; static const char* deal_otkaz = NULL;',
           '__attribute__((noreturn)) static void deal_refusal(const char* n){ deal_otkaz=n; longjmp(deal_jmp,1); }',
           'static double deal_div(double a,double b){ if(b==0) deal_refusal("деление_на_ноль"); return a/b; }',
           'static double deal_mod(double a,double b){ if(b==0) deal_refusal("деление_на_ноль"); double r=fmod(a,b); if(r!=0 && ((r<0)!=(b<0))) r+=b; return r; }',
           'const char* deal_last_otkaz(void){ return deal_otkaz; }']
    for n, d in sdelki.items():
        src.append("double %s(%s);" % (I(n), ", ".join("double " + I(v["имя"])
                                                       for v in d["входы"])))
    for n, d in sdelki.items():
        src.append("double %s(%s) {" % (I(n), ", ".join("double " + I(v["имя"])
                                                        for v in d["входы"])))
        for v in sorted(_assigned(d["тело"], set())):
            src.append("  double %s = 0;" % I(v))
        _body(d["тело"], src, "  ", I)
        src.append("  return 0;\n}")
    for n, d in sdelki.items():
        args = ", ".join("double " + I(v["имя"]) for v in d["входы"])
        call = ", ".join(I(v["имя"]) for v in d["входы"])
        src.append("double call_%s(%s){ deal_otkaz=NULL; if(setjmp(deal_jmp)==0) return %s(%s); return 0; }"
                   % (I(n), args, I(n), call))
    return "\n".join(src), I


def sobrat(sdelki, katalog=None):
    katalog = katalog or tempfile.mkdtemp(prefix="deal_c_")
    src, I = emit(sdelki)
    os.makedirs(katalog, exist_ok=True)  # [v0.10.1] CI-ubuntu: rmtree по
    # несуществующей папке проходил молча — deal.c писался в никуда
    cf = os.path.join(katalog, "deal.c")
    so = os.path.join(katalog, "libdeal.so")
    with open(cf, "w", encoding="utf-8") as fh:
        fh.write(src)
    r = subprocess.run(["cc", "-O2", "-shared", "-fPIC", "-o", so, cf, "-lm"],
                       capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError("cc: " + r.stderr[-400:])
    return so, I


def zagruzit(so, sdelki, I):
    lib = ctypes.CDLL(so)
    lib.deal_last_otkaz.restype = ctypes.c_char_p
    for n, d in sdelki.items():
        f = getattr(lib, "call_" + I(n))
        f.argtypes = [ctypes.c_double] * len(d["входы"])
        f.restype = ctypes.c_double
    return lib


def zov(lib, sdelka, argy, I):
    f = getattr(lib, "call_" + I(sdelka["имя"]))
    val = f(*[float(a) for a in argy])
    otk = lib.deal_last_otkaz()
    if otk:
        return ("отказ", otk.decode("utf-8"))
    return ("знач", val)
