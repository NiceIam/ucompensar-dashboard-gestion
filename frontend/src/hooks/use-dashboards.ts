"use client"

import { keepPreviousData, useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import { api } from "@/lib/api"
import { EMPTY_FILTERS, filtersKey, filtersToRequest } from "@/lib/dashboard-filters"
import { drillTarget, drillVariant } from "@/lib/drill"
import type { Dashboard } from "@/types/api"
import type {
  AppliedFilters,
  DashboardFilters,
  DrillRequest,
  DrillResponse,
  FilterOptions,
  WidgetNote,
} from "@/types/dashboard-filters"

export interface DashboardDetail {
  dashboard_id: string
  name: string
  description: string | null
  created_at: string
}

export interface ChartDataPoint {
  name: string
  value: number
  /** Valor exacto de la celda cuando `name` es una versión recortada (sirve para abrir el detalle). */
  key?: string
  /** El grupo «(sin dato)». */
  empty?: boolean
  /** La porción «Otros (n)» de una torta. */
  other?: boolean
  [key: string]: string | number | boolean | undefined
}

export type MeasureUnit = "money" | "count" | "number"

export interface ChartConfig {
  /** Id del widget guardado (null en los tableros antiguos, que se calculan por defecto). */
  id?: string | null
  type: "bar" | "line" | "pie" | "area"
  title: string
  data: ChartDataPoint[]
  x: string
  y: string
  color: string
  /** Unidad de la medida (la decide el servidor por la columna medida). */
  unit?: MeasureUnit
  /** Si el gráfico no se pudo calcular (columna renombrada, hoja borrada…): el resto del tablero sigue. */
  error?: string
  /** Encabezados legibles de los ejes («Mes», «Ventas»). */
  x_label?: string
  y_label?: string
  /** Se puede tocar un dato para ver su detalle (gráficos guardados, no los de tableros antiguos). */
  drillable?: boolean
  /** Sin filas con los filtros activos: no es un error. */
  empty?: boolean
  message?: string
  /** Avisos discretos («este gráfico no tiene fecha»). */
  notes?: WidgetNote[]
}

export interface KpiConfig {
  id?: string | null
  label: string
  /** null cuando la cifra no se pudo calcular (ver `error`). */
  value: number | null
  /** Pista de icono del backend ("Database", "TrendingUp", "DollarSign"…). */
  icon: string
  /** Unidad explícita del servidor: manda sobre cualquier heurística ("money" en pesos, "count" cantidad). */
  unit?: MeasureUnit
  /** Columna de origen del cálculo. Si es de dinero (total, precio, valor…), se muestra en pesos. */
  column?: string
  error?: string
  empty?: boolean
  message?: string
  notes?: WidgetNote[]
}

export interface ExecuteResult {
  charts: ChartConfig[]
  kpis: KpiConfig[]
  /** true: tablero sin gráficos guardados, calculado con la regla por defecto. */
  legacy?: boolean
  /** Filtros que el servidor aplicó (solo si había alguno activo). */
  filters?: AppliedFilters
  notes?: WidgetNote[]
}

export type SuggestStatus = "created" | "exists" | "no_data" | "has_dashboards" | "already_suggested" | "nothing"

export interface SuggestResult {
  status: SuggestStatus
  source: "ai" | "rules" | null
  dashboards: { id: string; name: string; widgets: number | null; existing: boolean }[]
}

export function useDashboards() {
  return useQuery<Dashboard[]>({
    queryKey: ["dashboards"],
    queryFn: (): Promise<Dashboard[]> => api.get("/api/v1/dashboards"),
    staleTime: 30_000,
    refetchOnWindowFocus: false,
  })
}

export function useDashboardMeta(id: string) {
  return useQuery<DashboardDetail>({
    queryKey: ["dashboard-meta", id],
    queryFn: (): Promise<DashboardDetail> => api.get(`/api/v1/dashboards/${id}`),
    enabled: Boolean(id),
    staleTime: 60_000,
    refetchOnWindowFocus: false,
  })
}

/**
 * Calcula el tablero con los datos de este momento (POST sin efectos de lado visibles). Se modela como
 * `useQuery`: `queryFn` se llama una sola vez por `queryKey` (respetando `staleTime`), igual que un GET, y
 * resiste el doble montaje de React Strict Mode (una mutation disparada desde un efecto queda atascada).
 */
export function useDashboardExecute(id: string, filters: DashboardFilters = EMPTY_FILTERS) {
  const request = filtersToRequest(filters)
  const query = useQuery<ExecuteResult>({
    // Con filtros distintos es OTRA consulta (el tablero no se modifica: es solo lectura).
    queryKey: ["dashboard-execute", id, filtersKey(filters)],
    queryFn: (): Promise<ExecuteResult> => api.post(`/api/v1/dashboards/${id}/execute`, request ? { filters: request } : {}),
    enabled: Boolean(id),
    staleTime: 30_000,
    refetchOnWindowFocus: false,
    retry: 1,
    retryDelay: 1000,
    // Al cambiar un filtro se queda a la vista lo anterior (atenuado) en vez de volver a un esqueleto.
    placeholderData: keepPreviousData,
  })

  return {
    data: query.data,
    isLoading: query.isLoading,
    isFetching: query.isFetching,
    /** true: lo que se ve es del filtro anterior mientras llega el nuevo. */
    isStale: query.isPlaceholderData,
    isError: query.isError,
    error: query.error,
    updatedAt: query.dataUpdatedAt,
    refetch: () => query.refetch(),
  }
}

/** Qué se puede filtrar en el tablero: rango de fechas y valores más frecuentes de cada categoría. */
export function useDashboardFilterOptions(id: string) {
  return useQuery<FilterOptions>({
    queryKey: ["dashboard-filter-options", id],
    queryFn: (): Promise<FilterOptions> => api.get(`/api/v1/dashboards/${id}/filter-options`),
    enabled: Boolean(id),
    staleTime: 5 * 60_000,
    refetchOnWindowFocus: false,
    retry: 1,
  })
}

/** Busca valores de UNA categoría que contengan `q` (el selector con búsqueda). */
export function useFilterValueSearch(id: string, key: string | null, q: string) {
  const text = q.trim()
  return useQuery<FilterOptions>({
    queryKey: ["dashboard-filter-search", id, key, text],
    queryFn: (): Promise<FilterOptions> =>
      api.get(`/api/v1/dashboards/${id}/filter-options?key=${encodeURIComponent(key ?? "")}&q=${encodeURIComponent(text)}`),
    enabled: Boolean(id && key && text),
    staleTime: 60_000,
    refetchOnWindowFocus: false,
    retry: false,
    placeholderData: keepPreviousData,
  })
}

/** Detalle de un dato tocado (POST de solo lectura, modelado como consulta para cachearlo y reintentarlo). */
export function useDrill(dashboardId: string, widgetId: string | null, request: DrillRequest | null) {
  const target = widgetId && request ? drillTarget(widgetId, request) : ""
  return useQuery<DrillResponse>({
    // [3] = qué dato se tocó; [4] = cómo se mira (Ver por + filtros). Cambiar solo lo segundo conserva la tabla a la vista.
    queryKey: ["dashboard-drill", dashboardId, target, request ? drillVariant(request) : ""],
    queryFn: (): Promise<DrillResponse> => api.post(`/api/v1/dashboards/${dashboardId}/widgets/${widgetId}/drill`, request),
    enabled: Boolean(dashboardId && widgetId && request),
    staleTime: 30_000,
    refetchOnWindowFocus: false,
    retry: false,
    // Al cambiar «Ver por» se conserva la tabla anterior (atenuada); al tocar OTRO dato no se muestra el anterior.
    placeholderData: (previous, previousQuery) => (previousQuery?.queryKey[2] === target ? previous : undefined),
  })
}

/** "Sugerir tableros": crea 1-3 tableros con los datos (una llamada pequeña a la IA o una regla sin IA). */
export function useSuggestDashboards() {
  const queryClient = useQueryClient()

  return useMutation<SuggestResult, Error, { auto?: boolean } | void>({
    mutationFn: (options): Promise<SuggestResult> =>
      api.post("/api/v1/dashboards/suggest", { auto: Boolean(options && options.auto) }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["dashboards"] })
    },
  })
}

export function useDeleteDashboard() {
  const queryClient = useQueryClient()

  return useMutation<void, Error, string>({
    mutationFn: (id: string): Promise<void> => api.delete(`/api/v1/dashboards/${id}`),
    onSuccess: (_void, id) => {
      queryClient.invalidateQueries({ queryKey: ["dashboards"] })
      queryClient.removeQueries({ queryKey: ["dashboard-meta", id] })
      queryClient.removeQueries({ queryKey: ["dashboard-execute", id] })
      queryClient.removeQueries({ queryKey: ["dashboard-filter-options", id] })
      queryClient.removeQueries({ queryKey: ["dashboard-drill", id] })
    },
  })
}
