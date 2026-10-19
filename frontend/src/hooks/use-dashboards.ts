"use client"

import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import { api } from "@/lib/api"
import type { Dashboard, WidgetConfig } from "@/types/api"

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

export interface ChartConfig {
  type: "bar" | "line" | "pie" | "area"
  title: string
  data: ChartDataPoint[]
  x: string
  y: string
  color: string
}

export interface KpiConfig {
  label: string
  value: number
  /** Pista de icono del backend ("Database", "TrendingUp", "DollarSign"…). */
  icon: string
  /**
   * Unidad explícita (opcional, aún no la manda el backend). Si llega, manda
   * sobre cualquier heurística: "money" se muestra en pesos, "count" como cantidad.
   */
  unit?: "money" | "count" | "number"
  /** Columna de origen del cálculo (opcional). Si es de dinero (total, precio, valor…), se muestra en pesos. */
  column?: string
}

export interface ExecuteResult {
  charts: ChartConfig[]
  kpis: KpiConfig[]
}

export interface ScriptResponse {
  script: string
  dashboard_id: string
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
 * Ejecuta el script Python del dashboard (POST con efectos de lado en el
 * servidor). Se modela como `useQuery` -- aunque el verbo HTTP sea POST, para
 * TanStack Query no importa: `queryFn` se llama una sola vez por `queryKey`
 * (respetando `staleTime`), igual que un GET. Antes se usaba `useMutation`
 * disparada a mano desde un `useEffect`, pero ese patron queda atascado en
 * "pending" para siempre en dev bajo React Strict Mode (el doble-montaje de
 * efectos deja el observer interno de la mutation desincronizado del render
 * activo). `useQuery` esta diseñado para ser resistente a ese doble-montaje.
 */
export function useDashboardExecute(id: string) {
  const query = useQuery<ExecuteResult>({
    queryKey: ["dashboard-execute", id],
    queryFn: (): Promise<ExecuteResult> =>
      api.post(`/api/v1/dashboards/${id}/execute`, {}),
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

export function useDashboardScript(id: string, enabled: boolean) {
  return useQuery<ScriptResponse>({
    queryKey: ["dashboard-script", id],
    queryFn: (): Promise<ScriptResponse> =>
      api.get(`/api/v1/dashboards/${id}/script`),
    enabled: Boolean(id) && enabled,
    staleTime: Infinity,
    refetchOnWindowFocus: false,
  })
}

export function useCreateDashboard() {
  const queryClient = useQueryClient()

  return useMutation<Dashboard, Error, { name: string; description?: string; file_id?: string }>({
    mutationFn: (data): Promise<Dashboard> =>
      api.post("/api/v1/dashboards", data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["dashboards"] })
    },
  })
}

export function useUpdateWidget() {
  const queryClient = useQueryClient()

  return useMutation<
    WidgetConfig,
    Error,
    { dashboardId: string; widgetId: string; data: Partial<WidgetConfig> }
  >({
    mutationFn: ({ dashboardId, widgetId, data }): Promise<WidgetConfig> =>
      api.put(`/api/v1/dashboards/${dashboardId}/widgets/${widgetId}`, data),
    onSuccess: (_result, variables) => {
      queryClient.invalidateQueries({
        queryKey: ["dashboards", variables.dashboardId],
      })
    },
  })
}

export function useDeleteDashboard() {
  const queryClient = useQueryClient()

  return useMutation<void, Error, string>({
    mutationFn: (id: string): Promise<void> =>
      api.delete(`/api/v1/dashboards/${id}`),
    onSuccess: (_void, id) => {
      queryClient.invalidateQueries({ queryKey: ["dashboards"] })
      queryClient.removeQueries({ queryKey: ["dashboard-meta", id] })
      queryClient.removeQueries({ queryKey: ["dashboard-execute", id] })
      queryClient.removeQueries({ queryKey: ["dashboard-script", id] })
    },
  })
}

export function useDownloadDashboardScript() {
  return useMutation<void, Error, { id: string }>({
    mutationFn: ({ id }) =>
      api.downloadBlob(
        `/api/v1/dashboards/${id}/script/download`,
        `dashboard_${id.slice(0, 8)}.py`,
      ),
  })
}
