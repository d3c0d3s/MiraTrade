# MiraTrade · archivos de marca

Estado: logo aprobado provisionalmente (27 sep 2026). MiraTrade es «a Mirandas Group company» y su
símbolo deriva del sistema **Pilares** del grupo: el mismo marco y los tres pilares, con el pilar
central en azul MiraTrade y una flecha verde en zigzag que pasa por detrás y rompe el marco.

## Carpetas

| Carpeta | Contenido |
|---|---|
| `simbolo/` | Símbolo en SVG y PNG (16–1024 px): `fondo-oscuro` (principal), `fondo-claro`, `monocromo`, `alternativa-ambar` |
| `icono/` | Icono de app sobre baldosa redondeada (SVG, PNG 16–1024) y `miratrade.ico` para Windows |
| `firma/` | Símbolo + nombre «MiraTrade» para fondo oscuro y claro, sola o con el respaldo «a Mirandas Group company» (`-respaldo-`): SVG y PNG transparente (`png/`, a 1×, 2× y 4×) |
| `manual/` | PDF exportado del lienzo del manual de marca |
| `fuente-diseno/` | Fuentes editables: tableros del lienzo (`manual-marca/`, `mockup-app/`) y los generadores en Python |

## Manual, publicidad y web (v1.0, septiembre 2026)

En el lienzo del manual hay tres páginas nuevas:

- **Manual** (12 láminas): portada, esencia y voz, símbolo, construcción, versiones y tamaños, firma,
  color, tipografía, interfaz, gráficos e infografía, voz y usos incorrectos, aplicaciones.
- **Publicidad**, a tamaño real: 2 posts de 1080×1080, infografía de 1080×1350, historia de 1080×1920,
  cabecera de 1500×500, anuncio de 1200×628 y display de 300×250 y 728×90.
- **Sitio web**: página de inicio en escritorio (1440) y móvil (390).

La promesa es «Señales con evidencia, no con promesas». Ninguna pieza anuncia aciertos ni
rentabilidad, porque el análisis de 5 años aún no ha validado ninguna regla. Las cifras van como
`[N]`, `[X] %` y solo se rellenan con datos del último reporte validado. Toda pieza que hable de
resultados lleva el aviso de riesgo. Revisa los anuncios pagados con un asesor legal.

Pendiente: precio, sitio web (dominio), Pantone y los datos entre corchetes. Fuentes:
`fuente-diseno/manual-marca/` (tableros) y `fuente-diseno/gen_manual_mt.py` (generador).

## Reglas rápidas

- **Fondo oscuro** (`#0B0E13`) para la versión principal. La flecha lleva un filo del color del
  fondo, así que cada variante está hecha para su fondo: usa `fondo-claro` sobre fondos claros.
- Colores: marco y pilar central `#6E9BFF`, pilares laterales `#F5F1E8`, flecha `#3FD19B`.
  Sobre claro: `#2F5BC8`, `#0E1726`, `#0E8A5F`.
- Por debajo de 48 px usa los PNG de tamaño pequeño (trazos engrosados), no un reescalado del grande.
- Tipografía: IBM Plex Sans (texto), IBM Plex Mono (cifras). En las firmas el nombre va convertido a
  trazos, así que se ven igual sin tener la fuente instalada. Las fuentes (licencia OFL) están en
  `MirandasGroup/Brand/Tipografia/IBM Plex/`.

## Proporciones (iguales en todas las marcas del grupo)

Marco y barras salen de `fuente-diseno/pilares.py`, la geometría común de Mirandas Group
(retícula de 64): marco 50×50 con radio 13; barras de 7 de ancho (laterales 27 de alto, central 15,
colgando de arriba). Grosor del marco según tamaño: 3,4 (≥ 64 px), 4,2 (40–63), 5,0 (24–39),
6,0 (< 24). El icono de app coloca el símbolo al 81,25 % dentro de la baldosa, igual que el grupo.
No redibujes ni estires el marco o las barras: cambia solo colores y el elemento propio de la marca.

## Lienzos (privados, en claude.ai)

- Manual de marca y propuestas: https://claude.ai/artifact/8gmPJYdgAHNYy7TanrFyy1
- Mockup de la app: https://claude.ai/artifact/RELWdggQD7uJvjR8SYgbp7
- Identidad de Mirandas Group: https://claude.ai/artifact/3HGZuY56TpAdBvhNXhbvuu

Regenerar los archivos: `python brand/fuente-diseno/export_brand.py` (necesita PySide6, Pillow para el
`.ico` de varios tamaños y la carpeta de fuentes IBM Plex; rutas dentro del script).
