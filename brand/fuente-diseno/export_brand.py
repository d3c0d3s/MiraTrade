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
SIZES = (16, 32, 48, 64, 128, 256, 512, 1024)
INSET = 0.8125                                    # must match pilares.TILE_INSET
app = QApplication.instance() or QApplication(sys.argv)

_src = (HERE / "gen_pilares_mt.py").read_text(encoding="utf-8").split('page = f"""')[0]
mt = {"__file__": str(HERE / "gen_pilares_mt.py")}
exec(_src, mt)


def render_png(svg_text: str, size: int, path: Path):
    img = QImage(size, size, QImage.Format_ARGB32)
    img.fill(QColor(0, 0, 0, 0))
    p = QPainter(img)
    p.setRenderHint(QPainter.Antialiasing)
    QSvgRenderer(QByteArray(svg_text.encode())).render(p, QRectF(0, 0, size, size))
    p.end()
    img.save(str(path))


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
    return ('<svg xmlns="http://www.w3.org/2000/svg" width="560" height="120" viewBox="0 0 560 120">'
            f'<g transform="translate(0 12) scale(1.5)" fill="none">{group_body(96, gold, fg, gold)}</g>'
            f'<text x="116" y="66" font-family="IBM Plex Serif, Georgia, serif" font-size="46" font-weight="600" letter-spacing="5" fill="{fg}">MIRANDAS</text>'
            f'<text x="119" y="96" font-family="IBM Plex Sans, Segoe UI, sans-serif" font-size="16" letter-spacing="10" fill="{gold}">GROUP</text></svg>')


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
    return ('<svg xmlns="http://www.w3.org/2000/svg" width="520" height="120" viewBox="0 0 520 120">'
            f'<g transform="translate(0 10) scale(1.5625)" fill="none">{mt["symbol_body"](100, **kw)}</g>'
            f'<text x="118" y="78" font-family="IBM Plex Sans, Segoe UI, sans-serif" font-size="58" letter-spacing="-2">'
            f'<tspan font-weight="700" fill="{fg}">Mira</tspan><tspan font-weight="300" fill="{accent}">Trade</tspan></text></svg>')


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
    (GROUP_DIR / "firma").mkdir(parents=True, exist_ok=True)
    (GROUP_DIR / "firma" / "mirandas-group-firma-horizontal.svg").write_text(group_lockup(), encoding="utf-8")
    (GROUP_DIR / "firma" / "mirandas-group-firma-horizontal-sobre-claro.svg").write_text(
        group_lockup("#0E1726", "#7F611A"), encoding="utf-8")

    save_set(mt_symbol, MT_DIR / "simbolo", "miratrade-simbolo-fondo-oscuro")
    save_set(lambda s: mt_symbol(s, **LIGHT), MT_DIR / "simbolo", "miratrade-simbolo-fondo-claro")
    save_set(lambda s: mt_symbol(s, **MONO), MT_DIR / "simbolo", "miratrade-simbolo-monocromo")
    save_set(lambda s: mt_symbol(s, arrow="#F4B740"), MT_DIR / "simbolo", "miratrade-simbolo-alternativa-ambar")
    save_set(mt_app_icon, MT_DIR / "icono", "miratrade-icono-app")
    save_ico(mt_app_icon, MT_DIR / "icono" / "miratrade.ico")
    (MT_DIR / "firma").mkdir(parents=True, exist_ok=True)
    (MT_DIR / "firma" / "miratrade-firma-horizontal-fondo-oscuro.svg").write_text(mt_lockup(True), encoding="utf-8")
    (MT_DIR / "firma" / "miratrade-firma-horizontal-fondo-claro.svg").write_text(mt_lockup(False), encoding="utf-8")
    print("exported")
