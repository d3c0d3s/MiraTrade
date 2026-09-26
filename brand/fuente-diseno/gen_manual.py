"""Mirandas Group identity manual: one 1440x900 artboard per section, on the canvas page "Manual".

Marks come from pilares.py and the lockups from export_brand.py (text outlined from IBM Plex),
so the manual always shows exactly the files that ship. Run with QT_QPA_PLATFORM=offscreen.
"""
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
BRAND = HERE                                      # export_brand.py and pilares.py sit beside this file
sys.path.insert(0, str(BRAND))
import export_brand as eb  # noqa: E402  (loads IBM Plex, pilares and the MiraTrade mark)
import pilares as pil  # noqa: E402

OUT = HERE
NAVY, IVORY, GOLD, GOLD_L, GOLD_HI = "#0E1726", "#F5F1E8", "#C9A24A", "#7F611A", "#E3C477"
PANEL, LINE, MUTED, MONO_G = "#121D30", "#243049", "#A7B0BE", "#5B6472"
INK2 = "#4A5261"                                   # secondary text on ivory
MT_BLUE = "#6E9BFF"
TOTAL = 12


# --------------------------------------------------------------------------- colour maths
def _lin(c):
    c = c / 255
    return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4


def lum(h):
    r, g, b = (int(h[i:i + 2], 16) for i in (1, 3, 5))
    return 0.2126 * _lin(r) + 0.7152 * _lin(g) + 0.0722 * _lin(b)


def contrast(a, b):
    la, lb = sorted((lum(a), lum(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def rgb(h):
    return tuple(int(h[i:i + 2], 16) for i in (1, 3, 5))


def cmyk(h):
    r, g, b = (v / 255 for v in rgb(h))
    k = 1 - max(r, g, b)
    if k >= 1:
        return 0, 0, 0, 100
    return tuple(round(100 * v) for v in ((1 - r - k) / (1 - k), (1 - g - k) / (1 - k), (1 - b - k) / (1 - k), k))


def ratio(a, b):
    return f"{contrast(a, b):.1f}".replace(".", ",") + ":1"


# --------------------------------------------------------------------------- marks
def mark(px, frame_c=GOLD, side=IVORY, centre=GOLD, label=None, extra=""):
    aria = f'role="img" aria-label="{label}"' if label else 'aria-hidden="true"'
    return (f'<svg width="{px}" height="{px}" viewBox="0 0 64 64" fill="none" {aria}>'
            f'{pil.frame(px, frame_c)}{pil.bars(side, centre)}{extra}</svg>')


def light_mark(px, label=None):
    return mark(px, GOLD_L, NAVY, GOLD_L, label)


def app_icon(px, label=None):
    s = eb.group_app_icon(px)
    return inline(s, px, px, label)


def mt_mark(px, bg="#0B0E13", label=None, **kw):
    aria = f'role="img" aria-label="{label}"' if label else 'aria-hidden="true"'
    return (f'<svg width="{px}" height="{px}" viewBox="0 0 64 64" fill="none" {aria}>'
            f'{eb.mt["symbol_body"](px, bg=bg, **kw)}</svg>')


def inline(svg_text, w, h, label=None):
    """Exported SVG (lockups, icons) placed inline at a given display size."""
    aria = f' role="img" aria-label="{label}"' if label else ' aria-hidden="true"'
    s = re.sub(r'^<svg xmlns="http://www.w3.org/2000/svg" width="[\d.]+" height="[\d.]+"',
               f'<svg width="{w}" height="{h}"{aria}', svg_text, count=1)
    return re.sub(r"<(rect|path|polyline|polygon|line|circle)([^>]*)/>", r"<\1\2></\1>", s)


def lockup_h(w, dark=True, label="Firma horizontal de Mirandas Group"):
    s = eb.group_lockup() if dark else eb.group_lockup(NAVY, GOLD_L)
    return inline(s, w, round(w * 120 / 560), label)


def lockup_v(w, dark=True, label="Firma vertical de Mirandas Group"):
    s = eb.group_lockup_v() if dark else eb.group_lockup_v(NAVY, GOLD_L)
    return inline(s, w, round(w * 200 / 360), label)


# --------------------------------------------------------------------------- page shell
HEAD = """<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8">
<title>{title}</title>
<script src="./support.js"></script>
</head>
<body>
<x-dc>
<helmet>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500&amp;family=IBM+Plex+Sans:wght@300;400;500;600;700&amp;family=IBM+Plex+Serif:wght@400;500;600&amp;display=swap" rel="stylesheet">
<style>
body{{margin:0;background:{bg};font-family:'IBM Plex Sans',sans-serif;color:{fg}}}
a{{color:{accent}}}a:hover{{color:{accent_hi}}}
.lbl{{font-family:'IBM Plex Mono',monospace;font-size:12px;letter-spacing:.14em;color:{muted}}}
.h1{{font-family:'IBM Plex Serif',serif;font-size:44px;font-weight:600;line-height:1.1;margin:0}}
.h2{{font-size:17px;font-weight:600;margin:0}}
.p{{font-size:14px;line-height:1.6;margin:0;color:{body}}}
.small{{font-size:12.5px;line-height:1.55;margin:0;color:{body}}}
.mono{{font-family:'IBM Plex Mono',monospace}}
.card{{border:1px solid {line};border-radius:14px;background:{panel}}}
</style>
</helmet>
"""
TAIL = """</x-dc>
<script type="text/x-dc" data-dc-script data-props='{"$preview":{"width":1440,"height":900}}'>
class Component extends DCLogic {
  renderVals() { return {}; }
}
</script>
</body>
</html>
"""
DARK = dict(bg=NAVY, fg=IVORY, accent=GOLD, accent_hi=GOLD_HI, muted=MUTED, body="#C9CFDA",
            line=LINE, panel=PANEL)
LIGHT = dict(bg=IVORY, fg=NAVY, accent=GOLD_L, accent_hi="#5E4712", muted=INK2, body="#2B3342",
             line="#DDD5C4", panel="#FBF8F1")


def board(num, section, title, lead, content, theme=DARK, header=True):
    t = theme
    top = ""
    if header:
        top = (f'<div style="display: flex; justify-content: space-between; align-items: center">'
               f'<span class="lbl">MIRANDAS GROUP · MANUAL DE IDENTIDAD</span>'
               f'<span class="lbl">{num:02d} / {TOTAL:02d} · {section.upper()}</span></div>'
               f'<div style="display: flex; flex-direction: column; gap: 10px; max-width: 980px">'
               f'<h1 class="h1">{title}</h1><p class="p" style="font-size: 16px">{lead}</p></div>')
    html = (HEAD.format(title=f"Mirandas Group · {num:02d} {section}", **t)
            + f'<div style="width: 1440px; height: 900px; box-sizing: border-box; padding: 40px 56px 44px; '
              f'background: {t["bg"]}; color: {t["fg"]}; display: flex; flex-direction: column; gap: 26px; overflow: hidden">'
            + top + content + "</div>\n" + TAIL)
    return re.sub(r"<(rect|path|polyline|polygon|line|circle|text)([^>]*?)\s*/>", r"<\1\2></\1>", html)


def lbl(text, style=""):
    return f'<span class="lbl" style="{style}">{text}</span>'


def col(*items, gap=12, style=""):
    return f'<div style="display: flex; flex-direction: column; gap: {gap}px; {style}">{"".join(items)}</div>'


def row(*items, gap=16, style=""):
    return f'<div style="display: flex; gap: {gap}px; {style}">{"".join(items)}</div>'


def grid(n, *items, gap=16, style=""):
    return (f'<div style="display: grid; grid-template-columns: repeat({n}, minmax(0, 1fr)); gap: {gap}px; {style}">'
            f'{"".join(items)}</div>')


def cross(color="#C4302B"):
    return (f'<svg width="22" height="22" viewBox="0 0 24 24" fill="none" aria-hidden="true">'
            f'<circle cx="12" cy="12" r="10" stroke="{color}" stroke-width="2"></circle>'
            f'<path d="M8.5 8.5 L15.5 15.5 M15.5 8.5 L8.5 15.5" stroke="{color}" stroke-width="2" stroke-linecap="round"></path></svg>')


def tick(color="#1F7A4D"):
    return (f'<svg width="22" height="22" viewBox="0 0 24 24" fill="none" aria-hidden="true">'
            f'<circle cx="12" cy="12" r="10" stroke="{color}" stroke-width="2"></circle>'
            f'<path d="M7.5 12.5 L10.5 15.5 L16.5 9" stroke="{color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"></path></svg>')


# --------------------------------------------------------------------------- 01 Portada
SECTIONS = ["Portada", "Esencia", "Símbolo", "Construcción", "Protección y tamaños", "Versiones",
            "Firma", "Color", "Tipografía", "Arquitectura de marcas", "Usos incorrectos", "Aplicaciones"]


def p01():
    idx = "".join(f'<div style="display: flex; gap: 14px; align-items: baseline; padding: 7px 0; border-bottom: 1px solid {LINE}">'
                  f'<span class="mono" style="font-size: 12px; color: {GOLD}">{i:02d}</span>'
                  f'<span style="font-size: 15px">{s}</span></div>' for i, s in enumerate(SECTIONS[1:], 2))
    left = col(
        lbl("MANUAL DE IDENTIDAD · VERSIÓN 1.0 · SEPTIEMBRE 2026"),
        f'<div style="flex-grow: 1; display: flex; flex-direction: column; justify-content: center; gap: 36px">'
        f'{lockup_v(520)}'
        f'<p class="p" style="font-size: 18px; max-width: 520px; color: #C9CFDA">Sistema <strong style="color: {IVORY}">Pilares</strong>: '
        f'la base común de la que nacen el logo del grupo y el de cada una de sus marcas.</p></div>',
        gap=0, style="flex-grow: 1")
    right = col(lbl("CONTENIDO"), f'<div style="display: flex; flex-direction: column">{idx}</div>',
                f'<p class="small" style="margin-top: auto; color: {MUTED}">Archivos de marca: carpeta '
                f'<span class="mono">Brand/Mirandas Group/</span> · fuentes en <span class="mono">Brand/Tipografia/IBM Plex/</span></p>',
                gap=14, style="width: 420px")
    return board(1, "Portada", "", "", row(left, right, gap=80, style="flex-grow: 1; padding: 20px 0 0"),
                 header=False)


# --------------------------------------------------------------------------- 02 Esencia
def p02():
    traits = [("Solidez", GOLD, "Responde quien firma. Un apellido detrás de cada negocio.",
               "Frases cortas y afirmaciones que se pueden comprobar."),
              ("Tecnología", MT_BLUE, "Datos, software y nube como herramientas del día a día.",
               "Precisión: cifras exactas, fuentes citadas, sin jerga innecesaria."),
              ("Familia", IVORY, "Un grupo familiar, no una marca de catálogo.",
               "Trato cercano y directo; hablamos en primera persona del plural."),
              ("Premium", GOLD_HI, "Sobrio y cuidado. La calidad se nota en el detalle, no en el brillo.",
               "Pocas palabras, bien elegidas. Nada de superlativos vacíos.")]
    cards = "".join(
        f'<div class="card" style="padding: 22px; display: flex; flex-direction: column; gap: 12px">'
        f'<span style="font-family: \'IBM Plex Serif\', serif; font-size: 26px; font-weight: 600; color: {c}">{n}</span>'
        f'<p class="p">{d}</p><span class="lbl" style="margin-top: 6px">CÓMO SUENA</span><p class="small">{v}</p></div>'
        for n, c, d, v in traits)
    who = col(lbl("QUIÉNES SOMOS"),
              f'<p class="p" style="font-size: 17px; color: {IVORY}">Mirandas Group es el grupo de la familia Miranda. '
              'Reúne sus negocios bajo una misma firma: trading y datos, tecnología, y bienestar.</p>',
              f'<p class="p">Cada negocio tiene nombre, color y público propios. El grupo aporta lo que no cambia: '
              'la forma del símbolo, la tipografía, la paleta base y el respaldo «a Mirandas Group company».</p>',
              gap=12, style="flex: 1")
    voice = col(lbl("TONO DE VOZ"),
                row(col(row(tick("#3FD19B"), '<span class="h2">Así sí</span>', gap=8, style="align-items: center"),
                        '<p class="small">«Probamos la estrategia con cinco años de datos.»</p>'
                        '<p class="small">«Esto es lo que sabemos y esto lo que no.»</p>', gap=8, style="flex: 1"),
                    col(row(cross("#FF8A80"), '<span class="h2">Así no</span>', gap=8, style="align-items: center"),
                        '<p class="small">«¡La mejor plataforma del mundo, resultados garantizados!»</p>'
                        '<p class="small">«Soluciones disruptivas de siguiente nivel.»</p>', gap=8, style="flex: 1"),
                    gap=24),
                gap=14, style="flex: 1")
    content = col(row(who, voice, gap=56), lbl("PERSONALIDAD · UNA MEZCLA DE CUATRO RASGOS"), grid(4, cards, gap=14),
                  gap=22, style="flex-grow: 1")
    return board(2, "Esencia", "Esencia de marca",
                 "Qué es Mirandas Group, cómo se comporta la marca y cómo habla. Es la base para decidir todo lo demás.",
                 content)


# --------------------------------------------------------------------------- 03 Símbolo
def p03():
    hero = (f'<div class="card" style="flex: 0 0 560px; display: flex; align-items: center; justify-content: center; background: #0B1220">'
            f'{mark(340, label="Símbolo de Mirandas Group")}</div>')
    parts = [("El marco", "Un cuadrado de esquinas redondeadas: la casa, lo que el grupo protege y comparte. Es igual en todas las marcas."),
             ("Los pilares laterales", "Dos pilares iguales, en marfil: los apoyos firmes. Con el central forman la M de Miranda."),
             ("El pilar central", "Más corto y colgando desde arriba, en oro. Es la pieza que cambia de color en cada marca del grupo."),
             ("La lectura doble", "Columna de un edificio y barra de un gráfico: solidez y datos, los dos mundos del grupo.")]
    items = "".join(f'<div style="display: flex; gap: 16px; padding: 14px 0; border-bottom: 1px solid {LINE}">'
                    f'<span class="mono" style="font-size: 13px; color: {GOLD}; width: 22px">{i}</span>'
                    f'<div style="display: flex; flex-direction: column; gap: 4px"><span class="h2">{t}</span><p class="p">{d}</p></div></div>'
                    for i, (t, d) in enumerate(parts, 1))
    right = col(lbl("QUÉ SIGNIFICA"), f'<div>{items}</div>',
                row(mark(64), mark(40), mark(24), mark(16), gap=28, style="align-items: flex-end; margin-top: auto"),
                '<p class="small">El símbolo se reconoce igual a 16 px que en una fachada.</p>', gap=12, style="flex: 1")
    return board(3, "Símbolo", "El símbolo: tres pilares",
                 "Tres pilares dentro de un marco forman una M. Es el signo del grupo y el punto de partida de cada marca.",
                 row(hero, right, gap=48, style="flex-grow: 1"))


# --------------------------------------------------------------------------- 04 Construcción
def construction_svg(w):
    g = []
    for i in range(0, 65, 2):
        c = "#2A3854" if i % 8 == 0 else "#18233A"
        g.append(f'<line x1="{i}" y1="0" x2="{i}" y2="64" stroke="{c}" stroke-width="0.12"></line>')
        g.append(f'<line x1="0" y1="{i}" x2="64" y2="{i}" stroke="{c}" stroke-width="0.12"></line>')
    body = pil.frame(96, GOLD) + pil.bars(IVORY, GOLD)
    a = "#6E9BFF"

    def dim(x1, y1, x2, y2, tag, tx, ty):
        return (f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{a}" stroke-width="0.3"></line>'
                + (f'<line x1="{x1}" y1="{y1 - 0.9}" x2="{x1}" y2="{y1 + 0.9}" stroke="{a}" stroke-width="0.3"></line>'
                   f'<line x1="{x2}" y1="{y2 - 0.9}" x2="{x2}" y2="{y2 + 0.9}" stroke="{a}" stroke-width="0.3"></line>'
                   if y1 == y2 else
                   f'<line x1="{x1 - 0.9}" y1="{y1}" x2="{x1 + 0.9}" y2="{y1}" stroke="{a}" stroke-width="0.3"></line>'
                   f'<line x1="{x2 - 0.9}" y1="{y2}" x2="{x2 + 0.9}" y2="{y2}" stroke="{a}" stroke-width="0.3"></line>')
                + f'<circle cx="{tx}" cy="{ty}" r="1.55" fill="{a}"></circle>'
                  f'<text x="{tx}" y="{ty + 0.62}" text-anchor="middle" font-family="IBM Plex Mono, monospace" '
                  f'font-size="1.75" font-weight="500" fill="{NAVY}">{tag}</text>')
    d = [dim(7, 3.2, 57, 3.2, "A", 32, 3.2),
         dim(62, 21, 62, 48, "B", 62, 34.5),
         dim(18, 51.5, 25, 51.5, "C", 21.5, 54.2),
         dim(25, 44, 28.5, 44, "D", 26.75, 41),
         dim(37.25, 21, 37.25, 36, "E", 37.25, 39),
         dim(14, 9, 14, 21, "F", 14, 15),
         dim(14, 48, 14, 59, "G", 14, 53.5),
         f'<path d="M7 22 A13 13 0 0 1 20 9" stroke="{a}" stroke-width="0.3" stroke-dasharray="0.8 0.6"></path>'
         f'<circle cx="11" cy="13" r="1.55" fill="{a}"></circle><text x="11" y="13.62" text-anchor="middle" '
         f'font-family="IBM Plex Mono, monospace" font-size="1.75" font-weight="500" fill="{NAVY}">H</text>']
    return (f'<svg width="{w}" height="{w}" viewBox="0 0 64 64" fill="none" role="img" '
            f'aria-label="Construcción del símbolo sobre una retícula de 64 unidades">{"".join(g)}{body}{"".join(d)}</svg>')


def p04():
    legend = [("A", "Marco", "50 × 50 u"), ("H", "Radio de las esquinas", "13 u"),
              ("·", "Grosor del marco", "3,4 u (ver tamaños pequeños)"),
              ("C", "Ancho de cada pilar", "7 u · esquinas de 2 u"), ("D", "Separación entre pilares", "3,5 u"),
              ("B", "Alto de los pilares laterales", "27 u"), ("E", "Alto del pilar central", "15 u, cuelga desde arriba"),
              ("F", "Del marco a los pilares, arriba", "12 u"), ("G", "De los pilares al marco, abajo", "11 u"),
              ("·", "Margen lateral interior", "11 u a cada lado")]
    rows_ = "".join(f'<div style="display: grid; grid-template-columns: 30px 1fr auto; gap: 10px; padding: 9px 0; border-bottom: 1px solid {LINE}; align-items: baseline">'
                    f'<span class="mono" style="font-size: 13px; color: {MT_BLUE}">{k}</span><span style="font-size: 14px">{n}</span>'
                    f'<span class="mono" style="font-size: 13px; color: {GOLD_HI}">{v}</span></div>' for k, n, v in legend)
    right = col(lbl("MEDIDAS · RETÍCULA DE 64 UNIDADES"), f'<div>{rows_}</div>',
                f'<div class="card" style="padding: 16px 18px; margin-top: auto"><p class="small"><strong style="color: {IVORY}">Regla del sistema.</strong> '
                'Estas medidas son iguales en todas las marcas del grupo. Una marca nueva solo cambia colores y añade su elemento '
                'propio; nunca redibuja el marco ni los pilares. Fuente única: <span class="mono">fuente-diseno/pilares.py</span>.</p></div>',
                gap=12, style="flex: 1")
    left = (f'<div class="card" style="flex: 0 0 600px; display: flex; align-items: center; justify-content: center; background: #0B1220">'
            f'{construction_svg(560)}</div>')
    return board(4, "Construcción", "Construcción y retícula",
                 "El símbolo se dibuja sobre una retícula de 64 × 64 unidades. Las proporciones son fijas.",
                 row(left, right, gap=48, style="flex-grow: 1; min-height: 0"))


# --------------------------------------------------------------------------- 05 Protección y tamaños
def clear_svg(w):
    x = 15
    fx0, fy0, fx1, fy1 = 5.3, 7.3, 58.7, 60.7
    body = pil.frame(96, GOLD) + pil.bars(IVORY, GOLD)
    a = MT_BLUE
    zone = (f'<rect x="{fx0 - x}" y="{fy0 - x}" width="{fx1 - fx0 + 2 * x}" height="{fy1 - fy0 + 2 * x}" '
            f'fill="#132441" stroke="{a}" stroke-width="0.35" stroke-dasharray="1.2 0.9"></rect>'
            f'<rect x="{fx0}" y="{fy0}" width="{fx1 - fx0}" height="{fy1 - fy0}" fill="{NAVY}" stroke="{a}" stroke-width="0.25"></rect>')
    marks = ""
    for (bx, by) in ((fx0 - x + 4, fy0 - x + 0.0), (fx1 + 4, fy1 - 15), ):
        pass
    unit = (f'<rect x="{fx1 + 4}" y="{fy0}" width="7" height="15" rx="2" fill="{GOLD}" opacity="0.55"></rect>'
            f'<rect x="{fx0 + 20}" y="{fy1 + 4}" width="15" height="7" rx="2" fill="{GOLD}" opacity="0.55"></rect>'
            f'<text x="{fx1 + 7.5}" y="{fy0 + 20}" text-anchor="middle" font-family="IBM Plex Mono, monospace" font-size="3" fill="{a}">x</text>'
            f'<text x="{fx0 + 27.5}" y="{fy1 + 14.5}" text-anchor="middle" font-family="IBM Plex Mono, monospace" font-size="3" fill="{a}">x</text>')
    vb = f"{fx0 - x - 2} {fy0 - x - 2} {fx1 - fx0 + 2 * x + 4} {fy1 - fy0 + 2 * x + 4}"
    return (f'<svg width="{w}" height="{w}" viewBox="{vb}" fill="none" role="img" '
            f'aria-label="Área de protección: x alrededor del marco, x igual a la altura del pilar central">{zone}{body}{unit}</svg>')


def p05():
    sizes = [(128, "≥ 64 px", "3,4"), (48, "40–63 px", "4,2"), (32, "24–39 px", "5,0"), (16, "< 24 px", "6,0")]
    cells = "".join(f'<div class="card" style="padding: 18px 10px; display: flex; flex-direction: column; align-items: center; gap: 10px">'
                    f'<div style="height: 132px; display: flex; align-items: center">{mark(s)}</div>'
                    f'<span class="mono" style="font-size: 13px; color: {IVORY}">{s} px</span>'
                    f'<span class="small" style="text-align: center">{r}<br>marco {t} u</span></div>' for s, r, t in sizes)
    mins = [("Símbolo", "16 px", "6 mm"), ("Firma horizontal", "140 px de ancho", "35 mm"),
            ("Firma vertical", "96 px de ancho", "22 mm"), ("Icono de app", "16 px (favicon)", "—")]
    mrows = "".join(f'<div style="display: grid; grid-template-columns: 1fr 140px 80px; gap: 10px; padding: 9px 0; border-bottom: 1px solid {LINE}">'
                    f'<span style="font-size: 14px">{n}</span><span class="mono" style="font-size: 13px; color: {GOLD_HI}">{d}</span>'
                    f'<span class="mono" style="font-size: 13px; color: {GOLD_HI}">{p}</span></div>' for n, d, p in mins)
    left = col(lbl("ÁREA DE PROTECCIÓN"),
               f'<div class="card" style="display: flex; align-items: center; justify-content: center; padding: 14px; background: #0B1220">{clear_svg(330)}</div>',
               '<p class="small"><strong style="color: #F5F1E8">x = la altura del pilar central</strong> (15 u). Ningún texto, borde '
               'o imagen entra en esa zona alrededor del marco. En las firmas se mide igual, desde el borde del conjunto.</p>',
               gap=12, style="flex: 0 0 380px")
    right = col(lbl("AJUSTE ÓPTICO POR TAMAÑO · EL MARCO ENGROSA AL REDUCIR"), grid(4, cells, gap=12),
                '<p class="small">Por debajo de 64 px usa los PNG de su tamaño (<span class="mono">simbolo/png/…-16.png</span>, -32, -48): '
                'ya llevan el marco engrosado. No reduzcas el archivo grande.</p>',
                lbl("TAMAÑOS MÍNIMOS", "margin-top: 8px"),
                f'<div style="display: grid; grid-template-columns: 1fr 140px 80px; gap: 10px; padding-bottom: 6px">'
                f'<span class="lbl">PIEZA</span><span class="lbl">PANTALLA</span><span class="lbl">IMPRESO</span></div>'
                f'<div style="margin-top: -12px">{mrows}</div>', gap=12, style="flex: 1")
    return board(5, "Protección y tamaños", "Área de protección y tamaños",
                 "El símbolo necesita aire para leerse con autoridad, y trazos más gruesos cuando es pequeño.",
                 row(left, right, gap=48, style="flex-grow: 1"))


# --------------------------------------------------------------------------- 06 Versiones
def p06():
    vs = [("Principal", "Sobre medianoche. Es la versión por defecto.", NAVY, mark(150, label="Versión principal"), LINE, IVORY),
          ("Sobre claro", "Sobre marfil o blanco. El oro se oscurece a #7F611A.", IVORY, light_mark(150, "Versión sobre claro"), "#DDD5C4", NAVY),
          ("Monocromo claro", "Una tinta clara sobre fondos oscuros o fotos oscuras.", "#1A2233",
           mark(150, IVORY, IVORY, "#A7B0BE", "Versión monocromo claro"), LINE, IVORY),
          ("Monocromo oscuro", "Una tinta oscura: sellos, grabado, fax, documentos en B/N.", "#FFFFFF",
           mark(150, NAVY, NAVY, "#5B6472", "Versión monocromo oscuro"), "#DDD5C4", NAVY),
          ("Icono de app", "Baldosa medianoche; símbolo al 81,25 %. Favicon, redes, escritorio.", "#0B1220",
           app_icon(150, "Icono de app"), LINE, IVORY)]
    cells = "".join(f'<div style="display: flex; flex-direction: column; gap: 12px">'
                    f'<div style="height: 250px; border-radius: 14px; background: {bg}; border: 1px solid {bd}; display: flex; align-items: center; justify-content: center">{m}</div>'
                    f'<span class="h2">{n}</span><p class="small">{d}</p></div>' for n, d, bg, m, bd, _ in vs)
    files = ('<p class="small">Archivos: <span class="mono">simbolo/mirandas-group-simbolo[-sobre-claro | -monocromo-claro | -monocromo-oscuro].svg</span> '
             'y <span class="mono">icono/mirandas-group-icono-app.svg</span>, <span class="mono">mirandas-group.ico</span>. '
             'Cada uno con PNG de 16 a 1024 px en su carpeta <span class="mono">png/</span>.</p>')
    rule = (f'<div class="card" style="padding: 16px 18px"><p class="small"><strong style="color: {IVORY}">Elegir versión:</strong> '
            'fondo oscuro → principal; fondo claro → sobre claro; una sola tinta o foto → monocromo; espacio cuadrado '
            'pequeño o redes → icono de app. Si el fondo no da un contraste claro, cámbialo, no el símbolo.</p></div>')
    return board(6, "Versiones", "Versiones del símbolo",
                 "Cinco versiones cubren cualquier fondo y soporte. No hay otras: no se crean variantes nuevas.",
                 col(grid(5, cells, gap=16), rule, files, gap=18))


# --------------------------------------------------------------------------- 07 Firma
def p07():
    h_dark = (f'<div style="height: 200px; border-radius: 14px; background: {NAVY}; border: 1px solid {LINE}; display: flex; align-items: center; padding-left: 48px">'
              f'{lockup_h(560)}</div>')
    h_light = (f'<div style="height: 200px; border-radius: 14px; background: {IVORY}; display: flex; align-items: center; padding-left: 48px">'
               f'{lockup_h(560, False, "Firma horizontal sobre claro")}</div>')
    v_dark = (f'<div style="height: 200px; border-radius: 14px; background: {NAVY}; border: 1px solid {LINE}; display: flex; align-items: center; justify-content: center">'
              f'{lockup_v(300)}</div>')
    v_light = (f'<div style="height: 200px; border-radius: 14px; background: {IVORY}; display: flex; align-items: center; justify-content: center">'
               f'{lockup_v(300, False, "Firma vertical sobre claro")}</div>')
    left = col(lbl("FIRMA HORIZONTAL · PRINCIPAL"), h_dark, h_light, gap=12, style="flex: 1.6")
    right = col(lbl("FIRMA VERTICAL · ESPACIOS ESTRECHOS"), v_dark, v_light, gap=12, style="flex: 1")
    rules = grid(3,
                 col('<span class="h2">Composición fija</span>', '<p class="small">MIRANDAS en IBM Plex Serif SemiBold con espaciado '
                     'amplio; GROUP en Plex Sans, en oro, más espaciado aún. No se recompone: usa siempre los archivos.</p>', gap=6),
                 col('<span class="h2">Cuándo usar cada una</span>', '<p class="small">Horizontal: cabeceras, web, documentos, firmas de correo. '
                     'Vertical: portadas, tarjetas, redes y espacios cuadrados. Símbolo solo: cuando la marca ya se nombra cerca.</p>', gap=6),
                 col('<span class="h2">Archivos</span>', '<p class="small"><span class="mono">firma/mirandas-group-firma-horizontal[-sobre-claro]</span> '
                     'y <span class="mono">-vertical[-sobre-claro]</span>, en SVG y PNG 1×/2×/4×. El texto va en trazos: no necesita la fuente.</p>', gap=6),
                 gap=28)
    return board(7, "Firma", "La firma: símbolo y nombre",
                 "La firma une el símbolo con el nombre del grupo. Hay dos composiciones, cada una para fondo oscuro y claro.",
                 col(row(left, right, gap=20), rules, gap=26))


# --------------------------------------------------------------------------- 08 Color
def p08():
    prim = [("Medianoche", NAVY, "Fondo principal, texto sobre claro"), ("Marfil", IVORY, "Texto sobre oscuro, fondos claros"),
            ("Oro Miranda", GOLD, "Pilar central, marco, acentos sobre oscuro"), ("Oro sobre claro", GOLD_L, "El oro cuando el fondo es claro")]
    sup = [("Panel", PANEL, "Tarjetas y superficies"), ("Línea", LINE, "Bordes y divisores"),
           ("Texto secundario", MUTED, "Notas sobre oscuro"), ("Gris tinta", MONO_G, "Monocromos, notas sobre claro"),
           ("Oro claro", GOLD_HI, "Enlaces activos, resaltes")]

    def chip(n, h, use, big):
        r, g, b = rgb(h)
        c, m, y, k = cmyk(h)
        on = f'{ratio(h, NAVY)} sobre medianoche' if h not in (NAVY, PANEL, LINE) else f'{ratio(h, IVORY)} con marfil'
        border = f"border: 1px solid {LINE};" if h in (NAVY, PANEL) else ""
        return (f'<div style="display: flex; flex-direction: column; gap: 8px">'
                f'<div style="height: {150 if big else 76}px; border-radius: 12px; background: {h}; {border}"></div>'
                f'<span class="h2" style="font-size: {16 if big else 14}px">{n}</span>'
                f'<span class="mono" style="font-size: 12px; line-height: 1.6; color: #C9CFDA">{h}<br>RGB {r} {g} {b}<br>CMYK {c} {m} {y} {k}</span>'
                f'<span class="small" style="font-size: 12px">{use}<br><span style="color: {MUTED}">{on}</span></span></div>')
    bar = (f'<div style="display: flex; height: 28px; border-radius: 8px; overflow: hidden; border: 1px solid {LINE}">'
           f'<div style="flex: 60; background: {NAVY}"></div><div style="flex: 25; background: {IVORY}"></div>'
           f'<div style="flex: 10; background: {LINE}"></div><div style="flex: 5; background: {GOLD}"></div></div>'
           f'<div style="display: flex; justify-content: space-between" class="mono"><span style="font-size: 12px; color: {MUTED}">60 medianoche</span>'
           f'<span style="font-size: 12px; color: {MUTED}">25 marfil · 10 apoyo · 5 oro</span></div>')
    brand = (f'<div class="card" style="padding: 14px 16px; display: flex; gap: 14px; align-items: center">{mt_mark(44, bg=PANEL)}'
             f'<p class="small">Cada marca añade <strong style="color: {IVORY}">un color propio</strong> para su pilar central '
             f'(MiraTrade: azul <span class="mono">{MT_BLUE}</span>). El oro es solo del grupo.</p></div>')
    note = ('<p class="small" style="color: #A7B0BE">CMYK calculado desde RGB como referencia: pide a la imprenta una prueba '
            'de color. Pantone: [PENDIENTE DE PRUEBA DE IMPRESIÓN]. Contraste según WCAG 2.1; texto normal ≥ 4,5:1.</p>')
    content = col(lbl("PRINCIPALES"), grid(4, *(chip(*p, True) for p in prim), gap=16),
                  row(col(lbl("APOYO"), grid(5, *(chip(*s, False) for s in sup), gap=12), gap=12, style="flex: 1.7"),
                      col(lbl("PROPORCIÓN DE USO (%)"), bar, brand, note, gap=10, style="flex: 1"), gap=36),
                  gap=12)
    return board(8, "Color", "Color",
                 "Una paleta sobria: medianoche y marfil hacen casi todo el trabajo; el oro aparece poco y siempre con intención.",
                 content)


# --------------------------------------------------------------------------- 09 Tipografía
def p09():
    fam = [("IBM Plex Serif", "'IBM Plex Serif', serif", "El apellido y los titulares", "Regular 400 · Medium 500 · SemiBold 600", "Georgia"),
           ("IBM Plex Sans", "'IBM Plex Sans', sans-serif", "Nombres de producto y todo el texto", "Light 300 · Regular 400 · Medium 500 · SemiBold 600 · Bold 700", "Segoe UI, Arial"),
           ("IBM Plex Mono", "'IBM Plex Mono', monospace", "Datos, cifras, etiquetas y código", "Regular 400 · Medium 500", "Consolas")]
    cards = "".join(f'<div class="card" style="padding: 20px; display: flex; flex-direction: column; gap: 10px">'
                    f'<span style="font-family: {ff}; font-size: 40px; line-height: 1">Aa Mm 0123</span>'
                    f'<span class="h2">{n}</span><p class="small">{u}</p>'
                    f'<span class="mono" style="font-size: 11.5px; color: {MUTED}">{w}<br>Alternativa: {fb}</span></div>'
                    for n, ff, u, w, fb in fam)
    scale = [("Titular grande", "'IBM Plex Serif', serif", 48, 600, "Construimos sobre pilares firmes", "Serif 600 · 48/52"),
             ("Titular", "'IBM Plex Serif', serif", 32, 500, "Un grupo, varias marcas", "Serif 500 · 32/40"),
             ("Subtítulo", "'IBM Plex Sans', sans-serif", 20, 600, "Trading y datos, tecnología, bienestar", "Sans 600 · 20/28"),
             ("Texto", "'IBM Plex Sans', sans-serif", 16, 400, "Cada negocio conserva su nombre y su color; el grupo aporta la base común.", "Sans 400 · 16/26"),
             ("Etiqueta", "'IBM Plex Mono', monospace", 12, 500, "A MIRANDAS GROUP COMPANY", "Mono 500 · 12 · espaciado 0,14 em")]
    srows = "".join(f'<div style="display: grid; grid-template-columns: 130px 1fr 210px; gap: 16px; align-items: baseline; padding: 10px 0; border-bottom: 1px solid {LINE}">'
                    f'<span class="lbl">{n.upper()}</span>'
                    f'<span style="font-family: {ff}; font-size: {px}px; font-weight: {wt}; line-height: 1.2; {"letter-spacing: 0.14em;" if px == 12 else ""} '
                    f'white-space: nowrap; overflow: hidden; text-overflow: ellipsis">{s}</span>'
                    f'<span class="mono" style="font-size: 12px; color: {GOLD_HI}">{spec}</span></div>' for n, ff, px, wt, s, spec in scale)
    content = col(grid(3, cards, gap=16), lbl("ESCALA", "margin-top: 6px"), f'<div>{srows}</div>',
                  '<p class="small" style="color: #A7B0BE">Licencia SIL Open Font License: uso comercial libre, también en web y apps. '
                  'Archivos en <span class="mono">Brand/Tipografia/IBM Plex/</span>; en web, Google Fonts. «Construimos sobre pilares firmes» es una frase de ejemplo, no un lema aprobado.</p>',
                  gap=14)
    return board(9, "Tipografía", "Tipografía: una superfamilia",
                 "IBM Plex tiene tres ramas que conviven sin esfuerzo. El grupo firma en serif; las marcas hablan en sans; los datos van en mono.",
                 content)


# --------------------------------------------------------------------------- 10 Arquitectura
def p10():
    grp = col(mark(96, label="Mirandas Group"), '<span class="h2">Mirandas Group</span>',
              f'<span class="small">Pilar central en oro</span>', gap=8, style="align-items: center")
    mt = col(mt_mark(96, bg=PANEL, label="MiraTrade"), '<span class="h2">MiraTrade</span>',
             f'<span class="small">Pilar azul + flecha propia</span>', gap=8, style="align-items: center")
    nxt = col(mark(96, "#8A93A3", IVORY, "#8A93A3", "Plantilla para una marca nueva"),
              '<span class="h2">[PRÓXIMA MARCA]</span>', '<span class="small">[su color] + [su elemento]</span>',
              gap=8, style="align-items: center; opacity: 0.85")
    rr = col(f'<div style="width: 96px; height: 96px; border-radius: 16px; border: 1.5px dashed {MUTED}; display: flex; align-items: center; '
             f'justify-content: center; text-align: center"><span class="mono" style="font-size: 11px; color: {MUTED}">MANUAL<br>PROPIO</span></div>',
             '<span class="h2">Ripped &amp; Renew</span>', '<span class="small">Conserva su marca; añade el respaldo</span>',
             gap=8, style="align-items: center")
    tree = (f'<div class="card" style="padding: 24px 28px; display: flex; flex-direction: column; gap: 18px; background: #0B1220">'
            f'<div style="display: flex; justify-content: center">{grp}</div>'
            f'<div style="height: 1px; background: {LINE}; margin: 0 60px"></div>'
            f'<div style="display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 10px">{mt}{nxt}{rr}</div></div>')
    rules = [("1", "Marco y pilares idénticos", "Mismas medidas que el grupo (página 04). Nunca se redibujan."),
             ("2", "Un color propio", "Solo el pilar central y el marco toman el color de la marca. Los laterales siguen en marfil."),
             ("3", "Un único elemento propio", "Opcional. Pasa por detrás o alrededor de los pilares, nunca encima (la flecha de MiraTrade)."),
             ("4", "Nombre en IBM Plex Sans", "El nombre de cada marca va en Plex Sans; la serif queda para el grupo."),
             ("5", "Respaldo del grupo", "«a Mirandas Group company» con el símbolo pequeño del grupo, bajo el nombre.")]
    rl = "".join(f'<div style="display: flex; gap: 14px; padding: 10px 0; border-bottom: 1px solid {LINE}">'
                 f'<span class="mono" style="font-size: 13px; color: {GOLD}">{n}</span>'
                 f'<div style="display: flex; flex-direction: column; gap: 3px"><span class="h2" style="font-size: 15px">{t}</span><p class="small">{d}</p></div></div>'
                 for n, t, d in rules)
    endorse = (f'<div style="display: flex; gap: 14px">'
               f'<div style="flex: 1; height: 120px; border-radius: 12px; background: #0B0E13; display: flex; align-items: center; justify-content: center">'
               f'{inline(eb.mt_lockup_endorsed(True), 330, 80, "MiraTrade, a Mirandas Group company")}</div>'
               f'<div style="flex: 1; height: 120px; border-radius: 12px; background: #F5F7FB; display: flex; align-items: center; justify-content: center">'
               f'{inline(eb.mt_lockup_endorsed(False), 330, 80, "MiraTrade sobre claro, con respaldo")}</div></div>')
    left = col(lbl("MODELO: MARCAS RESPALDADAS"), tree, lbl("RESPALDO · EJEMPLO REAL", "margin-top: 6px"), endorse,
               '<p class="small" style="color: #A7B0BE">En español, cuando el contexto lo pida: «una empresa de Mirandas Group».</p>',
               gap=12, style="flex: 1.25")
    right = col(lbl("CÓMO NACE UNA MARCA DEL GRUPO"), f'<div>{rl}</div>', gap=8, style="flex: 1")
    return board(10, "Arquitectura de marcas", "Arquitectura de marcas",
                 "Cada negocio tiene identidad propia, pero todas nacen del mismo símbolo y llevan la firma del grupo.",
                 row(left, right, gap=44, style="flex-grow: 1"))


# --------------------------------------------------------------------------- 11 Usos incorrectos
def p11():
    L = dict(frame_c=GOLD_L, side=NAVY, centre=GOLD_L)
    base = pil.frame(96, GOLD_L)
    bad = [
        ("No deformar", f'<svg width="170" height="110" viewBox="0 0 64 64" preserveAspectRatio="none" fill="none" aria-hidden="true">{base}{pil.bars(NAVY, GOLD_L)}</svg>'),
        ("No girar", f'<svg width="120" height="120" viewBox="0 0 64 64" fill="none" aria-hidden="true"><g transform="rotate(-14 32 34)">{base}{pil.bars(NAVY, GOLD_L)}</g></svg>'),
        ("No cambiar las proporciones", f'<svg width="120" height="120" viewBox="0 0 64 64" fill="none" aria-hidden="true">{base}'
                                        f'<rect x="16" y="18" width="9" height="32" rx="2" fill="{NAVY}"></rect><rect x="28.5" y="18" width="7" height="32" rx="2" fill="{GOLD_L}"></rect>'
                                        f'<rect x="39" y="26" width="9" height="24" rx="2" fill="{NAVY}"></rect></svg>'),
        ("No reordenar los pilares", f'<svg width="120" height="120" viewBox="0 0 64 64" fill="none" aria-hidden="true">{base}'
                                     f'<rect x="18" y="21" width="7" height="27" rx="2" fill="{NAVY}"></rect><rect x="28.5" y="33" width="7" height="15" rx="2" fill="{GOLD_L}"></rect>'
                                     f'<rect x="39" y="21" width="7" height="27" rx="2" fill="{NAVY}"></rect></svg>'),
        ("No cambiar los colores", mark(120, "#B3261E", "#2F5BC8", "#3FD19B")),
        ("No añadir sombras ni efectos", f'<svg width="120" height="120" viewBox="0 0 64 64" fill="none" aria-hidden="true">'
                                         f'<g transform="translate(3 3)" opacity="0.35"><rect x="7" y="9" width="50" height="50" rx="13" stroke="#000" stroke-width="3.4"></rect>'
                                         f'{pil.bars("#000", "#000")}</g>{base}{pil.bars(NAVY, GOLD_L)}</svg>'),
        ("No usar solo contornos", f'<svg width="120" height="120" viewBox="0 0 64 64" fill="none" aria-hidden="true">{base}'
                                   + "".join(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="2" stroke="{NAVY}" stroke-width="1.2"></rect>' for x, y, w, h in pil.BARS)
                                   + '</svg>'),
        ("No usar sobre fondos sin contraste", None),
    ]
    cells = []
    for n, svg_ in bad:
        if svg_ is None:
            tile = (f'<div style="width: 100%; height: 170px; border-radius: 12px; background: #A38B5A; display: flex; align-items: center; justify-content: center">'
                    f'{mark(120, GOLD, IVORY, GOLD)}</div>')
        else:
            tile = (f'<div style="width: 100%; height: 170px; border-radius: 12px; background: #FFFFFF; border: 1px solid #DDD5C4; '
                    f'display: flex; align-items: center; justify-content: center">{svg_}</div>')
        cells.append(f'<div style="display: flex; flex-direction: column; gap: 10px">{tile}'
                     f'<div style="display: flex; gap: 8px; align-items: center">{cross()}<span style="font-size: 14px; font-weight: 600">{n}</span></div></div>')
    ok = (f'<div style="display: flex; gap: 18px; align-items: center; padding: 16px 20px; border-radius: 14px; background: #FBF8F1; border: 1px solid #DDD5C4">'
          f'{tick()}<p class="small"><strong>Ante la duda:</strong> usa el archivo original de la versión que corresponde al fondo '
          '(página 06) y respeta su área de protección (página 05). Si algo no encaja, cambia el fondo o el tamaño, nunca el símbolo.</p></div>')
    return board(11, "Usos incorrectos", "Usos incorrectos",
                 "El símbolo solo funciona si se reconoce siempre igual. Estas son las alteraciones más habituales, y ninguna está permitida.",
                 col(grid(4, *cells, gap=18), ok, gap=22), theme=LIGHT)


# --------------------------------------------------------------------------- 12 Aplicaciones
def p12():
    card_front = (f'<div style="width: 340px; height: 200px; border-radius: 10px; background: {NAVY}; border: 1px solid {LINE}; '
                  f'display: flex; align-items: center; justify-content: center">{lockup_v(210, label="Tarjeta, anverso")}</div>')
    card_back = (f'<div style="width: 340px; height: 200px; border-radius: 10px; background: {IVORY}; box-sizing: border-box; padding: 22px 24px; '
                 f'display: flex; flex-direction: column; justify-content: space-between; color: {NAVY}">'
                 f'<div style="display: flex; justify-content: space-between; align-items: flex-start">'
                 f'<div style="display: flex; flex-direction: column; gap: 3px"><span style="font-family: \'IBM Plex Serif\', serif; font-size: 18px; font-weight: 600">[NOMBRE APELLIDO]</span>'
                 f'<span style="font-size: 11px; color: {INK2}">[CARGO]</span></div>{light_mark(34)}</div>'
                 f'<div class="mono" style="font-size: 10.5px; line-height: 1.7; color: #2B3342">[TELÉFONO]<br>[CORREO]<br>[SITIO WEB]</div></div>')
    sig = (f'<div class="card" style="padding: 20px 22px; background: #FFFFFF; border-color: #DDD5C4; color: {NAVY}; display: flex; flex-direction: column; gap: 12px">'
           f'<span style="font-size: 13px; color: #2B3342">Un saludo,</span>'
           f'<div style="display: flex; gap: 14px; align-items: center; padding-top: 12px; border-top: 1px solid #E6E0D2">{light_mark(44)}'
           f'<div style="display: flex; flex-direction: column; gap: 2px"><span style="font-size: 14px; font-weight: 600">[Nombre Apellido]</span>'
           f'<span style="font-size: 12px; color: {INK2}">[Cargo] · Mirandas Group</span>'
           f'<span class="mono" style="font-size: 11px; color: {INK2}">[teléfono] · [sitio web]</span></div></div></div>')
    avatar = (f'<div style="display: flex; gap: 18px; align-items: center">'
              f'<div style="width: 120px; height: 120px; border-radius: 50%; background: {NAVY}; border: 1px solid {LINE}; display: flex; align-items: center; justify-content: center">'
              f'{mark(78, label="Avatar para redes")}</div>'
              f'<div style="display: flex; flex-direction: column; gap: 8px">{app_icon(64, "Icono de app")}'
              f'<span class="small">Avatar circular: símbolo al 65 % del círculo.<br>Icono y favicon: <span class="mono">mirandas-group.ico</span></span></div></div>')
    banner = (f'<div style="height: 150px; border-radius: 12px; background: {NAVY}; border: 1px solid {LINE}; box-sizing: border-box; padding: 0 36px; '
              f'display: flex; align-items: center; justify-content: space-between; overflow: hidden">'
              f'{lockup_h(330, label="Portada de redes")}'
              f'<span style="font-family: \'IBM Plex Serif\', serif; font-size: 22px; color: {IVORY}; max-width: 330px; text-align: right">[FRASE DE PORTADA]</span></div>')
    left = col(lbl("TARJETA DE PRESENTACIÓN · 85 × 55 MM"), row(card_front, card_back, gap=16),
               lbl("PORTADA DE REDES", "margin-top: 10px"), banner, gap=12, style="flex: 0 0 700px")
    right = col(lbl("FIRMA DE CORREO"), sig, lbl("REDES Y APLICACIONES", "margin-top: 10px"), avatar,
                '<p class="small" style="color: #A7B0BE; margin-top: auto">Los textos entre corchetes son datos por completar. '
                'Cada pieza usa la firma o el símbolo originales; nada se redibuja.</p>', gap=12, style="flex: 1")
    return board(12, "Aplicaciones", "Aplicaciones",
                 "Ejemplos de uso en las piezas más comunes. Sirven de plantilla: cambian los datos, no la composición.",
                 row(left, right, gap=40, style="flex-grow: 1"))


PAGES = [("Manual-01-Portada", p01), ("Manual-02-Esencia", p02), ("Manual-03-Simbolo", p03), ("Manual-04-Construccion", p04),
         ("Manual-05-Proteccion", p05), ("Manual-06-Versiones", p06), ("Manual-07-Firma", p07), ("Manual-08-Color", p08),
         ("Manual-09-Tipografia", p09), ("Manual-10-Arquitectura", p10), ("Manual-11-Usos-incorrectos", p11),
         ("Manual-12-Aplicaciones", p12)]

if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    idx_path = OUT / "canvas.json"
    idx = json.loads(idx_path.read_text(encoding="utf-8"))
    idx["pages"] = [{"id": "propuestas", "name": "Propuestas"}, {"id": "manual", "name": "Manual"}]
    idx["launch"] = {"view": "canvas", "page": "manual"}
    for i, (stem, fn) in enumerate(PAGES):
        name = f"{stem}.dc.html"
        (OUT / name).write_text(fn(), encoding="utf-8")
        r, c = divmod(i, 3)
        idx["boards"][name] = {"x": c * 1520, "y": r * 1020, "w": 1440, "h": 900, "page": "manual",
                               "title": f"{i + 1:02d} · {SECTIONS[i]}"}
        if name not in idx["order"]:
            idx["order"].append(name)
    idx["notes"]["manualTitle"] = {"kind": "title1", "maxW": 4400, "page": "manual", "w": 240, "x": 0, "y": -300,
                                   "text": "Mirandas Group · Manual de identidad v1.0"}
    idx_path.write_text(json.dumps(idx, ensure_ascii=False, indent=2), encoding="utf-8")
    print("\n".join(f"{p.name}: {p.stat().st_size // 1024} KB" for p in sorted(OUT.glob("Manual-*.dc.html"))))
