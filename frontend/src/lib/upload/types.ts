/**
 * Contratos de los endpoints de carga, tal como los devuelve el backend hoy
 * (no se cambian): POST /api/v1/schema/analyze y POST /api/v1/schema/smart-upload.
 */

export interface AnalysisColumn {
  original_name: string
  clean_name: string
  inferred_type: string
  non_null_count: number
  total_count: number
  null_count: number
  unique_count: number
  sample_values: string[]
  is_required: boolean
}

export interface MatchingTable {
  table_id: string
  table_name: string
  display_name: string
  match_score: number
  matched_columns: string[]
  missing_in_table: string[]
  extra_in_table: string[]
}

/** Respuesta de /schema/analyze (lee solo la PRIMERA hoja de un Excel). */
export interface FileAnalysis {
  row_count: number
  column_count: number
  columns: AnalysisColumn[]
  suggested_table_name: string
  suggested_display_name: string
  matching_table: MatchingTable | null
}

export interface SmartUploadSheetResult {
  sheet_name?: string | null
  status: string
  table_name?: string
  table_id?: string
  rows_inserted?: number
  total_rows?: number
  error?: string
}

/** Respuesta de /schema/smart-upload (una hoja o varias). */
export interface SmartUploadResult {
  status: string
  table_name?: string
  table_id?: string
  match_score?: number
  rows_inserted?: number
  total_rows?: number
  actions?: unknown[]
  multi_sheet?: boolean
  sheets_processed?: number
  total_rows_inserted?: number
  sheets?: SmartUploadSheetResult[]
}

/** Umbral con el que el servidor decide cargar en una tabla existente. */
export const MATCH_THRESHOLD = 0.5
