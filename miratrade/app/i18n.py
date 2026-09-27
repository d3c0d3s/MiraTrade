"""Interface language.

English is the source: every string in the screens is written in English and looked up here, so
an untranslated string still reads correctly instead of showing a key. ``t()`` returns the
translation for the language in the settings, or the English original when there is none.

Adding a language is adding one dict of ``{English: translation}`` to ``CATALOGS``; anything it
leaves out falls back to English on its own.
"""
from __future__ import annotations

LANGUAGES = {"en": "English", "es": "Español"}
DEFAULT = "en"

ES: dict[str, str] = {
    # ---------------------------------------------------------------- navigation and header
    "Signals": "Señales",
    "Practice": "Práctica",
    "Reports": "Reportes",
    "Settings": "Configuración",
    "Go to {name}": "Ir a {name}",
    "● PRACTICE MODE": "● MODO PRÁCTICA",
    "● REAL MONEY ALLOWED": "● DINERO REAL PERMITIDO",
    "Stop everything": "Detener todo",
    "Cancels pending entries and blocks new ones. The stops on open positions stay.":
        "Cancela las entradas pendientes y bloquea nuevas. Los stops de las posiciones abiertas se mantienen.",
    "Pending entry orders at Schwab will be cancelled and new entries blocked.\n"
    "The stops and targets on open positions stay.\n\nContinue?":
        "Se cancelarán las órdenes de entrada pendientes en Schwab y se bloquearán entradas nuevas.\n"
        "Los stops y objetivos de las posiciones abiertas se mantienen.\n\n¿Continuar?",
    "Done. Entries cancelled: {count}. New entries stay blocked until you resume them.":
        "Hecho. Entradas canceladas: {count}. Las nuevas entradas están bloqueadas hasta que las reanudes.",
    "Could not finish: {error}\n\nCheck the orders at Schwab directly.":
        "No se pudo completar: {error}\n\nRevisa las órdenes en Schwab directamente.",
    # ---------------------------------------------------------------- signals
    "New signals": "Señales nuevas",
    "Profile": "Perfil",
    "Size": "Tamaño",
    "Update data": "Actualizar datos",
    "Update data · automatic every {minutes} min": "Actualizar datos · automático cada {minutes} min",
    "Update data · automatic paused": "Actualizar datos · automático en pausa",
    "Outside the {start}–{end} New York window. You can still press it.":
        "Fuera de la franja {start}–{end} de Nueva York. Puedes pulsarlo igualmente.",
    "Cancel": "Cancelar",
    "Filter by ticker": "Filtrar por ticker",
    "Filter the events by ticker": "Filtrar los eventos por ticker",
    "{count} EVENTS": "{count} EVENTOS",
    "{shown} OF {total}": "{shown} DE {total}",
    "No event matching «{text}».": "Ningún evento con «{text}».",
    "No search yet. Press «Update data»: the first time it downloads the SEC Form 4 filings of "
    "those days and can take several minutes. Everything is cached.":
        "Aún no hay búsqueda. Pulsa «Actualizar datos»: la primera vez descarga los Form 4 de la SEC de "
        "esos días y puede tardar varios minutos. Todo queda en caché.",
    "No new event in those days. Try more days.": "Ningún evento nuevo en esos días. Prueba con más días.",
    "This download predates the size filter and did not save the companies' market "
    "capitalisation. Press «Update data», or choose «All» under Size.":
        "Esta descarga es anterior al filtro de tamaño y no guardó la capitalización de las empresas. "
        "Pulsa «Actualizar datos», o elige «Todas» en Tamaño.",
    "Only {days} days downloaded; press «Update data» to bring more.":
        "Solo hay {days} días descargados; pulsa «Actualizar datos» para traer más.",
    "Filtering by size: {tier}.": "Filtrando por tamaño: {tier}.",
    "Show events from the last days": "Mostrar los eventos de los últimos días",
    "Filters what is already downloaded. It does not search again.":
        "Filtra lo ya descargado. No vuelve a buscar.",
    "Filters what is already downloaded by company size. It does not search again.":
        "Filtra lo ya descargado por tamaño de empresa. No vuelve a buscar.",
    "New events": "Eventos nuevos",
    "Chart": "Gráfico",
    "Pick an event to see its chart.": "Elige un evento para ver su gráfico.",
    "Candlestick chart": "Gráfico de velas",
    "event of {date}": "evento del {date}",
    "REFERENCE TRADE": "OPERACIÓN DE REFERENCIA",
    "Evidence": "Evidencia",
    "green: target · coral: stop · grey: neither": "verde: objetivo · coral: stop · gris: ninguno",
    "Similar = same kind of event": "Parecidos = mismo tipo de evento",
    "VALIDATED RULES": "REGLAS VALIDADAS",
    "None yet: the analysis has not confirmed any rule for this profile. Treat the evidence as "
    "history, not as a forecast.":
        "Ninguna todavía: el análisis no ha confirmado ninguna regla para este perfil. Trata la "
        "evidencia como historial, no como predicción.",
    "CONTEXT (DOES NOT TRIGGER SIGNALS)": "CONTEXTO (NO DISPARA SEÑALES)",
    "Nothing remarkable.": "Nada destacable.",
    "There is no report with events: run an analysis under Reports to have evidence.":
        "No hay un reporte con eventos: ejecuta un análisis en Reportes para tener evidencia.",
    "Preview on Schwab": "Vista previa en Schwab",
    "Needs an active Schwab session: the preview comes from the broker.":
        "Necesita una sesión de Schwab activa: la vista previa la da el bróker.",
    "Add to practice": "Añadir a práctica",
    "Analysis, not advice. With options you can lose the whole premium.":
        "Análisis, no asesoramiento. Con opciones puedes perder la prima entera.",
    "Search {span} · {source}": "Búsqueda {span} · {source}",
    "evidence from {name}": "evidencia de {name}",
    "no report with events for the evidence": "sin reporte con eventos para la evidencia",
    "No search yet": "Sin búsqueda todavía",
    "Downloading the last {days} days…": "Descargando los últimos {days} días…",
    "The search ended with an error (code {code}). Check the log.":
        "La búsqueda terminó con error (código {code}). Revisa el registro.",
    "Cancelled. What was downloaded is kept.": "Cancelada. Lo descargado queda en caché.",
    "Open Settings": "Abrir Configuración",
    "Use public web sources": "Usar webs públicas",
    "Yahoo / Stooq, for your personal research only, while you have no broker account connected.":
        "Yahoo / Stooq, solo para tu investigación personal, mientras no tengas conectada una cuenta de bróker.",
    "{reason} Without prices the search cannot start.":
        "{reason} Sin precios, la búsqueda no puede empezar.",
    "Could not check the price source: {error}": "No se pudo comprobar la fuente de precios: {error}",
    # ---------------------------------------------------------------- contract card
    "No contract": "Sin contrato",
    "This profile buys the shares, not an option.": "Este perfil compra la acción, no una opción.",
    "Pick an event.": "Elige un evento.",
    "Premium": "Prima",
    "Delta": "Delta",
    "Cost of 1 contract": "Coste 1 contrato",
    "Theta · $/day": "Theta · $/día",
    "Strike": "Strike",
    "Vega": "Vega",
    "Implied volatility": "Vol. implícita",
    "Above the strike": "Sobre el strike",
    "expires {date} · {days} days · stock at {price} $":
        "vence el {date} · {days} días · acción a {price} $",
    "Sell at {target} $ (+{up} %) · stop at {stop} $ (−{down} %)":
        "Vender en {target} $ (+{up} %) · stop en {stop} $ (−{down} %)",
    "Modelled prices, not quotes. With your account connected the real chain is used.":
        "Precios de modelo, no cotizaciones. Con tu cuenta conectada se usará la cadena real.",
    # ---------------------------------------------------------------- practice
    "Update value": "Actualizar valor",
    "Re-values the open positions with the latest saved prices.":
        "Vuelve a valorar las posiciones abiertas con los últimos precios guardados.",
    "Close the selected one": "Cerrar la seleccionada",
    "Summary": "Resumen",
    "Open": "Abiertas",
    "Closed": "Cerradas",
    "Position": "Posición",
    "Opened": "Abierta",
    "Quantity": "Cantidad",
    "Entry": "Entrada",
    "Now": "Ahora",
    "Stop": "Stop",
    "Target": "Objetivo",
    "Profit": "Ganancia",
    "Event": "Evento",
    "Exit": "Salida",
    "Reason": "Motivo",
    "{open} open · {closed} closed": "{open} abiertas · {closed} cerradas",
    "Saved in {path}": "Se guarda en {path}",
    "You have not added any trade yet. Go to Signals, pick an event and press «Add to practice».":
        "Todavía no has añadido ninguna operación. Ve a Señales, elige un evento y pulsa «Añadir a práctica».",
    "No real money. A call's value is modelled from the stock's price, not a quote.":
        "Sin dinero real. El valor de una call es de modelo, calculado desde el precio de la acción, "
        "no una cotización.",
    "With two closed trades your running result appears here.":
        "Con dos operaciones cerradas aparecerá aquí tu resultado acumulado.",
    "Practice account, trade by trade": "Cuenta de práctica, operación a operación",
    "Sum of each closed trade's result, in the order you closed them.":
        "Suma del resultado de cada operación cerrada, en el orden en que las cerraste.",
    "Account {equity} · invested {invested} · open risk {risk}":
        "Cuenta {equity} · invertido {invested} · riesgo abierto {risk}",
    "Closed {closed} · winners {hit} · realised {realised} · open {unrealised}":
        "Cerradas {closed} · aciertos {hit} · realizado {realised} · abierto {unrealised}",
    "Positions sized on {equity}: {source}.": "Posiciones dimensionadas sobre {equity}: {source}.",
    "fixed practice balance (no broker connected)": "saldo de práctica fijo (sin bróker conectado)",
    "your account could not be read; using the fixed balance":
        "no se pudo leer tu cuenta; usando el saldo fijo",
    "your account returned no balance; using the fixed one": "tu cuenta no devolvió saldo; usando el fijo",
    "real balance of your Schwab account": "saldo real de tu cuenta de Schwab",
    "real balance of your E*TRADE account": "saldo real de tu cuenta de E*TRADE",
    "Pick an open position first.": "Elige primero una posición abierta.",
    "Close {label} at the last known value ({price})?": "¿Cerrar {label} al último valor conocido ({price})?",
    "Result: {result}": "Resultado: {result}",
    "Close position": "Cerrar posición",
    "Closed: {list}.": "Se cerraron: {list}.",
    "No saved price for {list}: update the data under Signals.":
        "Sin precio guardado para {list}: actualiza los datos en Señales.",
    "Pick an event with a contract to add it.": "Elige un evento con contrato para añadirlo.",
    "Added: {quantity} × {label}": "Añadida: {quantity} × {label}",
    "Cost {cost} $ · risk to the stop {risk} $.": "Coste {cost} $ · riesgo hasta el stop {risk} $.",
    "No real money; you will see it on the Practice screen.":
        "Sin dinero real; la verás en la pantalla Práctica.",
    "target": "objetivo",
    "stop": "stop",
    "expiry": "vencimiento",
    "manual close": "cierre manual",
    "{ticker} · shares": "{ticker} · acción",
    "{ticker} {strike} C · expires {expiry}": "{ticker} {strike} C · vence {expiry}",
    # ---------------------------------------------------------------- reports
    "New analysis": "Nuevo análisis",
    "Run analysis": "Ejecutar análisis",
    " days": " días",
    "Analysis period in days": "Periodo del análisis en días",
    "The first time it downloads SEC and FINRA data; it can take hours. Everything is cached and "
    "you can keep using the app.":
        "La primera vez descarga datos de la SEC y FINRA; puede tardar horas. Todo queda en caché y puedes "
        "seguir usando la app.",
    "History": "Historial",
    "No reports yet": "Sin reportes todavía",
    "Charts": "Gráficas",
    "Report": "Reporte",
    "Validated rules": "Reglas validadas",
    "Walk-forward": "Walk-forward",
    "Candidates": "Candidatos",
    "Analysis finished.": "Análisis terminado.",
    "The analysis ended with an error (code {code}). Check the log.":
        "El análisis terminó con error (código {code}). Revisa el registro.",
    "Cancelled. What was downloaded is kept.": "Cancelado. Lo descargado queda en caché.",
    "Result added up, event by event": "Resultado acumulado, evento a evento",
    "Distribution of the results": "Distribución de los resultados",
    "Mean result by kind of event": "Resultado medio por tipo de evento",
    "Mean result by profile": "Resultado medio por perfil",
    "No data for this report.": "Sin datos para este reporte.",
    "This report did not save the per-event results (events.csv).":
        "Este reporte no guardó los resultados por evento (events.csv).",
    "{count} events with a result in profile {variant}. Call prices are modelled, not quotes.":
        "{count} eventos con resultado en el perfil {variant}. Los precios de las calls son de modelo, "
        "no cotizaciones.",
    # ---------------------------------------------------------------- settings
    "Market data": "Datos de mercado",
    "Price history": "Historial de precios",
    "Quotes and options": "Cotizaciones y opciones",
    "Each download brings": "Cada descarga trae",
    "Refresh only": "Actualizar solo",
    "Only when I ask": "Solo cuando yo lo pida",
    "Window (New York)": "Franja (Nueva York)",
    "to": "a",
    "Weekdays only": "Solo de lunes a viernes",
    "On your clock: from {start} to {end}.": "En tu reloj: de {start} a {end}.",
    "Language": "Idioma",
    "Interface language": "Idioma de la interfaz",
    "The app restarts the screens to change language.":
        "La app rehace las pantallas para cambiar de idioma.",
    "Close and open MiraTrade to see it in {name}.":
        "Cierra y abre MiraTrade para verlo en {name}.",
    "Risk": "Riesgo",
    "Real money": "Dinero real",
    "Schwab account": "Cuenta de Schwab",
    "E*TRADE account": "Cuenta de E*TRADE",
    "Save credentials…": "Guardar credenciales…",
    "Save keys…": "Guardar claves…",
    "Sign in to Schwab…": "Iniciar sesión en Schwab…",
    "Sign in to E*TRADE…": "Iniciar sesión en E*TRADE…",
    "Sign out": "Cerrar sesión",
    "Save changes": "Guardar cambios",
    "Saved.": "Guardado.",
    "Saved in {path}": "Se guarda en {path}",
}

CATALOGS: dict[str, dict[str, str]] = {"es": ES}
_language = DEFAULT


def set_language(code: str) -> str:
    """Pick the language for later ``t()`` calls; an unknown code falls back to English."""
    global _language
    _language = code if code in LANGUAGES else DEFAULT
    return _language


def language() -> str:
    return _language


def t(text: str, **fields) -> str:
    """The text in the current language, with ``{placeholders}`` filled in. An English string
    with no translation is returned as it is, so nothing ever shows as a missing key."""
    translated = CATALOGS.get(_language, {}).get(text, text)
    return translated.format(**fields) if fields else translated


def missing(code: str) -> list[str]:
    """English strings with no translation in ``code``; used by the tests to keep catalogs honest."""
    catalog = CATALOGS.get(code, {})
    return [s for s in ES if s not in catalog] if code != "es" else []
