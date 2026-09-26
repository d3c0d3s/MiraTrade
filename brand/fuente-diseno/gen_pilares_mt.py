"""MiraTrade final mark: the Mirandas Group pillars (blue central pillar) with a rising arrow
passing BEHIND the three bars and breaking out of the frame."""
import math
from pathlib import Path

BLUE, IVORY, GREEN, BG, PANEL = "#6E9BFF", "#F5F1E8", "#3FD19B", "#0B0E13", "#0F131A"
START, TIP = (5.0, 57.0), (59.5, 4.5)
VERTS = [(21.0, 31.0), (32.0, 45.0)]   # up behind the left bar, V under the blue bar


def arrow_geom(head_len=8.0, half=4.8):
    last = VERTS[-1] if VERTS else START
    dx, dy = TIP[0] - last[0], TIP[1] - last[1]
    L = math.hypot(dx, dy); ux, uy = dx / L, dy / L
    base = (TIP[0] - head_len * ux, TIP[1] - head_len * uy)
    px, py = -uy * half, ux * half
    head = f"{TIP[0]},{TIP[1]} {base[0] + px:.2f},{base[1] + py:.2f} {base[0] - px:.2f},{base[1] - py:.2f}"
    return base, head


def symbol(size, bg=BG, frame=BLUE, side=IVORY, mid=BLUE, arrow=GREEN, sw=1.0, label="", head_len=8.0, half=4.8):
    base, head = arrow_geom(head_len, half)
    aria = f'role="img" aria-label="{label}"' if label else 'aria-hidden="true"'
    pts = " ".join(f"{x},{y}" for x, y in [START, *VERTS]) + f" {base[0]:.2f},{base[1]:.2f}"
    line = f'points="{pts}"'
    edge = f'stroke="{bg}" stroke-width="{2.4 * sw:.1f}"'
    return f"""<svg width="{size}" height="{size}" viewBox="0 0 64 64" fill="none" {aria}>
<rect x="7" y="9" width="50" height="50" rx="13" stroke="{frame}" stroke-width="{3.4 * sw:.1f}"></rect>
<polyline {line} stroke="{bg}" stroke-width="{8 * sw:.1f}" stroke-linecap="round" stroke-linejoin="round"></polyline>
<polygon points="{head}" fill="{bg}" stroke="{bg}" stroke-width="{3.5 * sw:.1f}" stroke-linejoin="round"></polygon>
<polyline {line} stroke="{arrow}" stroke-width="{3.4 * sw:.1f}" stroke-linecap="round" stroke-linejoin="round"></polyline>
<polygon points="{head}" fill="{arrow}" stroke="{arrow}" stroke-width="1" stroke-linejoin="round"></polygon>
<rect x="18" y="21" width="7" height="27" rx="2" fill="{side}" {edge}></rect>
<rect x="28.5" y="21" width="7" height="15" rx="2" fill="{mid}" {edge}></rect>
<rect x="39" y="21" width="7" height="27" rx="2" fill="{side}" {edge}></rect>
</svg>"""


GROUP = ('<svg width="18" height="18" viewBox="0 0 64 64" fill="none" aria-hidden="true"><rect x="7" y="9" width="50" height="50" rx="13" '
         'stroke="#C9A24A" stroke-width="5"></rect><rect x="18" y="21" width="7" height="27" rx="2" fill="#F5F1E8"></rect>'
         '<rect x="28.5" y="21" width="7" height="15" rx="2" fill="#C9A24A"></rect><rect x="39" y="21" width="7" height="27" rx="2" fill="#F5F1E8"></rect></svg>')

page = f"""<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8">
<title>MiraTrade · logo final</title>
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
    <span class="lbl">MIRATRADE · PILARES DEL GRUPO + FLECHA ASCENDENTE</span>
    <div class="cell" style="flex-grow: 1; background: #0B0E13">
      {symbol(340, label="Símbolo de MiraTrade: los tres pilares de Mirandas Group dentro de un marco azul, el central azul; por detrás pasa una flecha verde ascendente que rompe el marco hacia arriba a la derecha")}
    </div>
    <div style="display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 12px">
      <div style="display: flex; flex-direction: column; gap: 3px"><span class="k">Marco y pilares</span><span class="v">el símbolo del grupo tal cual</span></div>
      <div style="display: flex; flex-direction: column; gap: 3px"><span class="k" style="color: #6E9BFF">Pilar central azul</span><span class="v">el color de MiraTrade, según la regla del sistema</span></div>
      <div style="display: flex; flex-direction: column; gap: 3px"><span class="k" style="color: #3FD19B">Flecha por detrás</span><span class="v">el elemento propio de la marca: la subida que sale del marco</span></div>
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
      {symbol(48, sw=1.2)}
      {symbol(32, sw=1.45, head_len=10, half=6)}
      {symbol(16, sw=1.9, head_len=12, half=7.5)}
      <p class="v" style="margin: 0 0 2px; max-width: 330px; color: #9AA4B2">En tamaños pequeños la flecha y el marco engruesan y la punta crece, para que la subida se siga leyendo en la pestaña del navegador.</p>
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
here = Path(__file__).parent
(here / "project" / "Logo-Velas.dc.html").write_text(page, encoding="utf-8")
(here / "miratrade-mark-final.svg").write_text(symbol(512), encoding="utf-8")
(here / "miratrade-mark-16.svg").write_text(symbol(16, sw=1.9, head_len=12, half=7.5), encoding="utf-8")
print("ok")
