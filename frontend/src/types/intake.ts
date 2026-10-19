/**
 * Contrato de la CARGA INTELIGENTE (backend: /api/v1/intake/* y PUT /api/v1/schema/tables/{id}/roles).
 *
 * Flujo: `POST /intake/analyze` (varios archivos -> una propuesta por hoja, no guarda nada) ->
 * `POST /intake/commit` (los MISMOS archivos + el plan confirmado) -> opcional `POST /intake/undo`.
 */

/** Tipo de hoja que entiende el sistema. */
export type SheetKind =
  | "productos"
  | "ventas"
  | "compras"
  | "cuentas_por_cobrar"
  | "movimientos_inventario"
  | "clientes"
  | "proveedores"
  | "otro"

/** Quién decidió los roles: reglas del sistema, el modelo de IA o la persona. */
export type MappingSource = "heuristic" | "ai" | "user"

export interface OntologyKind {
  kind: SheetKind
  /** "ventas", "cuentas por cobrar"... */
  label: string
  /** Frase para el desplegable: "Ventas (lo que vendiste)". */
  choice_label: string
}

export interface OntologyRole {
  role: string
  label: string
  /** "lo que pagaste por cada producto" */
  explain: string
}

export interface Ontology {
  kinds: OntologyKind[]
  roles: Record<SheetKind, OntologyRole[]>
}

export interface IntakeColumn {
  index: number
  /** Nombre limpio con el que se guarda la columna. */
  name: string
  original_name: string
  role: string
  role_label: string
  explain: string
  /** 0..1 */
  confidence: number
  type: string
  sample: string[]
  source: MappingSource | "cache"
}

export type DestinationAction = "create" | "append" | "ask"

export interface IntakeDestination {
  action: DestinationAction
  /** Hoja existente a la que se sumaría (o con la que hay duda). */
  table_id: string | null
  /** Clave de otra hoja DEL MISMO cargue a la que se sumaría. */
  into_sheet: string | null
  table_name?: string | null
  display_name: string | null
  similarity: number | null
  /** Nombre propuesto si se guarda como hoja nueva. */
  new_display_name: string
  new_table_name?: string
  text: string
}

export interface IntakeTokens {
  model_calls: number
  prompt: number
  output: number
  thoughts: number
  total: number
  from_cache: boolean
}

export type SheetStatus = "ready" | "empty" | "error"

export interface IntakeSheet {
  key: string
  sheet_name: string | null
  status: SheetStatus
  rows?: number
  columns_count?: number
  kind?: SheetKind
  kind_label?: string
  kind_confidence?: number
  mapping_source?: MappingSource
  from_cache?: boolean
  needs_review?: boolean
  review_reasons?: string[]
  period?: { from: string; to: string } | null
  /** "tus ventas" */
  kind_phrase?: string
  /** "731 filas, de mayo a octubre de 2026" */
  stats?: string
  /** "Encontré tus ventas: 731 filas, de mayo a octubre de 2026." */
  summary?: string
  columns?: IntakeColumn[]
  tokens?: IntakeTokens
  signature?: string
  destination?: IntakeDestination
  note?: string
  error?: { code: string; message: string }
}

export interface IntakeFile {
  file_name: string
  file_hash?: string
  size_bytes?: number
  status: "ok" | "error"
  error: { code: string; message: string } | null
  sheets: IntakeSheet[]
}

export interface AnalyzeResponse {
  files: IntakeFile[]
  ai: { model_calls: number; prompt_tokens: number; output_tokens: number; thoughts_tokens: number; cache_hits: number }
  limits: { max_files: number; max_rows: number }
}

// --- commit -----------------------------------------------------------------

export interface PlanColumn {
  name: string
  role: string
  confidence?: number
  edited?: boolean
}

export type PlanAction = "create" | "append" | "skip"

export interface PlanSheet {
  file_name: string
  sheet_name: string | null
  action: PlanAction
  table_id?: string | null
  into_sheet?: string | null
  display_name?: string | null
  kind?: SheetKind | null
  mapping_source?: MappingSource | null
  columns?: PlanColumn[] | null
}

export interface UndoInfo {
  action: "delete_table" | "delete_rows" | "none"
  table_id: string | null
  loaded_at?: string
}

export type CommitStatus = "created" | "appended" | "duplicate" | "skipped" | "error"

export interface CommitResult {
  key: string
  file_name: string
  sheet_name: string | null
  status: CommitStatus
  table_id: string | null
  table_name: string | null
  display_name: string | null
  kind: SheetKind | null
  kind_label: string | null
  rows_inserted: number
  total_rows: number | null
  message: string | null
  error: { code: string; message: string } | null
  undo: UndoInfo
  loaded_at?: string | null
}

export interface CommitResponse {
  results: CommitResult[]
  totals: { created: number; appended: number; duplicates: number; errors: number; rows_inserted: number }
}

/** Respuesta de PUT /schema/tables/{id}/roles. */
export interface UpdatedRoles {
  table_id: string
  table_name: string
  display_name: string
  kind: SheetKind
  kind_label: string
  mapping_source: MappingSource
  columns: Array<{ name: string; label: string; type: string | null; role: string; role_label: string; explain: string; confidence: number }>
}
