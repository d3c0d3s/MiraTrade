# Estructura del repositorio

Una regla, y todo lo demás se deduce de ella:

> **El núcleo no sabe que existen las interfaces. Las interfaces importan del núcleo; el núcleo no
> importa de ninguna.**

Eso es lo que permite que la app de escritorio, el servidor web y la línea de órdenes sean tres
formas de mirar el mismo trabajo en lugar de tres copias divergentes de él. En cuanto el núcleo
importa algo de `app/`, la versión web deja de poder usarlo sin arrastrar Qt; en cuanto importa algo
de `web/`, la app de escritorio deja de arrancar sin un servidor.

No es una convención de estilo. **`tests/test_structure.py` la comprueba**, porque una capa que solo
existe en un documento se rompe el primer martes que alguien tiene prisa.

```
MiraTrade/
├── miratrade/              EL NÚCLEO. Ni Qt ni HTTP. Pandas, requests y SQLite.
│   ├── store/              el almacén compartido: esquema, migraciones, lectura y escritura
│   ├── data/               una descarga por fuente (SEC, FINRA, precios, cadenas, congreso…)
│   ├── signals/            las condiciones: directivos, flujo, técnico, dinero institucional
│   ├── news/               MiraSig: ingesta de noticias, punto-en-el-tiempo, evaluación
│   ├── app/                INTERFAZ: escritorio (PySide6)
│   └── web/                INTERFAZ: API HTTP y la web
├── deploy/                 LXC, systemd, cloudflared. No es Python y nadie lo importa.
├── docs/                   los contratos y las fronteras
├── brand/                  la marca: fuente del manual
└── tests/
```

## Qué va en cada sitio

### `miratrade/` — el núcleo

Todo lo que responde a «qué es un evento», «qué contrato se compra», «esto se puede operar», «cuánto
retraso llevan los datos». Si una función se puede llamar desde un script sin abrir una ventana ni
levantar un servidor, va aquí.

Los módulos que ya existen y por qué son núcleo:

| Módulo | Responde a |
|---|---|
| `store/` | dónde vive todo lo descargado y lo derivado (contrato en `DATA.md`) |
| `scan.py` | una descarga completa, y los eventos que produce |
| `reprocess.py` | los mismos eventos otra vez, sin red, con otros ajustes |
| `scanner.py` | consultas sobre lo recopilado, sin estrategia |
| `backtest.py`, `edge.py`, `outcomes.py` | la simulación y la minería de reglas |
| `liquidity.py` | si un contrato se puede operar de verdad |
| `freshness.py` | cuánto retraso lleva el almacén |
| `prefs.py`, `params.py` | los ajustes, y cómo se presentan |
| `attempts.py` | cuántas configuraciones se han probado, y qué le hace eso a un resultado |
| `notify.py` | el aviso, por correo y por push |
| `schedule.py` | la descarga desatendida |

`*_cli.py` son la línea de órdenes de cada área. Son núcleo: `argparse` no es una interfaz gráfica.

### `miratrade/news/` — MiraSig

El motor de noticias. Interpreta lo que se publicó **alrededor** de un evento y ayuda a confirmarlo o
descartarlo. Vacío por ahora; el hueco tiene la forma correcta a propósito, y su `__init__.py`
describe la única restricción que no es negociable (ver `ALCANCE.md`): una noticia solo puede
condicionar un backtest si se tiene **el texto como estaba en su marca de tiempo**.

### `miratrade/app/` y `miratrade/web/` — las dos interfaces

No se hablan entre ellas. Nunca. Comparten el núcleo y el almacén, que es exactamente lo que las
mantiene coherentes sin acoplarlas.

* `app/` es PySide6: una pantalla por archivo en `app/pages/`, los textos en inglés y el catálogo
  español en `app/i18n.py`.
* `web/` es la API y la web. **No envía órdenes**, por decisión y no por omisión: las credenciales
  del bróker y la decisión de operar son del usuario, en su propio equipo.

### `deploy/` — no es Python

Unidades de systemd, la definición del contenedor LXC, la configuración de `cloudflared`. Nada lo
importa y no se instala con el paquete. Está en el repo porque un despliegue que solo vive en la
cabeza de alguien no es reproducible.

### `docs/`

| Archivo | Qué fija |
|---|---|
| `DATA.md` | el contrato del almacén, para que otra app lo lea |
| `LICENCIAS.md` | qué fuente se puede usar en qué modo, y qué hay que apagar al cambiar de modo |
| `ALCANCE.md` | las etapas del producto y qué cambia en cada salto |
| `ESTRUCTURA.md` | esto |

## Lo que la prueba comprueba

`tests/test_structure.py` lee los `import` del código, no los ejecuta, y falla si:

1. algo de `miratrade/` fuera de `app/` importa `PySide6`;
2. algo del núcleo importa de `miratrade.app` o de `miratrade.web`;
3. `app/` importa de `web/`, o al revés;
4. un módulo nuevo en la raíz de `miratrade/` no tiene docstring — el sitio donde se explica por qué
   existe es el propio archivo.

Las tres primeras son la regla de arriba. La cuarta es más pequeña y más útil de lo que parece: el
razonamiento se pierde en meses, y un módulo sin explicación se reescribe en lugar de entenderse.
