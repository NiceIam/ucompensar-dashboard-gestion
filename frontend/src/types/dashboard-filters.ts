/**
 * Filtros de lectura del tablero (periodo + categorías) y detalle al tocar un dato.
 * Contrato con el backend: `POST /dashboards/{id}/execute` (cuerpo `{ filters }`),
 * `GET /dashboards/{id}/filter-options` y `POST /dashboards/{id}/widgets/{widget}/drill`.
 */

export type PeriodPresetId = "last_7" | "last_30" | "last_90" | "this_month" | "last_month" | "this_year" | "all"

/** Periodo: un atajo o un rango (ISO AAAA-MM-DD, ambos extremos inclusivos; uno de los dos puede faltar). */
export interface PeriodFilter {
  preset?: PeriodPresetId
  from?: string
  to?: string
}

export interface CategoryFilter {
  /** Clave que entrega el servidor ("producto", "cliente", "metodo_pago"...). */
  key: string
  values: string[]
}

/** Estado de los filtros de la pantalla (vive en la URL). */
export interface DashboardFilters {
  /** null = todo el tiempo. */
  period: PeriodFilter | null
  where: CategoryFilter[]
}

/** Lo que se manda al servidor (solo si hay algo activo). */
export interface FiltersRequest {
  period?: { preset: PeriodPresetId } | { from?: string; to?: string }
  where?: CategoryFilter[]
}

/** Opciones de filtro (GET /filter-options). */
export interface FilterOptionValue {
  value: string
  count: number
}

export interface FilterDimension {
  key: string
  label: string
  values: FilterOptionValue[]
  /** Cuántos valores distintos tiene en total. */
  distinct: number
  /** Cuántos valores más hay que no se listan (se buscan escribiendo). */
  more: number
  tables?: string[]
}

export interface FilterOptions {
  today: string
  presets: { id: PeriodPresetId; label: string }[]
  date: { column: string; label: string; min: string; max: string; tables: string[] } | null
  dimensions: FilterDimension[]
}

/** Lo que el servidor confirma haber aplicado. */
export interface AppliedFilters {
  period?: { preset: PeriodPresetId | null; label: string | null; from: string | null; to: string | null }
  where?: CategoryFilter[]
}

/** Aviso discreto en un gráfico o cifra ("este gráfico no tiene fecha"). */
export interface WidgetNote {
  code: "no_date" | "no_dimension" | "legacy_filters" | string
  message: string
}

// ─── Detalle al tocar un dato ────────────────────────────────────────────────

/** Qué se tocó. `value` = clave exacta del dato (o su nombre); null = el grupo «(sin dato)». */
export interface DrillRequest {
  value?: string | number | null
  /** Dimensión de detalle elegida («Ver por»); si falta, el servidor elige la mejor. */
  by?: string
  /** La porción «Otros (n)» de una torta. */
  other?: boolean
  filters?: FiltersRequest
}

export interface DrillRow {
  name: string
  value: number
  /** 0..1 sobre el total (null si la medida no se suma: promedios, máximos...). */
  share: number | null
}

export interface DrillDimension {
  by: string
  label: string
  kind: "category" | "period"
}

export interface DrillResponse {
  title: string
  widget: { id: string | null; title: string }
  x: { label: string; bucket: "day" | "week" | "month" | "year" | null }
  measure: { label: string; fn: string; unit: "money" | "count" | "number" }
  total: number | null
  /** Filas (registros) que cumplen. */
  records: number
  additive: boolean
  by: DrillDimension | null
  dimensions: DrillDimension[]
  rows: DrillRow[]
  groups: number
  shown: number
  truncated: boolean
  /** «Mostrando 20 de 63» cuando hay más filas que las mostradas. */
  message: string | null
  rest?: { groups: number; value: number | null }
  order: "value" | "period"
  notes: string[]
  empty: boolean
  filters?: AppliedFilters
  /** Pregunta lista para el asistente con este contexto. */
  question?: string
}
