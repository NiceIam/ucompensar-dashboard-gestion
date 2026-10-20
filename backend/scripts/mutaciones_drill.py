"""Mutaciones del detalle (drill) y los filtros del tablero, en una COPIA temporal — PI0320251.

Comprueba que las pruebas de verdad detectan errores reales: copia `backend/` y `test-data/` a una carpeta temporal,
le aplica UNA mutacion a la vez al codigo de los servicios y corre las pruebas de la copia. Cada mutacion debe
hacer FALLAR alguna prueba; si una sobrevive, la prueba que la cubriria no es lo bastante estricta.

Uso (desde cualquier carpeta):
  C:\\ucompensar\\brujula-demo\\venv313\\Scripts\\python.exe backend\\scripts\\mutaciones_drill.py [filtro]

No toca el repositorio: todo ocurre en un directorio temporal que se borra al final.
"""

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SUITES = ["tests/test_dashboards_drill.py", "tests/test_dashboards_filters.py", "tests/test_data_labels.py"]

# (nombre, archivo relativo a backend/, texto original, texto mutado)
MUTATIONS = [
    ("drill: el valor tocado filtra con != en vez de =", "app/services/dashboard_drill_service.py",
     'return [[col.name, "=", text]]', 'return [[col.name, "!=", text]]'),
    ("drill: la semana dura 6 dias", "app/services/dashboard_drill_service.py", "_WEEK_DAYS = 7", "_WEEK_DAYS = 6"),
    ("drill: el porcentaje se calcula sin dividir por el total", "app/services/dashboard_drill_service.py",
     '"share": round(n / total_value, 4) if share_ok else None', '"share": round(n, 4) if share_ok else None'),
    ("drill: by deja de validarse contra la lista blanca", "app/services/dashboard_drill_service.py",
     "        if by is None:\n            raise DrillError(\"No se puede ver el detalle por esa columna en este gráfico.\")",
     "        if by is None:\n            by = dims[0]"),
    ("drill: el aviso de truncamiento cuenta mal", "app/services/dashboard_drill_service.py",
     'f"Mostrando {len(rows_out)} de {groups}" if truncated else None',
     'f"Mostrando {len(rows_out)} de {len(rows_out)}" if truncated else None'),
    ("drill: Otros incluye una porcion visible mas", "app/services/dashboard_drill_service.py",
     "    keep = points - 1\n", "    keep = points\n"),
    ("drill: el grupo sin dato filtra por igualdad", "app/services/dashboard_drill_service.py",
     'return [[col.name, "null"]]', 'return [[col.name, "="  , ""]]'),
    ("drill: ignora los filtros globales activos", "app/services/dashboard_drill_service.py",
     "    filters = base_filters + slice_f\n", "    filters = slice_f\n"),
    ("drill: el mes se toma como un dia", "app/services/dashboard_drill_service.py",
     'return [[col.name, "=", text]]\n    if empty or value is None:\n        return [[col.name, "null"]]',
     'return [[col.name, "=", text + "-01"]]\n    if empty or value is None:\n        return [[col.name, "null"]]'),
    ("filtros: el fin del rango es exclusivo", "app/services/dashboard_filters.py",
     'extra.append((col.name, "<=", gf.date_to.isoformat()))', 'extra.append((col.name, "<", gf.date_to.isoformat()))'),
    ("filtros: una categoria no se aplica", "app/services/dashboard_filters.py",
     '        extra.append((dim.column.name, "=" if len(values) == 1 else "in", *values))', "        pass"),
    ("filtros: 'ultimos 30 dias' son 29", "app/services/dashboard_filters.py",
     "return today - timedelta(days=days - 1), today", "return today - timedelta(days=days - 2), today"),
    ("filtros: sin fecha no avisa", "app/services/dashboard_filters.py",
     'notes.append({"code": NOTE_NO_DATE,', 'notes.append({"code": "x",'),
    ("filtros: una categoria inexistente ya no es un error", "app/services/dashboard_filters.py",
     "        if key not in keys:\n            raise FilterError(", "        if False:\n            raise FilterError("),
    ("filtros: el mes anterior es el actual", "app/services/dashboard_filters.py",
     "    if preset == \"last_month\":\n        last = today.replace(day=1) - timedelta(days=1)\n        return last.replace(day=1), last",
     "    if preset == \"last_month\":\n        return today.replace(day=1), _month_end(today.replace(day=1))"),
    ("render: los filtros globales no se aplican al calcular", "app/services/dashboard_render_service.py",
     "        spec, notes = dfilters.apply(e[\"spec\"], _table_of(catalog, e[\"spec\"]), gf)",
     "        spec, notes = e[\"spec\"], []"),
    ("opciones: cuenta las celdas vacias como un valor", "app/services/dashboard_filter_options_service.py",
     'else [[dim.column.name, "notnull"]]', "else []"),
    ("unidad: el rol de dinero ya no cuenta", "app/services/data_labels.py",
     "    if role in MONEY_ROLES:\n        return \"money\"", "    if False:\n        return \"money\""),
    ("titulos: vuelve al encabezado crudo", "app/services/data_labels.py",
     "    return lower_phrase(humanize(raw_name(col)))", "    return lower_phrase(raw_name(col))"),
]


def run(workdir: Path, label: str) -> bool:
    env = {**os.environ, "GOOGLE_API_KEY": "", "PYTHONDONTWRITEBYTECODE": "1"}
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-x", "-p", "no:cacheprovider", *SUITES],
        cwd=workdir / "backend", env=env, capture_output=True, text=True,
    )
    return proc.returncode == 0


def main() -> int:
    only = sys.argv[1].lower() if len(sys.argv) > 1 else ""
    survivors, killed = [], 0
    with tempfile.TemporaryDirectory(prefix="mut_drill_") as tmp:
        root = Path(tmp)
        shutil.copytree(REPO / "backend", root / "backend", ignore=shutil.ignore_patterns("__pycache__", "venv", ".pytest_cache"))
        shutil.copytree(REPO / "test-data", root / "test-data")
        if not run(root, "base"):
            print("La copia SIN mutar ya falla: arregla las pruebas antes de medir mutaciones.")
            return 2
        for name, rel, old, new in MUTATIONS:
            if only and only not in name.lower():
                continue
            target = root / "backend" / rel
            original = target.read_bytes()
            text = original.decode("utf-8")
            crlf = "\r\n" in text
            text = text.replace("\r\n", "\n")
            if old not in text:
                print(f"?? NO APLICA  {name}  (el texto original ya no esta en {rel})")
                survivors.append(name)
                continue
            mutated = text.replace(old, new, 1)
            target.write_bytes((mutated.replace("\n", "\r\n") if crlf else mutated).encode("utf-8"))
            try:
                survived = run(root, name)
            finally:
                target.write_bytes(original)
            print(("SOBREVIVIO " if survived else "detectada  ") + name)
            if survived:
                survivors.append(name)
            else:
                killed += 1
    print(f"\n{killed} mutaciones detectadas, {len(survivors)} sobrevivieron o no aplicaron.")
    return 1 if survivors else 0


if __name__ == "__main__":
    raise SystemExit(main())
