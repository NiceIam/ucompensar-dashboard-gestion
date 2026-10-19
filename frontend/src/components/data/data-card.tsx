"use client"

import { Download, Eye, FileDown, MessageCircleQuestion, MoreHorizontal, Pencil, SlidersHorizontal, Trash2 } from "lucide-react"
import { Button } from "@/components/ui/button"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import { ColumnPill } from "@/components/data/column-kind"
import { TableIcon } from "@/components/data/table-icon"
import { StatusBadge } from "@/components/kit/status-badge"
import type { OrgTable } from "@/hooks/use-templates"
import { pluralize } from "@/lib/format"
import { KIND_NAME, storedKind } from "@/lib/intake/plan"
import { cn } from "@/lib/utils"

const MAX_PILLS = 4

/** Tarjeta legible de una hoja de datos: nombre humano, filas, columnas con icono y acciones. */
export function DataCard({
  table,
  selected,
  onView,
  onAsk,
  onRename,
  onFixRoles,
  onDelete,
  onDownloadTemplate,
  onExport,
}: {
  table: OrgTable
  selected: boolean
  onView: () => void
  onAsk: () => void
  onRename: () => void
  onFixRoles?: () => void
  onDelete: () => void
  onDownloadTemplate: () => void
  onExport: () => void
}) {
  const cols = table.columns_definition ?? []
  const empty = table.row_count === 0
  const kind = storedKind(cols)
  return (
    <article
      className={cn(
        "surface group flex flex-col gap-4 p-5 transition-[box-shadow,border-color,transform] duration-200 hover:-translate-y-0.5 hover:shadow-raised",
        selected && "border-primary ring-2 ring-primary/30"
      )}
      aria-label={table.display_name}
    >
      <div className="flex items-start gap-3">
        <TableIcon name={`${table.table_name} ${table.display_name}`} />
        <div className="min-w-0 flex-1">
          <h3 className="truncate font-display text-xl font-semibold leading-tight">{table.display_name}</h3>
          <p className="mt-0.5 text-sm text-muted-foreground">
            {empty ? "Sin filas todavía" : pluralize(table.row_count, "fila", "filas")} · {pluralize(cols.length, "columna", "columnas")}
          </p>
          {kind && (
            <p className="mt-1.5">
              <StatusBadge tone="primary" title="Así entendí esta hoja">
                {KIND_NAME[kind]}
              </StatusBadge>
            </p>
          )}
        </div>
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button variant="ghost" size="icon-sm" aria-label={`Más opciones de ${table.display_name}`}>
              <MoreHorizontal aria-hidden="true" />
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end" className="w-60">
            <DropdownMenuItem onClick={onRename} className="cursor-pointer">
              <Pencil className="h-4 w-4" aria-hidden="true" />
              Cambiar nombre o columnas
            </DropdownMenuItem>
            {onFixRoles && !empty && (
              <DropdownMenuItem onClick={onFixRoles} className="cursor-pointer">
                <SlidersHorizontal className="h-4 w-4" aria-hidden="true" />
                Revisar lo que entendí
              </DropdownMenuItem>
            )}
            {!empty && (
              <DropdownMenuItem onClick={onExport} className="cursor-pointer">
                <FileDown className="h-4 w-4" aria-hidden="true" />
                Descargar los datos (CSV)
              </DropdownMenuItem>
            )}
            <DropdownMenuItem onClick={onDownloadTemplate} className="cursor-pointer">
              <Download className="h-4 w-4" aria-hidden="true" />
              Descargar plantilla vacía
            </DropdownMenuItem>
            <DropdownMenuSeparator />
            <DropdownMenuItem onClick={onDelete} className="cursor-pointer text-danger-strong focus:bg-danger-soft focus:text-danger-strong">
              <Trash2 className="h-4 w-4" aria-hidden="true" />
              Eliminar esta hoja
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>

      {cols.length > 0 && (
        <ul className="flex flex-wrap gap-1.5" aria-label="Columnas">
          {cols.slice(0, MAX_PILLS).map((c) => (
            <li key={c.name} className="max-w-full">
              <ColumnPill column={c} />
            </li>
          ))}
          {cols.length > MAX_PILLS && (
            <li className="inline-flex items-center rounded-full px-2 py-1 text-xs font-medium text-muted-foreground">
              +{cols.length - MAX_PILLS} más
            </li>
          )}
        </ul>
      )}

      <div className="mt-auto flex flex-wrap items-center gap-2 pt-1">
        {empty ? (
          <>
            <StatusBadge tone="highlight">Lista para llenar</StatusBadge>
            <Button variant="ghost" size="sm" className="ml-auto" onClick={onDownloadTemplate}>
              <Download aria-hidden="true" />
              Plantilla
            </Button>
          </>
        ) : (
          <>
            <Button variant={selected ? "default" : "soft"} size="sm" onClick={onView} aria-pressed={selected}>
              <Eye aria-hidden="true" />
              {selected ? "Viendo" : "Ver datos"}
            </Button>
            <Button variant="ghost" size="sm" onClick={onAsk}>
              <MessageCircleQuestion aria-hidden="true" />
              Preguntar
            </Button>
          </>
        )}
      </div>
    </article>
  )
}
