# Pendiente

Cosas decididas a medias, a propósito, con lo que falta para terminarlas. Está en el repositorio y
no en una conversación porque el trabajo va repartido entre sesiones y lo que no está aquí se
pierde.

Cada entrada dice **qué se hizo**, **qué falta**, y **cómo saber que ha llegado el momento**.

---

## Precios: el universo completo

**Estado: acotado (2026-09-30).**

Se descargaron los precios de las empresas con una compra de directivo de **250.000 $ o más**:
1.565 empresas, de las que faltaban 1.089. El universo completo —cualquier compra con código P— son
**3.373 empresas**.

| | Empresas | Por qué |
|---|---:|---|
| Acotado (hecho) | 1.565 | muestra utilizable sin horas de descarga |
| **Completo (pendiente)** | **3.373** | necesario para medir sin sesgo de tamaño |

**Qué falta:** quitar el filtro de 250.000 $ y volver a lanzar. Es seguro repetirlo: la tabla
`coverage` registra a qué se ha preguntado ya, incluidas las empresas que no devolvieron nada, así
que solo pedirá lo que falte.

**Por qué importa quitarlo, y no es un detalle:** un mínimo de 250.000 $ no es un corte neutral. Las
empresas pequeñas hacen compras pequeñas, así que el universo acotado **está sesgado hacia empresas
grandes** — y es justo en las pequeñas donde la literatura sitúa la ventaja de los directivos.
Cualquier resultado medido sobre el acotado hereda ese sesgo, y hay que decirlo al presentarlo.

**Cuándo hacerlo:** antes de cualquier afirmación sobre tamaño de empresa, y antes de cualquier
reporte que vaya a citarse como validación. Para explorar un mecanismo, el acotado sirve.

**Coste:** horas contra Yahoo / Stooq. Esa fuente es `price_source = research`, de **uso personal no
comercial** (ver `LICENCIAS.md`): sirve para tu investigación y no puede alimentar nada que se
venda ni que vea otra persona.

---

## La medición de los 8-K, rehecha sobre el historial largo

**Estado: medida una vez, sobre una muestra que no bastaba.**

La primera medición (ver `ALCANCE.md` y el commit `1c74580`) encontró que los items 3.02 y 1.01
aparecen cerca de los eventos mucho más que en días normales — y que **son la misma cosa**: una
financiación, no una noticia. La tabla de eventos filtrándose.

Lo que **no** se pudo mostrar fue si eso cambia el resultado, porque todos los eventos guardados
caían entre el 28-08 y el 28-09-2026: un mes de mercado muestreado 373 veces.

**Qué falta:** ya hay 523.197 filas de Form 4 desde 2025-01-02. Falta reprocesar sobre esa ventana
—lo que necesita los precios de arriba— y repetir la comparación con una separación dentro y fuera
de muestra.

**Cómo saber que ha llegado el momento:** cuando `events` cubra más de un año.

---

## Despliegue en Odin

**Estado: construido para desplegar, no desplegado.**

`odin.mgmt.miratechcloud.com` responde en `192.168.111.201` y el 8006 (Proxmox) está abierto, pero
**el puerto 22 agota el tiempo de espera** desde la máquina de trabajo.

**Qué falta:** abrir el 22, dar el puerto alternativo si lo hay, o que lo despliegue la sesión que
gestiona la red local. `deploy/LEEME.md` tiene lo que ya está decidido.

---

## El modo de uso: hecho (2026-09-30)

Ya no es un documento. `miratrade/usage.py` lo impone: las fuentes restringidas **preguntan antes
de descargar** y se niegan. `data.usage_mode` está en el formulario de Ajustes, con sus tres
opciones y su porqué.

| Modo | Prohíbe |
|---|---|
| **personal** | nada |
| **feedback** | congresistas, precios de webs públicas, clave gratuita de Alpha Vantage |
| **commercial** | lo anterior **más** los precios de tu propia cuenta de bróker |

Dos decisiones que merecen quedar escritas:

- **Un modo irreconocible se lee como `personal`**, el más estricto. Un error de escritura que
  concediera derechos comerciales en silencio sería el único fallo que esto existe para evitar.
- **Los conflictos se avisan en Ajustes**, no al descargar. Pasar a comercial con Yahoo todavía
  seleccionado es un error que se comete una vez; enterarse a las tres de la mañana porque una
  descarga programada falla es peor que enterarse en la pantalla.

Lo que **no** resuelve: sigue sin ser asesoramiento legal, y no sustituye al abogado que
`LICENCIAS.md` marca como necesario antes de que nadie pague.

## La app de escritorio

**Estado: en funcionamiento, y va a desaparecer.**

La web sustituye a la app de escritorio, no la acompaña. Mientras coexistan hay duplicación
consciente: `miratrade/card.py` arma la ficha de un evento para la web, y `app/pages/signals.py`
sigue armando la suya, enredada con los widgets de Qt.

**Qué falta:** cuando la web esté completa, o bien el escritorio pasa a usar `card.py`, o bien se
retira. Lo que no puede quedarse es la duplicación sin fecha.

---

## Notificaciones por suscripción: horario fijo o por evento

**Estado: sin decidir, y no es una decisión técnica.**

Ver `LICENCIAS.md`, marcado **ABOGADO**. La exclusión del editor de la Investment Advisers Act gira
sobre «circulación general y **regular**». Un boletín de los martes lo es; una alerta que salta
cuando el mercado se mueve es zona gris.

**Qué falta:** decidirlo con un abogado de valores **antes** de construir el notificador de pago,
porque cambia cómo se construye.
