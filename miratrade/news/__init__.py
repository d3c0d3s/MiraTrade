"""MiraSig: lo que se publicó alrededor de un evento, y qué se puede afirmar con ello.

Un directivo que compra **dentro** de una situación que se derrumba no está haciendo la misma cosa
que uno que compra en el vacío. Ese es el mecanismo, y es razonable. Este paquete es donde vive.

Vacío a propósito por ahora. Antes de que entre código hay una restricción que decide el diseño
entero, y escribirla aquí es más útil que descubrirla a mitad de un backtest:

    Una noticia solo puede condicionar un resultado si se tiene el texto **como estaba en su marca
    de tiempo**.

No es una preferencia metodológica. Un artículo de 2023 leído hoy puede haber sido actualizado, y a
menudo describe lo que pasó después: usarlo para juzgar un evento de 2023 es leer el resultado y
llamarlo predicción. Y un modelo de lenguaje interpretándolo tiene el problema al cuadrado, porque se
entrenó con datos que incluyen el desenlace — ninguna instrucción de prompt arregla eso de forma que
se pueda verificar.

De ahí salen dos etapas con una puerta en medio (ver ``docs/ALCANCE.md``):

* **Evidencia mostrada.** Las noticias de esos días aparecen junto al evento, con su fecha, sin
  afirmar nada sobre el resultado. Útil desde el primer día, e imposible de equivocar.
* **Condición medida.** La evaluación entra en el panel y se mide como cualquier otra condición.
  Empieza cuando exista una fuente con texto sellado en el tiempo, y no antes.

Lo que se guarde aquí va al almacén compartido como todo lo demás, con su cobertura, para que no se
descargue dos veces y para que otra app lo pueda leer (``docs/DATA.md``). Y cada condición nueva es
otra prueba: ``miratrade.attempts`` lleva la cuenta, y con noticias dentro el espacio de búsqueda
crece mucho más rápido que sin ellas.
"""
