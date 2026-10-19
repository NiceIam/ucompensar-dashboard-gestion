import { CalendarDays, Coins, Hash, Tag, ToggleRight, Type, type LucideIcon } from "lucide-react"
import { KIND_INFO, columnKind, columnLabel, type ColumnKind, type ColumnLike } from "@/lib/data-vocabulary"
import { cn } from "@/lib/utils"

export const KIND_ICON: Record<ColumnKind, LucideIcon> = {
  date: CalendarDays,
  money: Coins,
  number: Hash,
  text: Type,
  boolean: ToggleRight,
  id: Tag,
}

const KIND_STYLE: Record<ColumnKind, string> = {
  date: "bg-info-soft text-info-strong",
  money: "bg-success-soft text-success-strong",
  number: "bg-primary-soft text-primary-strong",
  text: "bg-secondary text-foreground/80",
  boolean: "bg-secondary text-foreground/80",
  id: "bg-muted text-muted-foreground",
}

/** Icono de la clase de columna (fecha, dinero, número…) con su color suave. */
export function ColumnKindIcon({ kind, className }: { kind: ColumnKind; className?: string }) {
  const Icon = KIND_ICON[kind]
  return (
    <span className={cn("inline-flex h-7 w-7 shrink-0 items-center justify-center rounded-lg", KIND_STYLE[kind], className)}>
      <Icon className="h-3.5 w-3.5" aria-hidden="true" />
    </span>
  )
}

/** Píldora "icono + nombre de columna" (para resúmenes compactos). */
export function ColumnPill({ column }: { column: ColumnLike }) {
  const kind = columnKind(column)
  const Icon = KIND_ICON[kind]
  return (
    <span
      className="inline-flex max-w-full items-center gap-1.5 rounded-full border bg-card px-2.5 py-1 text-xs font-medium"
      title={`${columnLabel(column)} · ${KIND_INFO[kind].label}`}
    >
      {/* Icono en gris: con decenas de píldoras, el naranja dejaría de guiar la atención */}
      <Icon className="h-3.5 w-3.5 shrink-0 text-muted-foreground" aria-hidden="true" />
      <span className="truncate">{columnLabel(column)}</span>
    </span>
  )
}
