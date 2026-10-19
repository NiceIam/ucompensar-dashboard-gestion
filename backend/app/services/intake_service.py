"""Carga inteligente: analizar varios archivos, proponer, confirmar y guardar — PI0320251.

Flujo (sin estado en el servidor: el cliente reenvia los archivos al confirmar):
  analyze_uploads: lee TODAS las hojas de TODOS los archivos -> entiende cada una (schema_ai_service: cache ->
      determinista -> a lo sumo UNA llamada a Gemini si es ambigua) -> propone destino (hoja nueva / sumar a una
      existente / preguntar) -> NO guarda nada.
  commit_uploads: aplica lo confirmado (reutiliza create_table / modify_table / load_csv_to_table).
  update_table_roles: el duenio corrige un rol y el cambio queda como la verdad de esa estructura.

EMPAREJAMIENTO SEGURO. Una carga se SUMA a una hoja existente solo si el tipo (`kind`) coincide Y las columnas se
parecen mucho (>= 80 %). Si se parece pero no tanto (>= 50 %), se PROPONE y el duenio decide (por omisión se crea una
hoja nueva): jamas se mezcla en silencio. Una hoja de tipo `otro` solo se suma a otra con EXACTAMENTE las mismas
columnas. Dentro de un mismo cargue, hojas parecidas (p. ej. doce meses de ventas) se juntan en una sola.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import unicodedata
import uuid
import warnings
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Optional

import pandas as pd
from fastapi import HTTPException, UploadFile, status

from app.services import intake_ontology as onto
from app.services import schema_agent_service as agent
from app.services import schema_ai_service as ai
from app.services import schema_understanding as su
from app.services.business_insights_service import _MONTHS, fmt_int
from app.services.file_service import MAX_FILE_SIZE_BYTES, MAX_ROWS, parse_file_sheets
from app.services.intake_ontology import fold

logger = logging.getLogger(__name__)

MAX_FILES = 10
MAX_TOTAL_BYTES = 40 * 1024 * 1024
MAX_SHEETS_PER_FILE = 15
MAX_COLUMNS = 80
APPEND_MIN_SIMILARITY = 0.8        # sumar a una hoja existente sin preguntar
ASK_MIN_SIMILARITY = 0.5           # parecida pero no tanto: se le pregunta al duenio
ASK_MIN_COVERAGE = 0.6
DUPLICATE_SHARE = 0.9              # si el 90 % de las filas ya estan, la carga se omite (mismo archivo dos veces)
MAX_DISPLAY_CHARS = 150

FOUND_PHRASE = {
    "productos": "tu lista de productos", "ventas": "tus ventas", "compras": "tus compras",
    "cuentas_por_cobrar": "tus cuentas por cobrar", "movimientos_inventario": "tus movimientos de inventario",
    "clientes": "tu lista de clientes", "proveedores": "tu lista de proveedores", "otro": "tus datos",
}
_GENERIC_STEMS = frozenset({
    "datos", "data", "export", "exportacion", "reporte", "informe", "libro1", "libro", "book1", "book", "archivo",
    "nuevo", "untitled", "documento", "hoja1", "hoja", "sheet1", "sheet", "copia", "plantilla", "template",
    "descarga", "download", "file", "excel", "base", "bd", "listado", "lista",
})
_GENERIC_SHEET = re.compile(r"^(hoja|sheet|tabla|table)\s*\d*$", re.I)


class IntakeError(Exception):
    """Error HUMANO de una hoja o de un archivo (el mensaje se le muestra al duenio tal cual)."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


# ---------------------------------------------------------------------------
# Lectura y limpieza de la hoja
# ---------------------------------------------------------------------------

def normalize_frame(df: pd.DataFrame) -> pd.DataFrame:
    """Quita lo que estorba en una hoja de Excel "en desorden": filas y columnas completamente vacias y, cuando
    el encabezado real no esta en la primera fila (titulo, logo, fecha del reporte...), lo busca en las primeras 12."""
    if df.empty and len(df.columns) == 0:
        return df
    df = df.copy()
    names = [str(c) for c in df.columns]
    unnamed = sum(1 for n in names if n.startswith("Unnamed:"))
    if len(df) and unnamed >= max(2, len(names) / 2):
        width = len(df.columns)
        for pos in range(min(12, len(df))):
            row = df.iloc[pos]
            filled = [v for v in row.tolist() if not pd.isna(v) and str(v).strip()]
            texty = [v for v in filled if isinstance(v, str) and not re.fullmatch(r"[-+]?[\d.,\s$%]+", v.strip())]
            if len(filled) >= max(2, 0.6 * width) and len(texty) >= 0.8 * len(filled):
                header = [str(v).strip() if not pd.isna(v) and str(v).strip() else f"Columna {i + 1}"
                          for i, v in enumerate(row.tolist())]
                df = df.iloc[pos + 1:].reset_index(drop=True)
                df.columns = header
                break
    # columnas "Unnamed" totalmente vacias (cola de Excel) y filas totalmente vacias
    keep = [i for i, c in enumerate(df.columns)
            if not (str(c).startswith("Unnamed:") and df.iloc[:, i].isna().all())]
    df = df.iloc[:, keep]
    df = df.dropna(how="all").reset_index(drop=True)
    return df


@dataclass
class Prepared:
    df: pd.DataFrame
    analysis: dict
    profiles: list[su.ColumnProfile]


def prepare_sheet(df: pd.DataFrame, enforce_limits: bool = True) -> Prepared:
    df = normalize_frame(df)
    if len(df.columns) == 0:
        return Prepared(df, {"row_count": 0, "column_count": 0, "columns": []}, [])
    if enforce_limits and len(df.columns) > MAX_COLUMNS:
        raise IntakeError("too_many_columns", f"Esta hoja tiene {len(df.columns)} columnas y el límite es {MAX_COLUMNS}.")
    if enforce_limits and len(df) > MAX_ROWS:
        raise IntakeError(
            "too_many_rows",
            f"Esta hoja tiene {fmt_int(len(df))} filas y el límite es {fmt_int(MAX_ROWS)}. Divídela en partes más pequeñas.",
        )
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        analysis = agent.analyze_csv(df)
        profiles = su.profiles_from_frame(
            df, [c["clean_name"] for c in analysis["columns"]], [c["inferred_type"] for c in analysis["columns"]]
        )
    return Prepared(df, analysis, profiles)


# ---------------------------------------------------------------------------
# Nombres
# ---------------------------------------------------------------------------

def _slug(text: str) -> str:
    plain = "".join(c for c in unicodedata.normalize("NFKD", text) if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", "_", plain.casefold()).strip("_")


def _pretty(text: str) -> str:
    text = re.sub(r"\.(xlsx|xls|csv|json)$", "", text.strip(), flags=re.I)
    text = re.sub(r"[_\-]+", " ", text)
    text = re.sub(r"\s+", " ", onto.clean_text(text, MAX_DISPLAY_CHARS)).strip()
    if text and text == text.lower():
        text = text[0].upper() + text[1:]
    return text


def _is_generic(text: str) -> bool:
    f = fold(text)
    return not f or f.replace(" ", "") in _GENERIC_STEMS or bool(_GENERIC_SHEET.match(text.strip())) \
        or bool(re.fullmatch(r"(hoja|sheet|libro|book|copia de|datos)?\s*\d+", f))


def derive_display_name(kind: str, file_name: str, sheet_name: Optional[str], multi_sheet: bool) -> str:
    """Nombre amable para una hoja nueva: el de la pestana (si dice algo), si no el del archivo, si no el tipo."""
    stem = _pretty(file_name or "")
    sheet = _pretty(sheet_name or "") if sheet_name else ""
    if sheet and not _is_generic(sheet):
        name = sheet
    elif stem and not _is_generic(stem):
        name = stem + (f" - {sheet}" if multi_sheet and sheet else "")
    elif kind != "otro":
        name = onto.KIND_LABEL[kind].capitalize()
    else:
        name = stem or "Datos"
    return onto.clean_text(name, MAX_DISPLAY_CHARS) or "Datos"


def unique_table_name(display: str, taken: set[str]) -> str:
    base = (_slug(display) or "datos")[:60]
    name, n = base, 2
    while name in taken:
        name = f"{base}_{n}"
        n += 1
    return name


# ---------------------------------------------------------------------------
# Resumen en lenguaje del duenio
# ---------------------------------------------------------------------------

def _month_year(d: date) -> str:
    return f"{_MONTHS[d.month - 1]} de {d.year}"


def period_phrase(lo: date, hi: date) -> str:
    if (lo.year, lo.month) == (hi.year, hi.month):
        return f"de {_month_year(lo)}" if lo != hi else f"del {lo.day} de {_month_year(lo)}"
    if lo.year == hi.year:
        return f"de {_MONTHS[lo.month - 1]} a {_MONTHS[hi.month - 1]} de {hi.year}"
    return f"de {_month_year(lo)} a {_month_year(hi)}"


def date_span(series: pd.Series) -> Optional[tuple[date, date]]:
    """(primera, ultima) fecha legible de una columna, o None si no se lee como fechas."""
    values = series.dropna()
    if values.empty:
        return None
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        try:
            parsed = pd.to_datetime(values, errors="coerce", dayfirst=True, format="mixed")
        except (ValueError, TypeError):
            return None
    ok = parsed.dropna()
    if len(ok) < 0.7 * len(values) or ok.empty:
        return None
    lo, hi = ok.min().date(), ok.max().date()
    if lo.year < 1990 or hi.year > 2100:
        return None
    return lo, hi


def sheet_summary(kind: str, rows: int, columns: int, span: Optional[tuple[date, date]]) -> dict:
    n = f"{fmt_int(rows)} {'fila' if rows == 1 else 'filas'}"
    if kind == "otro":
        stats = f"{n} y {fmt_int(columns)} {'columna' if columns == 1 else 'columnas'}"
        return {"kind_phrase": FOUND_PHRASE[kind], "stats": stats, "summary": f"Guardaré tus datos tal cual: {stats}."}
    stats = n + (f", {period_phrase(*span)}" if span else "")
    return {"kind_phrase": FOUND_PHRASE[kind], "stats": stats, "summary": f"Encontré {FOUND_PHRASE[kind]}: {stats}."}


# ---------------------------------------------------------------------------
# Tablas existentes y emparejamiento seguro
# ---------------------------------------------------------------------------

async def load_org_tables(org_id: str) -> list[dict]:
    pool = await agent.get_org_pool(org_id)
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT id, table_name, display_name, row_count, columns_definition FROM org_data_tables"
        )
    out = []
    for r in rows:
        d = dict(r)
        d["columns_definition"] = onto.parse_columns(d.get("columns_definition"))
        out.append(d)
    return sorted(out, key=lambda t: t["table_name"])


@dataclass
class TableView:
    """Una tabla (existente o propuesta en este mismo cargue) vista para decidir si una hoja se le suma."""
    table_id: Optional[str]
    key: Optional[str]                 # clave de la hoja del cargue que la crea (tablas virtuales)
    table_name: str
    display_name: str
    row_count: int
    kind: str
    names: list[str]
    roles: dict[str, str]              # columna -> rol
    columns: list[dict] = field(default_factory=list)

    @property
    def virtual(self) -> bool:
        return self.table_id is None


def view_of_table(t: dict) -> TableView:
    cols = [c for c in onto.parse_columns(t.get("columns_definition")) if isinstance(c, dict) and isinstance(c.get("name"), str)]
    names = [c["name"] for c in cols]
    meta = onto.read_sheet_meta(cols)
    if meta is not None:
        kind = meta["kind"]
        roles = {n: r["role"] for n, r in onto.column_roles(cols).items() if r["role"] != onto.OTHER_ROLE}
    else:
        kind, _ = su.kind_of_names(names, t.get("table_name"))
        roles = {}
    return TableView(str(t["id"]), None, t["table_name"], t.get("display_name") or t["table_name"],
                     int(t.get("row_count") or 0), kind, names, roles, cols)


def match_columns(new_cols: list[su.ColumnResult], table: TableView) -> dict[int, str]:
    """indice de columna nueva -> columna de la tabla. Primero por nombre; lo que queda, por rol (mismo tipo)."""
    by_fold: dict[str, str] = {}
    for n in table.names:
        by_fold.setdefault(fold(n), n)
    mapping: dict[int, str] = {}
    used: set[str] = set()
    for c in new_cols:
        target = by_fold.get(fold(c.clean)) or by_fold.get(fold(c.original))
        if target and target not in used:
            mapping[c.index] = target
            used.add(target)
    role_to_col = {r: n for n, r in table.roles.items()}
    for c in new_cols:
        if c.index in mapping or c.role == onto.OTHER_ROLE:
            continue
        target = role_to_col.get(c.role)
        if target and target not in used:
            mapping[c.index] = target
            used.add(target)
    return mapping


@dataclass
class Candidate:
    table: TableView
    mapping: dict[int, str]
    similarity: float                  # Dice: 2*coincidentes / (columnas nuevas + columnas de la tabla)
    coverage_new: float                # que parte de las columnas nuevas ya existe en la tabla


def best_candidate(und: su.Understanding, tables: list[TableView]) -> Optional[Candidate]:
    best: Optional[Candidate] = None
    n_new = len(und.columns)
    for t in tables:
        if t.kind != und.kind or not n_new or not t.names:
            continue
        mapping = match_columns(und.columns, t)
        m = len(mapping)
        cand = Candidate(t, mapping, 2 * m / (n_new + len(t.names)), m / n_new)
        if und.kind == "otro" and not (m == n_new == len(t.names)):
            continue       # los datos sin tipo solo se suman a una hoja con EXACTAMENTE las mismas columnas
        key = (cand.similarity, t.row_count, t.table_name)
        if best is None or key > (best.similarity, best.table.row_count, best.table.table_name):
            best = cand
    return best


def decide(und: su.Understanding, cand: Optional[Candidate]) -> str:
    """'append' | 'ask' | 'create'."""
    if cand is None:
        return "create"
    if und.kind == "otro":
        return "append"
    if cand.table.row_count == 0 and not cand.table.virtual and cand.coverage_new >= ASK_MIN_COVERAGE:
        return "append"        # plantilla vacia: llenarla no mezcla nada
    if cand.similarity >= APPEND_MIN_SIMILARITY and cand.coverage_new >= APPEND_MIN_SIMILARITY:
        return "append"
    if cand.coverage_new >= ASK_MIN_COVERAGE and cand.similarity >= ASK_MIN_SIMILARITY:
        return "ask"
    return "create"


def _percent(x: float) -> int:
    return int(round(x * 100))


# ---------------------------------------------------------------------------
# Propuesta de una hoja
# ---------------------------------------------------------------------------

def _column_payload(c: su.ColumnResult, kind: str, p: su.ColumnProfile, col_type: str) -> dict:
    title, explain = onto.role_titles(kind, c.role)
    if c.role == onto.OTHER_ROLE and c.desc:
        explain = c.desc
    return {
        "index": c.index, "name": c.clean, "original_name": onto.clean_text(c.original, 80),
        "role": c.role, "role_label": title, "explain": explain, "confidence": round(c.confidence, 2),
        "type": col_type, "sample": p.sample[:3], "source": c.source,
    }


def _sheet_role_columns(und: su.Understanding, prep: Prepared) -> list[dict]:
    types = {c["clean_name"]: c["inferred_type"] for c in prep.analysis["columns"]}
    out = []
    for c, p in zip(und.columns, prep.profiles):
        out.append(_column_payload(c, und.kind, p, su.final_type(types.get(c.clean, "text"), c.role, p)))
    return out


def _span_of(und: su.Understanding, prep: Prepared) -> Optional[tuple[date, date]]:
    pref = ("fecha", "fecha_emision", "fecha_vencimiento")
    for role in pref:
        col = next((c for c in und.columns if c.role == role), None)
        if col is not None:
            return date_span(prep.df.iloc[:, col.index])
    return None


def build_columns_def(und: su.Understanding, prep: Prepared, kind_override: Optional[str] = None) -> list[dict]:
    """columns_definition de una hoja NUEVA, con roles y metadata de la hoja (ver intake_ontology)."""
    kind = kind_override or und.kind
    by_clean = {c["clean_name"]: c for c in prep.analysis["columns"]}
    cols: list[dict] = []
    for c, p in zip(und.columns, prep.profiles):
        a = by_clean[c.clean]
        role = c.role if onto.is_valid_role(kind, c.role) else onto.OTHER_ROLE
        entry = {
            "name": c.clean,
            "type": su.final_type(a["inferred_type"], role, p),
            "required": a["is_required"],
            "role": role,
            "role_confidence": round(c.confidence, 3),
            "label": onto.clean_text(c.original, 80),
        }
        if c.desc and role == onto.OTHER_ROLE:
            entry["desc"] = onto.clean_text(c.desc, 80)
        cols.append(entry)
    source = und.source if und.source in ("heuristic", "ai", "user") else ("user" if und.source == "cache" else "heuristic")
    return onto.with_sheet_meta(cols, onto.make_sheet_meta(kind, und.kind_confidence, source, und.signature))


def _virtual_view(key: str, display: str, table_name: str, und: su.Understanding, prep: Prepared, rows: int) -> TableView:
    cols = build_columns_def(und, prep)
    return TableView(None, key, table_name, display, rows, und.kind, [c["name"] for c in cols],
                     {c["name"]: c["role"] for c in cols if c["role"] != onto.OTHER_ROLE}, cols)


async def understand_sheet(org_id: str, prep: Prepared, sheet_name: Optional[str], file_name: Optional[str],
                           org_tables: list[dict], budget: ai.AiBudget, use_ai: bool = True) -> su.Understanding:
    return await ai.understand(
        org_id, prep.profiles, sheet_name=sheet_name, file_name=file_name, org_tables=org_tables,
        budget=budget, use_ai=use_ai,
    )


# ---------------------------------------------------------------------------
# analyze
# ---------------------------------------------------------------------------

async def _read_upload(upload: UploadFile) -> tuple[bytes, list[tuple[Optional[str], pd.DataFrame]]]:
    content = await upload.read()
    await upload.seek(0)
    if len(content) > MAX_FILE_SIZE_BYTES:
        raise IntakeError("too_large", f"El archivo pesa más de {MAX_FILE_SIZE_BYTES // 1024 // 1024} MB. Prueba con uno más liviano.")
    if not content:
        raise IntakeError("empty", "El archivo está vacío.")
    try:
        sheets = await parse_file_sheets(upload)
    except HTTPException as exc:
        code = "unsupported_type" if "no soportado" in str(exc.detail).lower() else "unreadable"
        raise IntakeError(code, str(exc.detail)) from exc
    if len(sheets) > MAX_SHEETS_PER_FILE:
        raise IntakeError("too_many_sheets", f"El Excel tiene {len(sheets)} hojas y el límite es {MAX_SHEETS_PER_FILE}.")
    return content, sheets


def ontology_payload() -> dict:
    """Vocabulario para los desplegables de correccion: tipos de hoja y roles por tipo, en lenguaje simple."""
    return {
        "kinds": [{"kind": k, "label": onto.KIND_LABEL[k], "choice_label": onto.KIND_CHOICE_LABEL[k]} for k in onto.KINDS],
        "roles": {k: onto.allowed_roles(k) for k in onto.KINDS},
    }


def sheet_key(file_name: str, sheet_name: Optional[str]) -> str:
    return f"{file_name}::{sheet_name or ''}"


async def analyze_uploads(org_id: str, uploads: list[UploadFile], *, use_ai: bool = True) -> dict:
    """Propuesta por hoja para TODOS los archivos. No guarda nada."""
    if not uploads:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="No llegó ningún archivo.")
    if len(uploads) > MAX_FILES:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                            detail=f"Puedes subir hasta {MAX_FILES} archivos a la vez.")
    org_tables = await load_org_tables(org_id)
    taken = {t["table_name"] for t in org_tables}
    existing_views = [view_of_table(t) for t in org_tables]
    budget = ai.AiBudget(org_id)
    batch_views: list[TableView] = []
    batch_creators: dict[str, dict] = {}          # clave de la hoja que crea -> su destination (para renombrar si se junta)
    total_bytes = 0
    files_out: list[dict] = []

    for upload in uploads:
        fname = onto.clean_text(upload.filename or "archivo", 200) or "archivo"
        entry: dict[str, Any] = {"file_name": fname, "status": "ok", "error": None, "sheets": []}
        files_out.append(entry)
        try:
            content, sheets = await _read_upload(upload)
            total_bytes += len(content)
            if total_bytes > MAX_TOTAL_BYTES:
                raise IntakeError("too_large", "Entre todos los archivos pesan demasiado. Súbelos en tandas más pequeñas.")
        except IntakeError as exc:
            entry["status"], entry["error"] = "error", {"code": exc.code, "message": exc.message}
            continue
        entry["file_hash"] = hashlib.sha256(content).hexdigest()[:16]
        entry["size_bytes"] = len(content)
        multi = len(sheets) > 1
        for sname, raw in sheets:
            key = sheet_key(fname, sname)
            sheet: dict[str, Any] = {"key": key, "sheet_name": sname, "status": "ready"}
            entry["sheets"].append(sheet)
            try:
                prep = prepare_sheet(raw)
            except IntakeError as exc:
                sheet.update(status="error", error={"code": exc.code, "message": exc.message}, rows=len(raw))
                continue
            if prep.df.empty or not prep.profiles:
                sheet.update(status="empty", rows=0, columns_count=0,
                             note="Esta hoja no tiene datos; la omitiré.")
                continue
            und = await understand_sheet(org_id, prep, sname, fname, org_tables, budget, use_ai)
            describe_into(sheet, und, prep)
            # --- destino ---
            cand = best_candidate(und, existing_views + batch_views)
            action = decide(und, cand)
            display = derive_display_name(und.kind, fname, sname, multi)
            dest: dict[str, Any] = {"action": action, "table_id": None, "into_sheet": None, "table_name": None,
                                    "display_name": None, "similarity": None, "new_display_name": display}
            if action in ("append", "ask") and cand is not None:
                t = cand.table
                dest.update(table_id=t.table_id, into_sheet=t.key, table_name=t.table_name,
                            display_name=t.display_name, similarity=round(cand.similarity, 2))
                if t.virtual:
                    creator = batch_creators.get(t.key)
                    if creator is not None and action == "append":
                        _name_batch_table(creator, t, und.kind, taken)
                    dest["display_name"], dest["table_name"] = t.display_name, t.table_name
                dest["text"] = (
                    f"Se sumará a «{dest['display_name']}» (se parece en un {_percent(cand.similarity)} %)."
                    if action == "append" else
                    f"Se parece en un {_percent(cand.similarity)} % a «{dest['display_name']}», pero no estoy seguro: "
                    "¿la sumo ahí o la guardo aparte?"
                )
            else:
                dest["text"] = f"Se guardará como una hoja nueva: «{display}»."
            if action in ("create", "ask"):
                tname = unique_table_name(display, taken)
                dest["new_table_name"] = tname
                taken.add(tname)
                # Esta hoja nueva queda disponible para que otras del mismo cargue se le sumen.
                v = _virtual_view(key, display, tname, und, prep, len(prep.df))
                batch_views.append(v)
                batch_creators[key] = dest
            sheet["destination"] = dest
            if action == "ask":
                sheet["needs_review"] = True
                sheet.setdefault("review_reasons", []).append("No estoy seguro de si esta hoja va junto a una que ya tienes.")
    # los marcadores internos no salen
    for f in files_out:
        for s in f.get("sheets", []):
            d = s.get("destination")
            if d:
                d.pop("_renamed", None)
    return {"files": files_out, "ai": budget.summary(), "limits": {"max_files": MAX_FILES, "max_rows": MAX_ROWS}}


def _name_batch_table(creator: dict, table: TableView, kind: str, taken: set[str]) -> None:
    """Dos o mas hojas de un mismo cargue se juntan en una: la hoja resultante lleva el nombre del tipo ("Ventas")
    y no el de la primera pestana ("Ventas enero")."""
    if kind == "otro" or creator.get("_renamed"):
        return
    generic = onto.KIND_LABEL[kind].capitalize()
    new_name = unique_table_name(generic, taken)
    if new_name != _slug(generic):
        return                  # ya hay una hoja con ese nombre: se deja el de la primera
    creator["_renamed"] = True
    creator["new_display_name"] = generic
    creator["new_table_name"] = new_name
    creator["text"] = f"Se guardará como una hoja nueva: «{generic}» (con las demás hojas parecidas de este cargue)."
    table.display_name, table.table_name = generic, new_name
    taken.add(new_name)


def describe_into(sheet: dict, und: su.Understanding, prep: Prepared) -> None:
    span = _span_of(und, prep)
    rows = len(prep.df)
    sheet.update(
        rows=rows, columns_count=len(prep.profiles), kind=und.kind, kind_label=onto.KIND_LABEL[und.kind],
        kind_confidence=round(und.kind_confidence, 2), mapping_source=und.source if und.source != "cache" else "ai",
        from_cache=und.from_cache, needs_review=und.needs_review, review_reasons=list(und.review_reasons),
        period={"from": span[0].isoformat(), "to": span[1].isoformat()} if span else None,
        columns=_sheet_role_columns(und, prep),
        tokens=_tokens_of(und), signature=und.signature,
    )
    sheet.update(sheet_summary(und.kind, rows, len(prep.profiles), span))
    if und.ai_error and und.ai_error not in ("desactivada",):
        sheet["ai_note"] = und.ai_error


def _tokens_of(und: su.Understanding) -> dict:
    u = und.usage or {}
    return {
        "model_calls": u.get("model_calls", 0), "prompt": u.get("prompt_tokens", 0), "output": u.get("output_tokens", 0),
        "thoughts": u.get("thoughts_tokens", 0), "total": u.get("total_tokens", 0), "from_cache": und.from_cache,
    }


# ---------------------------------------------------------------------------
# commit
# ---------------------------------------------------------------------------

def _validate_plan_columns(item: dict, prep: Prepared, kind: str) -> Optional[dict[str, tuple[str, float, bool]]]:
    """{columna limpia: (rol, confianza, editada)} de lo que mando el cliente, validado contra listas blancas."""
    raw = item.get("columns")
    if raw is None:
        return None
    clean_names = {p.clean for p in prep.profiles}
    out: dict[str, tuple[str, float, bool]] = {}
    seen_roles: dict[str, str] = {}
    for col in raw:
        name, role = col.get("name"), col.get("role")
        if name not in clean_names:
            raise IntakeError("unknown_column", "Una de las columnas que mandaste no está en el archivo. Vuelve a subirlo.")
        if not onto.is_valid_role(kind, role):
            raise IntakeError("invalid_role", f"«{onto.clean_text(role, 40)}» no es un uso válido para una columna de {onto.KIND_LABEL[kind]}.")
        if role != onto.OTHER_ROLE:
            if role in seen_roles:
                title = onto.role_titles(kind, role)[0]
                raise IntakeError("duplicate_role", f"Elegiste «{title}» para dos columnas ({seen_roles[role]} y {name}). Cada uso va en una sola columna.")
            seen_roles[role] = name
        conf = col.get("confidence")
        conf = float(conf) if isinstance(conf, (int, float)) and not isinstance(conf, bool) and 0 <= conf <= 1 else 0.8
        edited = bool(col.get("edited"))
        out[name] = (role, 1.0 if edited else conf, edited)
    return out


async def _understanding_from_plan(org_id: str, prep: Prepared, item: dict, fname: str, org_tables: list[dict]) -> su.Understanding:
    kind = item.get("kind")
    if kind is not None and not onto.is_kind(kind):
        raise IntakeError("invalid_kind", "El tipo de hoja que mandaste no es válido.")
    roles = _validate_plan_columns(item, prep, kind) if kind and item.get("columns") is not None else None
    sig = onto.signature(p.original for p in prep.profiles)
    if kind is None or roles is None:
        # sin lo confirmado por el duenio: lo que ya se sepa (cache de esta estructura) o el paso determinista; NUNCA el modelo
        und = await ai.understand(org_id, prep.profiles, sheet_name=item.get("sheet_name"), file_name=fname,
                                  org_tables=org_tables, budget=ai.AiBudget(org_id, 0), use_ai=False)
        if kind is not None and kind != und.kind:
            for c in und.columns:
                if not onto.is_valid_role(kind, c.role):
                    c.role, c.confidence = onto.OTHER_ROLE, 0.0
            und.kind = kind
        return und
    cols = []
    for p in prep.profiles:
        role, conf, _edited = roles.get(p.clean, (onto.OTHER_ROLE, 0.0, False))
        cols.append(su.ColumnResult(p.index, p.original, p.clean, role, conf, "user"))
    any_edited = any(e for (_r, _c, e) in roles.values())
    source = "user" if any_edited else (item.get("mapping_source") if item.get("mapping_source") in ("heuristic", "ai") else "heuristic")
    kind_conf = 1.0 if any_edited else 0.8
    return su.Understanding(kind, kind_conf, cols, source=source, signature=sig, clear=True)


async def _find_table(org_id: str, table_id: str) -> Optional[dict]:
    tid = agent._parse_uuid(table_id)
    if tid is None:
        return None
    for t in await load_org_tables(org_id):
        if t["id"] == tid:
            return t
    return None


async def _existing_row_keys(org_id: str, table_uuid, limit: int = 50_000) -> set[str]:
    pool = await agent.get_org_pool(org_id)
    async with pool.acquire() as conn:
        rows = await conn.fetch(f"SELECT data FROM org_data_rows WHERE table_id = $1 LIMIT {int(limit)}", table_uuid)
    keys = set()
    for r in rows:
        data = r["data"]
        if isinstance(data, str):
            try:
                data = json.loads(data)
            except (ValueError, TypeError):
                continue
        keys.add(json.dumps(data, sort_keys=True, ensure_ascii=False))
    return keys


def _merged_columns(table_cols: list, und: su.Understanding, mapping: dict[int, str], kind: str) -> tuple[list, bool]:
    """Roles de la hoja nueva anotados en las columnas de la tabla que aun no tienen uno (nunca pisa un rol existente).
    Una tabla anterior a la carga inteligente (sin `kind`) queda con su metadata desde ahora."""
    meta = onto.read_sheet_meta(table_cols)
    by_idx = {c.index: c for c in und.columns}
    target_src = {mapping[i]: by_idx[i] for i in mapping if i in by_idx}
    used_roles = {c.get("role") for c in table_cols if isinstance(c, dict) and isinstance(c.get("role"), str)
                  and c.get("role") != onto.OTHER_ROLE}
    changed = False
    out = []
    for c in table_cols:
        nc = c
        if isinstance(c, dict) and isinstance(c.get("name"), str):
            src = target_src.get(c["name"])
            has_role = isinstance(c.get("role"), str) and c["role"] != onto.OTHER_ROLE
            if (src is not None and src.role != onto.OTHER_ROLE and not has_role and src.role not in used_roles
                    and (meta is None or meta["kind"] == kind) and onto.is_valid_role(kind, src.role)):
                nc = {**c, "role": src.role, "role_confidence": round(src.confidence, 3),
                      "label": c.get("label") or onto.clean_text(src.original, 80)}
                used_roles.add(src.role)
                changed = True
        out.append(nc)
    if meta is None and out:
        source = und.source if und.source in ("heuristic", "ai", "user") else "heuristic"
        out = onto.with_sheet_meta(out, onto.make_sheet_meta(kind, und.kind_confidence, source, und.signature))
        changed = True
    return out, changed


async def _write_columns(org_id: str, table_uuid, cols: list) -> None:
    pool = await agent.get_org_pool(org_id)
    async with pool.acquire() as conn:
        await conn.execute("UPDATE org_data_tables SET columns_definition = $1::jsonb WHERE id = $2",
                           json.dumps(cols), table_uuid)


def _result(base: dict, **kw) -> dict:
    out = {"key": base["key"], "file_name": base["file_name"], "sheet_name": base.get("sheet_name"),
           "status": "error", "table_id": None, "table_name": None, "display_name": None, "kind": None,
           "kind_label": None, "rows_inserted": 0, "total_rows": None, "message": None, "error": None,
           "undo": {"action": "none", "table_id": None}, "loaded_at": None}
    out.update(kw)
    return out


async def create_sheet(org_id: str, prep: Prepared, und: su.Understanding, display: str) -> dict:
    """Crea la hoja y carga los datos; si la carga falla no queda una tabla huerfana."""
    taken = {t["table_name"] for t in await load_org_tables(org_id)}
    cols = build_columns_def(und, prep)
    name = unique_table_name(display, taken)
    created = None
    for _ in range(6):                 # una carrera por el nombre (otra peticion lo tomo) se resuelve con otro sufijo
        created = await agent.create_table(org_id, name, display, cols)
        if "error" not in created:
            break
        taken.add(name)
        name = unique_table_name(display, taken)
    if created is None or "error" in created:
        raise IntakeError("name_taken", "No pude crear la hoja nueva. Intenta de nuevo.")
    try:
        load = await agent.load_csv_to_table(prep.df.copy(), org_id, created["table_id"])
    except Exception:
        await agent._drop_table_record(org_id, created["table_id"])
        raise
    return {"table_id": created["table_id"], "table_name": created["table_name"], "display_name": display,
            "rows_inserted": load["rows_inserted"], "total_rows": load["total_rows"]}


async def append_sheet(org_id: str, prep: Prepared, und: su.Understanding, table_row: dict,
                       guard_duplicates: bool = True) -> dict:
    """Suma los datos a una hoja existente de LA MISMA clase. Devuelve duplicate=True si ya estaban."""
    view = view_of_table(table_row)
    table_uuid = table_row["id"]
    mapping = match_columns(und.columns, view)
    rename: dict[Any, str] = {}
    for i, target in mapping.items():
        col_label = prep.df.columns[i]
        if agent._clean_column_names([col_label])[0] != target:
            rename[col_label] = target
    # columnas que la hoja existente no tiene: se declaran (con su rol si no choca con uno ya usado)
    full_defs = {d["name"]: d for d in build_columns_def(und, prep)}
    new_defs = []
    for c in und.columns:
        if c.index in mapping:
            continue
        d = {k: v for k, v in full_defs[c.clean].items() if k != "sheet"}
        if d.get("role") != onto.OTHER_ROLE and (d["role"] in view.roles.values() or not onto.is_valid_role(view.kind, d["role"])):
            d["role"], d["role_confidence"] = onto.OTHER_ROLE, 0.0
        new_defs.append(d)
    df = prep.df.copy()
    # 1. la misma carga dos veces no se duplica
    if guard_duplicates and view.row_count > 0:
        probe = df.rename(columns=rename)
        new_keys = [json.dumps(r, sort_keys=True, ensure_ascii=False) for r in agent.frame_rows(probe)]
        existing = await _existing_row_keys(org_id, table_uuid)
        dup = sum(1 for k in new_keys if k in existing)
        if new_keys and dup / len(new_keys) >= DUPLICATE_SHARE:
            return {"table_id": str(table_uuid), "table_name": view.table_name, "display_name": view.display_name,
                    "rows_inserted": 0, "total_rows": view.row_count, "duplicate": True}
    # 2. columnas nuevas + roles en las existentes
    if new_defs:
        await agent.modify_table(org_id, str(table_uuid), add_columns=new_defs)
        fresh = await _find_table(org_id, str(table_uuid))
        table_cols = onto.parse_columns(fresh["columns_definition"]) if fresh else []
    else:
        table_cols = view.columns
    merged, changed = _merged_columns(table_cols, und, mapping, view.kind)
    if changed:
        await _write_columns(org_id, table_uuid, merged)
    # 3. datos
    load = await agent.load_csv_to_table(df, org_id, str(table_uuid), column_mapping=rename or None)
    return {"table_id": str(table_uuid), "table_name": view.table_name, "display_name": view.display_name,
            "rows_inserted": load["rows_inserted"], "total_rows": load["total_rows"], "duplicate": False,
            "loaded_at": load.get("loaded_at")}


async def commit_uploads(org_id: str, uploads: list[UploadFile], plan: list[dict]) -> dict:
    """Aplica el plan confirmado. Cada hoja es independiente: una que falla no tumba a las demas."""
    if not plan:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="No hay nada que guardar.")
    if len(uploads) > MAX_FILES:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=f"Puedes subir hasta {MAX_FILES} archivos a la vez.")
    parsed: dict[str, Any] = {}
    for u in uploads:
        fname = onto.clean_text(u.filename or "archivo", 200) or "archivo"
        if fname in parsed:
            parsed[fname] = IntakeError("duplicate_file", "Mandaste dos archivos con el mismo nombre.")
            continue
        try:
            _content, sheets = await _read_upload(u)
            parsed[fname] = {s_name: df for s_name, df in sheets}
        except IntakeError as exc:
            parsed[fname] = exc
    org_tables = await load_org_tables(org_id)
    created: dict[str, dict] = {}
    results: list[dict] = []
    for item in plan:
        fname = onto.clean_text(item.get("file_name") or "", 200)
        sname = item.get("sheet_name")
        key = sheet_key(fname, sname)
        base = {"key": key, "file_name": fname, "sheet_name": sname}
        action = item.get("action")
        if action == "skip":
            results.append(_result(base, status="skipped", message="La dejé sin guardar, como pediste."))
            continue
        try:
            source = parsed.get(fname)
            if isinstance(source, IntakeError):
                raise source
            if source is None or sname not in source:
                raise IntakeError("sheet_not_found", "No encontré esa hoja en los archivos que mandaste. Vuelve a subirlos.")
            prep = prepare_sheet(source[sname])
            if prep.df.empty or not prep.profiles:
                results.append(_result(base, status="skipped", message="La hoja no tenía datos."))
                continue
            und = await _understanding_from_plan(org_id, prep, item, fname, org_tables)
            kind_label = onto.KIND_LABEL[und.kind]
            if action == "create":
                display = onto.clean_text(item.get("display_name") or "", MAX_DISPLAY_CHARS) or derive_display_name(
                    und.kind, fname, sname, len(source) > 1)
                res = await create_sheet(org_id, prep, und, display)
                created[key] = res
                results.append(_result(
                    base, status="created", kind=und.kind, kind_label=kind_label,
                    message=f"Guardé {fmt_int(res['rows_inserted'])} filas en «{display}».",
                    undo={"action": "delete_table", "table_id": res["table_id"]}, **res))
            elif action == "append":
                target_row = None
                if item.get("into_sheet"):
                    tgt = created.get(item["into_sheet"])
                    if tgt is None:
                        raise IntakeError("target_not_saved", "La hoja a la que se sumaba no se pudo guardar.")
                    target_row = await _find_table(org_id, tgt["table_id"])
                elif item.get("table_id"):
                    target_row = await _find_table(org_id, item["table_id"])
                if target_row is None:
                    raise IntakeError("table_not_found", "La hoja a la que querías sumar ya no existe.")
                tview = view_of_table(target_row)
                if tview.kind != und.kind:
                    raise IntakeError(
                        "kind_mismatch",
                        f"«{tview.display_name}» es de {onto.KIND_LABEL[tview.kind]} y esta hoja parece de {kind_label}: "
                        "no las mezclo. Guárdala como hoja nueva o cambia el tipo.")
                res = await append_sheet(org_id, prep, und, target_row)
                if res.pop("duplicate"):
                    results.append(_result(
                        base, status="duplicate", kind=und.kind, kind_label=kind_label,
                        message=f"Estos datos ya estaban en «{res['display_name']}»; no los dupliqué.", **res))
                else:
                    results.append(_result(
                        base, status="appended", kind=und.kind, kind_label=kind_label,
                        message=f"Sumé {fmt_int(res['rows_inserted'])} filas a «{res['display_name']}».",
                        undo=({"action": "delete_rows", "table_id": res["table_id"], "loaded_at": res["loaded_at"]}
                              if res.get("loaded_at") else {"action": "none", "table_id": None}), **res))
            else:
                raise IntakeError("invalid_action", "No entendí qué hacer con esta hoja.")
        except IntakeError as exc:
            results.append(_result(base, status="error", error={"code": exc.code, "message": exc.message}, message=exc.message))
        except HTTPException as exc:
            results.append(_result(base, status="error", error={"code": "rejected", "message": str(exc.detail)}, message=str(exc.detail)))
        except Exception:
            logger.exception("Fallo guardando la hoja %r", key[:80])
            msg = "No pude guardar esta hoja. Intenta de nuevo; si sigue igual, avísanos."
            results.append(_result(base, status="error", error={"code": "internal", "message": msg}, message=msg))
    totals = {
        "created": sum(1 for r in results if r["status"] == "created"),
        "appended": sum(1 for r in results if r["status"] == "appended"),
        "duplicates": sum(1 for r in results if r["status"] == "duplicate"),
        "errors": sum(1 for r in results if r["status"] == "error"),
        "rows_inserted": sum(r["rows_inserted"] or 0 for r in results),
    }
    return {"results": results, "totals": totals}


# ---------------------------------------------------------------------------
# roles (correccion del duenio)
# ---------------------------------------------------------------------------

def columns_payload(cols: list, kind: str) -> list[dict]:
    roles = onto.column_roles(cols)
    out = []
    for c in cols:
        if not isinstance(c, dict) or not isinstance(c.get("name"), str):
            continue
        r = roles.get(c["name"], {"role": onto.OTHER_ROLE, "confidence": 0.0, "label": c["name"]})
        title, explain = onto.role_titles(kind, r["role"])
        if r["role"] == onto.OTHER_ROLE and isinstance(c.get("desc"), str):
            explain = c["desc"]
        out.append({"name": c["name"], "label": r["label"], "type": c.get("type"), "role": r["role"],
                    "role_label": title, "explain": explain, "confidence": round(r["confidence"], 2)})
    return out


async def undo_commit_load(org_id: str, table_id: str, loaded_at: str) -> dict:
    res = await agent.undo_load(org_id, table_id, loaded_at)
    if "error" in res:
        raise IntakeError("not_found" if "Tabla" in res["error"] else "invalid_load", res["error"])
    return res


async def update_table_roles(org_id: str, table_id: str, roles: dict[str, Optional[str]], kind: Optional[str] = None) -> dict:
    """El duenio corrige el tipo y/o el rol de columnas de una hoja ya guardada. Se guarda como verdad
    (`mapping_source: "user"`) y la cache de firma de esa estructura se actualiza: las proximas hojas con los mismos
    encabezados salen ya corregidas, sin llamar al modelo."""
    row = await _find_table(org_id, table_id)
    if row is None:
        raise IntakeError("not_found", "Tabla no encontrada")
    cols = onto.parse_columns(row["columns_definition"])
    names = [c["name"] for c in cols if isinstance(c, dict) and isinstance(c.get("name"), str)]
    meta = onto.read_sheet_meta(cols)
    if kind is not None and not onto.is_kind(kind):
        raise IntakeError("invalid_kind", "Ese tipo de hoja no es válido.")
    new_kind = kind or (meta["kind"] if meta else su.kind_of_names(names, row["table_name"])[0])
    unknown = [n for n in roles if n not in names]
    if unknown:
        raise IntakeError("unknown_column", f"La columna «{onto.clean_text(unknown[0], 40)}» no existe en esta hoja.")
    current = {n: r["role"] for n, r in onto.column_roles(cols).items()}
    final: dict[str, str] = {}
    for n in names:
        if n in roles:
            r = roles[n] or onto.OTHER_ROLE
            if not onto.is_valid_role(new_kind, r):
                raise IntakeError("invalid_role", f"«{onto.clean_text(r, 40)}» no es un uso válido para una hoja de {onto.KIND_LABEL[new_kind]}.")
            final[n] = r
        else:
            r = current.get(n, onto.OTHER_ROLE)
            final[n] = r if onto.is_valid_role(new_kind, r) else onto.OTHER_ROLE
    seen: dict[str, str] = {}
    for n, r in final.items():
        if r != onto.OTHER_ROLE:
            if r in seen:
                title = onto.role_titles(new_kind, r)[0]
                raise IntakeError("duplicate_role", f"Elegiste «{title}» para dos columnas ({seen[r]} y {n}). Cada uso va en una sola columna.")
            seen[r] = n
    new_cols = []
    for c in cols:
        if isinstance(c, dict) and isinstance(c.get("name"), str):
            c = dict(c)
            n = c["name"]
            c["role"] = final[n]
            if n in roles or final[n] != current.get(n, onto.OTHER_ROLE):
                c["role_confidence"] = 1.0
            elif "role_confidence" not in c:
                c["role_confidence"] = 0.0
            if final[n] != onto.OTHER_ROLE:
                c.pop("desc", None)
        new_cols.append(c)
    old_sig = (meta or {}).get("signature")
    sig = old_sig or onto.signature(
        [c.get("label") if isinstance(c.get("label"), str) else c["name"] for c in new_cols if isinstance(c, dict) and "name" in c])
    new_cols = onto.with_sheet_meta(new_cols, onto.make_sheet_meta(new_kind, 1.0, "user", sig))
    await _write_columns(org_id, row["id"], new_cols)
    # la cache de firma se recalcula con lo corregido
    ai.cache_invalidate(org_id, sig)
    found = ai.mapping_from_table_columns(new_cols)
    if found:
        ai.cache_put(org_id, found[0], found[1])
    return {
        "table_id": str(row["id"]), "table_name": row["table_name"], "display_name": row["display_name"],
        "kind": new_kind, "kind_label": onto.KIND_LABEL[new_kind], "mapping_source": "user",
        "columns": columns_payload(new_cols, new_kind),
    }
