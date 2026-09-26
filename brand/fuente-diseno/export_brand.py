"""Export each brand's graphics as separate files (SVG + PNG sizes + ICO) into the brand folders.

Frame, bars and app-icon tile come from pilares.py, so every Mirandas Group brand keeps exactly
the same proportions; MiraTrade's arrow comes from gen_pilares_mt.py.
"""
import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
from PySide6.QtCore import QByteArray, QRectF  # noqa: E402
from PySide6.QtGui import QColor, QImage, QPainter  # noqa: E402
from PySide6.QtSvg import QSvgRenderer  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from pilares import bars, frame, svg, tile  # noqa: E402

ROOT = Path("D:/MyDocs/Projects/MirandasGroup")
GROUP_DIR = ROOT / "Brand" / "Mirandas Group"
MT_DIR = ROOT / "MiraTrade" / "brand"
FONT_DIR = ROOT / "Brand" / "Tipografia" / "IBM Plex"
SIZES = (16, 32, 48, 64, 128, 256, 512, 1024)
INSET = 0.8125                                    # must match pilares.TILE_INSET
app = QApplication.instance() or QApplication(sys.argv)

from PySide6.QtGui import QFont, QFontDatabase, QFontMetricsF, QPainterPath  # noqa: E402

FONTS_OK = False
for ttf in sorted(FONT_DIR.glob("*.ttf")):        # wordmarks are outlined from IBM Plex
    FONTS_OK |= QFontDatabase.addApplicationFont(str(ttf)) != -1
if not FONTS_OK:
    sys.exit(f"IBM Plex not found in {FONT_DIR}: the wordmarks would be outlined in a fallback font")

_src = (HERE / "gen_pilares_mt.py").read_text(encoding="utf-8").split('page = f"""')[0]
mt = {"__file__": str(HERE / "gen_pilares_mt.py")}
exec(_src, mt)


def outline(text: str, family: str, weight: int, px: float, x: float, y: float, fill: str,
            spacing: float = 0.0) -> tuple[str, float]:
    """Text as an SVG path (logo files must not depend on installed fonts); returns (path, end x)."""
    font = QFont(family)
    font.setPixelSize(round(px))
    font.setWeight(QFont.Weight(weight))
    font.setLetterSpacing(QFont.AbsoluteSpacing, spacing)
    qp = QPainterPath()
    qp.addText(x, y, font, text)
    d, i = [], 0
    while i < qp.elementCount():
        e = qp.elementAt(i)
        if e.isMoveTo():
            d.append(f"M{e.x:.2f} {e.y:.2f}")
        elif e.isLineTo():
            d.append(f"L{e.x:.2f} {e.y:.2f}")
        else:                                       # curveTo + two control-data elements
            c1, c2 = qp.elementAt(i + 1), qp.elementAt(i + 2)
            d.append(f"C{e.x:.2f} {e.y:.2f} {c1.x:.2f} {c1.y:.2f} {c2.x:.2f} {c2.y:.2f}")
            i += 2
        i += 1
    end = x + QFontMetricsF(font).horizontalAdvance(text)
    return f'<path fill="{fill}" d="{"".join(d)}"/>', end


def render_png(svg_text: str, size: int, path: Path):
    img = QImage(size, size, QImage.Format_ARGB32)
    img.fill(QColor(0, 0, 0, 0))
    p = QPainter(img)
    p.setRenderHint(QPainter.Antialiasing)
    QSvgRenderer(QByteArray(svg_text.encode())).render(p, QRectF(0, 0, size, size))
    p.end()
    img.save(str(path))


def save_lockup(svg_text: str, folder: Path, name: str, w: int, h: int):
    """Wordmark lockup (text already outlined): SVG plus transparent PNG at 1x, 2x and 4x."""
    folder.mkdir(parents=True, exist_ok=True)
    (folder / f"{name}.svg").write_text(svg_text, encoding="utf-8")
    (folder / "png").mkdir(exist_ok=True)
    for k in (1, 2, 4):
        img = QImage(w * k, h * k, QImage.Format_ARGB32)
        img.fill(QColor(0, 0, 0, 0))
        p = QPainter(img)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.TextAntialiasing)
        QSvgRenderer(QByteArray(svg_text.encode())).render(p, QRectF(0, 0, w * k, h * k))
        p.end()
        img.save(str(folder / "png" / f"{name}@{k}x.png"))


def save_set(make, folder: Path, name: str):
    """make(size) -> svg; small sizes get their own drawing (thicker frame and details)."""
    folder.mkdir(parents=True, exist_ok=True)
    (folder / f"{name}.svg").write_text(make(512), encoding="utf-8")
    (folder / "png").mkdir(exist_ok=True)
    for s in SIZES:
        render_png(make(s), s, folder / "png" / f"{name}-{s}.png")


def save_ico(make, path: Path):
    """Windows icon; multi-size with Pillow when installed, else the 256 px image."""
    pngs = []
    for s in (16, 24, 32, 48, 64, 128, 256):
        f = path.parent / f"_ico_{s}.png"
        render_png(make(s), s, f)
        pngs.append(f)
    try:
        from PIL import Image
        imgs = [Image.open(f) for f in pngs]
        imgs[-1].save(path, sizes=[i.size for i in imgs], append_images=imgs[:-1])
    except ImportError:
        QImage(str(pngs[-1])).save(str(path))
    for f in pngs:
        f.unlink()


# --------------------------------------------------------------------------- Mirandas Group
def group_body(size, frame_c="#C9A24A", side="#F5F1E8", centre="#C9A24A"):
    return frame(size, frame_c) + bars(side, centre)


def group_symbol(size, **kw):
    return svg(size, group_body(size, **kw))


def group_app_icon(size):
    return tile(size, "#0E1726", group_body(size * INSET))


def group_lockup(fg="#F5F1E8", gold="#C9A24A"):
    name, _ = outline("MIRANDAS", "IBM Plex Serif", 600, 46, 116, 66, fg, spacing=5)
    group, _ = outline("GROUP", "IBM Plex Sans", 400, 16, 119, 96, gold, spacing=10)
    return ('<svg xmlns="http://www.w3.org/2000/svg" width="560" height="120" viewBox="0 0 560 120">'
            f'<g transform="translate(0 12) scale(1.5)" fill="none">{group_body(96, gold, fg, gold)}</g>'
            f'{name}{group}</svg>')


def centred(text, family, weight, px, y, fill, spacing, width):
    """Outline ``text`` centred in ``width`` (the trailing letter-spacing is not counted)."""
    _, end = outline(text, family, weight, px, 0, y, fill, spacing)
    return outline(text, family, weight, px, (width - (end - spacing)) / 2, y, fill, spacing)[0]


def group_lockup_v(fg="#F5F1E8", gold="#C9A24A"):
    """Stacked lockup: symbol above, MIRANDAS / GROUP centred below."""
    return ('<svg xmlns="http://www.w3.org/2000/svg" width="360" height="200" viewBox="0 0 360 200">'
            f'<g transform="translate(132 0) scale(1.5)" fill="none">{group_body(96, gold, fg, gold)}</g>'
            f'{centred("MIRANDAS", "IBM Plex Serif", 600, 40, 146, fg, 5, 360)}'
            f'{centred("GROUP", "IBM Plex Sans", 400, 15, 180, gold, 10, 360)}</svg>')


def group_mini(size, dark=True):
    """Small group mark for endorsements (uses the small-size frame automatically)."""
    return group_body(size, "#C9A24A", "#F5F1E8", "#C9A24A") if dark else \
        group_body(size, "#7F611A", "#0E1726", "#7F611A")


# --------------------------------------------------------------------------- MiraTrade
LIGHT = dict(bg="#F5F7FB", frame_c="#2F5BC8", side="#0E1726", mid="#2F5BC8", arrow="#0E8A5F")
MONO = dict(bg="#0F131A", frame_c="#E6EAF2", side="#E6EAF2", mid="#8A93A3", arrow="#E6EAF2")


def mt_symbol(size, **kw):
    return svg(size, mt["symbol_body"](size, **kw))


def mt_app_icon(size):
    return tile(size, "#12161D", mt["symbol_body"](size * INSET, bg="#12161D"))


def mt_lockup(dark=True):
    kw = {} if dark else LIGHT
    fg, accent = ("#E6EAF2", "#6E9BFF") if dark else ("#0E1726", "#2F5BC8")
    mira, end = outline("Mira", "IBM Plex Sans", 700, 58, 118, 78, fg, spacing=-2)
    trade, _ = outline("Trade", "IBM Plex Sans", 300, 58, end, 78, accent, spacing=-2)
    return ('<svg xmlns="http://www.w3.org/2000/svg" width="520" height="120" viewBox="0 0 520 120">'
            f'<g transform="translate(0 10) scale(1.5625)" fill="none">{mt["symbol_body"](100, **kw)}</g>'
            f'{mira}{trade}</svg>')


def mt_lockup_endorsed(dark=True):
    """MiraTrade lockup plus the group endorsement line, aligned with the wordmark."""
    base = mt_lockup(dark)
    grey = "#A7B0BE" if dark else "#4A5261"
    text, _ = outline("a Mirandas Group company", "IBM Plex Sans", 400, 15, 148, 114, grey, spacing=0.6)
    mini = f'<g transform="translate(119 96) scale(0.34375)" fill="none">{group_mini(22, dark)}</g>'
    return (base.replace('height="120" viewBox="0 0 520 120"', 'height="126" viewBox="0 0 520 126"')
            .replace("</svg>", f"{mini}{text}</svg>"))


if __name__ == "__main__":
    save_set(group_symbol, GROUP_DIR / "simbolo", "mirandas-group-simbolo")
    save_set(lambda s: group_symbol(s, frame_c="#7F611A", side="#0E1726", centre="#7F611A"),
             GROUP_DIR / "simbolo", "mirandas-group-simbolo-sobre-claro")
    save_set(lambda s: group_symbol(s, frame_c="#F5F1E8", side="#F5F1E8", centre="#A7B0BE"),
             GROUP_DIR / "simbolo", "mirandas-group-simbolo-monocromo-claro")
    save_set(lambda s: group_symbol(s, frame_c="#0E1726", side="#0E1726", centre="#5B6472"),
             GROUP_DIR / "simbolo", "mirandas-group-simbolo-monocromo-oscuro")
    save_set(group_app_icon, GROUP_DIR / "icono", "mirandas-group-icono-app")
    save_ico(group_app_icon, GROUP_DIR / "icono" / "mirandas-group.ico")
    save_lockup(group_lockup(), GROUP_DIR / "firma", "mirandas-group-firma-horizontal", 560, 120)
    save_lockup(group_lockup("#0E1726", "#7F611A"), GROUP_DIR / "firma",
                "mirandas-group-firma-horizontal-sobre-claro", 560, 120)
    save_lockup(group_lockup_v(), GROUP_DIR / "firma", "mirandas-group-firma-vertical", 360, 200)
    save_lockup(group_lockup_v("#0E1726", "#7F611A"), GROUP_DIR / "firma",
                "mirandas-group-firma-vertical-sobre-claro", 360, 200)

    save_set(mt_symbol, MT_DIR / "simbolo", "miratrade-simbolo-fondo-oscuro")
    save_set(lambda s: mt_symbol(s, **LIGHT), MT_DIR / "simbolo", "miratrade-simbolo-fondo-claro")
    save_set(lambda s: mt_symbol(s, **MONO), MT_DIR / "simbolo", "miratrade-simbolo-monocromo")
    save_set(lambda s: mt_symbol(s, arrow="#F4B740"), MT_DIR / "simbolo", "miratrade-simbolo-alternativa-ambar")
    save_set(mt_app_icon, MT_DIR / "icono", "miratrade-icono-app")
    save_ico(mt_app_icon, MT_DIR / "icono" / "miratrade.ico")
    save_lockup(mt_lockup(True), MT_DIR / "firma", "miratrade-firma-horizontal-fondo-oscuro", 520, 120)
    save_lockup(mt_lockup(False), MT_DIR / "firma", "miratrade-firma-horizontal-fondo-claro", 520, 120)
    save_lockup(mt_lockup_endorsed(True), MT_DIR / "firma", "miratrade-firma-respaldo-fondo-oscuro", 520, 126)
    save_lockup(mt_lockup_endorsed(False), MT_DIR / "firma", "miratrade-firma-respaldo-fondo-claro", 520, 126)
    print("exported")
