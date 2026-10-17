"use client"

import { useState } from "react"
import { toast } from "sonner"
import { ChevronLeft, ChevronRight, Trash2, X } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Skeleton } from "@/components/ui/skeleton"
import { ConfirmDialog } from "@/components/kit/confirm-dialog"
import { EmptyState, ErrorState } from "@/components/kit/empty-state"
import { ColumnKindIcon } from "@/components/data/column-kind"
import { TableIcon } from "@/components/data/table-icon"
import { useDeleteRow, useTableRows } from "@/hooks/use-data"
import type { OrgTable } from "@/hooks/use-templates"
import { columnKind, columnLabel, type ColumnKind } from "@/lib/data-vocabulary"
import { humanizeError } from "@/lib/errors"
import { formatDate, formatMoney, formatNumber, pluralize } from "@/lib/format"
import { cn } from "@/lib/utils"

const PAGE_SIZE = 20

/** Valor de una celda guardada, formateado según la clase de columna. */
export function formatStoredValue(value: unknown, kind: ColumnKind): string {
  if (value === null || value === undefined || value === "") return ""
  if (typeof value === "boolean") return value ? "Sí" : "No"
  if (kind === "boolean" && typeof value === "string") {
    const v = value.trim().toLowerCase()
    if (["true", "si", "sí", "1", "yes"].includes(v)) return "Sí"
    if (["false", "no", "0"].includes(v)) return "No"
  }
  if (typeof value === "number") {
    if (kind === "money") return formatMoney(value)
    if (kind === "id") return String(value)
    return formatNumber(value)
  }
  if (kind === "date" && typeof value === "string") {
    const m = value.match(/^(\d{4})-(\d{2})-(\d{2})(?:[ T](\d{2}):(\d{2}))?/)
    if (m) {
      const d = new Date(+m[1], +m[2] - 1, +m[3])
      const time = m[4] && (m[4] !== "00" || m[5] !== "00") ? ` ${m[4]}:${m[5]}` : ""
      return `${formatDate(d)}${time}`
    }
  }
  if (typeof value === "object") return JSON.stringify(value)
  return String(value)
}

/** Vista de las filas de una hoja, paginada, con opción de borrar filas sueltas. */
export function DataViewer({ table, onClose }: { table: OrgTable; onClose: () => void }) {
  const [page, setPage] = useState(0)
  const [rowToDelete, setRowToDelete] = useState<string | null>(null)
  const { data, isLoading, isError, error, refetch, isFetching } = useTableRows(table.id, page, PAGE_SIZE)
  const deleteRow = useDeleteRow(table.id)
  const cols = table.columns_definition ?? []
  const total = data?.total ?? table.row_count
  const pages = Math.max(1, Math.ceil(total / PAGE_SIZE))
  const start = total === 0 ? 0 : page * PAGE_SIZE + 1
  const end = Math.min((page + 1) * PAGE_SIZE, total)

  async function confirmDelete() {
    if (!rowToDelete) return
    try {
      await deleteRow.mutateAsync(rowToDelete)
      toast.success("Fila eliminada")
      setRowToDelete(null)
    } catch (err) {
      const h = humanizeError(err, "delete")
      toast.error(h.title, { description: h.description })
    }
  }

  return (
    <section aria-labelledby="viewer-title" className="surface overflow-hidden">
      <header className="flex items-center gap-3 border-b px-5 py-4">
        <TableIcon name={`${table.table_name} ${table.display_name}`} className="h-10 w-10" />
        <div className="min-w-0 flex-1">
          <h2 id="viewer-title" className="truncate font-display text-xl font-semibold">
            {table.display_name}
          </h2>
          <p className="text-sm text-muted-foreground">{pluralize(total, "fila", "filas")} · lo más reciente primero</p>
        </div>
        <Button variant="ghost" size="icon-sm" onClick={onClose} aria-label="Cerrar la vista de datos">
          <X aria-hidden="true" />
        </Button>
      </header>

      {isError ? (
        <ErrorState compact error={humanizeError(error, "load")} onRetry={() => void refetch()} retrying={isFetching} />
      ) : !isLoading && data && data.rows.length === 0 ? (
        <EmptyState
          compact
          illustration="sheets"
          title="Esta hoja todavía no tiene filas"
          description="Sube un archivo con estas columnas y aparecerán aquí."
        />
      ) : (
        <div className={cn("overflow-x-auto transition-opacity", isFetching && !isLoading && "opacity-60")}>
          <table className="w-full min-w-max text-sm">
            <caption className="sr-only">Filas de {table.display_name}</caption>
            <thead>
              <tr className="border-b bg-muted/50">
                {cols.map((c) => (
                  <th
                    key={c.name}
                    scope="col"
                    className={cn(
                      "whitespace-nowrap px-4 py-3 text-left font-semibold",
                      (columnKind(c) === "money" || columnKind(c) === "number") && "text-right"
                    )}
                  >
                    <span className="inline-flex items-center gap-2">
                      <ColumnKindIcon kind={columnKind(c)} className="h-6 w-6 rounded-md" />
                      {columnLabel(c)}
                    </span>
                  </th>
                ))}
                <th scope="col" className="w-12 px-2 py-3">
                  <span className="sr-only">Acciones</span>
                </th>
              </tr>
            </thead>
            <tbody>
              {isLoading
                ? Array.from({ length: 6 }).map((_, i) => (
                    <tr key={i} className="border-b last:border-0">
                      {cols.map((c) => (
                        <td key={c.name} className="px-4 py-3">
                          <Skeleton className="h-4 w-20" />
                        </td>
                      ))}
                      <td />
                    </tr>
                  ))
                : data?.rows.map((row) => (
                    <tr key={row.id} className="group border-b transition-colors last:border-0 hover:bg-muted/40">
                      {cols.map((c) => {
                        const kind = columnKind(c)
                        const text = formatStoredValue(row.data?.[c.name], kind)
                        return (
                          <td
                            key={c.name}
                            className={cn(
                              "max-w-[240px] truncate whitespace-nowrap px-4 py-3",
                              (kind === "money" || kind === "number") && "text-right tabular"
                            )}
                            title={text}
                          >
                            {text || <span className="text-muted-foreground/50">—</span>}
                          </td>
                        )
                      })}
                      <td className="px-2 py-1.5 text-right">
                        <Button
                          variant="ghost"
                          size="icon-xs"
                          className="text-muted-foreground opacity-100 hover:text-destructive sm:opacity-0 sm:focus-visible:opacity-100 sm:group-hover:opacity-100"
                          onClick={() => setRowToDelete(row.id)}
                          aria-label="Eliminar esta fila"
                        >
                          <Trash2 aria-hidden="true" />
                        </Button>
                      </td>
                    </tr>
                  ))}
            </tbody>
          </table>
        </div>
      )}

      {total > 0 && !isError && (
        <footer className="flex flex-wrap items-center justify-between gap-3 border-t px-5 py-3 text-sm">
          <p className="text-muted-foreground">
            Filas <span className="font-semibold text-foreground tabular">{formatNumber(start)}–{formatNumber(end)}</span> de{" "}
            {formatNumber(total)}
          </p>
          <div className="flex items-center gap-1">
            <Button variant="outline" size="icon-sm" disabled={page === 0 || isFetching} onClick={() => setPage((p) => p - 1)} aria-label="Página anterior">
              <ChevronLeft aria-hidden="true" />
            </Button>
            <span className="min-w-[4.5rem] text-center tabular text-muted-foreground">
              {page + 1} de {formatNumber(pages)}
            </span>
            <Button variant="outline" size="icon-sm" disabled={page >= pages - 1 || isFetching} onClick={() => setPage((p) => p + 1)} aria-label="Página siguiente">
              <ChevronRight aria-hidden="true" />
            </Button>
          </div>
        </footer>
      )}

      <ConfirmDialog
        open={Boolean(rowToDelete)}
        onOpenChange={(open) => !open && setRowToDelete(null)}
        title="¿Eliminar esta fila?"
        description="Se borra para siempre de esta hoja. El resto de tus datos no cambia."
        confirmLabel="Eliminar fila"
        loading={deleteRow.isPending}
        onConfirm={confirmDelete}
      />
    </section>
  )
}
