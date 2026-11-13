/* Zakat Insight: skrip kecil tanpa pustaka (kecuali Plotly untuk grafik). Tidak ada skrip inline (CSP). */
(function () {
  "use strict";

  // Form pemilih berkas dan filter terkirim begitu pilihan berubah; tombol cadangan disembunyikan.
  document.querySelectorAll("form[data-kirim-otomatis]").forEach(function (form) {
    form.querySelectorAll(".tanpa-js").forEach(function (b) { b.hidden = true; });
    form.addEventListener("change", function () {
      form.setAttribute("aria-busy", "true");
      document.body.classList.add("memuat");
      form.submit();
    });
  });

  // Tombol pengirim formulir memberi tanda sedang diproses (gerak hanya menjawab tindakan).
  document.querySelectorAll("form").forEach(function (form) {
    form.addEventListener("submit", function () {
      var b = form.querySelector("button[type=submit]");
      if (b) { b.classList.add("tombol--proses"); b.setAttribute("aria-disabled", "true"); }
    });
  });

  // Grafik Plotly dari figur yang dibuat server (src/charts.py lalu web/grafik.py).
  function gambar() {
    if (!window.Plotly) { return; }
    document.querySelectorAll("[data-figur]").forEach(function (el) {
      var fig;
      try { fig = JSON.parse(el.getAttribute("data-figur")); } catch (e) { return; }
      if (!fig || !fig.data) { return; }
      var sempit = el.clientWidth < 520;
      fig.layout = fig.layout || {};
      if (sempit) {
        fig.layout.height = Math.min(fig.layout.height || 320, 280);
        fig.layout.legend = Object.assign({}, fig.layout.legend, { font: { size: 11 } });
        // Layar sempit: label pita Ramadan disingkat dan label bulan dijarangkan agar tidak bertumpuk.
        (fig.layout.shapes || []).forEach(function (b) { if (b.label) { b.label.text = "R"; } });
        var x = fig.layout.xaxis || {};
        if (x.tickvals && x.tickvals.length > 4) {
          var lompat = Math.ceil(x.tickvals.length / 4);
          x.tickvals = x.tickvals.filter(function (_, i) { return i % lompat === 0; });
          x.ticktext = x.ticktext.filter(function (_, i) { return i % lompat === 0; });
          x.tickangle = 0;
        }
      }
      window.Plotly.newPlot(el, fig.data, fig.layout, {
        displayModeBar: false, responsive: true, scrollZoom: false
      });
    });
  }
  if (document.readyState === "complete") { gambar(); } else { window.addEventListener("load", gambar); }
})();
