# Fuentes de datos: qué se puede usar, y en qué modo

Este documento existe porque el coste de sacar una fuente **después** de construir sobre ella es
mucho mayor que el de ponerla detrás de un interruptor desde el principio.

Tres modos, definidos en `ALCANCE.md`:

| Modo | Quién lo usa | Hay dinero |
|---|---|---|
| **personal** | solo el autor, en su equipo | no |
| **feedback** | unas pocas personas invitadas | no |
| **comercial** | suscriptores | **sí** |

La regla general, y la razón de casi todo lo que sigue: **cobrar convierte el uso en comercial**, y
casi ninguna fuente gratuita lo permite. Que la información salga por correo en lugar de por una
pantalla no la hace menos redistribución; si acaso, más directa.

> No soy abogado y esto no es asesoramiento legal. Es el mapa de lo que hay que resolver, y con quién,
> antes de que nadie pague. Lo marcado **ABOGADO** no se decide leyendo un ToS.

## La tabla

| Fuente | personal | feedback | comercial | Qué la limita |
|---|:--:|:--:|:--:|---|
| **SEC EDGAR** (Form 4, 13D/G, 8-K, XBRL) | sí | sí | sí | Dominio público. Solo hay que respetar el acceso justo: user-agent declarado y ≤ 10 peticiones/s. |
| **FINRA** volumen fuera de mercado | sí | sí | revisar | Publicado a diario y gratuito; su página tiene condiciones propias que hay que leer antes de cobrar. |
| **Congreso** (PTR de la Cámara, eFD del Senado) | sí | **no** | **NO** | Ethics in Government Act, **5 U.S.C. app. § 105(c)**: restringe el uso comercial de estas declaraciones. Es la única parte que hay que **desconectar** antes de que exista el primer suscriptor. |
| **Precios: cuenta propia de Schwab** | sí | no | no | Los términos de desarrollador individual cubren el uso del titular de la cuenta. Servir a terceros necesita un acuerdo de proveedor. |
| **Precios: E\*TRADE** | sí | no | no | *Individual Use Key* frente a *Vendor Use Key*. Lo segundo se solicita y se aprueba. |
| **Precios: Yahoo / Stooq** (`price_source=research`) | sí | **no** | **NO** | Sus condiciones permiten uso personal no comercial como máximo. Nunca es el valor por defecto de una app distribuida. |
| **Alpha Vantage** (calendario de resultados) | sí | revisar | revisar | Su ToS §2(a) define el uso comercial con cuatro criterios. Hay planes de pago; la clave gratuita no sirve para vender. |
| **Cadenas de opciones del bróker** | sí | no | no | Igual que los precios: son datos de tu cuenta. |
| **Noticias (MiraSig)** | depende | depende | depende | **Sin decidir**: depende del proveedor. Ver abajo. |

## Qué se apaga en cada salto

### personal → feedback

1. **Congresistas fuera.** No porque haya dinero, sino porque deja de ser uso personal.
2. **Precios: nada de Yahoo/Stooq.** Los datos que ve otra persona no pueden venir de ahí.
3. Aparece la autenticación, y con ella la responsabilidad de lo que se muestra.

### feedback → comercial

4. **Todas las fuentes de precios pasan a ser de pago y con licencia de redistribución.** Esto es el
   coste recurrente real del producto y hay que cifrarlo antes de prometer nada.
5. **ABOGADO — Investment Advisers Act de 1940.** Cobrar por enviar información de inversión a
   suscriptores toca la definición del §202(a)(11). Existe la exclusión del editor, §202(a)(11)(D),
   interpretada en *Lowe v. SEC* (1985), que protege publicaciones *bona fide*, impersonales y de
   **circulación general y regular**.

   La palabra que nos afecta es «regular». Un boletín que sale los martes lo es; una alerta que salta
   cuando el mercado se mueve es zona gris. **Consecuencia de diseño, y hay que decidirla antes de
   construir el notificador:** si el negocio va a apoyarse en esa exclusión, un **horario fijo** es
   más defendible que un disparador por evento.

   Además, nada puede adaptarse a la situación de una persona concreta. Por eso
   `RiskParams.size_on_balance` es `False` por defecto y `account_equity()` no consulta al bróker:
   dimensionar una sugerencia sobre el dinero real de alguien es otra cosa distinta, y un test lo
   impide.
6. **ABOGADO — registro estatal.** Algunos estados tienen sus propios requisitos para publicaciones
   de inversión, independientes de la SEC.

## Noticias: sin decidir

Ninguna decisión tomada todavía, y dos restricciones que la van a dominar:

1. **Punto-en-el-tiempo.** Para que una noticia pueda condicionar un backtest hace falta el texto
   **tal como estaba en su marca de tiempo**. Un artículo actualizado describe a menudo lo que pasó
   después, y usarlo no es un sesgo sutil: es leer el resultado. La mayoría de las APIs de noticias
   no ofrecen esto, y la que lo ofrezca será la que decida la elección — no el precio.
2. **Redistribución del texto.** Enviar titulares, y sobre todo fragmentos, a suscriptores es
   redistribuir la obra de un tercero. Los agregadores tienen condiciones muy distintas entre sí en
   este punto concreto.

Ver `ALCANCE.md` para por qué MiraSig entra primero como evidencia mostrada y no como condición
medida.

## Cómo se aplica esto en el código

El modo no es un comentario en un documento. Es un ajuste, y cada fuente restringida lo comprueba:

* `data.price_source` ya distingue `schwab` (tu cuenta) de `research` (webs públicas), con una carpeta
  de caché separada para cada uno, **para que los datos de investigación no alimenten nunca la ruta
  con licencia**.
* Los congresistas son un *extra* de `pyproject.toml`, no una dependencia, precisamente porque son la
  parte que tiene que salir.
* Lo que falta, y va en el roadmap: un ajuste `data.usage_mode` que los módulos afectados consulten,
  de modo que el modo comercial no pueda leer congresistas ni precios de investigación aunque alguien
  lo configure por error.
