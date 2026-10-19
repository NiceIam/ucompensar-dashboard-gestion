"use client"

import { useMutation, useQuery } from "@tanstack/react-query"
import { api } from "@/lib/api"
import { useInvalidateData } from "@/hooks/use-data"
import { withExplicitType, type LocalFileKind } from "@/lib/upload/local-file"
import type {
  AnalyzeResponse,
  CommitResponse,
  CommitResult,
  Ontology,
  PlanSheet,
  SheetKind,
  UpdatedRoles,
} from "@/types/intake"

export interface UploadItem {
  file: File
  kind: LocalFileKind
}

function formWithFiles(items: UploadItem[]): FormData {
  const form = new FormData()
  for (const { file, kind } of items) form.append("files", withExplicitType(file, kind), file.name)
  return form
}

/** POST /api/v1/intake/analyze — entiende varios archivos a la vez (no guarda nada). */
export function analyzeIntake(items: UploadItem[]): Promise<AnalyzeResponse> {
  return api.upload<AnalyzeResponse>("/api/v1/intake/analyze", formWithFiles(items))
}

/** POST /api/v1/intake/commit — guarda lo confirmado. Se mandan los MISMOS archivos (el servidor no guarda estado). */
export function commitIntake(items: UploadItem[], plan: PlanSheet[]): Promise<CommitResponse> {
  const form = formWithFiles(items)
  form.append("plan", JSON.stringify({ sheets: plan }))
  return api.upload<CommitResponse>("/api/v1/intake/commit", form)
}

/** Tipos de hoja y roles de columna en lenguaje simple (no cambia: se pide una vez). */
export function useOntology() {
  return useQuery<Ontology>({
    queryKey: ["intake", "ontology"],
    queryFn: () => api.get<Ontology>("/api/v1/intake/ontology"),
    staleTime: Infinity,
    gcTime: Infinity,
    retry: 1,
  })
}

/** Deshace lo que guardó una carga: borra las hojas nuevas y las filas que se sumaron a hojas que ya existían. */
export function useUndoIntake() {
  const invalidate = useInvalidateData()
  return useMutation<void, Error, CommitResult[]>({
    mutationFn: async (results) => {
      // De atrás hacia adelante: primero lo que se sumó, al final las hojas que se crearon.
      for (const r of [...results].reverse()) {
        if (r.undo.action === "delete_rows" && r.undo.table_id && r.undo.loaded_at) {
          await api.post("/api/v1/intake/undo", { table_id: r.undo.table_id, loaded_at: r.undo.loaded_at })
        }
      }
      for (const r of [...results].reverse()) {
        if (r.undo.action === "delete_table" && r.undo.table_id) {
          await api.delete(`/api/v1/schema/tables/${r.undo.table_id}`)
        }
      }
    },
    onSuccess: () => invalidate(),
  })
}

/** PUT /api/v1/schema/tables/{id}/roles — la persona corrige el tipo o el uso de una columna de una hoja ya guardada. */
export function useUpdateRoles() {
  const invalidate = useInvalidateData()
  return useMutation<UpdatedRoles, Error, { tableId: string; kind?: SheetKind; roles: Record<string, string | null> }>({
    mutationFn: ({ tableId, kind, roles }) => api.put<UpdatedRoles>(`/api/v1/schema/tables/${tableId}/roles`, { kind, roles }),
    onSuccess: () => invalidate(),
  })
}
