# Sumber berkas huruf

Disajikan sendiri (tanpa Google Fonts) agar tampilan sama dengan atau tanpa internet.

| Berkas | Keluarga | Paket npm asal | Lisensi |
|---|---|---|---|
| `plus-jakarta-sans-latin-wght-normal.woff2` | Plus Jakarta Sans (variabel, wght 200–800, subset latin) | `@fontsource-variable/plus-jakarta-sans@5.3.0` | SIL OFL 1.1 (`OFL-plus-jakarta-sans.txt`) |
| `source-serif-4-latin-opsz-normal.woff2` | Source Serif 4 (variabel, wght 200–900 dan opsz 8–60, subset latin) | `@fontsource-variable/source-serif-4@5.3.1` | SIL OFL 1.1 (`OFL-source-serif-4.txt`) |

`web/static/js/plotly.min.js` disalin dari paket Python `plotly` yang terpasang (berkas
`plotly/package_data/plotly.min.js`), sehingga versinya cocok dengan `fig.to_json()` di server.
Lisensi MIT tertulis di kepala berkas itu. Bila paket `plotly` diperbarui, salin ulang berkasnya.
