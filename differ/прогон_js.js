/* JS-прогон дифференциал-корпуса через веб-интерпретатор deal.js
 * [v0.7.0, №14]. Node: загрузить deal.js, исполнить каждый кейс той же
 * семантикой, канонизировать, писать JSON.
 *
 * Прогон: node differ/прогон_js.js <deal.js> <korpus.json> <itogi_js.json>
 */
"use strict";
var fs = require("fs");

var putDeal = process.argv[2];
var putKorpusa = process.argv[3];
var putItogov = process.argv[4];

/* deal.js объявляет функции голыми декларациями — НЕПРЯМОЙ eval исполняет
 * в глобальном скоупе (прямой под strict прятал бы их в скоупе eval);
 * POLKA остаётся пустой (полка вне корпуса) */
var iskhodny = fs.readFileSync(putDeal, "utf8");
(0, eval)(iskhodny);

function kanonich(x) {
  if (typeof x === "boolean") return x;
  if (typeof x === "number") {
    if (!isFinite(x)) return null;
    if (Number.isInteger(x) && Math.abs(x) <= 1e15) return x;
    return Number(x.toFixed(9));
  }
  if (typeof x === "string") return x;
  if (Array.isArray(x)) return x.map(kanonich);
  if (x !== null && typeof x === "object") {
    var o = {};
    Object.keys(x).forEach(function(k) { o[k] = kanonich(x[k]); });
    return o;
  }
  return null;
}

var korpus = JSON.parse(fs.readFileSync(putKorpusa, "utf8"));
var itogi = [];
var nomer = 0;
korpus["сделки"].forEach(function(sdelka) {
  var sdelki = {};
  korpus["сделки"].forEach(function(s) { sdelki[s["имя"]] = s; });
  var telo = sdelka["тело"] || [];
  (sdelka["свидетель"] || []).forEach(function(kz, n) {
    nomer++;
    var itog;
    try {
      var env = JSON.parse(JSON.stringify(kz["вход"] || {}));
      var rez = vypolnitTelo(JSON.parse(JSON.stringify(telo)), env, sdelki);
      itog = kanonich(rez ? rez[1] : null);
    } catch (e) {
      if (e instanceof DealOtkaz) itog = { отказ: e.imya };
      else throw e;
    }
    itogi.push({ сделка: sdelka["имя"], кейс: n + 1,
                 метка: kz["метка"] || "", итог: itog });
  });
});

fs.writeFileSync(putItogov, JSON.stringify(
  { исполнитель: "deal.js", кейсов: nomer, результаты: itogi }, null, 1),
  "utf8");
console.log("deal.js: " + nomer + " кейсов → " + putItogov);
