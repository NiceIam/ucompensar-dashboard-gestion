"use client"

import { AlertTriangle, CheckCircle2, FileJson, FileSpreadsheet, FileText, FileWarning, X, type LucideIcon } from "lucide-react"
import { StatusBadge } from "@/components/kit/status-badge"
import type { EntryStatus, FileEntry } from "@/lib/intake/state"
import { formatFileSize } from "@/lib/format"
import type { LocalFileKind } from "@/lib/upload/local-file"
import { cn } from "@/lib/utils"

const KIND_ICON: Record<LocalFileKind, LucideIcon> = { xlsx: FileSpreadsheet, csv: FileText, json: FileJson }

/** Estado de cada archivo en lenguaje simple: leyendo → entendiendo → listo. */
const STATUS: Record<
  EntryStatus,
  { label: string; tone: "info" | "success" | "warning" | "danger"; spinning?: boolean; icon?: LucideIcon }
> = {
  reading: { label: "Leyendo…", tone: "info", spinning: true },
  understanding: { label: "Entendiendo…", tone: "info", spinning: true },
  ready: { label: "Listo", tone: "success", icon: CheckCircle2 },
  attention: { label: "Necesita tu ayuda", tone: "warning", icon: AlertTriangle },
  problem: { label: "No pude usarlo", tone: "danger", icon: FileWarning },
}

export function FileCard({
  entry,
  summary,
  onRemove,
  className,
}: {
  className?: string
  entry: FileEntry
  /** Lo que se entendió del archivo, en una frase ("tus ventas · 731 filas"). */
  summary?: string
  onRemove?: () => void
}) {
  const Icon = entry.kind ? KIND_ICON[entry.kind] : FileText
  const st = STATUS[entry.status]
  return (
    <li
      className={cn(
        "flex min-w-0 flex-wrap items-start gap-x-3 gap-y-2 rounded-xl border bg-card px-3.5 py-3",
        entry.status === "problem" && "border-danger/40 bg-danger-soft/40 lg:col-span-2",
        className
      )}
    >
      <span className="mt-0.5 flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-primary-soft text-primary-strong">
        <Icon className="h-5 w-5" aria-hidden="true" />
      </span>
      <div className="min-w-[10rem] flex-1">
        <p className="truncate text-sm font-semibold" title={entry.file.name}>
          {entry.file.name}
        </p>
        <p className="text-xs text-muted-foreground">
          {formatFileSize(entry.file.size)}
          {summary ? ` · ${summary}` : ""}
        </p>
        {entry.status === "problem" && entry.problem && (
          <p className="mt-1 text-sm text-danger-strong">
            <span className="font-semibold">{entry.problem.title}</span>
            {entry.problem.description ? ` ${entry.problem.description}` : ""}
          </p>
        )}
      </div>
      <div className="ml-[3.25rem] flex shrink-0 items-center gap-1 sm:ml-0">
        <StatusBadge tone={st.tone} icon={st.icon} spinning={st.spinning}>
          {st.label}
        </StatusBadge>
        {onRemove && (
          <button
            type="button"
            onClick={onRemove}
            aria-label={`Quitar ${entry.file.name}`}
            className="inline-flex h-11 w-11 items-center justify-center rounded-lg text-muted-foreground transition hover:bg-accent hover:text-foreground sm:h-9 sm:w-9"
          >
            <X className="h-4 w-4" aria-hidden="true" />
          </button>
        )}
      </div>
    </li>
  )
}
