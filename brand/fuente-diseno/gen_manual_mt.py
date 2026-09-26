"""MiraTrade brand manual, advertising pieces and website mock-ups for the MiraTrade canvas.

Pages: "manual" (12 boards 1440x900), "publicidad" (real-size ads), "web" (home desktop + mobile).
Marks come from gen_pilares_mt / pilares, lockups from export_brand (outlined IBM Plex), UI colours
from miratrade/app/theme.py. Run with QT_QPA_PLATFORM=offscreen.
"""
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "group"))
import export_brand as eb  # noqa: E402
import pilares as pil  # noqa: E402
from gen_manual import cmyk, contrast, cross, inline, ratio, rgb, tick  # noqa: E402

OUT = HERE / "manual-marca"

# app theme (miratrade/app/theme.py) + logo colours
BG, PANEL, PANEL2, BORDER, BORDER2 = "#0B0E13", "#0F131A", "#12161D", "#1E242E", "#2A3240"
TEXT, TEXT2, BODY = "#E6EAF2", "#9AA4B2", "#C4CCD8"
BLUE, BLUE_HI, PRIMARY = "#6E9BFF", "#9BBAFF", "#3562D1"
UP, DOWN, INSIDER, OPTIONS, D13 = "#00D26A", "#FF8A7A", "#F4B740", "#B79CFF", "#F472B6"
IVORY, SEL = "#F5F1E8", "#141C2E"
L_BG, L_INK, L_BLUE, L_GREEN, L_MUTED = "#F5F7FB", "#0E1726", "#2F5BC8", "#008A45", "#4A5261"
DISCLAIMER = "Análisis, no asesoramiento. Operar conlleva riesgo de pérdida; con opciones puedes perder la prima entera."
TOTAL = 12


def mark(px, bg=BG, label=None, **kw):
    aria = f'role="img" aria-label="{label}"' if label else 'aria-hidden="true"'
    return (f'<svg width="{px}" height="{px}" viewBox="0 0 64 64" fill="none" {aria}>'
            f'{eb.mt["symbol_body"](px, bg=bg, **kw)}</svg>')


def light_mark(px, bg=L_BG, label=None):
    return mark(px, bg, label, frame_c=L_BLUE, side=L_INK, mid=L_BLUE, arrow=L_GREEN)


def lockup(w, dark=True, endorsed=False, label="Firma de MiraTrade"):
    s = eb.mt_lockup_endorsed(dark) if endorsed else eb.mt_lockup(dark)
    return inline(s, w, round(w * (126 if endorsed else 120) / 520), label)


def app_icon(px, label=None):
    return inline(eb.mt_app_icon(px), px, px, label)


def close_tags(html):
    return re.sub(r"<(rect|path|polyline|polygon|line|circle|text)([^>]*?)\s*/>", r"<\1\2></\1>", html)


FONTS = ('<link rel="preconnect" href="https://fonts.googleapis.com">\n'
         '<link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500;600&amp;'
         'family=IBM+Plex+Sans:wght@300;400;500;600;700&amp;family=IBM+Plex+Serif:wght@500;600&amp;display=swap" rel="stylesheet">')

BASE_CSS = """body{{margin:0;background:{bg};font-family:'IBM Plex Sans',sans-serif;color:{fg}}}
a{{color:{a}}}a:hover{{color:{ah}}}
.mono{{font-family:'IBM Plex Mono',monospace}}
.lbl{{font-size:12px;color:{muted};text-transform:uppercase;letter-spacing:.08em;font-weight:600}}
.h1{{font-size:44px;font-weight:600;line-height:1.1;letter-spacing:-.02em;margin:0}}
.h2{{font-size:17px;font-weight:600;margin:0}}
.p{{font-size:14px;line-height:1.6;margin:0;color:{body}}}
.small{{font-size:12.5px;line-height:1.55;margin:0;color:{body}}}
.card{{border:1px solid {line};border-radius:12px;background:{panel}}}
.pill{{display:inline-flex;align-items:center;gap:6px;padding:3px 10px;border-radius:999px;font-size:12px;font-weight:500;border:1px solid {line2}}}
.btn{{display:inline-flex;align-items:center;justify-content:center;min-height:44px;padding:0 18px;border-radius:8px;border:1px solid {line2};background:{panel2};color:{fg};font:500 14px 'IBM Plex Sans',sans-serif;text-decoration:none;cursor:pointer}}
.primary{{background:{primary};border-color:{primary};color:#FFFFFF}}
"""
DARK = dict(bg=BG, fg=TEXT, a=BLUE, ah=BLUE_HI, muted=TEXT2, body=BODY, line=BORDER, line2=BORDER2,
            panel=PANEL, panel2=PANEL2, primary=PRIMARY)
LIGHT = dict(bg=L_BG, fg=L_INK, a=L_BLUE, ah="#1F3F91", muted=L_MUTED, body="#2B3342", line="#DCE1EA",
             line2="#C9D0DC", panel="#FFFFFF", panel2="#FFFFFF", primary=L_BLUE)


def doc(title, w, h, inner, theme=DARK, css=""):
    return close_tags(
        f'<!doctype html>\n<html lang="es">\n<head>\n<meta charset="utf-8">\n<title>{title}</title>\n'
        f'<script src="./support.js"></script>\n</head>\n<body>\n<x-dc>\n<helmet>\n{FONTS}\n<style>\n'
        f'{BASE_CSS.format(**theme)}{css}</style>\n</helmet>\n{inner}\n</x-dc>\n'
        f'<script type="text/x-dc" data-dc-script data-props=\'{{"$preview":{{"width":{w},"height":{h}}}}}\'>\n'
        'class Component extends DCLogic {\n  renderVals() { return {}; }\n}\n</script>\n</body>\n</html>\n')


def col(*items, gap=12, style=""):
    return f'<div style="display: flex; flex-direction: column; gap: {gap}px; {style}">{"".join(items)}</div>'


def row(*items, gap=16, style=""):
    return f'<div style="display: flex; gap: {gap}px; {style}">{"".join(items)}</div>'


def grid(n, *items, gap=16, style=""):
    return (f'<div style="display: grid; grid-template-columns: repeat({n}, minmax(0, 1fr)); gap: {gap}px; {style}">'
            f'{"".join(items)}</div>')


def lbl(text, style=""):
    return f'<span class="lbl" style="{style}">{text}</span>'


SECTIONS = ["Portada", "Esencia", "Símbolo", "Construcción", "Versiones y tamaños", "Firma", "Color",
            "Tipografía", "Interfaz", "Gráficos e infografía", "Voz y usos incorrectos", "Aplicaciones"]


def board(num, title, lead, content, theme=DARK, header=True):
    t = theme
    top = ""
    if header:
        top = (f'<div style="display: flex; justify-content: space-between; align-items: center">'
               f'{lbl("MiraTrade · Manual de marca")}{lbl(f"{num:02d} / {TOTAL:02d} · {SECTIONS[num - 1]}")}</div>'
               f'<div style="display: flex; flex-direction: column; gap: 10px; max-width: 1000px">'
               f'<h1 class="h1">{title}</h1><p class="p" style="font-size: 16px">{lead}</p></div>')
    inner = (f'<div style="width: 1440px; height: 900px; box-sizing: border-box; padding: 40px 56px 44px; background: {t["bg"]}; '
             f'color: {t["fg"]}; display: flex; flex-direction: column; gap: 26px; overflow: hidden">{top}{content}</div>')
    return doc(f"MiraTrade · {num:02d} {SECTIONS[num - 1]}", 1440, 900, inner, theme)


# --------------------------------------------------------------------------- shared UI bits
EVENTS = [("ACME", "Directivos", "◆", INSIDER, "#6B5320", "3 directivos compraron acciones, el CEO incluido"),
          ("NOVA", "Opciones", "●", OPTIONS, "#4F4470", "Calls a 30 días muy por encima del interés abierto"),
          ("KLTR", "13D", "■", D13, "#6B2E52", "Un fondo activista supera el 5 %")]


def event_card(t, kind, icon, c, bd, what, on=False, compact=False):
    return (f'<div style="display: flex; flex-direction: column; gap: 7px; padding: {"10px 12px" if compact else "14px 16px"}; border-radius: 12px; '
            f'border: 1px solid {BLUE if on else BORDER}; background: {SEL if on else PANEL2}">'
            f'<div style="display: flex; justify-content: space-between; align-items: center">'
            f'<span class="mono" style="font-size: {15 if compact else 17}px; font-weight: 600">{t}</span>'
            f'<span class="pill" style="color: {c}; border-color: {bd}">{icon} {kind}</span></div>'
            f'<span style="font-size: {12.5 if compact else 14}px; line-height: 1.45; color: {BODY}">{what}</span></div>')


def candles(w, h, n=46, seed=4242, event_at=32):
    x = seed

    def rnd():
        nonlocal x
        x = (x * 9301 + 49297) % 233280
        return x / 233280
    ks, p = [], 41.0
    for k in range(n):
        drift = 0.006 if k > event_at else -0.001
        o = p
        c = o * (1 + (rnd() - 0.5) * 0.04 + drift)
        ks.append((o, c, max(o, c) * (1 + rnd() * 0.012), min(o, c) * (1 - rnd() * 0.012)))
        p = c
    hi, lo = max(k[2] for k in ks) * 1.02, min(k[3] for k in ks) * 0.98
    Y = lambda v: 10 + (hi - v) / (hi - lo) * (h - 20)  # noqa: E731
    step = (w - 16) / n
    out = [f'<line x1="0" x2="{w}" y1="{y}" y2="{y}" stroke="#1A2029" stroke-width="1"></line>' for y in (h * .25, h * .5, h * .75)]
    for j, (o, c, a, b) in enumerate(ks):
        cx = 8 + j * step + step / 2
        col_ = UP if c >= o else DOWN
        top, bot = Y(max(o, c)), Y(min(o, c))
        out.append(f'<line x1="{cx:.1f}" x2="{cx:.1f}" y1="{Y(a):.1f}" y2="{Y(b):.1f}" stroke="{col_}" stroke-width="1"></line>'
                   f'<rect x="{cx - step * .32:.1f}" y="{top:.1f}" width="{step * .64:.1f}" height="{max(1.5, bot - top):.1f}" rx="1" fill="{col_}"></rect>')
    ex = 8 + event_at * step + step / 2
    ey = Y(ks[event_at][3]) + 16
    out.append(f'<line x1="{ex:.1f}" x2="{ex:.1f}" y1="6" y2="{h - 6}" stroke="{INSIDER}" stroke-dasharray="4 4" opacity="0.6"></line>'
               f'<rect x="{ex - 6:.1f}" y="{ey:.1f}" width="12" height="12" transform="rotate(45 {ex:.1f} {ey + 6:.1f})" fill="{INSIDER}"></rect>')
    return (f'<svg width="{w}" height="{h}" viewBox="0 0 {w} {h}" role="img" aria-label="Gráfico de velas con la compra de directivos marcada">'
            f'{"".join(out)}</svg>')


def app_window(w=1100, h=640, label="Pantalla Señales de MiraTrade (datos de ejemplo)"):
    """Static replica of the Señales screen, scaled to fit ``w`` x ``h``."""
    nav = "".join(f'<div style="display: flex; align-items: center; min-height: 36px; padding: 0 12px; border-radius: 8px; font-size: 13px; '
                  f'color: {TEXT if i == 0 else TEXT2}; background: {"#18213A" if i == 0 else "transparent"}">{n}</div>'
                  for i, n in enumerate(["Señales", "Práctica", "Cartera", "Reportes", "Configuración"]))
    evs = "".join(event_card(*e, on=i == 0, compact=True) for i, e in enumerate(EVENTS))
    cw, ch = w - 170 - 270 - 250, h - 44 - 90
    return (f'<div role="img" aria-label="{label}" style="width: {w}px; height: {h}px; display: flex; flex-direction: column; border-radius: 12px; '
            f'overflow: hidden; border: 1px solid {BORDER2}; background: {BG}; box-shadow: 0 30px 80px rgba(0,0,0,.45)">'
            f'<div style="height: 44px; flex-shrink: 0; display: flex; align-items: center; gap: 12px; padding: 0 16px; background: {PANEL}; border-bottom: 1px solid {BORDER}">'
            f'{mark(22, PANEL)}<span style="font-size: 14px"><b>Mira</b><span style="font-weight: 300; color: {BLUE}">Trade</span></span>'
            f'<span style="flex-grow: 1"></span><span class="pill" style="border-color: {BLUE}; color: #BFD0FF; font-size: 11px">MODO PRÁCTICA</span>'
            f'<span class="mono" style="font-size: 11px; color: {TEXT2}">datos de ejemplo</span></div>'
            f'<div style="flex-grow: 1; display: flex; min-height: 0">'
            f'<div style="width: 170px; flex-shrink: 0; padding: 12px 8px; box-sizing: border-box; background: {PANEL}; border-right: 1px solid {BORDER}; display: flex; flex-direction: column; gap: 2px">{nav}</div>'
            f'<div style="width: 270px; flex-shrink: 0; padding: 14px; box-sizing: border-box; border-right: 1px solid {BORDER}; display: flex; flex-direction: column; gap: 8px">'
            f'<span class="lbl" style="font-size: 10.5px">3 eventos nuevos</span>{evs}</div>'
            f'<div style="flex-grow: 1; padding: 14px 16px; display: flex; flex-direction: column; gap: 10px; min-width: 0">'
            f'<div style="display: flex; gap: 10px; align-items: baseline"><span class="mono" style="font-size: 20px; font-weight: 600">ACME</span>'
            f'<span class="mono" style="font-size: 15px">$48,20</span><span class="mono" style="font-size: 13px; color: {UP}">+2,1 %</span></div>'
            f'<div style="border: 1px solid {BORDER}; border-radius: 10px; background: {PANEL}; overflow: hidden">{candles(cw, ch)}</div></div>'
            f'<div style="width: 250px; flex-shrink: 0; padding: 14px; box-sizing: border-box; border-left: 1px solid {BORDER}; background: {PANEL}; display: flex; flex-direction: column; gap: 10px">'
            f'<span class="lbl" style="font-size: 10.5px">Operación propuesta</span>'
            f'<span style="font-size: 15px; font-weight: 600">Call ACME · 45 días</span>'
            f'<div style="padding: 10px; border-radius: 10px; background: {PANEL2}; border: 1px solid {BORDER}; display: flex; flex-direction: column; gap: 4px">'
            f'<span style="font-size: 12.5px; font-weight: 600">Evidencia</span>'
            f'<span style="font-size: 12px; line-height: 1.5; color: {BODY}">[N] eventos parecidos: [X] % llegó al objetivo, [Y] % al stop.</span></div>'
            f'<span style="flex-grow: 1"></span>'
            f'<span class="btn primary" style="min-height: 36px; font-size: 12.5px">Vista previa en Schwab</span>'
            f'<span class="btn" style="min-height: 36px; font-size: 12.5px">Añadir a práctica</span>'
            f'<span style="font-size: 10.5px; color: {TEXT2}">Análisis, no asesoramiento.</span></div></div></div>')


# --------------------------------------------------------------------------- manual boards
def m01():
    idx = "".join(f'<div style="display: flex; gap: 14px; align-items: baseline; padding: 7px 0; border-bottom: 1px solid {BORDER}">'
                  f'<span class="mono" style="font-size: 12px; color: {BLUE}">{i:02d}</span><span style="font-size: 15px">{s}</span></div>'
                  for i, s in enumerate(SECTIONS[1:], 2))
    left = col(lbl("Manual de marca · versión 1.0 · septiembre 2026"),
               f'<div style="flex-grow: 1; display: flex; flex-direction: column; justify-content: center; gap: 34px">'
               f'{lockup(640, endorsed=True, label="MiraTrade, a Mirandas Group company")}'
               f'<p class="p" style="font-size: 20px; max-width: 600px; color: {TEXT}">Señales con evidencia, no con promesas.</p>'
               f'<p class="p" style="max-width: 560px">Identidad, interfaz, publicidad y sitio web de MiraTrade. Deriva del sistema '
               f'Pilares de Mirandas Group: mismo marco, mismos pilares, color y flecha propios.</p></div>', gap=0, style="flex-grow: 1")
    right = col(lbl("Contenido"), f'<div>{idx}</div>',
                f'<p class="small" style="margin-top: auto; color: {TEXT2}">Además, en este lienzo: página <b style="color: {TEXT}">Publicidad</b> '
                f'(anuncios a tamaño real) y página <b style="color: {TEXT}">Sitio web</b> (inicio en escritorio y móvil).</p>',
                gap=14, style="width: 420px")
    return board(1, "", "", row(left, right, gap=80, style="flex-grow: 1; padding-top: 20px"), header=False)


def m02():
    what = col(lbl("Qué es MiraTrade"),
               f'<p class="p" style="font-size: 17px; color: {TEXT}">Una aplicación de escritorio para Windows que vigila tres tipos '
               'de eventos del mercado de EE. UU. y dice, con datos, qué pasó otras veces que ocurrió algo parecido.</p>',
               grid(3, *(event_card(*e) for e in EVENTS), gap=10),
               '<p class="p">Solo los eventos disparan una señal; los indicadores técnicos son contexto. Cada regla se prueba con '
               'cinco años de datos, en un periodo y otra vez en otro. Se opera en práctica o con vista previa en Schwab, y ninguna '
               'orden real sale sin una confirmación escrita.</p>', gap=12, style="flex: 1.25")
    traits = [("Preciso", "Cifras exactas y con su fuente. Nunca «muchos» si se puede decir cuántos."),
              ("Honesto", "Enseña los aciertos y los fallos. Si una regla no se sostiene, lo dice."),
              ("Sereno", "Sin urgencias ni cuentas atrás. El mercado no se acaba hoy."),
              ("Cercano", "Español claro, de tú. Cada término técnico, explicado la primera vez.")]
    tr = "".join(f'<div class="card" style="padding: 16px; display: flex; flex-direction: column; gap: 6px">'
                 f'<span style="font-size: 19px; font-weight: 600; color: {BLUE}">{n}</span><p class="small">{d}</p></div>' for n, d in traits)
    right = col(lbl("Promesa"),
                f'<div class="card" style="padding: 20px 22px; background: {SEL}; border-color: {BLUE}">'
                f'<span style="font-size: 26px; font-weight: 600; letter-spacing: -.01em">Señales con evidencia, no con promesas.</span></div>',
                lbl("Personalidad", "margin-top: 8px"), grid(2, tr, gap=10), gap=12, style="flex: 1")
    return board(2, "Esencia de marca",
                 "MiraTrade no vende aciertos: enseña evidencia. Esa es la diferencia con casi todo el sector, y la base de su voz.",
                 row(what, right, gap=48, style="flex-grow: 1"))


def m03():
    step = lambda m, t, d: col(f'<div class="card" style="height: 230px; display: flex; align-items: center; justify-content: center; background: {PANEL}">{m}</div>',  # noqa: E731
                               f'<span class="h2">{t}</span>', f'<p class="small">{d}</p>', gap=10, style="flex: 1")
    group = (f'<svg width="150" height="150" viewBox="0 0 64 64" fill="none" aria-hidden="true">'
             f'{pil.frame(150, "#C9A24A")}{pil.bars(IVORY, "#C9A24A")}</svg>')
    blue = (f'<svg width="150" height="150" viewBox="0 0 64 64" fill="none" aria-hidden="true">'
            f'{pil.frame(150, BLUE)}{pil.bars(IVORY, BLUE)}</svg>')
    base, head = eb.mt["arrow_geom"](8.0, 4.8)
    pts = " ".join(f"{x},{y}" for x, y in [eb.mt["START"], *eb.mt["VERTS"]]) + f" {base[0]:.2f},{base[1]:.2f}"
    arrow = (f'<svg width="150" height="150" viewBox="0 0 64 64" fill="none" aria-hidden="true">'
             f'<polyline points="{pts}" stroke="{UP}" stroke-width="3.4" stroke-linecap="round" stroke-linejoin="round"></polyline>'
             f'<polygon points="{head}" fill="{UP}" stroke="{UP}" stroke-width="1" stroke-linejoin="round"></polygon></svg>')
    plus = f'<span style="font-size: 30px; color: {TEXT2}; align-self: center; margin-top: -80px">→</span>'
    flow = row(step(group, "1 · La base del grupo", "Marco y tres pilares de Mirandas Group, sin cambiar una medida."), plus,
               step(blue, "2 · El color de la marca", "El marco y el pilar central pasan a azul MiraTrade."), plus,
               step(arrow, "3 · El elemento propio", "Una flecha en zigzag que sube: un gráfico que dibuja la M."), plus,
               step(mark(150, PANEL, "Símbolo de MiraTrade"), "4 · El símbolo", "La flecha pasa por detrás de los pilares y rompe el marco arriba a la derecha."),
               gap=14, style="align-items: flex-start")
    meaning = grid(3,
                   col('<span class="h2">La M de Miranda</span>', '<p class="small">Los pilares vienen del grupo: MiraTrade es Miranda + Trade.</p>', gap=6),
                   col('<span class="h2">Un precio que sube</span>', '<p class="small">La flecha baja bajo el pilar azul y vuelve a subir: la forma real de un gráfico, no una línea recta ideal.</p>', gap=6),
                   col('<span class="h2">Fuera del marco</span>', '<p class="small">La punta sale del marco: el evento que se sale de lo normal y que MiraTrade detecta.</p>', gap=6),
                   gap=28)
    return board(3, "El símbolo", "Se construye en cuatro pasos sobre la base del grupo. Solo cambian el color y la flecha.",
                 col(flow, meaning, gap=28))


def construction_svg(w):
    g = []
    for i in range(0, 65, 2):
        c = "#232B38" if i % 8 == 0 else "#151A22"
        g.append(f'<line x1="{i}" y1="0" x2="{i}" y2="64" stroke="{c}" stroke-width="0.12"></line>'
                 f'<line x1="0" y1="{i}" x2="64" y2="{i}" stroke="{c}" stroke-width="0.12"></line>')
    body = eb.mt["symbol_body"](96, bg="#0B1018")
    a = INSIDER
    pts = [("1", 5, 57), ("2", 21, 31), ("3", 32, 45), ("4", 59.5, 4.5)]
    dots = "".join(f'<circle cx="{x}" cy="{y}" r="1.7" fill="{a}"></circle><text x="{x}" y="{y + 0.65}" text-anchor="middle" '
                   f'font-family="IBM Plex Mono, monospace" font-size="1.9" font-weight="600" fill="{BG}">{n}</text>' for n, x, y in pts)
    return (f'<svg width="{w}" height="{w}" viewBox="0 0 64 64" fill="none" role="img" aria-label="Construcción del símbolo de MiraTrade">'
            f'{"".join(g)}{body}{dots}</svg>')


def m04():
    legend = [("Marco y pilares", "Idénticos al grupo: marco 50 × 50 u, radio 13; pilares de 7 u (27 / 15 / 27)."),
              ("Recorrido de la flecha", "1 (5, 57) → 2 (21, 31) → 3 (32, 45) → 4 punta (59,5, 4,5)."),
              ("Grosor de la flecha", "3,4 u, extremos y uniones redondeados. Punta de 8 × 9,6 u."),
              ("Filo de separación", "Un trazo de 8 u del color del fondo recorta la flecha junto al marco; "
                                     "los pilares llevan un filo de 2,4 u. Por eso cada versión va con su fondo."),
              ("Por detrás", "La flecha pasa siempre por detrás de los tres pilares, nunca por delante."),
              ("Tamaños pequeños", "Detalles × 1,2 (40–63 px), × 1,45 (24–39 px), × 1,9 (< 24 px); la punta crece hasta × 1,5.")]
    rows_ = "".join(f'<div style="display: flex; flex-direction: column; gap: 3px; padding: 11px 0; border-bottom: 1px solid {BORDER}">'
                    f'<span class="h2" style="font-size: 15px">{t}</span><p class="small">{d}</p></div>' for t, d in legend)
    right = col(lbl("Medidas · retícula de 64 unidades"), f'<div>{rows_}</div>',
                f'<p class="small" style="margin-top: auto; color: {TEXT2}">Fuente única: <span class="mono">fuente-diseno/gen_pilares_mt.py</span> '
                '(flecha) y <span class="mono">pilares.py</span> (marco y pilares).</p>', gap=10, style="flex: 1")
    left = (f'<div class="card" style="flex: 0 0 600px; display: flex; align-items: center; justify-content: center; background: #0B1018">'
            f'{construction_svg(560)}</div>')
    return board(4, "Construcción", "Marco y pilares salen del grupo; la flecha tiene su propia geometría, igual de fija.",
                 row(left, right, gap=48, style="flex-grow: 1; min-height: 0"))


def m05():
    vs = [("Fondo oscuro · principal", BG, mark(140, BG, "Versión principal"), BORDER),
          ("Fondo claro", L_BG, light_mark(140, L_BG, "Versión fondo claro"), "#DCE1EA"),
          ("Monocromo", "#0F131A", mark(140, "#0F131A", "Versión monocromo", frame_c="#E6EAF2", side="#E6EAF2", mid="#8A93A3", arrow="#E6EAF2"), BORDER),
          ("Alternativa ámbar", BG, mark(140, BG, "Versión alternativa ámbar", arrow=INSIDER), BORDER),
          ("Icono de app", "#0B1018", app_icon(140, "Icono de app"), BORDER)]
    cells = "".join(f'<div style="display: flex; flex-direction: column; gap: 10px"><div style="height: 200px; border-radius: 12px; background: {bg}; '
                    f'border: 1px solid {bd}; display: flex; align-items: center; justify-content: center">{m}</div><span class="h2" style="font-size: 15px">{n}</span></div>'
                    for n, bg, m, bd in vs)
    sizes = "".join(f'<div style="display: flex; flex-direction: column; align-items: center; gap: 8px">'
                    f'<div style="height: 70px; display: flex; align-items: center">{mark(s)}</div>'
                    f'<span class="mono" style="font-size: 12px; color: {TEXT2}">{s} px</span></div>' for s in (64, 48, 32, 24, 16))
    rules = col('<p class="small"><b style="color: #E6EAF2">Cuál usar.</b> Oscuro por defecto (la app y la web son oscuras). '
                'Claro en documentos e impresión sobre blanco. Monocromo para una tinta. Ámbar solo cuando el verde se confunda con '
                'datos al lado (por ejemplo, junto a una cifra en verde).</p>',
                '<p class="small"><b style="color: #E6EAF2">Área de protección:</b> la altura del pilar central (15 u) alrededor del marco, '
                'contando la punta de la flecha. <b style="color: #E6EAF2">Mínimos:</b> símbolo 16 px / 6 mm; firma 130 px / 32 mm.</p>',
                '<p class="small">Por debajo de 64 px usa los PNG de su tamaño: llevan la flecha y el marco engrosados.</p>', gap=10)
    return board(5, "Versiones y tamaños", "Cinco versiones, cada una dibujada para su fondo porque la flecha lleva un filo del color del fondo.",
                 col(grid(5, cells, gap=14), row(col(lbl("Ajuste por tamaño"), row(sizes, gap=36, style="align-items: flex-end"), gap=12),
                                                 col(rules, style="flex: 1"), gap=56), gap=26))


def m06():
    tile = lambda inner, bg, bd="": (f'<div style="height: 190px; border-radius: 12px; background: {bg}; {bd} display: flex; align-items: center; '  # noqa: E731
                                     f'justify-content: center">{inner}</div>')
    grid_ = grid(2, tile(lockup(470), BG, f"border: 1px solid {BORDER};"),
                 tile(lockup(470, False, label="Firma sobre claro"), L_BG),
                 tile(lockup(470, endorsed=True, label="Firma con respaldo"), BG, f"border: 1px solid {BORDER};"),
                 tile(lockup(470, False, True, "Firma con respaldo sobre claro"), L_BG), gap=14)
    rules = grid(3,
                 col('<span class="h2">El nombre</span>', f'<p class="small">«Mira» en IBM Plex Sans Bold y «Trade» en Light, en azul. '
                     'Una sola palabra, sin espacio. En texto corrido se escribe MiraTrade, nunca MIRATRADE ni Mira Trade.</p>', gap=6),
                 col('<span class="h2">Con respaldo</span>', '<p class="small">En la web, la tienda, la publicidad y los documentos legales. '
                     'La línea «a Mirandas Group company» se alinea con el inicio del nombre.</p>', gap=6),
                 col('<span class="h2">Archivos</span>', '<p class="small"><span class="mono">firma/miratrade-firma-horizontal-*</span> y '
                     '<span class="mono">-respaldo-*</span>, en SVG y PNG 1×/2×/4×. El texto va en trazos.</p>', gap=6), gap=28)
    return board(6, "La firma", "Símbolo y nombre. Existe sola y con el respaldo del grupo, para fondo oscuro y claro.",
                 col(grid_, rules, gap=24))


def m07():
    def chip(n, h, use, big=False, on=BG):
        r, g, b = rgb(h)
        c, m, y, k = cmyk(h)
        bd = f"border: 1px solid {BORDER};" if contrast(h, BG) < 1.4 else ""
        return (f'<div style="display: flex; flex-direction: column; gap: 6px"><div style="height: {110 if big else 60}px; border-radius: 10px; background: {h}; {bd}"></div>'
                f'<span style="font-size: {15 if big else 13}px; font-weight: 600">{n}</span>'
                f'<span class="mono" style="font-size: 11.5px; line-height: 1.55; color: {BODY}">{h}<br>RGB {r} {g} {b}'
                + (f'<br>CMYK {c} {m} {y} {k}' if big else "") + f'</span><span style="font-size: 11.5px; line-height: 1.45; color: {TEXT2}">{use}'
                + (f' · {ratio(h, on)}' if contrast(h, on) >= 1.4 else "") + '</span></div>')
    brand = [("Azul MiraTrade", BLUE, "Marco, pilar, «Trade», enlaces", True), ("Verde flecha", UP, "Flecha del logo; sube, objetivo", True),
             ("Marfil", IVORY, "Pilares laterales del logo", True), ("Noche", BG, "Fondo de app, web y piezas", True)]
    ui = [("Panel", PANEL, "Barras y paneles"), ("Tarjeta", PANEL2, "Tarjetas"), ("Borde", BORDER, "Divisores"),
          ("Texto", TEXT, "Texto principal"), ("Texto 2", TEXT2, "Etiquetas, notas"), ("Botón", PRIMARY, "Acción principal (texto blanco)")]
    sem = [("Sube / objetivo", UP, "◆ nunca solo por color: + y flecha"), ("Baja / stop", DOWN, "con signo −"),
           ("Directivos", INSIDER, "◆ rombo"), ("Opciones", OPTIONS, "● círculo"), ("13D / 13G", D13, "■ cuadrado")]
    content = col(lbl("Colores de marca"), grid(4, *(chip(*c) for c in brand), gap=14),
                  row(col(lbl("Interfaz"), grid(6, *(chip(*c) for c in ui), gap=10), gap=10, style="flex: 1.3"),
                      col(lbl("Un significado por color"), grid(5, *(chip(*c) for c in sem), gap=10), gap=10, style="flex: 1.1"), gap=32),
                  f'<p class="small" style="color: {TEXT2}">Sobre claro: azul {L_BLUE}, verde {L_GREEN}, tinta {L_INK} sobre {L_BG}. '
                  'Cada color de datos va siempre con su forma o su signo, para quien no distingue colores. CMYK calculado como referencia; '
                  'Pantone: [PENDIENTE DE PRUEBA DE IMPRESIÓN]. Contraste medido sobre el fondo Noche.</p>', gap=12)
    return board(7, "Color", "Oscuro por naturaleza: se lee de noche frente al gráfico. Cada color de datos significa una sola cosa.", content)


def m08():
    fam = [("IBM Plex Sans", "'IBM Plex Sans', sans-serif", "Interfaz, web y publicidad. «Mira» en Bold 700, «Trade» en Light 300.", "Segoe UI"),
           ("IBM Plex Mono", "'IBM Plex Mono', monospace", "Tickers, precios, porcentajes, fechas. Cifras alineadas en tablas.", "Consolas"),
           ("IBM Plex Serif", "'IBM Plex Serif', serif", "Solo en piezas del grupo o citas largas. No en la interfaz.", "Georgia")]
    cards = "".join(f'<div class="card" style="padding: 18px; display: flex; flex-direction: column; gap: 8px">'
                    f'<span style="font-family: {ff}; font-size: 38px; line-height: 1">ACME 48,20</span><span class="h2">{n}</span>'
                    f'<p class="small">{u}</p><span class="mono" style="font-size: 11.5px; color: {TEXT2}">Alternativa: {fb}</span></div>' for n, ff, u, fb in fam)
    app = [("Título de pantalla", 20, 600, "Sans", "Señales nuevas"), ("Subtítulo", 16, 600, "Sans", "Operación propuesta"),
           ("Texto", 14, 400, "Sans", "3 directivos compraron acciones"), ("Nota", 13, 400, "Sans", "Análisis, no asesoramiento."),
           ("Etiqueta", 12, 600, "Sans", "OPERACIÓN PROPUESTA"), ("Cifra", 17, 600, "Mono", "$48,20  +2,1 %")]
    web = [("Titular", 56, 600, "Sans", "Señales con evidencia"), ("Sección", 36, 600, "Sans", "Cómo funciona"),
           ("Entradilla", 20, 400, "Sans", "Te dice qué pasó las otras veces"), ("Texto", 17, 400, "Sans", "Cada regla se prueba con cinco años de datos.")]

    def table(items):
        return "".join(f'<div style="display: grid; grid-template-columns: 140px 1fr 110px; gap: 12px; align-items: baseline; padding: 7px 0; border-bottom: 1px solid {BORDER}">'
                       f'<span class="lbl" style="font-size: 11px">{n}</span>'
                       f'<span style="font-family: {"IBM Plex Mono" if f == "Mono" else "IBM Plex Sans"}; font-size: {min(px, 30)}px; font-weight: {wt}; '
                       f'white-space: nowrap; overflow: hidden; text-overflow: ellipsis{"; letter-spacing: .06em" if n == "Etiqueta" else ""}">{s}</span>'
                       f'<span class="mono" style="font-size: 12px; color: {BLUE_HI}">{f} {wt} · {px}</span></div>' for n, px, wt, f, s in items)
    content = col(grid(3, cards, gap=14),
                  row(col(lbl("Escala de la app (theme.py)"), f'<div>{table(app)}</div>', gap=8, style="flex: 1"),
                      col(lbl("Escala web y publicidad"), f'<div>{table(web)}</div>',
                          f'<p class="small" style="color: {TEXT2}">En la web los titulares se muestran a tamaño real hasta 30 px en esta tabla. '
                          'Interlineado: 1,1 en titulares, 1,6 en texto.</p>', gap=8, style="flex: 1"), gap=40), gap=20)
    return board(8, "Tipografía", "La misma superfamilia que el grupo. MiraTrade habla en Sans y cuenta en Mono.", content)


def m09():
    btns = row('<button type="button" class="btn primary">Vista previa en Schwab</button>',
               '<button type="button" class="btn">Añadir a práctica</button>',
               f'<button type="button" class="btn" style="background: #3A1614; border-color: #8C3A33; color: #FFB4AA; font-weight: 600">Detener todo</button>',
               gap=10, style="flex-wrap: wrap")
    pills = row(f'<span class="pill" style="border-color: {BLUE}; color: #BFD0FF; font-weight: 600">● MODO PRÁCTICA</span>',
                f'<span class="pill" style="border-color: {DOWN}; color: #FFD2CC; background: #3A1614; font-weight: 600">● DINERO REAL</span>',
                *(f'<span class="pill" style="color: {c}; border-color: {bd}">{i} {k}</span>' for _, k, i, c, bd, _ in EVENTS), gap=8, style="flex-wrap: wrap")
    field = (f'<div style="display: flex; flex-direction: column; gap: 6px; max-width: 320px"><label for="risk" style="font-size: 13px; color: {TEXT2}">Riesgo por operación (%)</label>'
             f'<input id="risk" value="1,0" style="min-height: 40px; padding: 0 10px; border-radius: 8px; border: 1px solid {BORDER2}; background: {BG}; color: {TEXT}; font: 14px \'IBM Plex Mono\', monospace"></div>')
    evidence = (f'<div style="display: flex; flex-direction: column; gap: 6px; padding: 12px 14px; border-radius: 10px; background: {PANEL2}; border: 1px solid {BORDER}; max-width: 330px">'
                f'<span style="font-size: 14px; font-weight: 600">Evidencia</span><span style="font-size: 14px; line-height: 1.5; color: {BODY}">'
                '[N] eventos parecidos. [X] % llegó al objetivo, [Y] % al stop. Regla [confirmada / no confirmada] fuera de muestra.</span></div>')
    left = col(lbl("Botones"), btns, lbl("Estados y tipos de evento", "margin-top: 8px"), pills, lbl("Campo", "margin-top: 8px"), field,
               lbl("Caja de evidencia", "margin-top: 8px"), evidence, gap=12, style="flex: 1")
    rules = [("Un botón principal por pantalla", "Azul relleno, texto blanco. El resto, secundarios."),
             ("Detener todo, siempre visible", "Rojo apagado en la cabecera. Nunca se esconde en un menú."),
             ("Práctica o dinero real, siempre a la vista", "Una píldora en la cabecera dice en qué modo estás."),
             ("Toda señal muestra su evidencia", "Aciertos y fallos juntos, con el número de casos."),
             ("Objetivos de 44 px", "Botones y filas de navegación miden al menos 44 px de alto."),
             ("Foco visible", "Borde azul de 2 px al navegar con el teclado.")]
    rl = "".join(f'<div style="padding: 10px 0; border-bottom: 1px solid {BORDER}; display: flex; flex-direction: column; gap: 3px">'
                 f'<span class="h2" style="font-size: 15px">{t}</span><p class="small">{d}</p></div>' for t, d in rules)
    mid = col(lbl("Tarjeta de evento"), event_card(*EVENTS[0], on=True), event_card(*EVENTS[1]), gap=10, style="flex: 0 0 340px")
    return board(9, "Interfaz", "Los componentes de la app de escritorio, con las reglas que la hacen segura de usar.",
                 row(left, mid, col(lbl("Reglas"), f'<div>{rl}</div>', gap=8, style="flex: 1"), gap=40, style="flex-grow: 1"))


def m10():
    chart = f'<div class="card" style="overflow: hidden">{candles(620, 300)}</div>'
    rules = [("Velas", f"Verde {UP} si cierra arriba, coral {DOWN} si cierra abajo. Sin degradados ni 3D."),
             ("Eventos", "Una línea discontinua en el día del evento y su forma: ◆ directivos, ● opciones, ■ 13D/13G."),
             ("Rejilla", "Solo horizontal, muy tenue (#1A2029). Ejes y cifras en Mono 12."),
             ("Anotaciones", "Texto corto junto al dato, nunca una leyenda lejana.")]
    rl = "".join(f'<div style="padding: 9px 0; border-bottom: 1px solid {BORDER}"><span class="h2" style="font-size: 14px">{t}. </span>'
                 f'<span class="small">{d}</span></div>' for t, d in rules)
    steps = [("1", "Evento", "Una compra de directivos, unas opciones inusuales o un 13D.", INSIDER),
             ("2", "Contexto", "Tendencia, volumen y mercado: informan, no disparan.", OPTIONS),
             ("3", "Evidencia", "Qué pasó con eventos parecidos en 5 años.", BLUE),
             ("4", "Tú decides", "Práctica o vista previa en Schwab; confirmas tú.", UP)]
    info = "".join(f'<div style="flex: 1; display: flex; flex-direction: column; gap: 10px; padding: 18px; border-radius: 12px; background: {PANEL2}; border-top: 3px solid {c}">'
                   f'<span class="mono" style="font-size: 30px; font-weight: 600; color: {c}">{n}</span><span class="h2">{t}</span><p class="small">{d}</p></div>'
                   for n, t, d, c in steps)
    icons = row(*(f'<div style="display: flex; flex-direction: column; align-items: center; gap: 6px"><svg width="40" height="40" viewBox="0 0 24 24" fill="none" '
                  f'stroke="{TEXT}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">{p}</svg>'
                  f'<span style="font-size: 11.5px; color: {TEXT2}">{n}</span></div>'
                  for n, p in [("Señales", '<path d="M3 17l6-6 4 4 8-8"></path>'), ("Práctica", '<rect x="3" y="6" width="18" height="13" rx="2"></rect>'),
                               ("Cartera", '<circle cx="12" cy="12" r="8"></circle><path d="M12 4v8l6 4"></path>'),
                               ("Reportes", '<path d="M6 3h9l4 4v14H6z"></path>'),
                               ("Ajustes", '<circle cx="12" cy="12" r="3"></circle><path d="M12 3v3M12 18v3M3 12h3M18 12h3"></path>')]), gap=26)
    left = col(lbl("Gráficos"), chart, f'<div>{rl}</div>', gap=10, style="flex: 0 0 620px")
    right = col(lbl("Infografía · estilo"), f'<div style="display: flex; gap: 10px">{info}</div>',
                '<p class="small">Pasos numerados en Mono, un color de la paleta por paso, una idea por bloque. Las cifras reales '
                'solo si vienen del último reporte validado; si no, se dice «datos de ejemplo».</p>',
                lbl("Iconos", "margin-top: 8px"), icons, '<p class="small">Trazo de 2 px, esquinas redondeadas, retícula de 24. Nunca emojis.</p>',
                gap=12, style="flex: 1")
    return board(10, "Gráficos e infografía", "Los datos son el producto: se dibujan limpios, con un código de formas y colores constante.",
                 row(left, right, gap=40, style="flex-grow: 1"))


def m11():
    bad_marks = [("Flecha por delante de los pilares",
                  f'<svg width="110" height="110" viewBox="0 0 64 64" fill="none" aria-hidden="true">{pil.frame(110, BLUE)}{pil.bars(IVORY, BLUE)}'
                  f'<polyline points="5,57 21,31 32,45 55,9" stroke="{UP}" stroke-width="3.4" stroke-linecap="round" stroke-linejoin="round"></polyline></svg>'),
                 ("Flecha en rojo o bajando", mark(110, BG, arrow=DOWN)),
                 ("Pilar central en oro (es del grupo)", mark(110, BG, mid="#C9A24A", frame_c="#C9A24A")),
                 ("Versión oscura sobre fondo claro", mark(110, BG).replace("<svg", '<svg style="background: #F5F7FB; border-radius: 8px"', 1))]
    cells = "".join(f'<div style="display: flex; flex-direction: column; gap: 8px"><div style="height: 150px; border-radius: 12px; background: {"#F5F7FB" if "claro" in n else PANEL}; '
                    f'border: 1px solid {BORDER}; display: flex; align-items: center; justify-content: center">{m}</div>'
                    f'<div style="display: flex; gap: 8px; align-items: center">{cross("#FF8A80")}<span style="font-size: 13px; font-weight: 600">{n}</span></div></div>'
                    for n, m in bad_marks)
    yes = ["Probado con cinco años de datos.", "En [N] casos parecidos, [X] % llegó al objetivo.", "Esta regla no se confirmó fuera de muestra.", "Puedes perder la prima entera."]
    no = ["Gana dinero fácil con nuestras señales.", "El 90 % de nuestras señales aciertan.", "¡Última oportunidad, compra ya!", "Sin riesgo."]
    voice = row(col(row(tick("#00D26A"), '<span class="h2">Así sí</span>', gap=8, style="align-items: center"),
                    *(f'<p class="small">«{t}»</p>' for t in yes), gap=8, style="flex: 1"),
                col(row(cross("#FF8A80"), '<span class="h2">Así no, nunca</span>', gap=8, style="align-items: center"),
                    *(f'<p class="small">«{t}»</p>' for t in no), gap=8, style="flex: 1"), gap=24)
    legal = (f'<div class="card" style="padding: 16px 18px; display: flex; flex-direction: column; gap: 8px">'
             f'<span class="h2" style="font-size: 15px">Aviso obligatorio en toda pieza que hable de resultados</span>'
             f'<p class="small" style="color: {TEXT}">«{DISCLAIMER}»</p>'
             '<p class="small">Versión corta (banners pequeños): «Análisis, no asesoramiento. Operar conlleva riesgo.» '
             'Revisa los textos con un asesor legal antes de publicar anuncios pagados.</p></div>')
    return board(11, "Voz y usos incorrectos", "Qué no hacer con el símbolo y, sobre todo, qué no prometer nunca.",
                 row(col(lbl("El símbolo"), grid(2, cells, gap=14), gap=10, style="flex: 0 0 560px"),
                     col(lbl("La voz"), voice, legal, gap=14, style="flex: 1"), gap=44, style="flex-grow: 1"))


def m12():
    splash = (f'<div style="width: 420px; height: 260px; border-radius: 12px; background: {BG}; border: 1px solid {BORDER2}; display: flex; flex-direction: column; '
              f'align-items: center; justify-content: center; gap: 18px">{lockup(300, label="Pantalla de arranque")}'
              f'<div style="width: 180px; height: 4px; border-radius: 2px; background: #1A2029"><div style="width: 60%; height: 4px; border-radius: 2px; background: {BLUE}"></div></div>'
              f'<span class="mono" style="font-size: 11px; color: {TEXT2}">Cargando datos de mercado…</span></div>')
    toast = (f'<div style="width: 380px; display: flex; gap: 12px; padding: 14px 16px; border-radius: 10px; background: #1B2029; border: 1px solid {BORDER2}">'
             f'{app_icon(36)}<div style="display: flex; flex-direction: column; gap: 3px"><span style="font-size: 12px; color: {TEXT2}">MiraTrade</span>'
             f'<span style="font-size: 14px; font-weight: 600">Nuevo evento: ACME ◆ Directivos</span>'
             f'<span style="font-size: 13px; color: {BODY}">3 directivos compraron. Mira la evidencia antes de decidir.</span></div></div>')
    icons = row(*(f'<div style="display: flex; flex-direction: column; align-items: center; gap: 6px">{app_icon(s)}'
                  f'<span class="mono" style="font-size: 11px; color: {TEXT2}">{s}</span></div>' for s in (96, 48, 32, 24, 16)),
                gap=22, style="align-items: flex-end")
    email = (f'<div style="width: 420px; border-radius: 12px; overflow: hidden; border: 1px solid #DCE1EA; background: #FFFFFF; color: {L_INK}">'
             f'<div style="padding: 16px 20px; background: {BG}">{lockup(170, label="Cabecera de correo")}</div>'
             f'<div style="padding: 18px 20px; display: flex; flex-direction: column; gap: 8px"><span style="font-size: 17px; font-weight: 600">Resumen semanal</span>'
             f'<span style="font-size: 13px; line-height: 1.55; color: #2B3342">[N] eventos nuevos esta semana. Cada uno con su evidencia en la app.</span>'
             f'<span style="font-size: 11px; color: {L_MUTED}">{DISCLAIMER}</span></div></div>')
    avatar = (f'<div style="width: 110px; height: 110px; border-radius: 50%; background: {BG}; border: 1px solid {BORDER2}; display: flex; align-items: center; '
              f'justify-content: center">{mark(70, BG, "Avatar de redes")}</div>')
    return board(12, "Aplicaciones", "Dónde vive la marca fuera del manual: arranque de la app, avisos, iconos, correo y redes.",
                 row(col(lbl("Arranque de la app"), splash, lbl("Aviso de Windows", "margin-top: 8px"), toast, gap=10),
                     col(lbl("Icono en Windows · .ico de 16 a 256 px"), icons, lbl("Avatar de redes", "margin-top: 8px"), avatar, gap=10),
                     col(lbl("Correo"), email, gap=10), gap=40, style="flex-grow: 1"))


# --------------------------------------------------------------------------- publicidad (real size)
def ad_shell(w, h, inner, pad=72):
    return (f'<div style="width: {w}px; height: {h}px; box-sizing: border-box; padding: {pad}px; background: {BG}; color: {TEXT}; '
            f'display: flex; flex-direction: column; overflow: hidden; position: relative">{inner}</div>')


def glow_grid(w, h):
    """Subtle chart grid in the background of ads (no gradients)."""
    lines = "".join(f'<line x1="0" x2="{w}" y1="{y}" y2="{y}" stroke="#141922" stroke-width="2"></line>' for y in range(60, h, 120))
    return f'<svg width="{w}" height="{h}" viewBox="0 0 {w} {h}" aria-hidden="true" style="position: absolute; left: 0; top: 0">{lines}</svg>'


def foot(size=16, color=TEXT2, short=False):
    txt = "Análisis, no asesoramiento. Operar conlleva riesgo." if short else DISCLAIMER
    return f'<span style="font-size: {size}px; line-height: 1.45; color: {color}">{txt}</span>'


def ad_post_a():
    inner = (glow_grid(1080, 1080) + f'<div style="position: relative; display: flex; flex-direction: column; height: 100%">'
             f'{lockup(360, label="MiraTrade")}'
             f'<div style="flex-grow: 1; display: flex; flex-direction: column; justify-content: center; gap: 28px">'
             f'<span style="font-size: 92px; font-weight: 600; line-height: 1.02; letter-spacing: -.03em">Señales con<br>evidencia,<br>'
             f'<span style="font-weight: 300; color: {BLUE}">no con promesas.</span></span>'
             f'<span style="font-size: 30px; line-height: 1.4; color: {BODY}; max-width: 820px">Cada señal llega con su historial: cuántas veces funcionó y cuántas no.</span></div>'
             f'<div style="display: flex; justify-content: space-between; align-items: flex-end; gap: 40px">{foot(18)}'
             f'<span class="mono" style="font-size: 20px; color: {TEXT2}; white-space: nowrap">[SITIO WEB]</span></div></div>')
    return doc("Post 1080 · Promesa", 1080, 1080, ad_shell(1080, 1080, inner))


def ad_post_b():
    card = (f'<div style="display: flex; flex-direction: column; gap: 18px; padding: 34px 36px; border-radius: 22px; background: {PANEL2}; border: 2px solid {BLUE}">'
            f'<div style="display: flex; justify-content: space-between; align-items: center"><span class="mono" style="font-size: 44px; font-weight: 600">ACME</span>'
            f'<span class="pill" style="font-size: 24px; padding: 6px 18px; color: {INSIDER}; border-color: #6B5320">◆ Directivos</span></div>'
            f'<span style="font-size: 30px; line-height: 1.4; color: {BODY}">3 directivos compraron acciones, el CEO incluido.</span>'
            f'<div style="padding: 20px 24px; border-radius: 14px; background: {BG}; border: 1px solid {BORDER}; display: flex; flex-direction: column; gap: 6px">'
            f'<span style="font-size: 24px; font-weight: 600">Evidencia</span>'
            f'<span style="font-size: 26px; line-height: 1.45; color: {BODY}">[N] eventos parecidos · [X] % llegó al objetivo · [Y] % al stop</span></div></div>')
    inner = (f'<div style="display: flex; flex-direction: column; height: 100%; gap: 40px">'
             f'<span style="font-size: 64px; font-weight: 600; line-height: 1.08; letter-spacing: -.02em">Cuando los directivos compran,<br>'
             f'<span style="color: {BLUE}">MiraTrade te enseña qué pasó las otras veces.</span></span>{card}'
             f'<div style="margin-top: auto; display: flex; justify-content: space-between; align-items: flex-end">{lockup(300, endorsed=True)}'
             f'<span style="max-width: 420px; text-align: right">{foot(16)}</span></div></div>')
    return doc("Post 1080 · Directivos", 1080, 1080, ad_shell(1080, 1080, inner))


def ad_infographic():
    steps = [("01", "Detecta el evento", "Compras nuevas de directivos (formulario 4 de la SEC), opciones con volumen inusual y fondos que pasan del 5 % (13D / 13G).", INSIDER),
             ("02", "Añade contexto", "Tendencia, volumen y estado del mercado. Informan, pero no disparan señales.", OPTIONS),
             ("03", "Busca la evidencia", "Qué pasó con eventos parecidos en cinco años, probado en un periodo y confirmado en otro.", BLUE),
             ("04", "Tú decides", "Practica sin dinero o abre la vista previa en Schwab. Ninguna orden sale sin tu confirmación.", UP)]
    blocks = "".join(f'<div style="display: flex; gap: 28px; padding: 30px 32px; border-radius: 20px; background: {PANEL2}; border-left: 0; border-top: 4px solid {c}">'
                     f'<span class="mono" style="font-size: 54px; font-weight: 600; color: {c}; line-height: 1">{n}</span>'
                     f'<div style="display: flex; flex-direction: column; gap: 10px"><span style="font-size: 36px; font-weight: 600">{t}</span>'
                     f'<span style="font-size: 25px; line-height: 1.45; color: {BODY}">{d}</span></div></div>' for n, t, d, c in steps)
    inner = (f'<div style="display: flex; flex-direction: column; height: 100%; gap: 30px">'
             f'<div style="display: flex; justify-content: space-between; align-items: center">{lockup(280)}'
             f'<span class="mono" style="font-size: 20px; color: {TEXT2}">CÓMO FUNCIONA</span></div>'
             f'<span style="font-size: 60px; font-weight: 600; letter-spacing: -.02em; line-height: 1.08">Del evento a la decisión,<br>en cuatro pasos</span>'
             f'<div style="display: flex; flex-direction: column; gap: 16px">{blocks}</div>'
             f'<div style="margin-top: auto">{foot(17)}</div></div>')
    return doc("Infografía 1080×1350 · Cómo funciona", 1080, 1350, ad_shell(1080, 1350, inner, 64))


def ad_story():
    inner = (glow_grid(1080, 1920) + f'<div style="position: relative; display: flex; flex-direction: column; height: 100%; align-items: center; text-align: center">'
             f'<div style="margin-top: 120px">{mark(260, BG, "MiraTrade")}</div>'
             f'<span style="margin-top: 90px; font-size: 104px; font-weight: 600; line-height: 1.02; letter-spacing: -.03em">Señales con<br>evidencia</span>'
             f'<span style="margin-top: 20px; font-size: 104px; font-weight: 300; line-height: 1.02; color: {BLUE}">no con<br>promesas</span>'
             f'<span style="margin-top: 60px; font-size: 36px; line-height: 1.4; color: {BODY}; max-width: 820px">Directivos, opciones inusuales y grandes fondos, '
             f'contrastados con cinco años de datos.</span>'
             f'<span class="btn primary" style="margin-top: 70px; min-height: 110px; padding: 0 64px; border-radius: 20px; font-size: 38px; font-weight: 600">Descargar para Windows</span>'
             f'<div style="margin-top: auto; display: flex; flex-direction: column; align-items: center; gap: 24px">{lockup(360, endorsed=True)}{foot(22)}</div></div>')
    return doc("Historia 1080×1920", 1080, 1920, ad_shell(1080, 1920, inner, 80))


def ad_header():
    inner = (glow_grid(1500, 500) + f'<div style="position: relative; display: flex; align-items: center; justify-content: space-between; height: 100%; gap: 60px">'
             f'<div style="display: flex; flex-direction: column; gap: 22px; padding-left: 300px">'
             f'<span style="font-size: 58px; font-weight: 600; letter-spacing: -.02em; line-height: 1.05">Señales con evidencia,<br>'
             f'<span style="font-weight: 300; color: {BLUE}">no con promesas.</span></span>'
             f'<span class="mono" style="font-size: 20px; color: {TEXT2}">Directivos ◆ · Opciones ● · 13D / 13G ■</span></div>'
             f'<div style="flex-shrink: 0">{mark(300, BG, "MiraTrade")}</div></div>')
    return doc("Cabecera X / LinkedIn 1500×500", 1500, 500, ad_shell(1500, 500, inner, 60))


def ad_link():
    inner = (f'<div style="display: flex; height: 100%; gap: 50px; align-items: center">'
             f'<div style="flex: 1; display: flex; flex-direction: column; gap: 26px; height: 100%">{lockup(300, endorsed=True)}'
             f'<span style="margin-top: auto; font-size: 50px; font-weight: 600; letter-spacing: -.02em; line-height: 1.08">¿Qué pasó las otras veces que los directivos compraron?</span>'
             f'<span style="font-size: 23px; line-height: 1.4; color: {BODY}">MiraTrade te lo enseña antes de que decidas.</span>'
             f'<div style="margin-top: auto">{foot(15, short=True)}</div></div>'
             f'<div style="flex: 0 0 440px; display: flex; flex-direction: column; gap: 12px">{event_card(*EVENTS[0], on=True)}{event_card(*EVENTS[1])}{event_card(*EVENTS[2])}</div></div>')
    return doc("Anuncio 1200×628", 1200, 628, ad_shell(1200, 628, inner, 52))


def ad_mrec():
    inner = (f'<div style="display: flex; flex-direction: column; height: 100%; gap: 10px">{lockup(150)}'
             f'<span style="margin-top: 6px; font-size: 25px; font-weight: 600; line-height: 1.12; letter-spacing: -.01em">Señales con evidencia, '
             f'<span style="font-weight: 300; color: {BLUE}">no con promesas.</span></span>'
             f'<span class="btn primary" style="margin-top: auto; min-height: 40px; font-size: 14px">Descargar para Windows</span>'
             f'{foot(10.5, short=True)}</div>')
    return doc("Display 300×250", 300, 250, ad_shell(300, 250, inner, 18))


def ad_leader():
    inner = (f'<div style="display: flex; align-items: center; height: 100%; gap: 22px">{mark(52, BG)}'
             f'<span style="font-size: 23px; font-weight: 600; letter-spacing: -.01em; white-space: nowrap">Señales con evidencia, '
             f'<span style="font-weight: 300; color: {BLUE}">no con promesas.</span></span>'
             f'<span style="flex-grow: 1"></span><span style="max-width: 150px">{foot(10, short=True)}</span>'
             f'<span class="btn primary" style="min-height: 44px; font-size: 14px; white-space: nowrap">Descargar</span></div>')
    return doc("Display 728×90", 728, 90, ad_shell(728, 90, inner, 18))


# --------------------------------------------------------------------------- web
WEB_CSS = """.wnav{font-size:15px;color:#C4CCD8;text-decoration:none}
.sec{font-size:44px;font-weight:600;letter-spacing:-.02em;line-height:1.1;margin:0}
.lead{font-size:20px;line-height:1.55;color:#C4CCD8;margin:0}
.body{font-size:17px;line-height:1.65;color:#C4CCD8;margin:0}
"""


def features():
    return [("◆", INSIDER, "Compras de directivos", "Solo compras nuevas en el mercado abierto (formulario 4 de la SEC), no opciones ni regalos. Varias compras en 20 sesiones cuentan como un solo evento."),
            ("●", OPTIONS, "Opciones inusuales", "Contratos con un volumen muy por encima de lo normal, a partir de datos diarios de Schwab y Massive."),
            ("■", D13, "Grandes fondos (13D / 13G)", "Un fondo que supera el 5 % de una empresa y lo declara a la SEC.")]


def w_desktop():
    W = 1440
    nav = (f'<header style="display: flex; align-items: center; gap: 36px; padding: 22px 80px; border-bottom: 1px solid {BORDER}">{lockup(190)}'
           f'<span style="flex-grow: 1"></span>'
           + "".join(f'<a class="wnav" href="#{a}">{t}</a>' for t, a in [("Cómo funciona", "como"), ("Evidencia", "evidencia"), ("Seguridad", "seguridad"), ("Precio", "precio"), ("Preguntas", "faq")])
           + '<a class="btn primary" href="#descargar">Descargar para Windows</a></header>')
    hero = (f'<section style="display: flex; flex-direction: column; align-items: center; text-align: center; gap: 26px; padding: 96px 80px 0">'
            f'<span class="pill" style="border-color: {BORDER2}; color: {TEXT2}; font-size: 13px">Para Windows · mercado de EE. UU.</span>'
            f'<h1 style="margin: 0; font-size: 72px; font-weight: 600; letter-spacing: -.03em; line-height: 1.02">Señales con evidencia,<br>'
            f'<span style="font-weight: 300; color: {BLUE}">no con promesas.</span></h1>'
            f'<p class="lead" style="max-width: 760px">MiraTrade vigila las compras de directivos, las opciones inusuales y los grandes fondos. '
            'Cuando pasa algo, te enseña qué ocurrió las otras veces: los aciertos y los fallos.</p>'
            f'<div style="display: flex; gap: 12px"><a class="btn primary" href="#descargar" style="min-height: 52px; padding: 0 26px; font-size: 16px">Descargar para Windows</a>'
            f'<a class="btn" href="#como" style="min-height: 52px; padding: 0 26px; font-size: 16px">Cómo funciona</a></div>'
            f'<span style="font-size: 13px; color: {TEXT2}">[PRECIO / PRUEBA GRATUITA] · {DISCLAIMER}</span>'
            f'<div style="margin-top: 40px">{app_window(1180, 660)}</div></section>')
    feat = "".join(f'<div class="card" style="padding: 28px; display: flex; flex-direction: column; gap: 12px">'
                   f'<span style="font-size: 26px; color: {c}">{i}</span><span style="font-size: 22px; font-weight: 600">{t}</span><p class="body">{d}</p></div>'
                   for i, c, t, d in features())
    how = (f'<section id="como" style="padding: 120px 80px 0; display: flex; flex-direction: column; gap: 36px">'
           f'<div style="display: flex; flex-direction: column; gap: 14px; max-width: 760px"><span class="lbl">Qué vigila</span>'
           f'<h2 class="sec">Tres eventos que mueven el mercado</h2><p class="lead">Solo los eventos disparan una señal. Los indicadores técnicos '
           'se muestran como contexto, no como motivo para operar.</p></div>'
           f'<div style="display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 20px">{feat}</div></section>')
    ev_steps = [("Se prueba dos veces", "Cada regla se busca en un periodo de cinco años y se confirma en otro distinto. Si no se sostiene en los dos, se descarta."),
                ("Sin trampas de supervivencia", "Cuenta también las empresas que dejaron de cotizar, no solo las que siguen hoy."),
                ("Corrige la suerte", "Al probar muchas reglas, algunas salen bien por azar. MiraTrade ajusta por eso antes de dar nada por bueno."),
                ("Te enseña el resultado entero", "Cuántos casos, cuántos llegaron al objetivo y cuántos al stop. Siempre juntos.")]
    evid = (f'<section id="evidencia" style="padding: 120px 80px 0; display: grid; grid-template-columns: 1fr 1fr; gap: 64px; align-items: center">'
            f'<div style="display: flex; flex-direction: column; gap: 18px"><span class="lbl">Evidencia</span>'
            f'<h2 class="sec">Lo que no se puede comprobar, no se promete</h2>'
            + "".join(f'<div style="display: flex; flex-direction: column; gap: 4px; padding: 14px 0; border-bottom: 1px solid {BORDER}">'
                      f'<span style="font-size: 18px; font-weight: 600">{t}</span><p class="body">{d}</p></div>' for t, d in ev_steps)
            + f'</div><div class="card" style="padding: 32px; display: flex; flex-direction: column; gap: 18px; background: {PANEL2}">'
            f'<span class="lbl">Así se ve una señal</span>{event_card(*EVENTS[0], on=True)}'
            f'<div style="padding: 16px 18px; border-radius: 10px; background: {BG}; border: 1px solid {BORDER}; display: flex; flex-direction: column; gap: 6px">'
            f'<span style="font-size: 16px; font-weight: 600">Evidencia</span><span class="body">[N] eventos parecidos. [X] % llegó al objetivo, [Y] % al stop. '
            'Regla [confirmada / no confirmada] fuera de muestra.</span></div>'
            f'<span style="font-size: 13px; color: {TEXT2}">Datos de ejemplo. Las cifras reales salen del último reporte validado.</span></div></section>')
    safe = [("Modo práctica por defecto", "Empieza sin dinero real. Tú decides cuándo cambiar, y la app lo dice siempre en la cabecera."),
            ("Vista previa en Schwab", "Conecta tu cuenta con la API oficial. Ves la orden completa antes de enviarla."),
            ("Confirmación escrita", "Ninguna orden real sale sin que la confirmes tú, escribiéndolo."),
            ("Detener todo", "Un botón siempre visible cancela la automatización al instante."),
            ("Tus claves, en tu equipo", "Se guardan en el Administrador de credenciales de Windows, no en archivos ni en nuestros servidores.")]
    security = (f'<section id="seguridad" style="padding: 120px 80px 0; display: flex; flex-direction: column; gap: 32px">'
                f'<div style="display: flex; flex-direction: column; gap: 14px; max-width: 760px"><span class="lbl">Tú mandas</span>'
                f'<h2 class="sec">Diseñado para no hacer nada que no hayas decidido</h2></div>'
                f'<div style="display: grid; grid-template-columns: repeat(5, minmax(0, 1fr)); gap: 16px">'
                + "".join(f'<div class="card" style="padding: 22px; display: flex; flex-direction: column; gap: 10px">{tick(UP)}'
                          f'<span style="font-size: 17px; font-weight: 600">{t}</span><p class="small" style="font-size: 14px">{d}</p></div>' for t, d in safe)
                + '</div></section>')
    price = (f'<section id="precio" style="padding: 120px 80px 0; display: flex; justify-content: center">'
             f'<div class="card" style="width: 640px; padding: 44px; display: flex; flex-direction: column; align-items: center; gap: 18px; text-align: center; border-color: {BLUE}; background: {SEL}">'
             f'<span class="lbl">Precio</span><span style="font-size: 56px; font-weight: 600">[PRECIO]</span>'
             f'<p class="body">[QUÉ INCLUYE · PRUEBA GRATUITA · CONDICIONES]</p>'
             f'<a id="descargar" class="btn primary" href="#" style="min-height: 52px; padding: 0 30px; font-size: 16px">Descargar para Windows</a>'
             f'<span style="font-size: 13px; color: {TEXT2}">Windows 10 y 11 · [TAMAÑO] · [VERSIÓN]</span></div></section>')
    faqs = [("¿MiraTrade me dice qué comprar?", "No. Te enseña eventos y lo que pasó con eventos parecidos. La decisión es tuya."),
            ("¿Garantiza beneficios?", "No. Ninguna herramienta puede. Por eso enseña también los fallos."),
            ("¿Necesito una cuenta en un bróker?", "No para practicar. Para ver órdenes reales, una cuenta de Schwab con acceso a su API."),
            ("¿De dónde salen los datos?", "SEC EDGAR (formularios 4, 13D y 13G), FINRA, y datos de mercado de Schwab y Massive.")]
    faq = (f'<section id="faq" style="padding: 120px 80px 0; display: grid; grid-template-columns: 380px 1fr; gap: 64px">'
           f'<div style="display: flex; flex-direction: column; gap: 14px"><span class="lbl">Preguntas</span><h2 class="sec">Claro desde el principio</h2></div><div>'
           + "".join(f'<div style="padding: 20px 0; border-bottom: 1px solid {BORDER}; display: flex; flex-direction: column; gap: 6px">'
                     f'<span style="font-size: 19px; font-weight: 600">{q}</span><p class="body">{a}</p></div>' for q, a in faqs)
           + '</div></section>')
    footer = (f'<footer style="margin-top: 120px; padding: 48px 80px; border-top: 1px solid {BORDER}; background: {PANEL}; display: flex; flex-direction: column; gap: 24px">'
              f'<div style="display: flex; justify-content: space-between; align-items: center">{lockup(260, endorsed=True)}'
              f'<div style="display: flex; gap: 28px">' + "".join(f'<a class="wnav" href="#" style="font-size: 14px">{t}</a>' for t in ["Privacidad", "Términos", "Aviso de riesgo", "Contacto"])
              + f'</div></div><p class="small" style="color: {TEXT2}; max-width: 980px">{DISCLAIMER} Los resultados pasados no garantizan resultados futuros. '
              f'MiraTrade no es un asesor financiero registrado. Schwab es una marca de sus respectivos propietarios. © 2026 Mirandas Group.</p></footer>')
    H = 4600
    inner = (f'<div style="width: {W}px; height: {H}px; background: {BG}; color: {TEXT}; overflow: hidden">'
             f'{nav}{hero}{how}{evid}{security}{price}{faq}{footer}</div>')
    return doc("Web · Inicio (escritorio)", W, H, inner, css=WEB_CSS), H


def w_mobile():
    W = 390
    feat = "".join(f'<div class="card" style="padding: 18px; display: flex; flex-direction: column; gap: 8px">'
                   f'<span style="font-size: 20px; color: {c}">{i}</span><span style="font-size: 18px; font-weight: 600">{t}</span>'
                   f'<p class="small" style="font-size: 14px">{d}</p></div>' for i, c, t, d in features())
    safe = ["Modo práctica por defecto", "Vista previa en Schwab", "Confirmación escrita", "Botón «Detener todo»", "Claves en tu equipo"]
    inner = (f'<div style="width: {W}px; height: 2900px; background: {BG}; color: {TEXT}; overflow: hidden">'
             f'<header style="display: flex; align-items: center; justify-content: space-between; padding: 14px 16px; border-bottom: 1px solid {BORDER}">{lockup(140)}'
             f'<button type="button" aria-label="Abrir menú" class="btn" style="min-width: 44px; padding: 0 12px"><svg width="20" height="20" viewBox="0 0 24 24" fill="none" '
             f'stroke="{TEXT}" stroke-width="2" stroke-linecap="round" aria-hidden="true"><path d="M4 7h16M4 12h16M4 17h16"></path></svg></button></header>'
             f'<section style="padding: 40px 16px 0; display: flex; flex-direction: column; gap: 18px">'
             f'<span class="pill" style="align-self: flex-start; color: {TEXT2}">Para Windows · EE. UU.</span>'
             f'<h1 style="margin: 0; font-size: 40px; font-weight: 600; letter-spacing: -.03em; line-height: 1.05">Señales con evidencia, '
             f'<span style="font-weight: 300; color: {BLUE}">no con promesas.</span></h1>'
             f'<p class="p" style="font-size: 17px">Vigila compras de directivos, opciones inusuales y grandes fondos, y te enseña qué ocurrió las otras veces.</p>'
             f'<a class="btn primary" href="#" style="min-height: 50px; font-size: 16px">Descargar para Windows</a>'
             f'<span style="font-size: 12px; color: {TEXT2}">La app es para PC con Windows. [ENVIARME EL ENLACE POR CORREO]</span>'
             f'<div style="margin-top: 10px">{event_card(*EVENTS[0], on=True)}</div>'
             f'<div style="padding: 14px 16px; border-radius: 10px; background: {PANEL2}; border: 1px solid {BORDER}; display: flex; flex-direction: column; gap: 4px">'
             f'<span style="font-size: 15px; font-weight: 600">Evidencia</span><span class="small" style="font-size: 14px">[N] eventos parecidos. [X] % llegó al objetivo, [Y] % al stop.</span></div>'
             f'<span style="font-size: 12px; color: {TEXT2}">Datos de ejemplo.</span></section>'
             f'<section style="padding: 56px 16px 0; display: flex; flex-direction: column; gap: 14px"><span class="lbl">Qué vigila</span>'
             f'<h2 style="margin: 0; font-size: 30px; font-weight: 600; letter-spacing: -.02em; line-height: 1.1">Tres eventos que mueven el mercado</h2>{feat}</section>'
             f'<section style="padding: 56px 16px 0; display: flex; flex-direction: column; gap: 12px"><span class="lbl">Evidencia</span>'
             f'<h2 style="margin: 0; font-size: 30px; font-weight: 600; letter-spacing: -.02em; line-height: 1.1">Lo que no se puede comprobar, no se promete</h2>'
             f'<p class="p" style="font-size: 16px">Cada regla se prueba en un periodo de cinco años y se confirma en otro. Cuenta las empresas que dejaron de cotizar '
             'y corrige la suerte de probar muchas reglas. Y siempre te enseña aciertos y fallos juntos.</p></section>'
             f'<section style="padding: 56px 16px 0; display: flex; flex-direction: column; gap: 10px"><span class="lbl">Tú mandas</span>'
             + "".join(f'<div style="display: flex; gap: 12px; align-items: center; min-height: 44px; border-bottom: 1px solid {BORDER}">{tick(UP)}'
                       f'<span style="font-size: 16px">{t}</span></div>' for t in safe)
             + f'</section><section style="padding: 56px 16px 0"><div class="card" style="padding: 26px 20px; display: flex; flex-direction: column; gap: 12px; align-items: center; '
             f'text-align: center; background: {SEL}; border-color: {BLUE}"><span class="lbl">Precio</span><span style="font-size: 38px; font-weight: 600">[PRECIO]</span>'
             f'<p class="small" style="font-size: 14px">[QUÉ INCLUYE · PRUEBA GRATUITA]</p></div></section>'
             f'<footer style="margin-top: 56px; padding: 28px 16px; border-top: 1px solid {BORDER}; background: {PANEL}; display: flex; flex-direction: column; gap: 16px">'
             f'{lockup(230, endorsed=True)}<p class="small" style="font-size: 12px; color: {TEXT2}">{DISCLAIMER} Los resultados pasados no garantizan resultados futuros. © 2026 Mirandas Group.</p></footer></div>')
    return doc("Web · Inicio (móvil)", W, 2900, inner, css=WEB_CSS), 2900


# --------------------------------------------------------------------------- write + index
MANUAL = [("MT-01-Portada", m01), ("MT-02-Esencia", m02), ("MT-03-Simbolo", m03), ("MT-04-Construccion", m04),
          ("MT-05-Versiones", m05), ("MT-06-Firma", m06), ("MT-07-Color", m07), ("MT-08-Tipografia", m08),
          ("MT-09-Interfaz", m09), ("MT-10-Graficos", m10), ("MT-11-Voz-usos", m11), ("MT-12-Aplicaciones", m12)]
ADS = [("Ad-Post-Promesa", ad_post_a, 1080, 1080, "Post 1080 · Promesa"), ("Ad-Post-Directivos", ad_post_b, 1080, 1080, "Post 1080 · Directivos"),
       ("Ad-Infografia", ad_infographic, 1080, 1350, "Infografía 1080×1350"), ("Ad-Historia", ad_story, 1080, 1920, "Historia 1080×1920"),
       ("Ad-Cabecera", ad_header, 1500, 500, "Cabecera X / LinkedIn 1500×500"), ("Ad-Enlace", ad_link, 1200, 628, "Anuncio enlace 1200×628"),
       ("Ad-Display-300", ad_mrec, 300, 250, "Display 300×250"), ("Ad-Display-728", ad_leader, 728, 90, "Display 728×90")]

if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    idx = json.loads((OUT / "canvas.json").read_text(encoding="utf-8"))
    for p in ({"id": "manual", "name": "Manual"}, {"id": "publicidad", "name": "Publicidad"}, {"id": "web", "name": "Sitio web"}):
        if p["id"] not in {q["id"] for q in idx["pages"]}:
            idx["pages"].append(p)
    idx["launch"] = {"view": "canvas", "page": "manual"}

    def add(stem, html, x, y, w, h, page, title):
        name = f"{stem}.dc.html"
        (OUT / name).write_text(html, encoding="utf-8")
        idx["boards"][name] = {"x": x, "y": y, "w": w, "h": h, "page": page, "title": title}
        if name not in idx["order"]:
            idx["order"].append(name)

    for i, (stem, fn) in enumerate(MANUAL):
        r, c = divmod(i, 3)
        add(stem, fn(), c * 1520, r * 1020, 1440, 900, "manual", f"{i + 1:02d} · {SECTIONS[i]}")
    # ads: row 1 = square posts + infographic + story; row 2 = header, link ad, display
    pos = {"Ad-Post-Promesa": (0, 0), "Ad-Post-Directivos": (1160, 0), "Ad-Infografia": (2320, 0), "Ad-Historia": (3480, 0),
           "Ad-Cabecera": (0, 2040), "Ad-Enlace": (1580, 2040), "Ad-Display-300": (2860, 2040), "Ad-Display-728": (3240, 2040)}
    for stem, fn, w, h, title in ADS:
        add(stem, fn(), *pos[stem], w, h, "publicidad", title)
    dh, dhh = w_desktop()
    add("Web-Inicio-Escritorio", dh, 0, 0, 1440, dhh, "web", "Inicio · escritorio 1440")
    mh, mhh = w_mobile()
    add("Web-Inicio-Movil", mh, 1520, 0, 390, mhh, "web", "Inicio · móvil 390")
    idx["notes"]["mtManualTitle"] = {"kind": "title1", "maxW": 4400, "page": "manual", "w": 240, "x": 0, "y": -300,
                                     "text": "MiraTrade · Manual de marca v1.0"}
    idx["notes"]["mtAdsTitle"] = {"kind": "title1", "maxW": 4560, "page": "publicidad", "w": 240, "x": 0, "y": -300,
                                  "text": "Publicidad · piezas a tamaño real"}
    idx["notes"]["mtWebTitle"] = {"kind": "title1", "maxW": 1910, "page": "web", "w": 240, "x": 0, "y": -300,
                                  "text": "Sitio web · página de inicio"}
    (OUT / "canvas.json").write_text(json.dumps(idx, ensure_ascii=False, indent=2), encoding="utf-8")
    print(len(MANUAL), "manual,", len(ADS), "ads, 2 web")
