"use client"

import { useQuery, useMutation, useQueryClient, type QueryClient } from "@tanstack/react-query"
import { api } from "@/lib/api"
import type { Dashboard } from "@/types/api"

export interface DashboardDetail {
  dashboard_id: string
  name: string
  description: string | null
  created_at: string
}

export interface ChartDataPoint {
  name: string
  value: number
  [key: string]: string | number
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
}

export interface ExecuteResult {
  charts: ChartConfig[]
  kpis: KpiConfig[]
  /** true: tablero sin gráficos guardados, calculado con la regla por defecto. */
  legacy?: boolean
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
export function useDashboardExecute(id: string) {
  const query = useQuery<ExecuteResult>({
    queryKey: ["dashboard-execute", id],
    queryFn: (): Promise<ExecuteResult> => api.post(`/api/v1/dashboards/${id}/execute`, {}),
    enabled: Boolean(id),
    staleTime: 30_000,
    refetchOnWindowFocus: false,
    retry: 1,
    retryDelay: 1000,
  })

  return {
    data: query.data,
    isLoading: query.isLoading,
    isFetching: query.isFetching,
    isError: query.isError,
    error: query.error,
    updatedAt: query.dataUpdatedAt,
    refetch: () => query.refetch(),
  }
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
    },
  })
}

/** Refresca lo que depende de un tablero tras editarlo o deshacer una edición: su detalle, sus gráficos y la lista. */
export function invalidateDashboard(queryClient: QueryClient, id: string): void {
  void queryClient.invalidateQueries({ queryKey: ["dashboards"] })
  void queryClient.invalidateQueries({ queryKey: ["dashboard-meta", id] })
  void queryClient.invalidateQueries({ queryKey: ["dashboard-execute", id] })
}

export interface UndoEditInput {
  id: string
  /** Lo que `Deshacer` restaura: viene del bloque de edición del asistente. */
  version: string
  /** true: también se pierden las ediciones más recientes (la persona ya lo confirmó). */
  includeNewer?: boolean
}

export interface UndoEditResult {
  id: string
  name: string
  widgets: number
  discarded_newer: number
}

/**
 * Deshace una edición hecha por el asistente. El 404 (ya no se puede) y el 409 `newer_edits` los maneja la
 * tarjeta: llegan como `ApiError`.
 */
export function useUndoDashboardEdit() {
  const queryClient = useQueryClient()

  return useMutation<UndoEditResult, Error, UndoEditInput>({
    mutationFn: ({ id, version, includeNewer }): Promise<UndoEditResult> =>
      api.post(`/api/v1/dashboards/${id}/undo-edit`, { version, include_newer: Boolean(includeNewer) }),
    onSuccess: (_result, { id }) => invalidateDashboard(queryClient, id),
  })
}
