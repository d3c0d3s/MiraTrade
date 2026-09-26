"""Export each brand's graphics as separate files (SVG + PNG sizes + ICO) into the brand folders."""
import importlib.util
import sys
from pathlib import Path

from PySide6.QtCore import QByteArray, QRectF
from PySide6.QtGui import QColor, QImage, QPainter
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import QApplication

HERE = Path(__file__).parent
ROOT = Path("D:/MyDocs/Projects/MirandasGroup")
GROUP_DIR = ROOT / "Brand" / "Mirandas Group"
MT_DIR = ROOT / "MiraTrade" / "brand"
SIZES = (16, 32, 48, 64, 128, 256, 512, 1024)
app = QApplication.instance() or QApplication(sys.argv)


def render_png(svg: str, size: int, path: Path, bg: str | None = None):
    img = QImage(size, size, QImage.Format_ARGB32)
    img.fill(QColor(bg) if bg else QColor(0, 0, 0, 0))
    p = QPainter(img)
    p.setRenderHint(QPainter.Antialiasing)
    QSvgRenderer(QByteArray(svg.encode())).render(p, QRectF(0, 0, size, size))
    p.end()
    img.save(str(path))


def save_set(svg_by_size, folder: Path, name: str, bg: str | None = None, sizes=SIZES):
    """svg_by_size(size) -> svg text (small sizes may use a simplified drawing)."""
    folder.mkdir(parents=True, exist_ok=True)
    (folder / f"{name}.svg").write_text(svg_by_size(512), encoding="utf-8")
    png_dir = folder / "png"
    png_dir.mkdir(exist_ok=True)
    for s in sizes:
        render_png(svg_by_size(s), s, png_dir / f"{name}-{s}.png", bg)


def save_ico(svg_by_size, path: Path, bg: str | None = None):
    """Multi-size Windows icon from PNGs rendered at each size (via Pillow if present, else Qt 256)."""
    tmp = []
    for s in (16, 24, 32, 48, 64, 128, 256):
        f = path.parent / f"_ico_{s}.png"
        render_png(svg_by_size(s), s, f, bg)
        tmp.append(f)
    try:
        from PIL import Image
        imgs = [Image.open(f) for f in tmp]
        imgs[-1].save(path, sizes=[i.size for i in imgs], append_images=imgs[:-1])
    except ImportError:
        QImage(str(tmp[-1])).save(str(path))
    for f in tmp:
        f.unlink()


# --------------------------------------------------------------------------- Mirandas Group (Pilares)
def group_symbol(size, frame="#C9A24A", side="#F5F1E8", mid="#C9A24A"):
    sw = 3.2 if size >= 64 else 4.2 if size >= 32 else 5.5
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{size}" height="{size}" viewBox="0 0 64 64" fill="none">'
            f'<rect x="7" y="9" width="50" height="50" rx="13" stroke="{frame}" stroke-width="{sw}"/>'
            f'<rect x="18" y="21" width="7" height="27" rx="2" fill="{side}"/>'
            f'<rect x="28.5" y="21" width="7" height="15" rx="2" fill="{mid}"/>'
            f'<rect x="39" y="21" width="7" height="27" rx="2" fill="{side}"/></svg>')


def group_app_icon(size):
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{size}" height="{size}" viewBox="0 0 64 64" fill="none">'
            '<rect x="0" y="0" width="64" height="64" rx="14" fill="#0E1726"/>'
            + group_symbol(size).split('fill="none">', 1)[1])


def group_lockup(fg="#F5F1E8", gold="#C9A24A", mid=None):
    mid = mid or gold
    inner = group_symbol(96, gold, fg, mid).split('fill="none">', 1)[1].rsplit("</svg>", 1)[0]
    sym = f'<g transform="translate(0 12) scale(1.5)" fill="none">{inner}</g>'
    return ('<svg xmlns="http://www.w3.org/2000/svg" width="560" height="120" viewBox="0 0 560 120">' + sym +
            f'<text x="116" y="66" font-family="IBM Plex Serif, Georgia, serif" font-size="46" font-weight="600" letter-spacing="5" fill="{fg}">MIRANDAS</text>'
            f'<text x="119" y="96" font-family="IBM Plex Sans, Segoe UI, sans-serif" font-size="16" letter-spacing="10" fill="{gold}">GROUP</text></svg>')


# --------------------------------------------------------------------------- MiraTrade (pilares + flecha)
MT_GEN = next(p for p in (HERE / "gen_pilares_mt.py", HERE / "brand" / "gen_pilares_mt.py",
                          ROOT / "MiraTrade" / "brand" / "fuente-diseno" / "gen_pilares_mt.py") if p.exists())
src = MT_GEN.read_text(encoding="utf-8").split("GROUP = (")[0]
mt = {}
exec(src, mt)


def mt_svg(size, **kw):
    small = dict(sw=1.2) if 33 <= size <= 48 else dict(sw=1.45, head_len=10, half=6) if 24 <= size <= 32 else \
        dict(sw=1.9, head_len=12, half=7.5) if size < 24 else {}
    svg = mt["symbol"](size, **{**small, **kw})
    return svg.replace("<svg ", '<svg xmlns="http://www.w3.org/2000/svg" ', 1)


def mt_app_icon(size):
    """Symbol inset in the rounded tile so the arrow and its dark edge never leave the tile."""
    inner = mt_svg(size, bg="#12161D").split(">", 1)[1].rsplit("</svg>", 1)[0]
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{size}" height="{size}" viewBox="0 0 64 64" fill="none">'
            '<rect x="0" y="0" width="64" height="64" rx="14" fill="#12161D"/>'
            f'<g transform="translate(6 6) scale(0.8125)">{inner}</g></svg>')


def mt_lockup(dark=True):
    bg = "#0B0E13" if dark else "#F5F7FB"
    kw = {} if dark else dict(bg=bg, frame="#2F5BC8", side="#0E1726", mid="#2F5BC8", arrow="#0E8A5F")
    sym = mt_svg(100, **kw).split(">", 1)[1].rsplit("</svg>", 1)[0]
    fg, accent = ("#E6EAF2", "#6E9BFF") if dark else ("#0E1726", "#2F5BC8")
    return ('<svg xmlns="http://www.w3.org/2000/svg" width="520" height="120" viewBox="0 0 520 120">'
            f'<g transform="translate(0 10) scale(1.5625)" fill="none">{sym}</g>'
            f'<text x="118" y="78" font-family="IBM Plex Sans, Segoe UI, sans-serif" font-size="58" letter-spacing="-2">'
            f'<tspan font-weight="700" fill="{fg}">Mira</tspan><tspan font-weight="300" fill="{accent}">Trade</tspan></text></svg>')


if __name__ == "__main__":
    # Group
    save_set(lambda s: group_symbol(s), GROUP_DIR / "simbolo", "mirandas-group-simbolo")
    save_set(lambda s: group_symbol(s, "#7F611A", "#0E1726", "#7F611A"), GROUP_DIR / "simbolo", "mirandas-group-simbolo-sobre-claro")
    save_set(lambda s: group_symbol(s, "#F5F1E8", "#F5F1E8", "#A7B0BE"), GROUP_DIR / "simbolo", "mirandas-group-simbolo-monocromo-claro")
    save_set(lambda s: group_symbol(s, "#0E1726", "#0E1726", "#5B6472"), GROUP_DIR / "simbolo", "mirandas-group-simbolo-monocromo-oscuro")
    save_set(group_app_icon, GROUP_DIR / "icono", "mirandas-group-icono-app")
    save_ico(group_app_icon, GROUP_DIR / "icono" / "mirandas-group.ico")
    (GROUP_DIR / "firma").mkdir(parents=True, exist_ok=True)
    (GROUP_DIR / "firma" / "mirandas-group-firma-horizontal.svg").write_text(group_lockup(), encoding="utf-8")
    (GROUP_DIR / "firma" / "mirandas-group-firma-horizontal-sobre-claro.svg").write_text(
        group_lockup("#0E1726", "#7F611A"), encoding="utf-8")
    # MiraTrade
    save_set(lambda s: mt_svg(s), MT_DIR / "simbolo", "miratrade-simbolo-fondo-oscuro")
    save_set(lambda s: mt_svg(s, bg="#F5F7FB", frame="#2F5BC8", side="#0E1726", mid="#2F5BC8", arrow="#0E8A5F"),
             MT_DIR / "simbolo", "miratrade-simbolo-fondo-claro", bg=None)
    save_set(lambda s: mt_svg(s, bg="#0F131A", frame="#E6EAF2", side="#E6EAF2", mid="#8A93A3", arrow="#E6EAF2"),
             MT_DIR / "simbolo", "miratrade-simbolo-monocromo")
    save_set(lambda s: mt_svg(s, arrow="#F4B740"), MT_DIR / "simbolo", "miratrade-simbolo-alternativa-ambar")
    save_set(mt_app_icon, MT_DIR / "icono", "miratrade-icono-app")
    save_ico(mt_app_icon, MT_DIR / "icono" / "miratrade.ico")
    (MT_DIR / "firma").mkdir(parents=True, exist_ok=True)
    (MT_DIR / "firma" / "miratrade-firma-horizontal-fondo-oscuro.svg").write_text(mt_lockup(True), encoding="utf-8")
    (MT_DIR / "firma" / "miratrade-firma-horizontal-fondo-claro.svg").write_text(mt_lockup(False), encoding="utf-8")
    print("exported")
