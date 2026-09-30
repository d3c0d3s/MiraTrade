"""La segunda interfaz: una API HTTP y la web que la usa.

Existe para resolver un problema concreto: cuando no estás delante de la PC, no puedes usar la app.
Los datos y el motor viven en el servidor; la web y la app de escritorio son dos formas de mirarlos.

Vacío por ahora. Tres reglas que no son negociables y que conviene que estén escritas antes del
primer archivo:

1. **No envía órdenes.** Por decisión, no por omisión. Las credenciales del bróker y la decisión de
   operar son del usuario, en su propio equipo. Que una web pueda mandar una orden es un riesgo que
   este producto no necesita correr para ser útil.
2. **No importa nada de ``miratrade.app``**, ni al contrario. Las dos interfaces comparten el núcleo y
   el almacén, y eso es exactamente lo que las mantiene coherentes sin acoplarlas.
   ``tests/test_structure.py`` lo comprueba.
3. **Los parámetros se leen del almacén**, no de un fichero local. Por eso los ajustes se movieron a
   ``miratrade.prefs``: en cuanto hay dos interfaces, «dónde están los parámetros» tiene una
   respuesta o no la tiene, y dos respuestas es peor que cualquiera de las dos.

El servidor es de uso personal. Lo que se comercializa son notificaciones, no acceso a la plataforma
(ver ``docs/ALCANCE.md``), así que aquí no hay multi-tenencia: un almacén y una lista de envío.
"""
