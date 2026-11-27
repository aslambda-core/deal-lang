/* deal.js — веб-интерпретатор DEAL: исполнение канон-AST против свидетелей.
 * Порт семантики питон-ВМ (deal/vm.py, пилот v0.1.0): те же канон-отказы,
 * то же правило округления (половина вверх), та же глубина зова (300),
 * то же сравнение свидетелей (числа — с допуском 1e-9).
 * Отличие честно названо: полка (файлы состояния) в браузере — в памяти
 * вкладки, не на диске. */

/* ── SHA-256 (чистый JS, для примитивника «хеш») ── */
function sha256(tekst) {
  function rotr(x, n) { return (x >>> n) | (x << (32 - n)); }
  var K = [
    0x428a2f98,0x71374491,0xb5c0fbcf,0xe9b5dba5,0x3956c25b,0x59f111f1,0x923f82a4,0xab1c5ed5,
    0xd807aa98,0x12835b01,0x243185be,0x550c7dc3,0x72be5d74,0x80deb1fe,0x9bdc06a7,0xc19bf174,
    0xe49b69c1,0xefbe4786,0x0fc19dc6,0x240ca1cc,0x2de92c6f,0x4a7484aa,0x5cb0a9dc,0x76f988da,
    0x983e5152,0xa831c66d,0xb00327c8,0xbf597fc7,0xc6e00bf3,0xd5a79147,0x06ca6351,0x14292967,
    0x27b70a85,0x2e1b2138,0x4d2c6dfc,0x53380d13,0x650a7354,0x766a0abb,0x81c2c92e,0x92722c85,
    0xa2bfe8a1,0xa81a664b,0xc24b8b70,0xc76c51a3,0xd192e819,0xd6990624,0xf40e3585,0x106aa070,
    0x19a4c116,0x1e376c08,0x2748774c,0x34b0bcb5,0x391c0cb3,0x4ed8aa4a,0x5b9cca4f,0x682e6ff3,
    0x748f82ee,0x78a5636f,0x84c87814,0x8cc70208,0x90befffa,0xa4506ceb,0xbef9a3f7,0xc67178f2];
  var bajty = new TextEncoder().encode(tekst);
  var dl = bajty.length;
  var sDlinoy = dl + 9;
  var bloki = Math.ceil(sDlinoy / 64);
  var bufer = new Uint8Array(bloki * 64);
  bufer.set(bajty);
  bufer[dl] = 0x80;
  var bitlen = dl * 8;
  var dv = new DataView(bufer.buffer);
  dv.setUint32(bloki * 64 - 4, bitlen >>> 0);
  dv.setUint32(bloki * 64 - 8, Math.floor(bitlen / 4294967296));
  var h = [0x6a09e667,0xbb67ae85,0x3c6ef372,0xa54ff53a,0x510e527f,0x9b05688c,0x1f83d9ab,0x5be0cd19];
  var w = new Array(64);
  for (var b = 0; b < bloki; b++) {
    for (var i = 0; i < 16; i++) w[i] = dv.getUint32(b * 64 + i * 4);
    for (var i = 16; i < 64; i++) {
      var s0 = rotr(w[i-15],7) ^ rotr(w[i-15],18) ^ (w[i-15] >>> 3);
      var s1 = rotr(w[i-2],17) ^ rotr(w[i-2],19) ^ (w[i-2] >>> 10);
      w[i] = (w[i-16] + s0 + w[i-7] + s1) >>> 0;
    }
    var a=h[0],bb=h[1],c=h[2],d=h[3],e=h[4],f=h[5],g=h[6],hh=h[7];
    for (var i = 0; i < 64; i++) {
      var S1 = rotr(e,6) ^ rotr(e,11) ^ rotr(e,25);
      var ch = (e & f) ^ (~e & g);
      var t1 = (hh + S1 + ch + K[i] + w[i]) >>> 0;
      var S0 = rotr(a,2) ^ rotr(a,13) ^ rotr(a,22);
      var maj = (a & bb) ^ (a & c) ^ (bb & c);
      var t2 = (S0 + maj) >>> 0;
      hh=g; g=f; f=e; e=(d+t1)>>>0; d=c; c=bb; bb=a; a=(t1+t2)>>>0;
    }
    h[0]=(h[0]+a)>>>0; h[1]=(h[1]+bb)>>>0; h[2]=(h[2]+c)>>>0; h[3]=(h[3]+d)>>>0;
    h[4]=(h[4]+e)>>>0; h[5]=(h[5]+f)>>>0; h[6]=(h[6]+g)>>>0; h[7]=(h[7]+hh)>>>0;
  }
  return h.map(function(x){ return ('00000000' + x.toString(16)).slice(-8); }).join('');
}

/* ── канонический отказ: имя + причина словами ── */
function DealOtkaz(imya, prichina) {
  this.imya = imya;
  this.prichina = prichina || "";
  this.message = imya + (prichina ? ": " + prichina : "");
}
/* [корпус №14: опечатка DealOtxaz_prototype — необъявленная переменная;
 * в браузере неявный глобал, под strict в Node — ReferenceError] */
DealOtkaz.prototype = Object.create(Error.prototype);
DealOtkaz.prototype.constructor = DealOtkaz;

function otkaz(imya, prichina) { throw new DealOtkaz(imya, prichina); }

function imyaTipa(x) {
  if (typeof x === "number") return "число";
  if (typeof x === "string") return "строка";
  if (Array.isArray(x)) return "список";
  if (x !== null && typeof x === "object") return "словарь";
  return "статус";   // null, undefined, boolean
}

/* Питон-равенство: True==1, 1==1.0, "1"!=1 — не JS-приведение */
function pitonRavno(a, b) {
  if (typeof a === "boolean") a = a ? 1 : 0;
  if (typeof b === "boolean") b = b ? 1 : 0;
  if (typeof a === "number" && typeof b === "number") return a === b;
  if (typeof a !== typeof b) return false;
  if (Array.isArray(a) && Array.isArray(b)) {
    if (a.length !== b.length) return false;
    for (var i = 0; i < a.length; i++) if (!pitonRavno(a[i], b[i])) return false;
    return true;
  }
  if (a !== null && b !== null && typeof a === "object" && typeof b === "object") {
    var ka = Object.keys(a), kb = Object.keys(b);
    if (ka.length !== kb.length) return false;
    return ka.every(function(k){ return k in b && pitonRavno(a[k], b[k]); });
  }
  return a === b;
}

/* ── полка веб-интерпретатора: память вкладки (честно названо) ── */
var POLKA = {};

/* ── примитивник: замороженный набор (ИИ его не пишет) ── */
var PRIMITIVY = {
  "округлено": function(a) {
    // [дифференциал-корпус №14: бинарная мина — 1.005*100 = 100.4999…,
    // floor давал 1.0 против канона 1.01] Канон пилота (vm.py, v0.1.2):
    // Decimal от СТРОКОВОГО представления, половина вверх ОТ НУЛЯ.
    // Порт строкой: цифры величины + позиция точки, полразряда на строках.
    var x = Number(a[0]), n = parseInt(a[1], 10);
    if (isNaN(x) || isNaN(n)) otkaz("типы_не_сошлись", "округлено ждёт число и разряд");
    var s = String(x);
    var m = /^(-?)(\d+)(?:\.(\d+))?(?:e([+-]\d+))?$/.exec(s);
    if (!m) otkaz("типы_не_сошлись", "округлено не взял «" + s + "» — проверь типы и края");
    var znak = m[1], celi = m[2], drob = m[3] || "", ek = m[4] ? parseInt(m[4], 10) : 0;
    // цифры величины ВЕДУЩИЕ НУЛИ ХРАНЯТ: точка стоит после len(celi)+ek
    // цифр строки cif («0.005» → cif «0005», точка после 1-й цифры)
    var cif = celi + drob;
    var p = celi.length + ek;
    var p2 = p + n;                        // масштаб после умножения на 10^n
    var celye;
    if (p2 <= 0) celye = "0";
    else if (p2 >= cif.length) celye = cif + "0".repeat(p2 - cif.length);
    else celye = cif.slice(0, p2);
    celye = celye.replace(/^0+(?=\d)/, "") || "0";
    var sled = (p2 >= 0 && p2 < cif.length) ? cif[p2] : "0";
    if (sled >= "5") {                     // половина вверх на величине
      var i = celye.length - 1;
      var raz = celye.split("");
      for (; i >= 0; i--) { if (raz[i] < "9") { raz[i] = String.fromCharCode(raz[i].charCodeAt(0) + 1); break; } raz[i] = "0"; }
      if (i < 0) raz.unshift("1");
      celye = raz.join("");
    }
    var stroka;
    if (n <= 0) stroka = celye + "0".repeat(-n);
    else if (celye.length > n) stroka = celye.slice(0, celye.length - n) + "." + celye.slice(-n);
    else stroka = "0." + "0".repeat(n - celye.length) + celye;
    var rez = Number((znak === "-" ? "-" : "") + stroka);
    if (isNaN(rez)) otkaz("типы_не_сошлись", "округлено не взял «" + s + "»");
    return rez;
  },
  "хеш": function(a) { return sha256(String(a[0])); },
  "сумма": function(a) {
    if (!Array.isArray(a[0])) otkaz("типы_не_сошлись", "сумма ждёт список");
    return a[0].reduce(function(s, x){ return s + x; }, 0);
  },
  "длина": function(a) {
    if (!Array.isArray(a[0]) && typeof a[0] !== "string") otkaz("типы_не_сошлись", "длина ждёт список или строку");
    return a[0].length;
  },
  "максимум": function(a) {
    if (!Array.isArray(a[0]) || !a[0].length) otkaz("типы_не_сошлись", "максимум ждёт непустой список");
    return Math.max.apply(null, a[0]);
  },
  "минимум": function(a) {
    if (!Array.isArray(a[0]) || !a[0].length) otkaz("типы_не_сошлись", "минимум ждёт непустой список");
    return Math.min.apply(null, a[0]);
  },
  "склейка": function(a) {
    if (!Array.isArray(a[0])) otkaz("типы_не_сошлись", "склейка ждёт список");
    return a[0].map(function(x){ return String(x); }).join(String(a[2]));
  },
  "нижний-регистр": function(a) { return String(a[0]).toLowerCase(); },
  "время": function(a) { return Date.now() / 1000; },
  "логарифм": function(a) {
    var x = Number(a[0]);
    if (isNaN(x) || x <= 0) otkaz("типы_не_сошлись", "логарифм ждёт положительное число");
    return Math.log(x);
  },
  "поле-из-или": function(a) {
    return (a[0] !== null && typeof a[0] === "object" && !Array.isArray(a[0])) ? (a[1] in a[0] ? a[0][a[1]] : a[2]) : a[2];
  },
  "элемент": function(a) {
    var sp = a[0], i = a[1];
    if (!Array.isArray(sp) && typeof sp !== "string")
      otkaz("типы_не_сошлись", "элемент ждёт список, а получил " + imyaTipa(sp) + " — проверь тип");
    var nomer = parseInt(i, 10);
    if (isNaN(nomer)) otkaz("типы_не_сошлись", "элемент ждёт номер, а получил «" + String(i) + "» — приведи к числу");
    if (nomer < 0 || nomer >= sp.length)
      otkaz("за_краем", "элемент(список, " + nomer + "): за краем — длина " + sp.length + ", номера от 0 до " + (sp.length - 1));
    return sp[nomer];
  },
  "тип-из": function(a) { return imyaTipa(a[0]); },
  "список": function(a) { return a.slice(); },
  "словарь": function(a) { return {}; },
  "ключи": function(a) { return Object.keys(a[0]); },
  "поле-записать": function(a) { a[0][a[1]] = a[2]; return a[0]; },
  "поставить": function(a) {
    // [корпус №14] край: питон __setitem__ за краем IndexError →
    // типы_не_сошлись; JS-массив молча расширялся дырками
    var sp = a[0], nomer = parseInt(a[1], 10);
    if (!Array.isArray(sp) || isNaN(nomer) || nomer < 0 || nomer >= sp.length)
      otkaz("типы_не_сошлись", "поставить ждёт список и номер в пределах: длина " + (Array.isArray(sp) ? sp.length : "?"));
    sp[nomer] = a[2];
    return sp;
  },
  "полка-читай-или": function(a) {
    var adres = String(a[0]);
    return (adres in POLKA) ? POLKA[adres] : a[1];
  }
};

/* безопасная обёртка: сырое исключение примитивника = канон-отказ словами */
Object.keys(PRIMITIVY).forEach(function(imya) {
  var funk = PRIMITIVY[imya];
  PRIMITIVY[imya] = function(args) {
    try { return funk(args); }
    catch (e) {
      if (e instanceof DealOtkaz) throw e;
      otkaz("типы_не_сошлись", "примитив «" + imya + "» не взял аргументы: " + (e.message || e) + " — проверь типы и края");
    }
  };
});

/* ── арифметика: питон-семантика, деление на ноль — канон ── */
function arifmetika(lev, chem, prav) {
  // [дифференциал-корпус №14] булевы в питоне — целые: True+True=2,
  // True/True=1.0; в «*» канон v0.1.3 их запрещает нарочно — не коерсим
  if (chem !== "*") {
    if (typeof lev === "boolean") lev = lev ? 1 : 0;
    if (typeof prav === "boolean") prav = prav ? 1 : 0;
  }
  if (chem === "+") {
    if (typeof lev === "number" && typeof prav === "number") return lev + prav;
    if (typeof lev === "string" && typeof prav === "string") return lev + prav;
    if (Array.isArray(lev) && Array.isArray(prav)) return lev.concat(prav);
    // [корпус №14: мой первый фикс назвал это нет_операции и САМ ПОПАЛСЯ
    // сверкой — питонский арифметика-узел ловит TypeError в
    // типы_не_сошлись для всех операций, включая «+»]
    otkaz("типы_не_сошлись", "арифметика «+»: " + imyaTipa(lev) + " с " + imyaTipa(prav) + " не сложить — приведи типы");
  }
  if (chem === "*") {
    if (typeof lev === "number" && typeof prav === "number") return lev * prav;
    otkaz("типы_не_сошлись", "арифметика «*»: " + imyaTipa(lev) + " с " + imyaTipa(prav) + " не умножить — приведи типы");
  }
  if (typeof lev !== "number" || typeof prav !== "number")
    otkaz("типы_не_сошлись", "арифметика «" + chem + "»: " + imyaTipa(lev) + " с " + imyaTipa(prav) + " не считать — приведи типы");
  if (chem === "-") return lev - prav;
  if (chem === "/") {
    if (prav === 0) otkaz("деление_на_ноль", "правая часть равна 0");
    return lev / prav;
  }
  if (chem === "%") {
    if (prav === 0) otkaz("деление_на_ноль", "модуль по нулю");
    // [корпус №14] питон-модуль — FLOOR-MOD: знак остатка по делителю
    // (-7 % 3 = 2), не JS-усечение (-7 % 3 = -1)
    var ost = lev % prav;
    if (ost !== 0 && ((ost < 0) !== (prav < 0))) ost += prav;
    return ost;
  }
  otkaz("нет_операции", "неизвестная арифметика «" + chem + "»");
}

function sravnenie(lev, chem, prav) {
  // [корпус №14] булевы в порядке-сравнениях — целые (питон: False < 1)
  if (typeof lev === "boolean") lev = lev ? 1 : 0;
  if (typeof prav === "boolean") prav = prav ? 1 : 0;
  var odinakovy = (typeof lev === typeof prav) ||
                  (typeof lev === "number" && typeof prav === "number");
  if (chem === "==") return pitonRavno(lev, prav);
  if (chem === "!=") return !pitonRavno(lev, prav);
  if (!odinakovy ||
      (typeof lev !== "number" && typeof lev !== "string"))
    otkaz("типы_не_сошлись", "сравнение «" + chem + "»: " + imyaTipa(lev) + " с " + imyaTipa(prav) + " не сравнить — приведи типы");
  if (chem === "<") return lev < prav;
  if (chem === ">") return lev > prav;
  if (chem === "<=") return lev <= prav;
  return lev >= prav;
}

/* ── исполнение выражений ── */
var ГЛУБИНА_ПОТОЛОК = 300;
var glubina = 0;

function vyzhit(expr, env, sdelki) {
  try {
    return vyzhitSyr(expr, env, sdelki);
  } catch (e) {
    if (e instanceof DealOtkaz) throw e;
    if (e instanceof RangeError) otkaz("глубина", "выражение ушло в глубину — проверь рекурсию");
    otkaz("нет_операции", "кривой узел выражения: " + (e.message || e) + " — правь AST по канону");
  }
}

function vyzhitSyr(expr, env, sdelki) {
  var op = expr && expr["оп"];
  if (op === "константа") return expr["значение"];
  if (op === "поле") {
    var imya = expr["имя"];
    if (!(imya in env)) otkaz("нет_имени", "поле «" + imya + "» не объявлено во входах/пусть");
    return env[imya];
  }
  if (op === "и") return !!vyzhit(expr["лево"], env, sdelki) && !!vyzhit(expr["право"], env, sdelki);
  if (op === "или") return !!vyzhit(expr["лево"], env, sdelki) || !!vyzhit(expr["право"], env, sdelki);
  if (op === "не") return !vyzhit(expr["что"], env, sdelki);
  if (op === "сравнение") {
    var lev = vyzhit(expr["лево"], env, sdelki);
    var prav = vyzhit(expr["право"], env, sdelki);
    return sravnenie(lev, expr["чем"], prav);
  }
  if (op === "арифметика") {
    var lev2 = vyzhit(expr["лево"], env, sdelki);
    var prav2 = vyzhit(expr["право"], env, sdelki);
    return arifmetika(lev2, expr["чем"], prav2);
  }
  if (op === "полка-читай") {
    var adresCh = String(vyzhit(expr["адрес"], env, sdelki));
    if (!(adresCh in POLKA)) otkaz("полка_не_доступна", "файла нет на полке");
    return POLKA[adresCh];
  }
  if (op === "полка-пиши") {
    var adresP = String(vyzhit(expr["адрес"], env, sdelki));
    var znachP = vyzhit(expr["значение"], env, sdelki);
    POLKA[adresP] = znachP;
    return znachP;
  }
  if (op === "зов") {
    var imya2 = expr["договор"];
    if (imya2 in PRIMITIVY) {
      var args = expr["аргументы"].map(function(a){ return vyzhit(a, env, sdelki); });
      return PRIMITIVY[imya2](args);
    }
    if (!(imya2 in sdelki)) otkaz("нет_договора", "зов «" + imya2 + "»: договора нет в файле");
    var argy = expr["аргументы"].map(function(a){ return vyzhit(a, env, sdelki); });
    return zovSdelki(sdelki[imya2], argy, sdelki);
  }
  otkaz("нет_операции", "выражение с неизвестной операцией «" + op + "»");
}

/* ── исполнение тела ── */
function vypolnitTelo(telo, env, sdelki) {
  try {
    return vypolnitTeloSyr(telo, env, sdelki);
  } catch (e) {
    if (e instanceof DealOtkaz) throw e;
    if (e instanceof RangeError) otkaz("глубина", "тело ушло в глубину — цикл или рекурсия без выхода");
    otkaz("нет_операции", "кривой узел тела: " + (e.message || e) + " — правь AST по канону");
  }
}

function vypolnitTeloSyr(telo, env, sdelki) {
  for (var i = 0; i < telo.length; i++) {
    var st = telo[i];
    var op = st["оп"];
    if (op === "присваивание") {
      if (!("имя" in st)) otkaz("нет_операции", "присваивание без «имя» — правь тело");
      env[st["имя"]] = vyzhit(st["что"], env, sdelki);
    } else if (op === "верни") {
      return ["верни", vyzhit(st["что"], env, sdelki)];
    } else if (op === "стой") {
      if (!("отказ" in st)) otkaz("нет_операции", "стой без имени отказа — назови отказ");
      otkaz(st["отказ"], st["причина"] || "стой по договору сделки");
    } else if (op === "присоединить") {
      if (!("имя" in st)) otkaz("нет_операции", "присоединить без «имя» — правь тело");
      var spisok = env[st["имя"]];
      if (!Array.isArray(spisok)) { spisok = []; env[st["имя"]] = spisok; }
      spisok.push(vyzhit(st["что"], env, sdelki));
    } else if (op === "полка-пиши") {
      var adres = String(vyzhit(st["адрес"], env, sdelki));
      POLKA[adres] = vyzhit(st["значение"], env, sdelki);
    } else if (op === "если") {
      var uslovie = vyzhit(st["условие"] || {оп:"константа", значение:true}, env, sdelki);
      var vetv = uslovie ? (st["то"] || []) : (st["иначе"] || []);
      var itog = vypolnitTelo(vetv, env, sdelki);
      if (itog) return itog;
    } else if (op === "для-каждого-до") {
      if (!("переменная" in st)) otkaz("нет_операции", "цикл без переменной — правь тело");
      var d0 = vyzhit(st["до"], env, sdelki);
      var doChislo = parseInt(d0, 10);
      if (isNaN(doChislo)) otkaz("типы_не_сошлись", "«до» цикла ждёт целое число — проверь границу");
      for (var n = 0; n < doChislo; n++) {
        env[st["переменная"]] = n;
        var itog2 = vypolnitTelo(st["тело"] || [], env, sdelki);
        if (itog2) return itog2;
      }
    } else {
      otkaz("нет_операции", "тело: неизвестная операция «" + op + "»");
    }
  }
  return null;
}

function zovSdelki(sdelka, argy, sdelki) {
  var vhody = sdelka["входы"] || [];
  if (argy.length !== vhody.length)
    otkaz("нарушен_договор", "зов «" + (sdelka["имя"] || "?") + "»: у сделки " + vhody.length +
          " вход(ов), а подали " + argy.length + " — согласуй аргументы");
  if (glubina > ГЛУБИНА_ПОТОЛОК)
    otkaz("глубина", "рекурсия глубже " + ГЛУБИНА_ПОТОЛОК + ": сделка «" + (sdelka["имя"] || "?") +
          "» зовёт себя без остановки");
  glubina++;
  try {
    var env = {};
    for (var i = 0; i < vhody.length; i++) env[vhody[i]["имя"]] = argy[i];
    var trebuet = sdelka["требует"];
    if (trebuet && !vyzhit(trebuet, env, sdelki))
      otkaz("нарушен_договор", "требует не выполнено: " + JSON.stringify(trebuet));
    var itog = vypolnitTelo(sdelka["тело"] || [], env, sdelki);
    return itog ? itog[1] : null;
  } finally {
    glubina--;
  }
}

/* ── свидетели ── */
function sravnit(polucheno, ozhidaemoe) {
  if (typeof ozhidaemoe === "number" && typeof polucheno === "number")
    return Math.abs(polucheno - ozhidaemoe) < 1e-9;
  return pitonRavno(polucheno, ozhidaemoe);
}

function gonitSvideteley(sdelka, sdelki) {
  var itogi = [];
  var daet = sdelka["даёт"];
  var kesi = sdelka["свидетель"] || [];
  for (var n = 0; n < kesi.length; n++) {
    var kz = kesi[n];
    var env = {};
    var vhod = kz["вход"] || {};
    Object.keys(vhod).forEach(function(k){ env[k] = vhod[k]; });
    var daetOk = true;
    var polucheno;
    // ФИКСАТУРА: полка ставится в заявленное состояние ПЕРЕД кейсом (как в vm.py)
    if (kz["фиксатура"]) {
      Object.keys(kz["фиксатура"]).forEach(function(adres){ POLKA[adres] = kz["фиксатура"][adres]; });
    }
    try {
      var rez = vypolnitTelo(sdelka["тело"] || [], env, sdelki);
      polucheno = rez ? rez[1] : null;
      if (daet && !(polucheno && polucheno.length === 2 && polucheno[0] === "отказ")) {
        env["это"] = polucheno;
        daetOk = !!vyzhit(daet, env, sdelki);
      }
    } catch (e) {
      if (e instanceof DealOtkaz) polucheno = ["отказ", e.imya];
      else throw e;
    }
    if ("отказ" in kz) {
      var shoditsyaO = Array.isArray(polucheno) && polucheno[0] === "отказ" && polucheno[1] === kz["отказ"];
      itogi.push({кейс: n + 1, ожидали: "отказ " + kz["отказ"], сошлось: shoditsyaO});
    } else if ("свойство" in kz) {
      env["это"] = polucheno;
      var shoditsyaS = !(Array.isArray(polucheno) && polucheno[0] === "отказ") &&
        !!vyzhit(kz["свойство"], env, sdelki) && daetOk;
      itogi.push({кейс: n + 1, ожидали: "свойство", получили: polucheno, сошлось: shoditsyaS});
    } else {
      var shoditsyaV = !(Array.isArray(polucheno) && polucheno[0] === "отказ") &&
        sravnit(polucheno, kz["выход"]) && daetOk;
      itogi.push({кейс: n + 1, ожидали: kz["выход"], получили: polucheno,
                  сошлось: shoditsyaV, даёт: daetOk});
    }
  }
  var vsyo = itogi.every(function(i){ return i.сошлось; });
  return {сделка: sdelka["имя"], кейсы: itogi, зелёная: vsyo};
}

/* гонять все сделки файла (как делает компилятор) */
function gonitFajl(ast) {
  var sdelki = {};
  (ast["сделки"] || []).forEach(function(s){ sdelki[s["имя"]] = s; });
  return (ast["сделки"] || []).map(function(s){ return gonitSvideteley(s, sdelki); });
}
