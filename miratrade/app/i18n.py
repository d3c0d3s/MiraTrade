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
    # ---------------------------------------------------------------- what the event was
    "an executive officer buys": "compra un directivo ejecutivo",
    "$250,000 or more": "250.000 $ o más",
    "2 insiders or more": "2 directivos o más",
    "$1M or more in bullish premium": "1 M$ o más en primas alcistas",
    "13G from a non-index fund": "13G de un fondo no indexado",
    "13D (active intent)": "13D (intención activa)",
    "1 insider bought {amount}": "1 directivo compró {amount}",
    "{count} insiders bought {amount}": "{count} directivos compraron {amount}",
    "{filer} filed a {kind}": "{filer} presentó un {kind}",
    "{filer} filed a {kind} (amended)": "{filer} presentó un {kind} (modificación)",
    "options with unusual volume": "opciones con volumen inusual",
    "new event": "evento nuevo",
    # ---------------------------------------------------------------- the technical picture
    "Trending up (above its 20 and 50 averages)": "Tendencia al alza (por encima de sus medias de 20 y 50)",
    "Above its 200-session average": "Por encima de su media de 200 sesiones",
    "Up over the last 20 sessions": "Sube en las últimas 20 sesiones",
    "Low RSI (under 40)": "RSI bajo (menos de 40)",
    "High RSI (over 60)": "RSI alto (más de 60)",
    "Volume 1.5 times the usual": "Volumen 1,5 veces lo habitual",
    "Market (SPY) above its 50 average": "El mercado (SPY) por encima de su media de 50",
    "Little short selling": "Poca venta en corto",
    "Heavy short selling": "Mucha venta en corto",
    "Unusually high off-exchange volume (dark pool)": "Volumen fuera de bolsa inusualmente alto (dark pool)",
    "Unusually low off-exchange volume": "Volumen fuera de bolsa inusualmente bajo",
    # ---------------------------------------------------------------- evidence and profiles
    "Outcome profile for the evidence": "Perfil de resultado para la evidencia",
    "No similar event in the latest report.": "Sin eventos parecidos en el último reporte.",
    "{n} similar events: {target} reached the target first, {stop} the stop and "
    "{neither} neither. Average result {mean} %.":
        "{n} eventos parecidos: {target} llegó antes al objetivo, {stop} al stop y {neither} a ninguno. "
        "Resultado medio {mean} %.",
    "Stock {months} months": "Acción {months} meses",
    "Call {days} days": "Call {days} días",
    # ---------------------------------------------------------------- company size
    "All": "Todas",
    "Mega · $200B or more": "Mega · 200.000 M$ o más",
    "Large · $10B to $200B": "Grandes · 10.000 a 200.000 M$",
    "Mid · $2B to $10B": "Medianas · 2.000 a 10.000 M$",
    "Small · $300M to $2B": "Pequeñas · 300 a 2.000 M$",
    "Micro · under $300M": "Micro · menos de 300 M$",
    "Mid and above · $2B or more": "Medianas o mayores · 2.000 M$ o más",
    "Company size": "Tamaño de empresa",
    "Narrows the companies to download and simulate. It saves time; over the 5-year analysis no "
    "size band showed an edge on its own.":
        "Reduce las empresas a descargar y simular. Ahorra tiempo; en el análisis de 5 años ningún "
        "tramo de tamaño mostró ventaja por sí solo.",
    "Every size: {kept} companies.": "Todos los tamaños: {kept} empresas.",
    "Size «{tier}»: {kept} companies; {off} outside the band and {unknown} with no size figure.":
        "Tamaño «{tier}»: {kept} empresas; {off} fuera del tramo y {unknown} sin dato de tamaño.",
    # ---------------------------------------------------------------- price sources
    "Schwab (your account)": "Schwab (tu cuenta)",
    "Public websites: Yahoo / Stooq (personal research only)":
        "Webs públicas: Yahoo / Stooq (solo investigación personal)",
    "Prices from public websites (Yahoo / Stooq): for your personal research only.":
        "Precios de webs públicas (Yahoo / Stooq): solo para tu investigación personal.",
    "Prices come from your Schwab account and your app credentials are missing.":
        "Los precios vienen de tu cuenta de Schwab y faltan las credenciales de tu app.",
    "Prices come from your Schwab account and you have not signed in yet.":
        "Los precios vienen de tu cuenta de Schwab y falta iniciar sesión.",
    "Prices come from your Schwab account and the session expired.":
        "Los precios vienen de tu cuenta de Schwab y la sesión caducó.",
    "Prices from your Schwab account (session good for {days} more days).":
        "Precios de tu cuenta de Schwab (sesión válida {days} días más).",
    "Could not check the Schwab session: {error}.": "No se pudo comprobar la sesión de Schwab: {error}.",
    # ---------------------------------------------------------------- charts
    "No data in this report.": "Sin datos para este reporte.",
    "Cumulative result, event by event": "Resultado acumulado, evento a evento",
    "Sum of each event's result, in the order they happened. The vertical line separates the "
    "discovery period from the confirmation one.":
        "Suma de los resultados de cada evento, en el orden en que ocurrieron. La línea vertical "
        "separa el periodo de descubrimiento del de confirmación.",
    "confirmation →": "confirmación →",
    "How the results were distributed": "Distribución de los resultados",
    "Each bar counts events. The ends include the rarest results.":
        "Cada barra cuenta eventos. Los extremos incluyen los resultados más raros.",
    "Insiders": "Directivos",
    "Options": "Opciones",
    "13D / 13G": "13D / 13G",
    "Pick an event to see its chart.": "Elige un evento para ver su gráfico.",
    "Candlestick chart": "Gráfico de velas",
    # ---------------------------------------------------------------- reports
    "New analysis": "Nuevo análisis",
    " days": " días",
    "Length of the analysis in days": "Periodo del análisis en días",
    "Run analysis": "Ejecutar análisis",
    "The first time it downloads SEC and FINRA data and can take hours. Everything is cached and "
    "you can keep using the app.":
        "La primera vez descarga datos de la SEC y FINRA; puede tardar horas. Todo queda en caché y "
        "puedes seguir usando la app.",
    "History": "Historial",
    "No report yet": "Sin reportes todavía",
    "Charts": "Gráficas",
    "Report": "Reporte",
    "Validated rules": "Reglas validadas",
    "Walk-forward": "Walk-forward",
    "Candidates": "Candidatos",
    "Outcome profile": "Perfil de resultado",
    "Average result by kind of event": "Resultado medio por tipo de evento",
    "Average result by profile": "Resultado medio por perfil",
    "This report did not save the per-event results (events.csv).":
        "Este reporte no guardó los resultados por evento (events.csv).",
    "target +{pct} %": "objetivo +{pct} %",
    "stop −{pct} %": "stop −{pct} %",
    "Only the kind of event counts here, not the rules.": "Solo cuenta el tipo de evento, no las reglas.",
    "Each profile is one combination of instrument, target and stop.":
        "Cada perfil es una combinación de instrumento, objetivo y stop.",
    "{count} events with a result in the {variant} profile. Call prices are modelled, not quotes.":
        "{count} eventos con resultado en el perfil {variant}. Los precios de las calls son de modelo, "
        "no cotizaciones.",
    "Report · {start} → {end}": "Reporte · {start} → {end}",
    "Analysing {days} days…": "Analizando {days} días…",
    "Analysis finished.": "Análisis terminado.",
    "The analysis ended with an error (code {code}). Check the log.":
        "El análisis terminó con error (código {code}). Revisa el registro.",
    "Cancelled. What was downloaded stays cached.": "Cancelado. Lo descargado queda en caché.",
    "Rule": "Regla",
    "Discovery n": "Descubr. n",
    "Discovery R": "Descubr. R",
    "Validation n": "Valid. n",
    "Validation hit rate": "Valid. acierto",
    "Validation R": "Valid. R",
    "WF folds": "WF tramos",
    "WF n": "WF n",
    "WF R": "WF R",
    "WF confirmed": "WF confirmada",
    "{trades} trades · no validated rule": "{trades} operaciones · sin reglas validadas",
    "{trades} trades · {validated} validated rules · {confirmed} with walk-forward":
        "{trades} operaciones · {validated} reglas validadas · {confirmed} con walk-forward",
    "no dates": "sin fechas",
    # ---------------------------------------------------------------- settings: market data
    "Source of the price history": "Fuente del historial de precios",
    "Broker for quotes and option chains": "Bróker para cotizaciones y cadenas de opciones",
    "Days each update downloads": "Días que descarga cada actualización",
    "Only when I ask": "Solo cuando yo lo pida",
    "Update automatically every X minutes": "Actualizar automáticamente cada X minutos",
    "Price history": "Historial de precios",
    "Quotes and options": "Cotizaciones y opciones",
    "Each download brings": "Cada descarga trae",
    "Update on its own": "Actualizar solo",
    "The window starts at this New York time": "La franja empieza a esta hora de Nueva York",
    "The window ends at this New York time": "La franja termina a esta hora de Nueva York",
    "Monday to Friday only": "Solo de lunes a viernes",
    "to": "a",
    "Window (New York)": "Franja (Nueva York)",
    "On your clock: from {start} to {end}.": "En tu reloj: de {start} a {end}.",
    "Market data": "Datos de mercado",
    "Every user connects their own account; MiraTrade shares your data with nobody. E*TRADE offers "
    "no price history: the history comes from Schwab.":
        "Cada usuario conecta su propia cuenta; MiraTrade no comparte tus datos con nadie. E*TRADE no "
        "ofrece historial de precios: el historial viene de Schwab.",
    "The automatic update only fetches what is new, but it reads today's filings again on every "
    "pass. Under {minutes} minutes it stays off: you would ask the SEC for more than actually "
    "changes.":
        "La actualización automática solo baja lo nuevo, pero vuelve a leer los formularios de hoy en "
        "cada pasada. Por debajo de {minutes} minutos se queda apagada: pedirías a la SEC más de lo "
        "que cambia.",
    "Daily history from your own Schwab account, through your personal developer app.":
        "Historial diario desde tu propia cuenta de Schwab, con tu app de desarrollador personal.",
    "Yahoo / Stooq with no licence agreement: only for your personal, non-commercial research. "
    "Do not use this data in anything you share or sell.":
        "Yahoo / Stooq sin acuerdo de licencia: solo para tu investigación personal y no comercial. "
        "No uses estos datos en nada que compartas o vendas.",
    "Public websites": "Webs públicas",
    "Yahoo and Stooq have no licence agreement with MiraTrade: their data is only for your "
    "personal, non-commercial research. Use them for your analyses?":
        "Yahoo y Stooq no tienen un acuerdo de licencia con MiraTrade: sus datos sirven solo para tu "
        "investigación personal y no comercial. ¿Usarlos para tus análisis?",
    # ---------------------------------------------------------------- settings: brokers
    "Credentials of your Schwab app": "Credenciales de la app de Schwab",
    "developer.schwab.com → Dashboard → your app. They are kept in the Windows Credential Manager, "
    "never in files.":
        "developer.schwab.com → Dashboard → tu app. Se guardan en el Administrador de credenciales de "
        "Windows, nunca en archivos.",
    "Keys of your E*TRADE account": "Claves de tu cuenta de E*TRADE",
    "These are sandbox (test) keys": "Son claves de sandbox (pruebas)",
    "E*TRADE → Developer: your individual consumer key, for your own accounts only. Sign the API "
    "agreement there and, for real-time quotes, the market data one. They are kept in the Windows "
    "Credential Manager.":
        "E*TRADE → Developer: tu consumer key de uso individual, solo para tus propias cuentas. Firma "
        "allí el acuerdo de la API y, para cotizaciones en tiempo real, el de datos de mercado. Se "
        "guardan en el Administrador de credenciales de Windows.",
    "Read-only: balances, quotes and option chains. The session lasts until New York midnight. "
    "Orders go through Schwab only.":
        "Solo lectura: saldos, cotizaciones y cadenas de opciones. La sesión dura hasta la medianoche "
        "de Nueva York. Las órdenes se envían solo por Schwab.",
    "Schwab access lasts 7 days; after that you have to sign in again.":
        "El acceso de Schwab dura 7 días; después hay que iniciar sesión otra vez.",
    "No credentials yet. Press «Save credentials…».": "Sin credenciales. Pulsa «Guardar credenciales…».",
    "Credentials saved. You still have to sign in.": "Credenciales guardadas. Falta iniciar sesión.",
    "The session expired. Sign in again.": "La sesión caducó. Inicia sesión otra vez.",
    "Connected. The session lasts {days} more days.": "Conectado. La sesión dura {days} días más.",
    "Could not read the status: {error}": "No se pudo leer el estado: {error}",
    "Credentials": "Credenciales",
    "Save your app credentials first.": "Guarda primero las credenciales de tu app.",
    "Sign in to Schwab": "Iniciar sesión en Schwab",
    "Sign in in the browser window. When you finish, the browser shows an error at\n"
    "https://127.0.0.1… — that is normal. Copy the whole address from the bar and paste it here:":
        "Inicia sesión en la ventana del navegador. Al terminar, el navegador muestra un error en\n"
        "https://127.0.0.1… — es normal. Copia la dirección completa de la barra y pégala aquí:",
    "Could not sign in: {error}": "No se pudo iniciar sesión: {error}",
    "No keys yet. Press «Save keys…».": "Sin claves. Pulsa «Guardar claves…».",
    "Keys saved{env}. You still have to sign in.": "Claves guardadas{env}. Falta iniciar sesión.",
    "The session ended at midnight. Sign in again.": "La sesión terminó a medianoche. Inicia sesión otra vez.",
    "Connected{env}. The session lasts {hours} more hours.":
        "Conectado{env}. La sesión dura {hours} horas más.",
    "Save your E*TRADE keys first.": "Guarda primero tus claves de E*TRADE.",
    "Could not start the sign-in: {error}": "No se pudo empezar el inicio de sesión: {error}",
    "Sign in to E*TRADE": "Iniciar sesión en E*TRADE",
    "Sign in in the browser window and accept. E*TRADE shows you a verification code:\n"
    "copy it and paste it here:":
        "Inicia sesión en la ventana del navegador y acepta. E*TRADE te muestra un código de\n"
        "verificación: cópialo y pégalo aquí:",
    # ---------------------------------------------------------------- settings: risk and real money
    "Risk per trade": "Riesgo por operación",
    "Risk ceiling (rejects)": "Techo de riesgo (rechaza)",
    "Maximum daily loss": "Pérdida diaria máxima",
    "Maximum order value": "Valor máx. de una orden",
    "Minimum share price": "Precio mínimo por acción",
    "Maximum open positions": "Posiciones abiertas máx.",
    "Every entry carries a stop and is a limit order. They apply in practice and with real money.":
        "Toda entrada lleva stop y es una orden limitada. Se aplican en práctica y con dinero real.",
    "Risk": "Riesgo",
    "The risk per trade cannot be above the ceiling.":
        "El riesgo por operación no puede superar el techo.",
    "Allow real-money orders": "Permitir órdenes con dinero real",
    "Off by default. Even when it is on, every order needs a Schwab preview and a confirmation you "
    "type (for example «BUY 100 ACME»).":
        "Apagado por defecto. Aun activado, cada orden necesita una vista previa de Schwab y que "
        "escribas la confirmación (p. ej. «BUY 100 ACME»).",
    "Real money": "Dinero real",
    "You are about to let MiraTrade send real orders to Schwab.\n\nEvery order will still need the "
    "preview and your typed confirmation. Are you sure?":
        "Vas a permitir que MiraTrade envíe órdenes reales a Schwab.\n\nCada orden seguirá "
        "necesitando la vista previa y tu confirmación escrita. ¿Seguro?",
    # ---------------------------------------------------------------- odds and ends
    # ---------------------------------------------------------------- what was actually measured
    "No analysis has been run yet, so nothing here has been tested against history.":
        "Todavía no se ha ejecutado ningún análisis, así que nada de esto se ha probado contra el historial.",
    "The latest analysis validated no rule out of sample: there is no measured edge here yet, only "
    "events and what similar ones did.":
        "El último análisis no validó ninguna regla fuera de muestra: aquí todavía no hay ventaja medida, "
        "solo eventos y lo que hicieron otros parecidos.",
    "1 rule": "1 regla",
    "{count} rules": "{count} reglas",
    "The latest analysis validated {rules} out of sample, none confirmed by walk-forward.":
        "El último análisis validó {rules} fuera de muestra, ninguna confirmada por walk-forward.",
    "The latest analysis validated {rules} out of sample, {confirmed} confirmed by walk-forward.":
        "El último análisis validó {rules} fuera de muestra, {confirmed} confirmadas por walk-forward.",
    "Analysis, not advice. With options you can lose the whole premium, and the contract prices "
    "shown are modelled from the stock, not quotes.":
        "Análisis, no asesoramiento. Con opciones puedes perder toda la prima, y los precios de "
        "contrato que se muestran son de modelo a partir de la acción, no cotizaciones.",
    "Capital position sizes are worked out from": "Capital con el que se calcula el tamaño",
    "Capital to size from": "Capital para dimensionar",
    "Use my broker balance instead": "Usar el saldo de mi bróker en su lugar",
    "Off by default. A suggestion sized to your real account is advice about your money rather than "
    "analysis of a market, so it is yours to switch on.":
        "Apagado por defecto. Una sugerencia dimensionada a tu cuenta real es consejo sobre tu dinero "
        "y no análisis de un mercado, así que activarlo es tu decisión.",
    "Sizes come from the capital above, not from your account, so what the screens suggest does not "
    "depend on how much money you have.":
        "Los tamaños salen del capital de arriba, no de tu cuenta, así que lo que sugieren las "
        "pantallas no depende de cuánto dinero tengas.",
    "the capital you set under Settings": "el capital que fijaste en Configuración",
    "the standard practice capital": "el capital estándar de práctica",
    "no broker connected; using the capital you set":
        "sin bróker conectado; se usa el capital que fijaste",
    "your account could not be read; using the capital you set":
        "no se pudo leer tu cuenta; se usa el capital que fijaste",
    "your account returned no balance; using the capital you set":
        "tu cuenta no devolvió saldo; se usa el capital que fijaste",
    "Reports on {date}, before this contract expires: the premium usually collapses once the news "
    "is out, even when the stock moved the right way, and a gap can open past the stop.":
        "Publica resultados el {date}, antes de que venza este contrato: la prima suele desplomarse "
        "cuando sale la noticia, incluso si la acción se movió en la dirección correcta, y un hueco "
        "puede abrir por debajo del stop.",
    # ---------------------------------------------------------------- can this contract be traded
    "Not checked: no quotes and no open interest stored for this contract. That is not the same as "
    "fine.":
        "Sin comprobar: no hay cotizaciones ni interés abierto guardados de este contrato. Eso no es "
        "lo mismo que estar bien.",
    "Open interest of {oi} is under {floor}: with almost nobody on the other side the quote is "
    "decoration — you move the price getting in and find no bid getting out.":
        "Interés abierto de {oi}, por debajo de {floor}: sin casi nadie al otro lado la cotización es "
        "decorativa — mueves el precio al entrar y no encuentras comprador al salir.",
    "The spread is {gap} % of the mid, so entering and leaving costs {eats} % of this profile's "
    "whole target before the stock moves.":
        "El spread es el {gap} % del punto medio, así que entrar y salir cuesta el {eats} % de todo el "
        "objetivo de este perfil antes de que la acción se mueva.",
    "The spread is {gap} % of the mid, over the {cap} % limit.":
        "El spread es el {gap} % del punto medio, por encima del límite del {cap} %.",
    "Entering and leaving costs {eats} % of this profile's whole target: the move has to be that "
    "much bigger just to break even.":
        "Entrar y salir cuesta el {eats} % de todo el objetivo de este perfil: el movimiento tiene que "
        "ser justo eso más grande solo para no perder.",
    "Open interest of {oi} is enough; the spread is not stored, so what the round trip costs is "
    "unknown.":
        "El interés abierto de {oi} es suficiente; el spread no está guardado, así que no se sabe lo "
        "que cuesta entrar y salir.",
    "Tradeable: spread {gap} % of the mid, {eats} % of the target, open interest {oi}.":
        "Operable: spread {gap} % del punto medio, {eats} % del objetivo, interés abierto {oi}.",
    "Tradeable: spread {gap} % of the mid, {eats} % of the target.":
        "Operable: spread {gap} % del punto medio, {eats} % del objetivo.",
    "Tradeable: spread {gap} % of the mid, open interest {oi}.":
        "Operable: spread {gap} % del punto medio, interés abierto {oi}.",
    "Tradeable: spread {gap} % of the mid.": "Operable: spread {gap} % del punto medio.",
    "No price history, so not even the stock's liquidity is known.":
        "Sin historial de precios, así que ni siquiera se conoce la liquidez de la acción.",
    "The share trades about {vol} a day, under {floor}: a stock this thin rarely has an option "
    "market worth using.":
        "La acción negocia unas {vol} al día, por debajo de {floor}: una acción tan fina raramente "
        "tiene un mercado de opciones utilizable.",
    "The share trades about {vol} a day. Nothing is stored about the contract itself, so its spread "
    "is unknown.":
        "La acción negocia unas {vol} al día. No hay nada guardado del contrato en sí, así que su "
        "spread es desconocido.",
    "Could not read {path}: {error}": "No se pudo leer {path}: {error}",
    "Nothing downloaded yet. Press «Update data» under Signals, or run `miratrade scan`. It is "
    "stored in {path}.":
        "Todavía no se ha descargado nada. Pulsa «Actualizar datos» en Señales, o ejecuta "
        "`miratrade scan`. Se guarda en {path}.",
    # ---------------------------------------------------------------- notifications
    "Notifications": "Notificaciones",
    "Push topic": "Tema del push",
    "no push": "sin push",
    "Make one up": "Generar uno",
    "A topic on the public ntfy server is readable by anyone who knows its name, so it should be "
    "long and unguessable.":
        "Un tema en el servidor público de ntfy lo puede leer cualquiera que sepa su nombre, así que "
        "debe ser largo e imposible de adivinar.",
    "Email to": "Correo a",
    "no email": "sin correo",
    "Sent from": "Enviado desde",
    "the same address": "la misma dirección",
    "Mail server": "Servidor de correo",
    "Most events per message": "Máx. eventos por mensaje",
    "Only what the quotes make tradeable": "Solo lo que las cotizaciones hacen operable",
    "Save the email password…": "Guardar la contraseña de correo…",
    "Preview…": "Vista previa…",
    "Shows exactly what would be sent, without sending anything.":
        "Muestra exactamente lo que se enviaría, sin enviar nada.",
    "Send a test": "Enviar una prueba",
    "The push is short and the email carries the detail: what was filed, the evidence, the "
    "contract, whether the quotes make it usable and whether it sits through a results "
    "announcement.":
        "El push es corto y el correo lleva el detalle: qué se presentó, la evidencia, el contrato, "
        "si las cotizaciones lo hacen utilizable y si atraviesa un anuncio de resultados.",
    "Both always say that nothing has been validated out of sample. A list of tickers on a phone "
    "reads as a recommendation otherwise.":
        "Los dos dicen siempre que nada se ha validado fuera de muestra. Si no, una lista de tickers "
        "en el móvil se lee como una recomendación.",
    "Email password": "Contraseña de correo",
    "App password": "Contraseña de aplicación",
    "For Gmail this is an app password from your Google account, not the password you sign in with. "
    "It is kept in the Windows Credential Manager, never in the settings file.":
        "En Gmail esto es una contraseña de aplicación de tu cuenta de Google, no la contraseña con "
        "la que inicias sesión. Se guarda en el Administrador de credenciales de Windows, nunca en "
        "el archivo de configuración.",
    "push on": "push activo",
    "email on, password saved": "correo activo, contraseña guardada",
    "email address set, password still missing": "dirección puesta, falta la contraseña",
    "Nothing is announced yet.": "Todavía no se anuncia nada.",
    "Could not save: {error}": "No se pudo guardar: {error}",
    "Could not read the events: {error}": "No se pudieron leer los eventos: {error}",
    "This is what would be sent": "Esto es lo que se enviaría",
    "{count} events. Nothing has been sent.": "{count} eventos. No se ha enviado nada.",
    "Nothing new to announce right now.": "Ahora mismo no hay nada nuevo que anunciar.",
    "Set a push topic or an email address first.":
        "Pon primero un tema de push o una dirección de correo.",
    "Send a test notification to {where}?": "¿Enviar una notificación de prueba a {where}?",
    "MiraTrade test": "Prueba de MiraTrade",
    "If you are reading this, notifications work. Nothing here has been validated out of sample; "
    "MiraTrade shows analysis, not advice.":
        "Si estás leyendo esto, las notificaciones funcionan. Nada de esto se ha validado fuera de "
        "muestra; MiraTrade muestra análisis, no asesoramiento.",
    "Sent by {channels}.": "Enviado por {channels}.",
    "push": "push",
    "email": "correo",
    # ---------------------------------------------------------------- scanner filters
    "Search a name: insider, filer, member, asset":
        "Busca un nombre: directivo, presentador, congresista, activo",
    "New positions only": "Solo posiciones nuevas",
    "Bought into a holding they did not have, rather than adding to one.":
        "Compró entrando en una posición que no tenía, en vez de añadir a una existente.",
    "Exclude amendments": "Excluir modificaciones",
    "An /A restates an earlier filing rather than reporting something new.":
        "Una /A rehace una presentación anterior en vez de informar de algo nuevo.",
    "vol ≥ ": "vol ≥ ",
    "any volume": "cualquier volumen",
    "OI ≥ ": "IA ≥ ",
    "any open interest": "cualquier interés abierto",
    "Clear filters": "Limpiar filtros",
    "Fit columns": "Ajustar columnas",
    "Back to widths that fit the contents. Drag a heading to set your own; they are kept until you "
    "change source.":
        "Vuelve a anchos que se ajustan al contenido. Arrastra una cabecera para poner los tuyos; se "
        "mantienen hasta que cambies de fuente.",
    "The window: days to download and to show": "La ventana: días a descargar y a mostrar",
    "How many days «Update data» downloads, and how many the list shows. Changing it alone only "
    "re-reads what is already stored.":
        "Cuántos días descarga «Actualizar datos», y cuántos muestra la lista. Cambiarlo por sí solo "
        "solo vuelve a leer lo que ya está guardado.",
    "Narrows what is on screen by company size. It never downloads.":
        "Reduce lo que hay en pantalla por tamaño de empresa. Nunca descarga.",
    "Which profile the evidence and the contract are shown for. It never downloads.":
        "Para qué perfil se muestran la evidencia y el contrato. Nunca descarga.",
    "yes": "sí",
    "no": "no",
    # ------------------------------------------------- the parameter form itself
    "Conditions…": "Condiciones…",
    "Conditions": "Condiciones",
    "What counts as an event, and what contract a profile buys. Changing them and searching again "
    "is another test, and the form keeps the count.":
        "Qué cuenta como evento, y qué contrato compra un perfil. Cambiarlas y volver a buscar es "
        "otra prueba, y el formulario lleva la cuenta.",
    "What counts as an event, and what contract a profile buys. Changing them and analysing again "
    "is another test, and the form keeps the count.":
        "Qué cuenta como evento, y qué contrato compra un perfil. Cambiarlas y volver a analizar es "
        "otra prueba, y el formulario lleva la cuenta.",
    "Conditions changed. Press «Search signals» to apply them.":
        "Condiciones cambiadas. Pulsa «Buscar señales» para aplicarlas.",
    "Conditions changed. Press «Run analysis» to apply them.":
        "Condiciones cambiadas. Pulsa «Ejecutar análisis» para aplicarlas.",
    "Could not open the settings: {error}": "No se pudieron abrir los ajustes: {error}",
    "Save": "Guardar",
    "Back to defaults": "Volver a los valores por defecto",
    "changed · default {value}": "cambiado · por defecto {value}",
    "Start the count again": "Empezar la cuenta otra vez",
    "Use it when you genuinely begin a new line of research. It is a deliberate act with a date on "
    "it, not a way to make the warning go away.":
        "Úsalo cuando empieces de verdad una línea de investigación nueva. Es un acto deliberado y "
        "con fecha, no una forma de quitar el aviso de en medio.",
    "This forgets the {count} configurations tried so far. Do it when you are genuinely starting a "
    "new line of research — not to make a result look better than it is.":
        "Esto olvida las {count} configuraciones probadas hasta ahora. Hazlo cuando empieces de "
        "verdad una línea de investigación nueva, no para que un resultado parezca mejor de lo que es.",
    # The multiple-testing sentence (miratrade/attempts.py), said on the form and under a report.
    "First configuration tried: a result means what it says.":
        "Primera configuración probada: un resultado significa lo que dice.",
    "{count} configurations tried. A result now needs p < {alpha} to mean what p < {plain} would "
    "have meant on the first — about t = {t}. With this many tries, something clears {plain} by "
    "luck alone {chance} % of the time.":
        "{count} configuraciones probadas. Ahora un resultado necesita p < {alpha} para significar "
        "lo que p < {plain} habría significado en la primera: aproximadamente t = {t}. Con tantos "
        "intentos, algo supera {plain} solo por suerte el {chance} % de las veces.",
    # ------------------------------------------- the parameter form (miratrade/params.py)
    "Insider purchases":
        "Compras de directivos",
    "Form 4 code P: an open-market buy with the insider's own money. Awards, exercises and gifts are never counted, whatever these say.":
        "Form 4 con código P: una compra en mercado con el dinero del propio directivo. Las concesiones, los ejercicios y las donaciones no cuentan nunca, digan lo que digan estos ajustes.",
    "Smallest purchase that counts":
        "Compra más pequeña que cuenta",
    "Below this, a director buying a few hundred dollars of stock is noise. Raising it keeps the purchases somebody had to think about — and drops most of the events.":
        "Por debajo de esto, un consejero comprando unos cientos de dólares es ruido. Subirlo deja las compras que alguien tuvo que pensarse, y deja fuera la mayoría de los eventos.",
    "Days that make a cluster":
        "Días que forman un clúster",
    "Several insiders buying within this many days of each other is treated as one decision by the people who know the company, not as several unrelated ones.":
        "Varios directivos comprando con esta diferencia de días se trata como una sola decisión de quienes conocen la empresa, no como varias sin relación.",
    "How long a purchase keeps counting":
        "Cuánto tiempo sigue contando una compra",
    "A filing stays 'active' this long. Longer finds more events per company and makes each one mean less; shorter is stricter about what is recent.":
        "Una presentación sigue «activa» este tiempo. Más largo encuentra más eventos por empresa y hace que cada uno signifique menos; más corto es más estricto con lo que es reciente.",
    "Unusual option flow":
        "Flujo de opciones inusual",
    "Volume above open interest means positions being opened, not closed. Chains are only read for days that were captured.":
        "Volumen por encima del interés abierto significa posiciones que se abren, no que se cierran. Las cadenas solo se leen de los días que se capturaron.",
    "Smallest print":
        "Operación más pequeña",
    "The total paid for one print. Small prints are retail; the premise of this signal is somebody putting real money on a short clock.":
        "El total pagado en una sola operación. Las pequeñas son minoristas; la premisa de esta señal es alguien poniendo dinero de verdad con poco tiempo por delante.",
    "Volume over open interest":
        "Volumen sobre interés abierto",
    "Above 1, more contracts traded today than were open at the start: new positions. Under 1 it can all be closing.":
        "Por encima de 1, hoy se han negociado más contratos de los que había abiertos al empezar: posiciones nuevas. Por debajo de 1 puede ser todo cierre.",
    "Least open interest":
        "Interés abierto mínimo",
    "A contract with almost no open interest gives a spectacular ratio on almost no money. This is the floor under the arithmetic.":
        "Un contrato casi sin interés abierto da un ratio espectacular con casi nada de dinero. Esto es el suelo de esa cuenta.",
    "Longest expiry":
        "Vencimiento más largo",
    "Short-dated is more time-sensitive and usually more conviction; it is also where hedging lives, so this cuts both ways.":
        "El plazo corto es más sensible al tiempo y suele ser más convicción; también es donde vive la cobertura, así que corta por los dos lados.",
    "Furthest out of the money":
        "Máximo fuera del dinero",
    "Strikes beyond this are lottery tickets. 0.15 = 15 % above the share price.":
        "Los strikes más allá de esto son billetes de lotería. 0,15 = 15 % por encima del precio de la acción.",
    "Smart money":
        "Dinero institucional",
    "13D means an active stake with intent; 13G is usually an index fund crossing 5 % mechanically. FINRA's off-exchange volume is not short interest.":
        "Un 13D es una participación activa con intención; un 13G suele ser un fondo indexado cruzando el 5 % de forma mecánica. El volumen fuera de mercado de FINRA no es interés en corto.",
    "How long a filing keeps counting":
        "Cuánto tiempo sigue contando una presentación",
    "As with insiders: how long a new stake stays an active event.":
        "Como con los directivos: cuánto tiempo una participación nueva sigue siendo un evento activo.",
    "Entry and exits":
        "Entrada y salidas",
    "Every event is traded the same way, so that the conditions around it can be compared. These are multiples of the stock's own volatility (ATR), not fixed percentages: a 5 % stop means something different on a utility and on a biotech.":
        "Todos los eventos se operan igual, para poder comparar las condiciones que los rodean. Son múltiplos de la volatilidad del propio valor (ATR), no porcentajes fijos: un stop del 5 % no significa lo mismo en una eléctrica que en una biotecnológica.",
    "Stop, in ATR":
        "Stop, en ATR",
    "Below this much of the daily range, the trade is wrong. Tighter stops out more often on noise alone.":
        "Por debajo de esta parte del rango diario, la operación está equivocada. Más ajustado salta más veces solo por ruido.",
    "Target, in ATR":
        "Objetivo, en ATR",
    "Where it is taken. Together with the stop this sets how often it has to work to pay.":
        "Dónde se recoge. Junto con el stop, fija cuántas veces tiene que salir bien para ganar.",
    "Time stop":
        "Stop por tiempo",
    "Sessions after which it is closed whatever it is doing. Capital held in a trade that is going nowhere is capital.":
        "Sesiones tras las cuales se cierra haga lo que haga. El capital retenido en una operación que no va a ninguna parte es capital.",
    " sessions":
        " sesiones",
    "Cheapest share":
        "Acción más barata",
    "Signals on shares under this are skipped: they are thin, the spread is a large part of the price, and most have no usable option market at all.":
        "Las señales en acciones por debajo de esto se saltan: son estrechas, el spread es una parte grande del precio y la mayoría no tiene un mercado de opciones utilizable.",
    "Contract":
        "Contrato",
    "What a profile buys when the instrument is an option. Prices in the backtest are modelled from the stock, never quotes.":
        "Lo que compra un perfil cuando el instrumento es una opción. Los precios del backtest están modelados a partir de la acción, nunca son cotizaciones.",
    "How much of the share's move the option follows. 0.75–0.85 behaves like the stock with leverage; 0.30 is mostly a lottery ticket with a deadline.":
        "Cuánto del movimiento de la acción sigue la opción. 0,75-0,85 se comporta como la acción con apalancamiento; 0,30 es sobre todo un billete de lotería con fecha límite.",
    "Days to expiry":
        "Días hasta el vencimiento",
    "Longer costs more and decays slower. If an effect takes two months, a 30-day call cannot express it.":
        "Más largo cuesta más y se deteriora más despacio. Si un efecto tarda dos meses, una call a 30 días no puede expresarlo.",
    "Never closer than":
        "Nunca más cerca de",
    "A contract is not chosen inside this many days of expiry, where decay is fastest and a few quiet sessions cost more than the move is worth.":
        "No se elige un contrato a menos de estos días del vencimiento, donde el deterioro es más rápido y unas pocas sesiones tranquilas cuestan más de lo que vale el movimiento.",
    "Tradeable at all":
        "Operable siquiera",
    "A signal you cannot get filled on is not a signal. These are checked against the stored chain, and the verdict says so plainly on the contract card.":
        "Una señal que no puedes ejecutar no es una señal. Esto se comprueba contra la cadena guardada, y el veredicto lo dice con claridad en la ficha del contrato.",
    "Widest spread":
        "Spread máximo",
    "Bid to ask as a percentage of the mid. You pay half of it getting in and half getting out.":
        "De la demanda a la oferta, como porcentaje del punto medio. Pagas la mitad al entrar y la mitad al salir.",
    " %":
        " %",
    "How many contracts are open. Thin contracts move on your own order.":
        "Cuántos contratos hay abiertos. Los contratos estrechos se mueven con tu propia orden.",
    "Most of the target the round trip may eat":
        "Máximo del objetivo que puede comerse la ida y vuelta",
    "The backtest charged no spread. If getting in and out costs a third of what you were aiming for, the edge it measured was never there to take.":
        "El backtest no cobró spread. Si entrar y salir cuesta un tercio de lo que buscabas, la ventaja que midió nunca estuvo ahí para cogerla.",
    # ------------------------------------------------- downloading: only the Scanner does it
    "fetch ": "traer ",
    "How many days to download": "Cuántos días descargar",
    "How far back «Update data» asks for. Days already downloaded are skipped, so this is cheap "
    "to raise.":
        "Hasta dónde pide «Actualizar datos». Los días ya descargados se saltan, así que subirlo "
        "sale barato.",
    "How far behind the stored data is. Measured on what was downloaded, not on what was found: "
    "a quiet day and a day nobody asked about are not the same thing.":
        "Cuánto retraso lleva la información guardada. Se mide por lo descargado, no por lo "
        "encontrado: un día tranquilo y un día que nadie pidió no son lo mismo.",
    "{reason} Without prices a download cannot start.":
        "{reason} Sin precios no se puede empezar una descarga.",
    "The download ended with an error (code {code}). Check the log.":
        "La descarga terminó con un error (código {code}). Revisa el registro.",
    "Nothing downloaded yet. Press «Update data» above. It is stored in {path}.":
        "Todavía no se ha descargado nada. Pulsa «Actualizar datos» arriba. Se guarda en {path}.",
    "Nothing matches these filters. «Clear filters» puts them back.":
        "Nada coincide con estos filtros. «Limpiar filtros» los deja como estaban.",
    "Nothing collected here yet. «Update data» brings Form 4 filings, 13D/G and prices; "
    "`miratrade congress trades` brings congressional disclosures. It is stored in {path}.":
        "Aquí todavía no se ha recopilado nada. «Actualizar datos» trae los Form 4, los 13D/G y "
        "los precios; `miratrade congress trades` trae las declaraciones del Congreso. Se guarda "
        "en {path}.",
    # ------------------------------------------------- the screens that only read
    "Go to Scanner": "Ir al Scanner",
    "The Scanner is the only screen that downloads.":
        "El Scanner es la única pantalla que descarga.",
    "Search signals": "Buscar señales",
    "Finds the events in the stored data under the current settings. It never downloads: the "
    "Scanner does that.":
        "Busca los eventos en la información guardada con los ajustes actuales. Nunca descarga: "
        "de eso se encarga el Scanner.",
    "The window: how many days to search": "La ventana: cuántos días buscar",
    "How many days of stored data to search. How many are downloaded is set on the Scanner.":
        "Cuántos días de la información guardada se buscan. Cuántos se descargan se decide en el "
        "Scanner.",
    "Searching the last {days} days of stored data…":
        "Buscando en los últimos {days} días guardados…",
    "No events stored for this window. Press «Search signals» to look again under the current "
    "settings, or go to the Scanner to download more days.":
        "No hay eventos guardados para esta ventana. Pulsa «Buscar señales» para mirar otra vez "
        "con los ajustes actuales, o ve al Scanner a descargar más días.",
    "No event in those days under these settings. Try more days, a wider size band, or looser "
    "conditions.":
        "Ningún evento en esos días con estos ajustes. Prueba con más días, un tramo de tamaño más "
        "amplio o condiciones menos estrictas.",
    "These events predate the size filter and have no market capitalisation stored. Press "
    "«Search signals» to rebuild them, or choose «All» under Size.":
        "Estos eventos son anteriores al filtro de tamaño y no tienen capitalización guardada. "
        "Pulsa «Buscar señales» para rehacerlos, o elige «Todas» en Tamaño.",
    "Only {days} days are stored; the Scanner downloads more.":
        "Solo hay {days} días guardados; el Scanner descarga más.",
    "Cancelled. The stored events are unchanged.":
        "Cancelado. Los eventos guardados no han cambiado.",
    "Backtests the stored data under the current settings. It never downloads: the Scanner does "
    "that.":
        "Simula la información guardada con los ajustes actuales. Nunca descarga: de eso se "
        "encarga el Scanner.",
    "Simulates every event in the stored data and looks for rules that survive out of sample. "
    "Minutes, not hours: nothing is downloaded.":
        "Simula todos los eventos de la información guardada y busca reglas que aguanten fuera de "
        "muestra. Minutos, no horas: no se descarga nada.",
    "Analysing {days} days of stored data…": "Analizando {days} días guardados…",
    # ---------------------------------------------------------------- scanner
    "Scanner": "Scanner",
    "Everything collected, as it was filed. No strategy applied here.":
        "Todo lo recopilado, tal como se presentó. Aquí no se aplica ninguna estrategia.",
    "Rows in the shared market database, and the days they cover.":
        "Filas en la base de datos de mercado compartida, y los días que cubren.",
    "{label}: {count}": "{label}: {count}",
    "all history": "todo el historial",
    "How far back to look": "Hasta cuándo mirar atrás",
    "Ticker, or several: PFE, AAPL": "Ticker, o varios: PFE, AAPL",
    "any amount": "cualquier importe",
    "Smallest amount to show": "Importe mínimo a mostrar",
    "Exclude 10b5-1 plans": "Excluir planes 10b5-1",
    "A purchase set up months earlier by a plan is not a decision made this week.":
        "Una compra fijada meses antes por un plan no es una decisión de esta semana.",
    "Member": "Congresista",
    "Active stakes only": "Solo participaciones activas",
    "Leaves out the 13G filings index funds make mechanically.":
        "Deja fuera los 13G que los fondos indexados presentan de forma mecánica.",
    "Open the original filing": "Abrir el documento original",
    "Opens the document this row came from, at the SEC or the House of Representatives.":
        "Abre el documento del que sale esta fila, en la SEC o en la Cámara de Representantes.",
    "Export…": "Exportar…",
    "Saves exactly the rows shown, with the filters applied.":
        "Guarda exactamente las filas mostradas, con los filtros aplicados.",
    "Export the rows shown": "Exportar las filas mostradas",
    "Comma-separated values (*.csv);;JSON (*.json)":
        "Valores separados por comas (*.csv);;JSON (*.json)",
    "Could not save: {error}": "No se pudo guardar: {error}",
    "{total} rows · saved to {path}": "{total} filas · guardado en {path}",
    "{total} rows": "{total} filas",
    "{shown} of {total} rows — narrow the filters to see the rest":
        "{shown} de {total} filas — afina los filtros para ver el resto",
    "Nothing collected for these filters yet. The Reports screen downloads Form 4 filings and "
    "prices; `miratrade congress trades` brings congressional disclosures.":
        "Todavía no hay nada recopilado para estos filtros. La pantalla de Reportes descarga los "
        "Form 4 y los precios; `miratrade congress trades` trae las divulgaciones del Congreso.",
    "Could not read the market database: {error}":
        "No se pudo leer la base de datos de mercado: {error}",
    "Pick a row first.": "Elige primero una fila.",
    "This row does not say which document it came from.":
        "Esta fila no indica de qué documento proviene.",
    # ---------------------------------------------------------------- scanner: the sources
    "Insiders (Form 4)": "Directivos (Form 4)",
    "Congress": "Congreso",
    "13D / 13G stakes": "Participaciones 13D / 13G",
    "Option flow": "Flujo de opciones",
    "Off-exchange volume": "Volumen fuera de bolsa",
    "No capture for {days} — that volume cannot be recovered. Run «miratrade flow status».":
        "Sin captura de {days} — ese volumen no se puede recuperar. Ejecuta «miratrade flow status».",
    "Daily prices": "Precios diarios",
    "As filed, including the filers' own errors. Code P is an open-market purchase; A, M, F and G "
    "are awards, exercises, tax withholding and gifts.":
        "Tal como se presentó, con los errores de quien presenta incluidos. El código P es una compra "
        "en mercado abierto; A, M, F y G son concesiones, ejercicios, retención de impuestos y "
        "donaciones.",
    "Filed up to 45 days after the transaction, and disclosed as a range rather than an exact "
    "amount. Personal use only (5 U.S.C. app. § 105(c)).":
        "Se presenta hasta 45 días después de la operación, y el importe se divulga como un rango, no "
        "como cifra exacta. Solo para uso personal (5 U.S.C. app. § 105(c)).",
    "Someone crossed 5 % of a company. A 13D declares active intent; a 13G is passive, and from an "
    "index fund it is a consequence of fund flows rather than a view.":
        "Alguien superó el 5 % de una empresa. Un 13D declara intención activa; un 13G es pasivo, y "
        "de un fondo indexado es consecuencia de los flujos del fondo, no una opinión.",
    "One row per contract per day. Premium is volume × mid × 100. Volume above open interest means "
    "positions were opened, not closed.":
        "Una fila por contrato y día. La prima es volumen × medio × 100. Volumen por encima del "
        "interés abierto significa que se abrieron posiciones, no que se cerraron.",
    "FINRA's daily off-exchange volume: dark pools, ATSs and wholesalers. It is NOT short interest, "
    "and a third to a half of all volume trades this way normally.":
        "Volumen diario fuera de bolsa de FINRA: dark pools, ATS y mayoristas. NO es interés en "
        "corto, y normalmente entre un tercio y la mitad del volumen se negocia así.",
    "Where a bar came from matters: 'schwab' is your own broker account, 'research' is Yahoo/Stooq "
    "and is for personal research only.":
        "De dónde viene cada vela importa: «schwab» es tu propia cuenta de bróker, «research» es "
        "Yahoo/Stooq y es solo para investigación personal.",
    # ---------------------------------------------------------------- scanner: filter choices
    "Any transaction": "Cualquier operación",
    "Purchases (P)": "Compras (P)",
    "Sales (S)": "Ventas (S)",
    "Awards (A)": "Concesiones (A)",
    "Option exercises (M)": "Ejercicios de opciones (M)",
    "Anyone": "Cualquiera",
    "Officers": "Directivos ejecutivos",
    "Directors": "Consejeros",
    "10 % holders": "Titulares del 10 %",
    "Purchases": "Compras",
    "Sales": "Ventas",
    "Partial sales": "Ventas parciales",
    "Exchanges": "Canjes",
    "Both chambers": "Ambas cámaras",
    "House": "Cámara",
    "Senate": "Senado",
    "13D and 13G": "13D y 13G",
    "13D only (active)": "Solo 13D (activo)",
    "13G only (passive)": "Solo 13G (pasivo)",
    "Calls and puts": "Calls y puts",
    "Calls": "Calls",
    "Puts": "Puts",
    # ---------------------------------------------------------------- scanner: column headings
    "Filed": "Presentado",
    "Traded": "Operado",
    "Days late": "Días de retraso",
    "Ticker": "Ticker",
    "Insider": "Directivo",
    "Role": "Cargo",
    "Code": "Código",
    "Shares": "Acciones",
    "Price": "Precio",
    "Value": "Importe",
    "10b5-1": "10b5-1",
    "Filing": "Documento",
    "Chamber": "Cámara",
    "Asset": "Activo",
    "Held by": "Titular",
    "From": "Desde",
    "To": "Hasta",
    "Committee sectors": "Sectores del comité",
    "Filer": "Presentador",
    "Kind": "Clase",
    "Type": "Tipo",
    "Amended": "Modificado",
    "Passive": "Pasivo",
    "Day": "Día",
    "Expiry": "Vencimiento",
    "Strike": "Strike",
    "Volume": "Volumen",
    "Open interest": "Interés abierto",
    "Premium": "Prima",
    "Side": "Lado",
    "Off-exchange": "Fuera de bolsa",
    "Total": "Total",
    "Share %": "Porcentaje",
    "Open": "Apertura",
    "High": "Máximo",
    "Low": "Mínimo",
    "Close": "Cierre",
    "Source": "Fuente",
}

CATALOGS: dict[str, dict[str, str]] = {"es": ES}

# How numbers and dates are written in each language. A language with no entry uses ENGLISH_FORMAT,
# which is also what the console tools print.
ENGLISH_FORMAT = {"thousands": ",", "decimal": ".",
                  "months": ("Jan", "Feb", "Mar", "Apr", "May", "Jun",
                             "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")}
FORMATS: dict[str, dict] = {
    "es": {"thousands": ".", "decimal": ",",
           "months": ("ene", "feb", "mar", "abr", "may", "jun",
                      "jul", "ago", "sep", "oct", "nov", "dic")},
}
_language = DEFAULT


def set_language(code: str) -> str:
    """Pick the language for later ``t()`` calls; an unknown code falls back to English."""
    global _language
    _language = code if code in LANGUAGES else DEFAULT
    return _language


def language() -> str:
    return _language


def t(source: str, /, **fields) -> str:
    """The text in the current language, with ``{placeholders}`` filled in. An English string with
    no translation is returned as it is, so nothing ever shows as a missing key.

    The source string is positional-only so a placeholder may be called ``source`` or ``text``
    without colliding with it."""
    translated = CATALOGS.get(_language, {}).get(source, source)
    return translated.format(**fields) if fields else translated


def formats() -> dict:
    """The number and date conventions of the current language."""
    return FORMATS.get(_language, ENGLISH_FORMAT)


def missing(code: str) -> list[str]:
    """English strings with no translation in ``code``; used by the tests to keep catalogs honest."""
    catalog = CATALOGS.get(code, {})
    return [s for s in ES if s not in catalog] if code != "es" else []
