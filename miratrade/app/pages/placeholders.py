"""Screens whose content depends on the next engine step; they say so instead of faking data."""
from __future__ import annotations

from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from miratrade.app.widgets import card, muted


def _page(title: str, intro: str, items: list[str]) -> QWidget:
    page = QWidget()
    page.setObjectName("page")
    lay = QVBoxLayout(page)
    lay.setContentsMargins(24, 20, 24, 20)
    lay.setSpacing(16)
    h = QLabel(title)
    h.setObjectName("h1")
    lay.addWidget(h)
    lay.addWidget(card(muted(intro), *[muted("• " + i) for i in items], title="En construcción"))
    lay.addStretch(1)
    return page


def signals_page() -> QWidget:
    return _page(
        "Señales nuevas",
        "Aquí aparecerán las operaciones nuevas de directivos, los contratos de opciones inusuales y los "
        "filings de smart money de los últimos días, cada una con la probabilidad de alto beneficio que dio "
        "el análisis para eventos parecidos.",
        ["Compras de directivos (Form 4), 13D / 13G y flujo de opciones inusuales, por fecha de publicación.",
         "Para cada evento: qué reglas validadas cumple, su historial fuera de muestra y la operación propuesta "
         "(acción o call a 30/45/60 días, con stop y objetivo).",
         "Gráfico con el evento marcado y botón «Vista previa de la orden»."])


def practice_page() -> QWidget:
    return _page(
        "Práctica",
        "Operaciones en papel con el bróker simulado, con los mismos límites de riesgo que las reales.",
        ["Posiciones y órdenes pendientes, pérdida diaria usada frente al límite.",
         "Curva de resultados de las operaciones cerradas, por regla.",
         "El botón «Detener todo» de la cabecera ya funciona con la cuenta de Schwab."])
