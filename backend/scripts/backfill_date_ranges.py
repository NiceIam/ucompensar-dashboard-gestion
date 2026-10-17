#!/usr/bin/env python
"""Mantenimiento: guarda el rango de fechas (columns_definition[].range) de las tablas cargadas ANTES de que
existiera, para que el catalogo del chat lo muestre al modelo (ver schema_agent_service.backfill_date_ranges).

Las cargas nuevas ya lo calculan solas; esto solo es para las tablas viejas. Por defecto es un ENSAYO: calcula y
muestra, no escribe nada. Con --apply escribe. Corre contra la BD que indique el .env (DATABASE_*), asi que revisa
a cual apunta antes de usar --apply. Hacerlo sin cargas de archivos en curso.

Ejemplos (desde backend/):
  ./venv/Scripts/python.exe scripts/backfill_date_ranges.py --org-id <uuid>                  # ensayo
  ./venv/Scripts/python.exe scripts/backfill_date_ranges.py --org-id <uuid> --apply          # escribe
  ./venv/Scripts/python.exe scripts/backfill_date_ranges.py --org-id <uuid> --apply --refresh # recalcula TODAS
(--org-id se puede repetir; --refresh recalcula tambien columnas que ya tienen rango, p. ej. tras borrar filas.)
"""

import argparse
import asyncio
import contextlib
import os
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
os.chdir(BACKEND_DIR)                 # Settings lee ".env" relativo al cwd
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))


async def run(org_ids: list[str], apply: bool, refresh: bool) -> int:
    from app.database import close_all_pools
    from app.services.schema_agent_service import backfill_date_ranges

    failures = 0
    try:
        for org_id in org_ids:
            print(f"== org {org_id} ({'APLICANDO' if apply else 'ensayo, no escribe nada'})")
            try:
                report = await backfill_date_ranges(org_id, dry_run=not apply, refresh=refresh)
            except Exception as exc:        # una org con problemas no detiene a las demas
                failures += 1
                print(f"   ERROR: {type(exc).__name__}")
                continue
            if not report:
                print("   nada que calcular")
            for item in report:
                state = "guardado" if item["applied"] else ("cambiaria" if item["changed"] else "sin cambios")
                ranges = ", ".join(f"{c} {lo}→{hi}" for c, (lo, hi) in item["ranges"].items()) or "sin fechas legibles"
                print(f"   {item['table']} ({item['rows']} filas): {ranges} [{state}]")
    finally:
        await close_all_pools()
    return 1 if failures else 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--org-id", action="append", required=True, help="UUID de la organizacion (repetible)")
    parser.add_argument("--apply", action="store_true", help="escribe los rangos (por defecto solo ensayo)")
    parser.add_argument("--refresh", action="store_true", help="recalcula tambien las columnas que ya tienen rango")
    args = parser.parse_args()
    with contextlib.suppress(Exception):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    return asyncio.run(run(args.org_id, args.apply, args.refresh))


if __name__ == "__main__":
    sys.exit(main())
