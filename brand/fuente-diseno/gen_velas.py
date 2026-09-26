"""MiraTrade candle logo (v2, from the user's sketch): one geometry, every variant."""
from pathlib import Path

BLUE, IVORY, GREEN, BG, PANEL = "#6E9BFF", "#F5F1E8", "#3FD19B", "#0B0E13", "#0F131A"
ZIG = "5,57 20,33 31,47 55.2,10.7"          # enters bottom-left, M zigzag, breaks out top-right
HEAD = "59.5,4.5 59.02,13.29 51.46,8.05"  # arrowhead on the last segment's direction


def symbol(size, bg=BG, frame=BLUE, side=IVORY, mid=BLUE, arrow=GREEN, wicks=True, sw=1.0, label=""):
    aria = f'role="img" aria-label="{label}"' if label else 'aria-hidden="true"'
    w = f"""<line x1="20" y1="14" x2="20" y2="52" stroke="{side}" stroke-width="{1.8 * sw:.1f}" stroke-linecap="round"></line>
<line x1="32" y1="21" x2="32" y2="26" stroke="{mid}" stroke-width="{1.8 * sw:.1f}" stroke-linecap="round"></line>
<line x1="44" y1="14" x2="44" y2="52" stroke="{side}" stroke-width="{1.8 * sw:.1f}" stroke-linecap="round"></line>""" if wicks else ""
    return f"""<svg width="{size}" height="{size}" viewBox="0 0 64 64" fill="none" {aria}>
<rect x="7" y="9" width="50" height="50" rx="13" stroke="{frame}" stroke-width="{3.4 * sw:.1f}"></rect>
{w}
<rect x="16" y="20" width="8" height="26" rx="2" fill="{side}"></rect>
<path d="M28 28 Q28 26 30 26 H34 Q36 26 36 28 V36 L32 40.5 L28 36 Z" fill="{mid}"></path>
<rect x="40" y="20" width="8" height="26" rx="2" fill="{side}"></rect>
<polyline points="{ZIG}" stroke="{bg}" stroke-width="{7.5 * sw:.1f}" stroke-linecap="round" stroke-linejoin="round"></polyline>
<polygon points="{HEAD}" fill="{bg}" stroke="{bg}" stroke-width="{3 * sw:.1f}" stroke-linejoin="round"></polygon>
<polyline points="{ZIG}" stroke="{arrow}" stroke-width="{3.2 * sw:.1f}" stroke-linecap="round" stroke-linejoin="round"></polyline>
<polygon points="{HEAD}" fill="{arrow}" stroke="{arrow}" stroke-width="1" stroke-linejoin="round"></polygon>
</svg>"""


def tiny(size, bg=BG):
    """16 px: no wicks or candles, just frame + the M arrow, thicker."""
    return f"""<svg width="{size}" height="{size}" viewBox="0 0 64 64" fill="none" aria-hidden="true">
<rect x="6" y="8" width="52" height="52" rx="14" stroke="{BLUE}" stroke-width="7"></rect>
<polyline points="{ZIG}" stroke="{bg}" stroke-width="17" stroke-linecap="round" stroke-linejoin="round"></polyline>
<polyline points="{ZIG}" stroke="{GREEN}" stroke-width="9" stroke-linecap="round" stroke-linejoin="round"></polyline>
<polygon points="{HEAD}" fill="{GREEN}" stroke="{GREEN}" stroke-width="4" stroke-linejoin="round"></polygon>
</svg>"""


GROUP = ('<svg width="18" height="18" viewBox="0 0 64 64" fill="none" aria-hidden="true"><rect x="7" y="9" width="50" height="50" rx="13" '
         'stroke="#C9A24A" stroke-width="5"></rect><rect x="18" y="21" width="7" height="27" rx="2" fill="#F5F1E8"></rect>'
         '<rect x="28.5" y="21" width="7" height="15" rx="2" fill="#C9A24A"></rect><rect x="39" y="21" width="7" height="27" rx="2" fill="#F5F1E8"></rect></svg>')

page = f"""<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8">
<title>MiraTrade · logo de velas</title>
<script src="./support.js"></script>
</head>
<body>
<x-dc>
<helmet>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500&amp;family=IBM+Plex+Sans:wght@300;400;500;600;700&amp;display=swap" rel="stylesheet">
<style>
body{{margin:0;background:#0B0E13;font-family:'IBM Plex Sans',sans-serif;color:#E6EAF2}}
a{{color:#6E9BFF}}a:hover{{color:#9BBAFF}}
.lbl{{font-family:'IBM Plex Mono',monospace;font-size:12px;letter-spacing:.14em;color:#9AA4B2}}
.cell{{display:flex;align-items:center;justify-content:center;border-radius:14px;border:1px solid #1E242E;background:#0F131A}}
.k{{font-size:13px;font-weight:600}}
.v{{font-size:13px;line-height:1.5;color:#C4CCD8}}
</style>
</helmet>
<div style="width: 1440px; height: 900px; box-sizing: border-box; padding: 44px 52px; background: #0B0E13; display: grid; grid-template-columns: 540px minmax(0, 1fr); gap: 44px">
  <section style="display: flex; flex-direction: column; gap: 16px">
    <span class="lbl">MIRATRADE · SÍMBOLO DERIVADO DE MIRANDAS GROUP · V3</span>
    <div class="cell" style="flex-grow: 1; background: #0B0E13">
      {symbol(340, label="Símbolo de MiraTrade: tres velas dentro de un marco azul; una flecha verde entra por la esquina inferior izquierda, dibuja una M en zigzag sobre las velas y sale rompiendo el marco por la esquina superior derecha")}
    </div>
    <div style="display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 12px">
      <div style="display: flex; flex-direction: column; gap: 3px"><span class="k">Marco y tres velas</span><span class="v">la base Pilares del grupo, convertida en gráfico</span></div>
      <div style="display: flex; flex-direction: column; gap: 3px"><span class="k" style="color: #6E9BFF">Vela central azul</span><span class="v">el pilar con el color de la marca; su punta es el centro de la M</span></div>
      <div style="display: flex; flex-direction: column; gap: 3px"><span class="k" style="color: #3FD19B">Flecha que dibuja la M</span><span class="v">el precio escribe el nombre y rompe el marco al alza</span></div>
    </div>
  </section>
  <section style="display: flex; flex-direction: column; gap: 16px; min-width: 0">
    <span class="lbl">FIRMA PRINCIPAL</span>
    <div class="cell" style="height: 190px; justify-content: flex-start; gap: 22px; padding: 0 36px">
      {symbol(118, bg=PANEL)}
      <div style="display: flex; flex-direction: column; gap: 8px">
        <span style="font-size: 62px; line-height: 1; letter-spacing: -0.04em"><span style="font-weight: 700">Mira</span><span style="font-weight: 300; color: #6E9BFF">Trade</span></span>
        <span style="display: flex; align-items: center; gap: 8px; font-size: 13px; color: #9AA4B2">{GROUP}a Mirandas Group company</span>
      </div>
    </div>
    <div style="display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 14px">
      <div class="cell" style="height: 170px; flex-direction: column; gap: 8px; background: #F5F7FB; border-color: #D5DAE2">
        {symbol(80, bg="#F5F7FB", frame="#2F5BC8", side="#0E1726", mid="#2F5BC8", arrow="#0E8A5F")}
        <span style="font-size: 12px; color: #4B5563">sobre claro</span>
      </div>
      <div class="cell" style="height: 170px; flex-direction: column; gap: 8px">
        {symbol(80, bg=PANEL, frame="#E6EAF2", side="#E6EAF2", mid="#8A93A3", arrow="#E6EAF2")}
        <span style="font-size: 12px; color: #9AA4B2">monocromo</span>
      </div>
      <div class="cell" style="height: 170px; flex-direction: column; gap: 8px">
        {symbol(80, bg=PANEL, arrow="#F4B740")}
        <span style="font-size: 12px; color: #9AA4B2">alternativa: flecha ámbar</span>
      </div>
    </div>
    <span class="lbl" style="margin-top: 4px">ICONO DE APP Y FAVICON</span>
    <div style="display: flex; align-items: flex-end; gap: 24px">
      <div style="width: 140px; height: 140px; border-radius: 32px; background: #12161D; border: 1px solid #2A3240; display: flex; align-items: center; justify-content: center">{symbol(114, bg="#12161D")}</div>
      {symbol(48, sw=1.25, wicks=False)}
      {symbol(32, sw=1.5, wicks=False)}
      {tiny(16)}
      <p class="v" style="margin: 0 0 2px; max-width: 330px; color: #9AA4B2">Por debajo de 48 px se quitan las mechas y engruesan los trazos; a 16 px quedan el marco y la M de la flecha, que es lo que se reconoce en la pestaña del navegador.</p>
    </div>
  </section>
</div>
</x-dc>
<script type="text/x-dc" data-dc-script data-props='{{"$preview":{{"width":1440,"height":900}}}}'>
class Component extends DCLogic {{
  renderVals() {{ return {{}}; }}
}}
</script>
</body>
</html>
"""
out = Path(__file__).parent / "project" / "Logo-Velas.dc.html"
out.write_text(page, encoding="utf-8")
(Path(__file__).parent / "miratrade-mark.svg").write_text(symbol(512), encoding="utf-8")
print("ok")
