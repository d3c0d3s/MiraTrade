"""La capa que separa el núcleo de las interfaces, comprobada en vez de documentada.

Una regla: el núcleo no sabe que existen las interfaces. Las interfaces importan del núcleo; el
núcleo no importa de ninguna.

En cuanto algo del núcleo importa de ``app``, la versión web deja de poder usarlo sin arrastrar Qt;
en cuanto importa de ``web``, la app de escritorio deja de arrancar sin un servidor. Las dos cosas se
descubren tarde y se arreglan caro.

Estas pruebas leen los ``import`` con ``ast``, sin ejecutar nada, así que son rápidas y no dependen de
que PySide6 esté instalado.
"""
import ast
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
PACKAGE = ROOT / "miratrade"
# Los dos front-ends. Todo lo demás dentro de `miratrade/` es núcleo.
INTERFACES = ("app", "web")


def _modules(where: Path):
    for path in sorted(where.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        yield path, ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def _imported(tree: ast.AST) -> set[str]:
    """Todo lo que un módulo importa, incluidos los imports dentro de funciones."""
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            names.add(node.module)
            names.update(f"{node.module}.{alias.name}" for alias in node.names)
    return names


def _area(path: Path) -> str:
    """"app", "web" o "core", según dónde esté el archivo."""
    parts = path.relative_to(PACKAGE).parts
    return parts[0] if parts and parts[0] in INTERFACES else "core"


def _core_files():
    return [(p, t) for p, t in _modules(PACKAGE) if _area(p) == "core"]


def test_el_nucleo_no_conoce_qt():
    """Qt vive en `app/`. Un núcleo que lo importa no se puede servir por HTTP."""
    guilty = [str(p.relative_to(ROOT)) for p, tree in _core_files()
              if any(name.split(".")[0] == "PySide6" for name in _imported(tree))]
    assert guilty == [], f"importan PySide6 fuera de miratrade/app: {guilty}"


def _top_level_imports(tree: ast.AST) -> set[str]:
    """Only the imports paid when the module is imported — not the ones inside a function."""
    names = set()
    for node in tree.body:                        # deliberately not ast.walk: module level only
        if isinstance(node, ast.Import):
            names.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            names.add(node.module)
            names.update(f"{node.module}.{a.name}" for a in node.names)
    return names


def test_el_nucleo_no_importa_de_las_interfaces():
    """Con una excepción, y es estrecha a propósito: `cli.py` es el lanzador.

    Que quien arranca algo sepa qué arranca no es el acoplamiento que esta regla protege — lo que
    protege es que la *lógica* no dependa de una interfaz. Pero solo vale si el import es perezoso,
    dentro de la función: así `import miratrade.cli` no arrastra FastAPI ni Qt, y quien no tiene
    instalado el extra `web` sigue pudiendo usar la línea de órdenes.
    """
    launchers = {"cli.py"}
    guilty = []
    for path, tree in _core_files():
        inside_only = path.name in launchers
        names = _top_level_imports(tree) if inside_only else _imported(tree)
        for name in names:
            head = name.split(".")
            if len(head) >= 2 and head[0] == "miratrade" and head[1] in INTERFACES:
                guilty.append(f"{path.relative_to(ROOT)} → {name}")
    assert guilty == [], f"el núcleo importa de una interfaz: {guilty}"


@pytest.mark.parametrize("mine,theirs", [("app", "web"), ("web", "app")])
def test_las_dos_interfaces_no_se_hablan(mine, theirs):
    """Comparten el núcleo y el almacén. Eso es lo que las mantiene coherentes sin acoplarlas."""
    guilty = []
    for path, tree in _modules(PACKAGE / mine):
        for name in _imported(tree):
            if name.startswith(f"miratrade.{theirs}"):
                guilty.append(f"{path.relative_to(ROOT)} → {name}")
    assert guilty == [], f"{mine} importa de {theirs}: {guilty}"


def test_deploy_no_es_python():
    """Unidades de systemd y configuración de túnel. Si aparece un .py aquí, algo se ha puesto en el
    sitio equivocado: el código va en el paquete, donde se puede probar."""
    stray = [str(p.relative_to(ROOT)) for p in (ROOT / "deploy").rglob("*.py")]
    assert stray == [], f"código Python en deploy/: {stray}"


def test_cada_modulo_del_nucleo_dice_para_que_existe():
    """El razonamiento se pierde en meses, y un módulo sin explicación se reescribe en lugar de
    entenderse. Un docstring de una línea no basta para eso, pero uno vacío es una garantía de que
    nadie lo sabrá."""
    silent = []
    for path in sorted(PACKAGE.glob("*.py")):
        if path.name == "__init__.py":
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        doc = ast.get_docstring(tree)
        if not doc or len(doc.strip()) < 40:
            silent.append(path.name)
    assert silent == [], f"sin explicar por qué existen: {silent}"


def test_los_paquetes_nuevos_existen_y_estan_descritos():
    """`news` (MiraSig) y `web` están vacíos a propósito, pero su forma y sus reglas ya están
    escritas: descubrir a mitad de un backtest que las noticias no son punto-en-el-tiempo es caro."""
    for name in ("news", "web"):
        init = PACKAGE / name / "__init__.py"
        assert init.exists(), f"falta miratrade/{name}/__init__.py"
        doc = ast.get_docstring(ast.parse(init.read_text(encoding="utf-8")))
        assert doc and len(doc.strip()) > 200, f"miratrade/{name} no explica qué va dentro"


def test_los_documentos_de_frontera_existen():
    """Estructura, licencias y alcance. Los tres se consultan al decidir, no al terminar."""
    for name in ("DATA.md", "ESTRUCTURA.md", "LICENCIAS.md", "ALCANCE.md"):
        path = ROOT / "docs" / name
        assert path.exists(), f"falta docs/{name}"
        assert len(path.read_text(encoding="utf-8")) > 500, f"docs/{name} está casi vacío"
