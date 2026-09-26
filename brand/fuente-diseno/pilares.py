"""Mirandas Group "Pilares" geometry — the single source for every brand's frame and bars.

All marks are drawn on a 64-unit grid. Every brand uses exactly this frame and these three
bars; only colours (and each brand's own extra element, e.g. MiraTrade's arrow) change.
"""

FRAME = dict(x=7, y=9, w=50, h=50, rx=13)
BARS = ((18, 21, 7, 27), (28.5, 21, 7, 15), (39, 21, 7, 27))   # left, centre (hangs from the top), right
BAR_RX = 2
TILE_RX = 14                                   # app-icon tile corner radius
TILE_INSET = "translate(6 6) scale(0.8125)"     # symbol inside the app-icon tile (same for all brands)


def frame_stroke(size: float) -> float:
    """Frame thickness by rendered size: thicker when small so the frame stays visible."""
    return 3.4 if size >= 64 else 4.2 if size >= 40 else 5.0 if size >= 24 else 6.0


def detail_scale(size: float) -> float:
    """Multiplier for brand details (arrows, halos) at the same size breakpoints."""
    return 1.0 if size >= 64 else 1.2 if size >= 40 else 1.45 if size >= 24 else 1.9


def frame(size: float, color: str) -> str:
    f = FRAME
    return (f'<rect x="{f["x"]}" y="{f["y"]}" width="{f["w"]}" height="{f["h"]}" rx="{f["rx"]}" '
            f'stroke="{color}" stroke-width="{frame_stroke(size)}"/>')


def bars(side: str, centre: str, halo: str | None = None, halo_width: float = 0.0) -> str:
    """The three bars. ``halo`` draws a background-coloured outline *behind* them (for marks where
    something passes behind the bars) without making the bars any narrower."""
    out = []
    if halo:
        for x, y, w, h in BARS:
            out.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{BAR_RX}" fill="{halo}" '
                       f'stroke="{halo}" stroke-width="{halo_width:.2f}" stroke-linejoin="round"/>')
    for (x, y, w, h), c in zip(BARS, (side, centre, side)):
        out.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{BAR_RX}" fill="{c}"/>')
    return "".join(out)


def svg(size: float, body: str) -> str:
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{size}" height="{size}" viewBox="0 0 64 64" '
            f'fill="none">{body}</svg>')


def tile(size: float, bg: str, body: str) -> str:
    """App icon: rounded tile with the symbol inset the same way for every brand."""
    return svg(size, f'<rect x="0" y="0" width="64" height="64" rx="{TILE_RX}" fill="{bg}"/>'
                     f'<g transform="{TILE_INSET}">{body}</g>')
