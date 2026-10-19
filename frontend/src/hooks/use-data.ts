"use client"

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { api } from "@/lib/api"

/** Claves de caché compartidas por las pantallas de datos. */
export const DATA_KEYS = {
  tables: ["templates", "org-tables"] as const,
  rows: (tableId: string) => ["table-rows", tableId] as const,
  files: ["files"] as const,
  /** Los hallazgos dependen de los datos: cualquier cambio en ellos los deja viejos. */
  insights: ["insights"] as const,
}

export interface TableRow {
  id: string
  data: Record<string, unknown>
  created_at: string | null
}

export interface TableRowsResponse {
  table_name: string
  display_name: string
  total: number
  rows: TableRow[]
}

export function useTableRows(tableId: string | null, page: number, limit = 20) {
  return useQuery<TableRowsResponse>({
    queryKey: [...DATA_KEYS.rows(tableId ?? ""), page, limit],
    queryFn: () => api.get<TableRowsResponse>(`/api/v1/schema/tables/${tableId}/rows?limit=${limit}&offset=${page * limit}`),
    enabled: Boolean(tableId),
    placeholderData: (prev) => prev,
  })
}

export function useInvalidateData() {
  const qc = useQueryClient()
  return async () => {
    await Promise.all([
      qc.invalidateQueries({ queryKey: DATA_KEYS.tables }),
      qc.invalidateQueries({ queryKey: DATA_KEYS.files }),
      qc.invalidateQueries({ queryKey: ["table-rows"] }),
      qc.invalidateQueries({ queryKey: DATA_KEYS.insights }),
    ])
  }
}

export function useDeleteTable() {
  const invalidate = useInvalidateData()
  return useMutation<unknown, Error, string>({
    mutationFn: (tableId) => api.delete(`/api/v1/schema/tables/${tableId}`),
    onSuccess: () => invalidate(),
  })
}

export function useUpdateTable() {
  const invalidate = useInvalidateData()
  return useMutation<
    unknown,
    Error,
    { tableId: string; newDisplayName?: string; addColumns?: { name: string; type: string; label?: string }[] }
  >({
    mutationFn: ({ tableId, newDisplayName, addColumns }) => {
      const payload: { new_display_name?: string; add_columns?: { name: string; type: string; label?: string }[] } = {}
      if (newDisplayName) payload.new_display_name = newDisplayName
      if (addColumns && addColumns.length > 0) payload.add_columns = addColumns
      return api.put(`/api/v1/schema/tables/${tableId}`, payload)
    },
    onSuccess: () => invalidate(),
  })
}

export function useDeleteRow(tableId: string) {
  const qc = useQueryClient()
  return useMutation<unknown, Error, string>({
    mutationFn: (rowId) => api.delete(`/api/v1/schema/tables/${tableId}/rows/${rowId}`),
    onSuccess: async () => {
      await qc.invalidateQueries({ queryKey: DATA_KEYS.rows(tableId) })
      await qc.invalidateQueries({ queryKey: DATA_KEYS.tables })
      await qc.invalidateQueries({ queryKey: DATA_KEYS.insights })
    },
  })
}

/** Descargas (plantillas y exportaciones) con la sesión de la persona. */
export const downloads = {
  tableTemplate: (tableId: string, tableName: string) =>
    api.downloadBlob(`/api/v1/schema/tables/${tableId}/template`, `plantilla_${tableName}.csv`),
  tableExport: (tableId: string, tableName: string) =>
    api.downloadBlob(`/api/v1/schema/tables/${tableId}/export`, `${tableName}_datos.csv`),
  allTemplates: () => api.downloadBlob("/api/v1/schema/template-all", "plantilla_completa.xlsx"),
}
