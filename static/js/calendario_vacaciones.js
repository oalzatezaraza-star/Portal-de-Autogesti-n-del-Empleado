/* Calendario real (mes navegable) para elegir el rango de vacaciones.
 * Reemplaza los <input type="date"> por una selección visual, marcando
 * domingos y festivos de Colombia (mismo cálculo que permisos/calendario.py,
 * para que lo que ve el empleado coincida con lo que valida el servidor). */
(function () {
  "use strict";
  var cont = document.getElementById("calendario-vacaciones");
  if (!cont) return;

  var inputIni = document.getElementById("vi"), inputFin = document.getElementById("vf");
  var pintarPrevia = window.pintarPreviaVacaciones || function () {};

  function pad(n) { return String(n).padStart(2, "0"); }
  function iso(d) { return d.getFullYear() + "-" + pad(d.getMonth() + 1) + "-" + pad(d.getDate()); }
  function pascua(y) {
    var a = y % 19, b = Math.floor(y / 100), c = y % 100, d = Math.floor(b / 4), e = b % 4,
      f = Math.floor((b + 8) / 25), g = Math.floor((b - f + 1) / 3), h = (19 * a + b - d - g + 15) % 30,
      i = Math.floor(c / 4), k = c % 4, l = (32 + 2 * e + 2 * i - h - k) % 7,
      m = Math.floor((a + 11 * h + 22 * l) / 451), mes = Math.floor((h + l - 7 * m + 114) / 31),
      dia = (h + l - 7 * m + 114) % 31 + 1;
    return new Date(y, mes - 1, dia);
  }
  function alLunes(d) { var x = new Date(d); x.setDate(x.getDate() + ((7 - ((x.getDay() + 6) % 7)) % 7)); return x; }
  var cache = {};
  function festivos(y) {
    if (cache[y]) return cache[y];
    var p = pascua(y), set = {}, add = function (d) { set[iso(d)] = 1; };
    [[1, 1], [5, 1], [7, 20], [8, 7], [12, 8], [12, 25]].forEach(function (x) { add(new Date(y, x[0] - 1, x[1])); });
    [[1, 6], [3, 19], [6, 29], [8, 15], [10, 12], [11, 1], [11, 11]].forEach(function (x) { add(alLunes(new Date(y, x[0] - 1, x[1]))); });
    var v = new Date(p); v.setDate(v.getDate() - 3); add(v);
    v = new Date(p); v.setDate(v.getDate() - 2); add(v);
    [39, 60, 68].forEach(function (n) { var d = new Date(p); d.setDate(d.getDate() + n); add(alLunes(d)); });
    return (cache[y] = set);
  }

  var hoy = new Date(); hoy.setHours(0, 0, 0, 0);
  var vista = new Date(hoy.getFullYear(), hoy.getMonth(), 1);
  var sel = { ini: inputIni.value ? new Date(inputIni.value + "T00:00") : null, fin: inputFin.value ? new Date(inputFin.value + "T00:00") : null };

  var cab = document.createElement("div"); cab.className = "cal-cab";
  var btnAnt = document.createElement("button"); btnAnt.type = "button"; btnAnt.textContent = "‹"; btnAnt.className = "cal-nav";
  var btnSig = document.createElement("button"); btnSig.type = "button"; btnSig.textContent = "›"; btnSig.className = "cal-nav";
  var titulo = document.createElement("strong");
  cab.appendChild(btnAnt); cab.appendChild(titulo); cab.appendChild(btnSig);
  var grid = document.createElement("div"); grid.className = "cal-grid";
  var ayuda = document.createElement("p"); ayuda.className = "cal-ayuda";
  ayuda.textContent = "Elige el primer día y luego el último. Los domingos y festivos aparecen en rojo (no cuentan como días hábiles).";
  cont.appendChild(cab); cont.appendChild(grid); cont.appendChild(ayuda);

  var MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"];
  var DIAS = ["L", "M", "M", "J", "V", "S", "D"];

  function actualizarInputs() {
    inputIni.value = sel.ini ? iso(sel.ini) : "";
    inputFin.value = sel.fin ? iso(sel.fin) : "";
    inputIni.dispatchEvent(new Event("change"));
  }

  function clic(d) {
    if (!sel.ini || (sel.ini && sel.fin)) { sel = { ini: d, fin: null }; }
    else if (d < sel.ini) { sel.ini = d; }
    else { sel.fin = d; }
    actualizarInputs();
    pintar();
  }

  function pintar() {
    titulo.textContent = MESES[vista.getMonth()] + " de " + vista.getFullYear();
    grid.innerHTML = "";
    DIAS.forEach(function (d) { var c = document.createElement("div"); c.className = "cal-dow"; c.textContent = d; grid.appendChild(c); });
    var primero = new Date(vista.getFullYear(), vista.getMonth(), 1);
    var offset = (primero.getDay() + 6) % 7;
    for (var i = 0; i < offset; i++) grid.appendChild(document.createElement("div"));
    var dias = new Date(vista.getFullYear(), vista.getMonth() + 1, 0).getDate();
    for (var n = 1; n <= dias; n++) {
      var d = new Date(vista.getFullYear(), vista.getMonth(), n);
      var btn = document.createElement("button");
      btn.type = "button"; btn.className = "cal-dia"; btn.textContent = n;
      var esFestivo = d.getDay() === 0 || festivos(d.getFullYear())[iso(d)];
      if (esFestivo) btn.classList.add("cal-festivo");
      if (d < hoy) { btn.disabled = true; btn.classList.add("cal-pasado"); }
      if (sel.ini && iso(d) === iso(sel.ini)) btn.classList.add("cal-sel-ini");
      if (sel.fin && iso(d) === iso(sel.fin)) btn.classList.add("cal-sel-fin");
      if (sel.ini && sel.fin && d > sel.ini && d < sel.fin) btn.classList.add("cal-en-rango");
      if (iso(d) === iso(hoy)) btn.classList.add("cal-hoy");
      btn.addEventListener("click", function (dd) { return function () { clic(dd); }; }(d));
      grid.appendChild(btn);
    }
  }
  btnAnt.addEventListener("click", function () { vista.setMonth(vista.getMonth() - 1); pintar(); });
  btnSig.addEventListener("click", function () { vista.setMonth(vista.getMonth() + 1); pintar(); });
  pintar();
})();
