# -*- coding: utf-8 -*-
"""DEAL 2.0, П1: ПРОЕКЦИЯ КАК ВХОД — печать и разбор канона.

Контракт (канон неизменен — AST остаётся единственным источником):
  печать(ast)  -> детерминированный читаемый текст (проекция);
  разобрать(текст) -> канон-AST.
Мерка: разобрать(печать(ast)) == ast БАЙТ-В-БАЙТ (по канон-дампу) на всём
живом корпусе песка. Комментарии в тексте умирают (канон их не знает).

Грамматика (отступ = 2 пробела за уровень; табуляция — отказ):
  файл <имя>
  ввоз <договор> из <файл> хеш <hex>
  договор <имя>(вх: тип, ...) -> <выход>
    отказы а, б | требует <expr> | даёт <expr>
  сделка <имя>(вх: тип, ...) -> <выход>
    отказы а, б | требует <expr> | даёт <expr>
    тело:
      <имя> = <expr>            присваивание
      <имя> += <expr>           присоединить
      верни <expr>
      стой отказ <имя>
      если <expr>: ... [иначе: ...]
      для-каждого-до <имя> до <expr>: ...
      полка.пиши(<адрес>, <значение>)
    свидетель:
      [фиксатура <литерал>;] [вх=зн, ...] -> <зн> | -> отказ <имя> | -> свойство <expr>
Выражения: и/или/не, сравнения == != < > <= >=, арифметика + - * / %,
зов имя(арг,...), поле, полка.читай(x), полка.пиши(a, z), литералы
(число, "строка", [список], {словарь}, true/false/null).
Имена — буквы/цифры/подчёркивания; примитивники с дефисами печатаются
алиасами (поле-из-или -> поле_из_или и т.д.), разбор возвращает дефисы канона.
"""
import io
from decimal import Decimal

# ── отказ разбора словами ──

class ProekOtkaz(Exception):
    def __init__(self, stroka, chto):
        super().__init__("строка %d: %s" % (stroka, chto))
        self.stroka = stroka
        self.chto = chto


# ── алиасы примитивников с дефисами ──

ALIASY = {"поле_из_или": "поле-из-или",
          "полка_читай_или": "полка-читай-или",
          "нижний_регистр": "нижний-регистр",
          "поле_записать": "поле-записать",
          "тип_из": "тип-из"}
ALIASY_OBRATNO = {v: k for k, v in ALIASY.items()}


# ── двуязычие: канон-слово -> текст проекции. Рус — тождественный
# (умолчание, обратная совместимость); eng — вторая проекция того же AST.
SLOVA = {
    'rus': {'файл': 'файл', 'ввоз': 'ввоз', 'из': 'из', 'хеш': 'хеш',
            'метка': 'метка', 'договор': 'договор', 'сделка': 'сделка',
            'отказы': 'отказы', 'требует': 'требует', 'даёт': 'даёт',
            'тело': 'тело', 'свидетель': 'свидетель', 'фиксатура': 'фиксатура',
            'отказ': 'отказ', 'свойство': 'свойство', 'верни': 'верни',
            'стой': 'стой', 'причина': 'причина', 'если': 'если',
            'иначе': 'иначе', 'для_каждого_до': 'для_каждого_до', 'до': 'до',
            'не': 'не', 'и': 'и', 'или': 'или', 'полка': 'полка',
            'читай': 'читай', 'пиши': 'пиши'},
    'eng': {'файл': 'file', 'ввоз': 'import', 'из': 'from', 'хеш': 'hash',
            'метка': 'meta', 'договор': 'contract', 'сделка': 'deal',
            'отказы': 'rejects', 'требует': 'requires', 'даёт': 'ensures',
            'тело': 'body', 'свидетель': 'witness', 'фиксатура': 'fixture',
            'отказ': 'reject', 'свойство': 'property', 'верни': 'return',
            'стой': 'stop', 'причина': 'reason', 'если': 'if',
            'иначе': 'else', 'для_каждого_до': 'for_until', 'до': 'until',
            'не': 'not', 'и': 'and', 'или': 'or', 'полка': 'shelf',
            'читай': 'read', 'пиши': 'write'},
}


def slova_yaz(yaz):
    if yaz not in SLOVA:
        raise ProekOtkaz(0, 'неизвестный язык проекции «%s» (rus/eng)' % yaz)
    return SLOVA[yaz]


# ── двуязычие: канон-слово -> текст проекции. Рус — тождественный
# (умолчание, обратная совместимость); eng — вторая проекция того же AST.
SLOVA = {
    'rus': {'файл': 'файл', 'ввоз': 'ввоз', 'из': 'из', 'хеш': 'хеш',
            'метка': 'метка', 'договор': 'договор', 'сделка': 'сделка',
            'отказы': 'отказы', 'требует': 'требует', 'даёт': 'даёт',
            'тело': 'тело', 'свидетель': 'свидетель', 'фиксатура': 'фиксатура',
            'отказ': 'отказ', 'свойство': 'свойство', 'верни': 'верни',
            'стой': 'стой', 'причина': 'причина', 'если': 'если',
            'иначе': 'иначе', 'для_каждого_до': 'для_каждого_до', 'до': 'до',
            'не': 'не', 'и': 'и', 'или': 'или', 'полка': 'полка',
            'читай': 'читай', 'пиши': 'пиши'},
    'eng': {'файл': 'file', 'ввоз': 'import', 'из': 'from', 'хеш': 'hash',
            'метка': 'meta', 'договор': 'contract', 'сделка': 'deal',
            'отказы': 'rejects', 'требует': 'requires', 'даёт': 'ensures',
            'тело': 'body', 'свидетель': 'witness', 'фиксатура': 'fixture',
            'отказ': 'reject', 'свойство': 'property', 'верни': 'return',
            'стой': 'stop', 'причина': 'reason', 'если': 'if',
            'иначе': 'else', 'для_каждого_до': 'for_until', 'до': 'until',
            'не': 'not', 'и': 'and', 'или': 'or', 'полка': 'shelf',
            'читай': 'read', 'пиши': 'write'},
}


def slova_yaz(yaz):
    if yaz not in SLOVA:
        raise ProekOtkaz(0, 'неизвестный язык проекции «%s» (rus/eng)' % yaz)
    return SLOVA[yaz]


# ═══════════════════ ЛЕКСЕР ═══════════════════

_SIMV_2 = ("->", "==", "!=", "<=", ">=", "+=")
_SIMV_1 = "+-*/%()[]{},:.<>;="


def _ekran_zapis(tekst):
    return tekst.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n").replace("\t", "\\t")


def _ekran_chtenie(tekst):
    vyh, i = [], 0
    while i < len(tekst):
        c = tekst[i]
        if c == "\\" and i + 1 < len(tekst):
            sled = tekst[i + 1]
            vyh.append({"n": "\n", "t": "\t", '"': '"', "\\": "\\"}.get(sled, sled))
            i += 2
        else:
            vyh.append(c)
            i += 1
    return "".join(vyh)


def _chislo(tekst):
    try:
        return int(tekst)
    except ValueError:
        return float(tekst)


def leksery(tekst, nomer):
    """Строка -> [(вид, значение)]. Отказ — ProekOtkaz словами."""
    toki, i, dl = [], 0, len(tekst)
    while i < dl:
        c = tekst[i]
        if c in " \t":
            i += 1
            continue
        if c == "#":
            break
        if c == '"':
            j, nak = i + 1, []
            while j < dl and tekst[j] != '"':
                if tekst[j] == "\\" and j + 1 < dl:
                    nak.append(tekst[j:j + 2])
                    j += 2
                else:
                    nak.append(tekst[j])
                    j += 1
            if j >= dl:
                raise ProekOtkaz(nomer, "строка не закрыта кавычкой")
            toki.append(("СТР", _ekran_chtenie("".join(nak))))
            i = j + 1
            continue
        if c.isdigit():
            j = i
            while j < dl and (tekst[j].isdigit() or tekst[j] == "."):
                j += 1
            lit = tekst[i:j]
            if lit.count(".") > 1 or lit.endswith("."):
                raise ProekOtkaz(nomer, "кривое число «%s»" % lit)
            toki.append(("ЧИСЛО", _chislo(lit)))
            i = j
            continue
        if c.isalpha() or c == "_":
            j = i
            while j < dl and (tekst[j].isalnum() or tekst[j] == "_"):
                j += 1
            toki.append(("ИД", tekst[i:j]))
            i = j
            continue
        dvuh = tekst[i:i + 2]
        if dvuh in _SIMV_2:
            toki.append(("СИМ", dvuh))
            i += 2
            continue
        if c in _SIMV_1:
            toki.append(("СИМ", c))
            i += 1
            continue
        raise ProekOtkaz(nomer, "непонятный знак «%s»" % c)
    return toki


# ═══════════════════ ПЕЧАТЬ ═══════════════════

_PRIOR = {"или": 1, "и": 2, "не": 3, "сравнение": 4, "арифметика": 5}


def _prior_op(op, chem=""):
    if op in ("или", "и", "не"):
        return _PRIOR[op]
    if op == "сравнение":
        return _PRIOR["сравнение"]
    if op == "арифметика":
        return _PRIOR["арифметика"] + (1 if chem in ("*", "/", "%") else 0)
    return 9


def pechat_vyrazh(expr, prior_okr=0, slova=None):
    slova = slova or SLOVA["rus"]
    """Детерминированная печать выражения; скобки — по приоритету."""
    op = expr.get("оп")
    if op == "константа":
        return pechat_znacheniya(expr["значение"])
    if op == "поле":
        return expr["имя"]
    if op == "зов":
        imya = ALIASY_OBRATNO.get(expr["договор"], expr["договор"])
        return "%s(%s)" % (imya, ", ".join(pechat_vyrazh(a, 0, slova) for a in expr["аргументы"]))
    if op == "полка-читай":
        return "%s.%s(%s)" % (slova["полка"], slova["читай"],
                              pechat_vyrazh(expr["адрес"], 0, slova))
    if op == "полка-пиши":
        return "%s.%s(%s, %s)" % (slova["полка"], slova["пиши"],
                                  pechat_vyrazh(expr["адрес"], 0, slova),
                                  pechat_vyrazh(expr["значение"], 0, slova))
    # бинарные и «не»
    if op in ("или", "и", "сравнение", "арифметика"):
        znak = slova[op] if op in ("или", "и") else expr["чем"]
        moy = _prior_op(op, expr.get("чем", ""))
        lev = pechat_vyrazh(expr["лево"], moy, slova)
        prav = pechat_vyrazh(expr["право"], moy + 1, slova)
        tek = "%s %s %s" % (lev, znak, prav)
        return "(%s)" % tek if moy < prior_okr else tek
    if op == "не":
        tek = "%s %s" % (slova["не"], pechat_vyrazh(expr["что"], _PRIOR["не"], slova))
        return "(%s)" % tek if _PRIOR["не"] < prior_okr else tek
    return "<?%s?>" % op


def pechat_znacheniya(zn):
    if zn is True:
        return "true"
    if zn is False:
        return "false"
    if zn is None:
        return "null"
    if isinstance(zn, str):
        return '"%s"' % _ekran_zapis(zn)
    if isinstance(zn, list):
        return "[%s]" % ", ".join(pechat_znacheniya(x) for x in zn)
    if isinstance(zn, dict):
        return "{%s}" % ", ".join('"%s": %s' % (_ekran_zapis(str(k)), pechat_znacheniya(v))
                                   for k, v in zn.items())
    if isinstance(zn, float):
        r = repr(zn)
        # научная запись (1e+20) лексер не ест — фиксированная запись той же
        # точности; дробь обязана остаться, иначе float станет int в каноне
        if "e" in r or "E" in r:
            r = format(Decimal(r), "f")
        return r if "." in r else r + ".0"
    return repr(zn)


def _pechat_vhody(vkhody):
    return "(%s)" % ", ".join("%s: %s" % (v["имя"], v.get("тип", "")) for v in vkhody)


def _pechat_telo(telo, glub, stroki, slova):
    otstup = "  " * glub
    for st in telo:
        op = st.get("оп")
        if op == "присваивание":
            stroki.append("%s%s = %s" % (otstup, st["имя"], pechat_vyrazh(st["что"], 0, slova)))
        elif op == "присоединить":
            stroki.append("%s%s += %s" % (otstup, st["имя"], pechat_vyrazh(st["что"], 0, slova)))
        elif op == "верни":
            stroki.append("%s%s %s" % (otstup, slova["верни"],
                                       pechat_vyrazh(st["что"], 0, slova)))
        elif op == "стой":
            stroka = "%s%s %s %s" % (otstup, slova["стой"], slova["отказ"],
                                     st["отказ"])
            if "причина" in st:
                stroka += ' %s "%s"' % (slova["причина"],
                                        _ekran_zapis(st["причина"]))
            stroki.append(stroka)
        elif op == "полка-пиши":
            stroki.append("%s%s" % (otstup, pechat_vyrazh(st, 0, slova)))
        elif op == "если":
            stroki.append("%s%s %s:" % (otstup, slova["если"],
                                        pechat_vyrazh(st["условие"], 0, slova)))
            _pechat_telo(st["то"], glub + 1, stroki, slova)
            if "иначе" in st:
                stroki.append("%s%s:" % (otstup, slova["иначе"]))
                _pechat_telo(st["иначе"], glub + 1, stroki, slova)
        elif op == "для-каждого-до":
            stroki.append("%s%s %s %s %s:" % (
                otstup, slova["для_каждого_до"], st["переменная"],
                slova["до"], pechat_vyrazh(st["до"], 0, slova)))
            _pechat_telo(st["тело"], glub + 1, stroki, slova)
        else:
            stroki.append("%s#? операция «%s»" % (otstup, op))


def _pechat_svidetel(svid, glub, stroki, slova):
    otstup = "  " * glub
    for kz in svid:
        chasti = []
        if "фиксатура" in kz:
            chasti.append("%s %s;" % (slova["фиксатура"],
                                      pechat_znacheniya(kz["фиксатура"])))
        pary = ["%s=%s" % (k, pechat_znacheniya(v)) for k, v in kz.get("вход", {}).items()]
        if pary:
            chasti.append(", ".join(pary))
        if "отказ" in kz:
            pravo = "%s %s" % (slova["отказ"], kz["отказ"])
        elif "свойство" in kz:
            pravo = "%s %s" % (slova["свойство"],
                               pechat_vyrazh(kz["свойство"], 0, slova))
        else:
            pravo = pechat_znacheniya(kz.get("выход"))
        levo = " ".join(chasti)
        if levo:
            stroki.append("%s%s -> %s" % (otstup, levo, pravo))
        else:
            stroki.append("%s-> %s" % (otstup, pravo))


def _pechat_sdelka_dogovor(zapis, slovo, glub, stroki, slova):
    otstup = "  " * glub
    shapka = "%s%s %s%s" % (otstup, slova[slovo], zapis["имя"], _pechat_vhody(zapis.get("входы", [])))
    if zapis.get("выход"):
        shapka += " -> %s" % zapis["выход"]
    stroki.append(shapka)
    if zapis.get("отказы"):
        stroki.append("%s  %s %s" % (otstup, slova["отказы"],
                                     ", ".join(zapis["отказы"])))
    if zapis.get("требует"):
        stroki.append("%s  %s %s" % (otstup, slova["требует"],
                                     pechat_vyrazh(zapis["требует"], 0, slova)))
    if zapis.get("даёт"):
        stroki.append("%s  %s %s" % (otstup, slova["даёт"],
                                     pechat_vyrazh(zapis["даёт"], 0, slova)))
    if slovo == "сделка":
        stroki.append("%s  %s:" % (otstup, slova["тело"]))
        _pechat_telo(zapis.get("тело", []), glub + 2, stroki, slova)
        stroki.append("%s  %s:" % (otstup, slova["свидетель"]))
        _pechat_svidetel(zapis.get("свидетель", []), glub + 2, stroki, slova)


def pechat(ast, yaz="rus") -> str:
    slova = slova_yaz(yaz)
    stroki = ["%s %s" % (slova["файл"], ast.get("файл", "?"))]
    for v in ast.get("ввозы", []):
        stroki.append('%s %s %s %s %s "%s"' % (
            slova["ввоз"], v["договор"], slova["из"], v["из"], slova["хеш"],
            v["хеш"]))
    # метаполя файла (канон их носит: «происхождение» и прочие) — sorted
    izvest = {"файл", "ввозы", "договоры", "сделки"}
    for klyuch in sorted(k for k in ast.keys() if k not in izvest):
        stroki.append('%s "%s": %s' % (slova["метка"],
                                       _ekran_zapis(str(klyuch)),
                                       pechat_znacheniya(ast[klyuch])))
    for d in ast.get("договоры", []):
        _pechat_sdelka_dogovor(d, "договор", 0, stroki, slova)
    for s in ast.get("сделки", []):
        _pechat_sdelka_dogovor(s, "сделка", 0, stroki, slova)
    return "\n".join(stroki)


# ═══════════════════ РАЗБОР ═══════════════════

class _Tok:
    """Токен-поток одной строки с подглядыванием; несёт словарь проекции."""
    def __init__(self, toki, nomer, slova=None):
        self.toki = toki
        self.i = 0
        self.nomer = nomer
        self.slova = slova or SLOVA["rus"]

    def est(self):
        return self.i < len(self.toki)

    def vz(self):
        t = self.toki[self.i]
        self.i += 1
        return t

    def gl(self):
        return self.toki[self.i] if self.i < len(self.toki) else (None, None)

    def est_sim(self, chto):
        vid, zn = self.gl()
        return vid == "СИМ" and zn == chto

    def est_id(self, chto=None):
        vid, zn = self.gl()
        return vid == "ИД" and (chto is None or zn == chto)

    def beri_sim(self, chto):
        if not self.est():
            raise ProekOtkaz(self.nomer, "кончились знаки строки — ждал «%s»" % chto)
        if not self.est_sim(chto):
            raise ProekOtkaz(self.nomer, "ожидался знак «%s», а стоит «%s»"
                             % (chto, self.gl()[1]))
        return self.vz()[1]

    def beri_id(self, chto=None):
        if not self.est():
            raise ProekOtkaz(self.nomer, "кончились знаки строки — ждал «%s»"
                             % (chto or "имя"))
        vid, zn = self.vz()
        if vid != "ИД" or (chto is not None and zn != chto):
            zhd = chto or "имя"
            raise ProekOtkaz(self.nomer, "ожидалось «%s», а стоит «%s»" % (zhd, zn))
        return zn

    def beri_stroku(self):
        if not self.est():
            raise ProekOtkaz(self.nomer, "кончились знаки строки — ждал строку")
        vid, zn = self.vz()
        if vid != "СТР":
            raise ProekOtkaz(self.nomer, "ожидалась строка в кавычках, а стоит «%s»" % (zn,))
        return zn


_STROF = {"verni": None}


def razobrat_vyrazh(tk):
    """Рекурсивный спуск с приоритетами: или < и < не < сравнение < + - < * / %."""
    return _raz_or(tk)


def _raz_or(tk):
    lev = _raz_i(tk)
    while tk.est_id(tk.slova["или"]):
        tk.vz()
        prav = _raz_i(tk)
        lev = {"оп": "или", "лево": lev, "право": prav}
    return lev


def _raz_i(tk):
    lev = _raz_sravn(tk)
    while tk.est_id(tk.slova["и"]):
        tk.vz()
        prav = _raz_sravn(tk)
        lev = {"оп": "и", "лево": lev, "право": prav}
    return lev


_SR_STROKI = {"==", "!=", "<", ">", "<=", ">="}


def _raz_sravn(tk):
    lev = _raz_slag(tk)
    vid, zn = tk.gl()
    if vid == "СИМ" and zn in _SR_STROKI:
        tk.vz()
        prav = _raz_slag(tk)
        return {"оп": "сравнение", "чем": zn, "лево": lev, "право": prav}
    return lev


def _raz_slag(tk):
    lev = _raz_mnozh(tk)
    while tk.est_sim("+") or tk.est_sim("-"):
        chem = tk.vz()[1]
        prav = _raz_mnozh(tk)
        lev = {"оп": "арифметика", "чем": chem, "лево": lev, "право": prav}
    return lev


def _raz_mnozh(tk):
    lev = _raz_unar(tk)
    while tk.est_sim("*") or tk.est_sim("/") or tk.est_sim("%"):
        chem = tk.vz()[1]
        prav = _raz_unar(tk)
        lev = {"оп": "арифметика", "чем": chem, "лево": lev, "право": prav}
    return lev


def _raz_unar(tk):
    if tk.est_id(tk.slova["не"]):
        tk.vz()
        return {"оп": "не", "что": _raz_unar(tk)}
    return _raz_osnov(tk)


def _raz_osnov(tk):
    vid, zn = tk.gl()
    if vid == "ЧИСЛО":
        tk.vz()
        return {"оп": "константа", "значение": zn}
    if vid == "СТР":
        tk.vz()
        return {"оп": "константа", "значение": zn}
    if tk.est_sim("-"):
        tk.vz()
        n = tk.vz()
        if n[0] != "ЧИСЛО":
            raise ProekOtkaz(tk.nomer, "минус — только перед числом")
        znach = -n[1]
        return {"оп": "константа", "значение": znach}
    if tk.est_sim("("):
        tk.vz()
        vnut = razobrat_vyrazh(tk)
        tk.beri_sim(")")
        return vnut
    if tk.est_sim("["):
        tk.vz()
        sp = []
        if not tk.est_sim("]"):
            sp.append(_raz_lit_znachenie(tk))
            while tk.est_sim(","):
                tk.vz()
                sp.append(_raz_lit_znachenie(tk))
        tk.beri_sim("]")
        return {"оп": "константа", "значение": sp}
    if tk.est_sim("{"):
        tk.vz()
        sl = {}
        if not tk.est_sim("}"):
            k = tk.vz()
            if k[0] != "СТР":
                raise ProekOtkaz(tk.nomer, "ключ словаря — строка в кавычках")
            tk.beri_sim(":")
            sl[k[1]] = _raz_lit_znachenie(tk)
            while tk.est_sim(","):
                tk.vz()
                k = tk.vz()
                if k[0] != "СТР":
                    raise ProekOtkaz(tk.nomer, "ключ словаря — строка в кавычках")
                tk.beri_sim(":")
                sl[k[1]] = _raz_lit_znachenie(tk)
        tk.beri_sim("}")
        return {"оп": "константа", "значение": sl}
    if vid == "ИД":
        if zn in ("true", "false", "null"):
            tk.vz()
            znach = {"true": True, "false": False, "null": None}[zn]
            return {"оп": "константа", "значение": znach}
        if zn == tk.slova["полка"] and tk.i + 1 < len(tk.toki) \
                and tk.toki[tk.i + 1] == ("СИМ", "."):
            tk.vz()
            tk.beri_sim(".")
            vid_op = tk.beri_id()
            if vid_op == tk.slova["читай"]:
                tk.beri_sim("(")
                adr = razobrat_vyrazh(tk)
                tk.beri_sim(")")
                return {"оп": "полка-читай", "адрес": adr}
            if vid_op == tk.slova["пиши"]:
                tk.beri_sim("(")
                adr = razobrat_vyrazh(tk)
                tk.beri_sim(",")
                znach = razobrat_vyrazh(tk)
                tk.beri_sim(")")
                return {"оп": "полка-пиши", "адрес": adr, "значение": znach}
            raise ProekOtkaz(tk.nomer, "полка умеет читай/пиши, а не «%s»" % vid_op)
        tk.vz()
        if tk.est_sim("("):
            tk.vz()
            argy = []
            if not tk.est_sim(")"):
                argy.append(razobrat_vyrazh(tk))
                while tk.est_sim(","):
                    tk.vz()
                    argy.append(razobrat_vyrazh(tk))
            tk.beri_sim(")")
            return {"оп": "зов", "договор": ALIASY.get(zn, zn), "аргументы": argy}
        return {"оп": "поле", "имя": zn}
    raise ProekOtkaz(tk.nomer, "не выражение: «%s»" % (zn,))


def _raz_statju(tk):
    vid, zn = tk.gl()
    if vid != "ИД":
        raise ProekOtkaz(tk.nomer, "операция тела должна начинаться именем, а стоит «%s»" % (zn,))
    if zn == tk.slova["верни"]:
        tk.vz()
        return {"оп": "верни", "что": razobrat_vyrazh(tk)}
    if zn == tk.slova["стой"]:
        tk.vz()
        tk.beri_id(tk.slova["отказ"])
        imya = tk.beri_id()
        st = {"оп": "стой", "отказ": imya}
        if tk.est_id(tk.slova["причина"]):
            tk.vz()
            st["причина"] = tk.beri_stroku()
        return st
    if zn == tk.slova["если"]:
        tk.vz()
        usl = razobrat_vyrazh(tk)
        tk.beri_sim(":")
        return {"оп": "если", "условие": usl, "то": []}
    if zn == tk.slova["иначе"]:
        raise ProekOtkaz(tk.nomer, "«%s» без «%s»" % (tk.slova["иначе"],
                                                     tk.slova["если"]))
    if zn == tk.slova["для_каждого_до"]:
        tk.vz()
        perem = tk.beri_id()
        tk.beri_id(tk.slova["до"])
        do = razobrat_vyrazh(tk)
        tk.beri_sim(":")
        return {"оп": "для-каждого-до", "переменная": perem, "до": do, "тело": []}
    if zn == tk.slova["полка"] and tk.i + 1 < len(tk.toki) \
            and tk.toki[tk.i + 1] == ("СИМ", "."):
        tk.vz()
        tk.beri_sim(".")
        vid_op = tk.beri_id()
        if vid_op != tk.slova["пиши"]:
            raise ProekOtkaz(tk.nomer, "в теле полка умеет только пиши, а не «%s»" % vid_op)
        tk.beri_sim("(")
        adr = razobrat_vyrazh(tk)
        tk.beri_sim(",")
        znach = razobrat_vyrazh(tk)
        tk.beri_sim(")")
        return {"оп": "полка-пиши", "адрес": adr, "значение": znach}
    # имя = expr | имя += expr
    tk.vz()
    if tk.est_sim("+="):
        tk.vz()
        return {"оп": "присоединить", "имя": zn, "что": razobrat_vyrazh(tk)}
    tk.beri_sim("=")
    return {"оп": "присваивание", "имя": zn, "что": razobrat_vyrazh(tk)}


def _chitat_blok(stroki_txt, uk, baza_otstup, slova):
    """Блок = строки с отступом больше базового; вернёт список операций."""
    telo = []
    while uk.i < len(stroki_txt):
        nomer, otstup, tekst = stroki_txt[uk.i]
        if len(otstup) <= baza_otstup:
            break
        if len(otstup) % 2 != 0:
            raise ProekOtkaz(nomer, "отступ не кратен 2 пробелам")
        telo.append(_chitat_statju_i_vetki(stroki_txt, uk, len(otstup), slova))
    return telo


def _chitat_statju_i_vetki(stroki_txt, uk, otstup_dl, slova):
    nomer, _, tekst = stroki_txt[uk.i]
    tk = _Tok(leksery(tekst, nomer), nomer, slova)
    st = _raz_statju(tk)
    if tk.est():
        raise ProekOtkaz(nomer, "лишнее после операции: «%s»" % (tk.gl()[1],))
    uk.i += 1
    if st["оп"] == "если":
        st["то"] = _chitat_blok(stroki_txt, uk, otstup_dl, slova)
        if uk.i < len(stroki_txt):
            n2, o2, t2 = stroki_txt[uk.i]
            if len(o2) == otstup_dl and t2.strip() == slova["иначе"] + ":":
                uk.i += 1
                st["иначе"] = _chitat_blok(stroki_txt, uk, otstup_dl, slova)
    elif st["оп"] == "для-каждого-до":
        st["тело"] = _chitat_blok(stroki_txt, uk, otstup_dl, slova)
    return st


def _raz_lit_znachenie(tk):
    z = razobrat_vyrazh(tk)
    if z.get("оп") != "константа":
        raise ProekOtkaz(tk.nomer, "ожидалось значение-литерал")
    return z["значение"]


def _raz_keis(tekst, nomer, slova):
    tk = _Tok(leksery(tekst, nomer), nomer, slova)
    kz = {}
    if tk.est_id(slova["фиксатура"]):
        tk.vz()
        kz["фиксатура"] = _raz_lit_znachenie(tk)
        tk.beri_sim(";")
    vkh = {}
    while not tk.est_sim("->"):
        imya = tk.beri_id()
        tk.beri_sim("=")
        vkh[imya] = _raz_lit_znachenie(tk)
        if tk.est_sim(","):
            tk.vz()
            continue
        break
    if not tk.est_sim("->"):
        raise ProekOtkaz(nomer, "в кейсе нет стрелки «->»")
    tk.vz()
    if tk.est_id(slova["отказ"]):
        tk.vz()
        kz["отказ"] = tk.beri_id()
    elif tk.est_id(slova["свойство"]):
        tk.vz()
        kz["свойство"] = razobrat_vyrazh(tk)
        if tk.est():
            raise ProekOtkaz(nomer, "лишнее после свойства")
    else:
        kz["выход"] = _raz_lit_znachenie(tk)
        if tk.est():
            raise ProekOtkaz(nomer, "лишнее после выхода")
    kz["вход"] = vkh
    return kz


class _Uk:
    def __init__(self, i):
        self.i = i


def _raz_vhody(tekst, nomer):
    """(имя: тип, ...) -> [входы] — общий разбор шапки."""
    tk = _Tok(leksery(tekst, nomer), nomer)
    tk.beri_sim("(")
    vkh = []
    if not tk.est_sim(")"):
        while True:
            imya = tk.beri_id()
            tk.beri_sim(":")
            tip = tk.beri_id()
            vkh.append({"имя": imya, "тип": tip})
            if tk.est_sim(","):
                tk.vz()
                continue
            break
    tk.beri_sim(")")
    return tk, vkh


def razobrat(tekst, yaz="rus") -> dict:
    """Текст проекции -> канон-AST. Отказ словами ProekOtkaz (строка N: что)."""
    stroki_txt = []
    for n, s in enumerate(tekst.split("\n"), 1):
        bez = s.rstrip()
        if not bez.strip():
            continue
        otstup = bez[:len(bez) - len(bez.lstrip(" \t"))]
        if "\t" in otstup:
            raise ProekOtkaz(n, "табуляция в отступе — только пробелы")
        stroki_txt.append((n, otstup, bez.strip()))
    if not stroki_txt:
        raise ProekOtkaz(1, "пустой файл")
    uk = _Uk(0)
    slova = slova_yaz(yaz)
    ast = {"файл": "", "сделки": []}
    nomer, otstup, tekst = stroki_txt[0]
    tk = _Tok(leksery(tekst, nomer), nomer, slova)
    tk.beri_id(slova["файл"])
    ast["файл"] = tk.beri_id()
    if tk.est():
        raise ProekOtkaz(nomer, "лишнее после имени файла")
    uk.i = 1
    while uk.i < len(stroki_txt):
        nomer, otstup, tekst = stroki_txt[uk.i]
        if otstup:
            raise ProekOtkaz(nomer, "раздел файла должен быть без отступа")
        tk = _Tok(leksery(tekst, nomer), nomer, slova)
        slovo = tk.beri_id()
        if slovo == slova["ввоз"]:
            dog = tk.beri_id()
            tk.beri_id(slova["из"])
            iz_file = tk.beri_id()
            tk.beri_id(slova["хеш"])
            hesh = tk.beri_stroku()
            if tk.est():
                raise ProekOtkaz(nomer, "лишнее после хеша ввоза")
            ast.setdefault("ввозы", []).append(
                {"договор": dog, "из": iz_file, "хеш": hesh})
            uk.i += 1
        elif slovo == slova["метка"]:
            klyuch = tk.beri_stroku()
            tk.beri_sim(":")
            ast[klyuch] = _raz_lit_znachenie(tk)
            uk.i += 1
        elif slovo in (slova["сделка"], slova["договор"]):
            kanon_slovo = "сделка" if slovo == slova["сделка"] else "договор"
            zapis = _raz_sdelku(stroki_txt, uk, tk, kanon_slovo, nomer, slova)
            ast.setdefault({"сделка": "сделки", "договор": "договоры"}[kanon_slovo],
                           []).append(zapis)
        else:
            raise ProekOtkaz(nomer, "неизвестный раздел «%s» (жду ввоз/договор/сделка)" % slovo)
    return ast


def _raz_sdelku(stroki_txt, uk, tk, slovo, nomer, slova):
    imya = tk.beri_id()
    tk.beri_sim("(")
    vkh = []
    if not tk.est_sim(")"):
        while True:
            im = tk.beri_id()
            tk.beri_sim(":")
            tip = tk.beri_id()
            vkh.append({"имя": im, "тип": tip})
            if tk.est_sim(","):
                tk.vz()
                continue
            break
    tk.beri_sim(")")
    zapis = {"имя": imya, "входы": vkh}
    if tk.est_sim("->"):
        tk.vz()
        zapis["выход"] = tk.beri_id()
    if tk.est():
        raise ProekOtkaz(nomer, "лишнее в шапке %s" % slovo)
    uk.i += 1
    # секции на отступе 2
    while uk.i < len(stroki_txt):
        n2, o2, t2 = stroki_txt[uk.i]
        if len(o2) < 2:
            break
        if len(o2) != 2:
            raise ProekOtkaz(n2, "секция %s — на отступе 2 пробела" % slovo)
        tk2 = _Tok(leksery(t2, n2), n2, slova)
        sek = tk2.beri_id()
        if sek == slova["отказы"]:
            spisok = [tk2.beri_id()]
            while tk2.est_sim(","):
                tk2.vz()
                spisok.append(tk2.beri_id())
            if tk2.est():
                raise ProekOtkaz(n2, "лишнее после отказов")
            zapis["отказы"] = spisok
            uk.i += 1
        elif sek == slova["требует"]:
            zapis["требует"] = razobrat_vyrazh(tk2)
            if tk2.est():
                raise ProekOtkaz(n2, "лишнее после требует")
            uk.i += 1
        elif sek == slova["даёт"]:
            zapis["даёт"] = razobrat_vyrazh(tk2)
            if tk2.est():
                raise ProekOtkaz(n2, "лишнее после даёт")
            uk.i += 1
        elif sek == slova["тело"]:
            if slovo != "сделка":
                raise ProekOtkaz(n2, "у договора нет тела")
            uk.i += 1
            zapis["тело"] = _chitat_blok(stroki_txt, uk, 2, slova)
        elif sek == slova["свидетель"]:
            uk.i += 1
            zapis["свидетель"] = []
            while uk.i < len(stroki_txt):
                n3, o3, t3 = stroki_txt[uk.i]
                if len(o3) < 4:
                    break
                if len(o3) != 4:
                    raise ProekOtkaz(n3, "кейс свидетеля — на отступе 4 пробела")
                zapis["свидетель"].append(_raz_keis(t3, n3, slova))
                uk.i += 1
        else:
            raise ProekOtkaz(n2, "неизвестная секция «%s» (жду отказы/требует/даёт/тело/свидетель)" % sek)
    if slovo == "сделка" and "тело" not in zapis:
        raise ProekOtkaz(nomer, "у сделки «%s» нет секции тело" % imya)
    if slovo == "сделка" and "свидетель" not in zapis:
        raise ProekOtkaz(nomer, "у сделки «%s» нет секции свидетель" % imya)
    return zapis
