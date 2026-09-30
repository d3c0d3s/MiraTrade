# Alcance: qué es MiraTrade en cada etapa

MiraTrade es un **scanner**: descarga información financiera de varias fuentes, la organiza, la
filtra con criterios y la contrasta con el comportamiento del pasado. Lo que produce es **evidencia
para decidir**, no una decisión. Los criterios, las estrategias y las ecuaciones no tienen la última
palabra: la tiene quien opera, en su propio bróker.

Eso no es una advertencia legal pegada al final. Es lo que el producto es, y de ahí sale todo lo
demás — incluido que se pueda vender sin haber validado una ventaja, porque lo que se vende es el
acceso a la evidencia organizada.

## Las tres etapas

### 1. Personal — hoy

Una persona, su equipo, sus credenciales, sus datos. Todas las fuentes disponibles, congresistas
incluidos. Sin autenticación porque no hay nadie más.

### 2. Feedback — unas pocas personas invitadas

El objetivo es aprender qué le sirve a alguien que no lo construyó. Sin dinero de por medio.

Lo que cambia, y **no es solo la autenticación**:

* **Fuera los congresistas.** Deja de ser uso personal (ver `LICENCIAS.md`).
* **Fuera Yahoo / Stooq.** Lo que ve otra persona no puede venir de una fuente de uso personal.
* Aparece la responsabilidad de lo que se muestra: el aviso honesto, que ya se lee del último reporte
  y no del código, pasa a ser lo primero que alguien lee.

### 3. Comercial — suscriptores

**Lo que se vende no es acceso a la plataforma.** Son notificaciones: correo, Telegram u otra vía,
con el resultado del análisis. Quien lo recibe decide y opera en su bróker, si quiere.

Esa forma tiene una consecuencia arquitectónica grande y buena: **no hay multi-tenencia**. No hay
datos por usuario, ni carteras ajenas, ni credenciales de terceros. Hay un almacén y una lista de
envío. Es un producto sustancialmente más pequeño de construir que un SaaS con cuentas.

Y tiene una consecuencia legal que hay que resolver **antes** de la primera suscripción, no después:

> Cobrar por enviar información de inversión a suscriptores toca la Investment Advisers Act de 1940.
> La exclusión del editor protege publicaciones *bona fide*, impersonales y de **circulación general
> y regular**. «Regular» es la palabra que nos afecta: un boletín de los martes lo es; una alerta que
> salta cuando el mercado se mueve es zona gris.

**Decisión de diseño que sale de ahí, y que hay que tomar antes de construir el notificador de pago:
horario fijo o disparador por evento.** El horario fijo es más defendible; el disparador por evento es
más útil. No es una decisión técnica y no la tomo yo. Está en `LICENCIAS.md` marcada **ABOGADO**.

Lo que sí es técnico, y ya está hecho: nada se adapta a la situación de una persona concreta.
`RiskParams.size_on_balance` es `False` por defecto, `account_equity()` no consulta al bróker, y un
test comprueba que no lo consulta. Dimensionar una sugerencia sobre el dinero real de alguien es otra
cosa distinta de analizar un mercado.

## La puerta que no se salta

Ninguna etapa comercial afirma una rentabilidad ni una tasa de acierto sin un reporte que lo sostenga
fuera de muestra. Hoy el aviso honesto dice que ninguna regla ha sobrevivido a la validación, y lo
dice porque es cierto: 0 de 256 configuraciones positivas en los dos periodos, y con precios reales de
opciones t = 0,89 con mediana −28 %.

Ese aviso se **lee del último reporte**, no se escribe en el código, justo para que no pueda desviarse
de la evidencia en ninguna de las dos direcciones. El día que una regla sobreviva, lo dirá por sí
mismo.

Vender evidencia organizada es honesto sin ese reporte. Vender una ventaja no lo es.

## MiraSig: en dos pasos, con una puerta en medio

MiraSig añade un motor que interpreta las noticias —anteriores, actuales y futuras— y según su
evaluación ayuda a confirmar o descartar si se opera el activo.

El mecanismo es bueno: una compra de un directivo **dentro** de una situación que se derrumba no es la
misma compra que en el vacío. Pero medirlo es el diseño más delicado del proyecto, por dos razones que
se multiplican:

1. **Las noticias no son punto-en-el-tiempo.** Un artículo de 2023 leído hoy puede haber sido
   actualizado, y a menudo describe lo que pasó después. Juzgar un evento con él no es un sesgo
   sutil: es leer el resultado y llamarlo predicción.
2. **Un modelo de lenguaje interpretándolo tiene el problema al cuadrado.** Se entrenó con datos que
   incluyen el desenlace. Ninguna instrucción de prompt arregla eso de forma verificable.

Por eso entra en dos pasos:

| | Qué es | Qué afirma | Coste |
|---|---|---|---|
| **3a** | **Evidencia mostrada.** Las noticias de esos días aparecen junto al evento, con su fecha. | nada | bajo |
| **3b** | **Condición medida.** La evaluación entra en el panel y se mide como cualquier otra condición. | que mejora el resultado | alto: exige noticias punto-en-el-tiempo |

**3a es útil desde el primer día y no puede estar equivocado**, porque no afirma nada: quien decide ve
lo que se publicó. 3b solo empieza cuando exista una fuente con texto sellado en el tiempo. Si nunca
existe, 3a se queda, y eso está bien.

Y una advertencia que vale la pena escribir ahora: **3b multiplica el espacio de búsqueda**. Cada
condición de noticias es otra prueba, y `miratrade/attempts.py` ya cuenta cuántas configuraciones se
han probado y qué le hace eso a la significación de un resultado. Ese contador va a importar mucho más
con MiraSig dentro que sin ella.

## Cómo se comprueba el modo en el código

Falta, y va en el roadmap: un ajuste `data.usage_mode` (`personal` / `feedback` / `commercial`) que
las fuentes restringidas consulten, de modo que el modo comercial no pueda leer congresistas ni
precios de investigación **aunque alguien lo configure por error**. Un documento no impide nada; una
comprobación sí.
