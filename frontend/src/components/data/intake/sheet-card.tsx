"use client"

import { useId } from "react"
import {
  AlertTriangle,
  ArrowRight,
  CheckCircle2,
  CircleDashed,
  Eye,
  EyeOff,
  Layers,
  Pencil,
  Sparkles,
  type LucideIcon,
} from "lucide-react"
import { Button } from "@/components/ui/button"
import { Figure } from "@/components/kit/data-sentence"
import { NativeSelect } from "@/components/kit/native-select"
import { Notice } from "@/components/kit/notice"
import { StatusBadge } from "@/components/kit/status-badge"
import { TableIcon } from "@/components/data/table-icon"
import {
  CONFIDENCE_LABEL,
  OTHER_ROLE,
  attentionReasons,
  confidenceLevel,
  currentKind,
  currentRoles,
  isEdited,
  sheetHeadline,
  sheetNeedsAttention,
  type Decision,
  type SheetEdit,
} from "@/lib/intake/plan"
import { cn } from "@/lib/utils"
import type { CommitResult, IntakeColumn, IntakeSheet, Ontology, SheetKind } from "@/types/intake"

const LEVEL_TONE = { high: "success", medium: "info", low: "warning" } as const
const LEVEL_ICON: Record<"high" | "medium" | "low", LucideIcon> = { high: CheckCircle2, medium: CircleDashed, low: AlertTriangle }

/** Insignia de confianza: palabra + icono (el color nunca va solo). */
export function ConfidenceBadge({ confidence, className }: { confidence: number; className?: string }) {
  const level = confidenceLevel(confidence)
  return (
    <StatusBadge tone={LEVEL_TONE[level]} icon={LEVEL_ICON[level]} className={className}>
      {CONFIDENCE_LABEL[level]}
    </StatusBadge>
  )
}

/** Una columna del archivo, dicha en palabras del dueño: «Vlr Compra» → lo que pagaste por cada producto. */
function ColumnRow({
  column,
  role,
  edited,
  kind,
  ontology,
  editable,
  onRole,
}: {
  column: IntakeColumn
  role: string
  edited: boolean
  kind: SheetKind
  ontology?: Ontology
  editable: boolean
  onRole: (role: string) => void
}) {
  const roles = ontology?.roles?.[kind] ?? []
  const meta = roles.find((r) => r.role === role)
  const isOther = role === OTHER_ROLE
  const explain = isOther ? column.explain || "un dato extra que guardo tal cual" : meta?.explain ?? column.explain
  const options = [
    ...roles.filter((r) => r.role !== OTHER_ROLE).map((r) => ({ value: r.role, label: r.label })),
    { value: OTHER_ROLE, label: "Dato adicional (lo guardo tal cual)" },
  ]
  return (
    <li className="grid gap-2 py-3 sm:grid-cols-[minmax(0,1fr)_minmax(0,15rem)] sm:items-center sm:gap-4">
      <div className="min-w-0 space-y-0.5">
        <p className="text-[15px] leading-snug">
          <span className="font-semibold" title={column.original_name}>
            «{column.original_name}»
          </span>
          <ArrowRight className="mx-1.5 inline h-3.5 w-3.5 text-muted-foreground" aria-hidden="true" />
          <span className="text-foreground/85">{explain}</span>
        </p>
        <p className="flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-muted-foreground">
          {column.sample.length > 0 && (
            <span className="truncate">
              Por ejemplo: {column.sample.slice(0, 2).map((s) => (s.length > 24 ? `${s.slice(0, 24)}…` : s)).join(" · ")}
            </span>
          )}
          {!isOther && !edited && <ConfidenceBadge confidence={column.confidence} className="h-6 text-[11px]" />}
          {edited && (
            <StatusBadge tone="primary" icon={Pencil} className="h-6 text-[11px]">
              Lo elegiste tú
            </StatusBadge>
          )}
        </p>
      </div>
      {editable && (
        <NativeSelect
          label={`Qué es la columna «${column.original_name}»`}
          value={role}
          options={options}
          onChange={onRole}
        />
      )}
    </li>
  )
}

/**
 * Lo que entendí de UNA hoja: la frase ("Encontré tus ventas: 731 filas, de mayo a octubre de 2026"), lo que
 * haré con ella y cada columna explicada. Solo pide intervención si hay baja confianza o duda de mezcla.
 */
export function SheetCard({
  fileName,
  sheet,
  edit,
  decision,
  ontology,
  mode,
  result,
  onRole,
  onKind,
  onRename,
  onDecide,
  onSkip,
  onView,
  onFix,
}: {
  fileName: string
  sheet: IntakeSheet
  edit?: SheetEdit
  decision: Decision
  ontology?: Ontology
  mode: "review" | "saved"
  result?: CommitResult
  onRole?: (column: string, role: string) => void
  onKind?: (kind: SheetKind) => void
  onRename?: (name: string) => void
  onDecide?: (decision: Decision) => void
  /** Dejar la hoja sin guardar (o volver a incluirla). */
  onSkip?: (skip: boolean) => void
  onView?: (tableId: string) => void
  onFix?: (result: CommitResult) => void
}) {
  const uid = useId()
  const kind = currentKind(sheet, edit)
  const roles = currentRoles(sheet, edit)
  const needs = sheetNeedsAttention(sheet)
  const headline = sheetHeadline(sheet)
  const dest = sheet.destination!
  const sheetLabel = sheet.sheet_name ? `${fileName} · hoja «${sheet.sheet_name}»` : fileName
  const editable = mode === "review"
  const kindLabel = ontology?.kinds.find((k) => k.kind === kind)
  const edited = isEdited(sheet, edit)
  const original = Object.fromEntries((sheet.columns ?? []).map((c) => [c.name, c.role]))
  const shownHeadline =
    kind !== sheet.kind && kindLabel
      ? { lead: "Guardaré", kindPhrase: `esto como ${kindLabel.label}`, stats: sheet.stats ?? "" }
      : headline
  const newName = edit?.displayName ?? dest.new_display_name
  const skipped = decision === "skip"

  return (
    <article
      aria-label={sheetLabel}
      className={cn(
        "surface space-y-4 p-4 sm:p-5",
        needs && mode === "review" && !skipped && "border-warning/50 ring-1 ring-warning/20",
        skipped && "opacity-70"
      )}
    >
      <header className="flex items-start gap-3">
        <TableIcon name={`${kind} ${sheet.sheet_name ?? ""}`} />
        <div className="min-w-0 flex-1 space-y-1">
          {shownHeadline && (
            <h4 className="font-display text-xl font-semibold leading-snug text-balance sm:text-2xl">
              {shownHeadline.lead} <Figure>{shownHeadline.kindPhrase}</Figure>
              {shownHeadline.stats ? `: ${shownHeadline.stats}.` : "."}
            </h4>
          )}
          <p className="truncate text-sm text-muted-foreground" title={sheetLabel}>
            {sheetLabel}
          </p>
        </div>
        {mode === "review" && !needs && <ConfidenceBadge confidence={sheet.kind_confidence ?? 1} />}
        {mode === "review" && needs && (
          <StatusBadge tone="warning" icon={AlertTriangle}>
            Necesito tu ayuda
          </StatusBadge>
        )}
      </header>

      {/* Qué voy a hacer con ella */}
      {mode === "review" && skipped ? (
        <p className="flex items-center gap-2 text-sm text-muted-foreground">
          <EyeOff className="h-4 w-4 shrink-0" aria-hidden="true" />
          No voy a guardar esta hoja.
        </p>
      ) : mode === "review" ? (
        <DestinationBlock
          uid={uid}
          sheet={sheet}
          decision={decision}
          newName={newName}
          kindChanged={kind !== sheet.kind}
          onRename={onRename}
          onDecide={onDecide}
        />
      ) : (
        result && (
          <div className="flex flex-wrap items-center gap-2 rounded-xl bg-success-soft/60 px-3.5 py-2.5 text-sm">
            <CheckCircle2 className="h-4 w-4 shrink-0 text-success" aria-hidden="true" />
            <span className="min-w-0 flex-1 text-foreground/90">{result.message}</span>
            {result.table_id && onView && (
              <Button variant="ghost" size="sm" onClick={() => onView(result.table_id!)}>
                <Eye aria-hidden="true" />
                Ver
              </Button>
            )}
            {result.table_id && onFix && (
              <Button variant="ghost" size="sm" onClick={() => onFix(result)}>
                <Pencil aria-hidden="true" />
                Corregir
              </Button>
            )}
          </div>
        )
      )}

      {/* Dudas */}
      {mode === "review" && needs && (
        <Notice tone="warning" title="Revisa esto antes de guardar">
          <ul className="list-disc space-y-1 pl-4">
            {attentionReasons(sheet).map((r) => (
              <li key={r}>{r}</li>
            ))}
          </ul>
        </Notice>
      )}

      {mode === "review" && (needs || edited) && ontology && (
        <div className="space-y-1.5">
          <label htmlFor={`${uid}-kind`} className="text-sm font-semibold">
            ¿Qué es este archivo?
          </label>
          <NativeSelect
            id={`${uid}-kind`}
            label="Qué es este archivo"
            value={kind}
            onChange={(v) => onKind?.(v as SheetKind)}
            options={ontology.kinds.map((k) => ({ value: k.kind, label: k.choice_label }))}
          />
        </div>
      )}

      {/* Columnas, una por una */}
      <details open={needs && mode === "review"} className="group rounded-xl border bg-card/60">
        <summary className="flex min-h-11 cursor-pointer select-none items-center justify-between gap-3 px-4 py-2.5 text-sm font-semibold [&::-webkit-details-marker]:hidden">
          <span className="flex items-center gap-2">
            <Layers className="h-4 w-4 text-primary" aria-hidden="true" />
            Así entendí cada columna ({sheet.columns?.length ?? 0})
          </span>
          <span className="text-xs font-medium text-primary group-open:hidden">Ver</span>
          <span className="hidden text-xs font-medium text-primary group-open:inline">Ocultar</span>
        </summary>
        <ul className="divide-y border-t px-4" aria-label="Columnas del archivo">
          {(sheet.columns ?? []).map((c) => (
            <ColumnRow
              key={c.name}
              column={c}
              role={roles[c.name] ?? c.role}
              edited={roles[c.name] !== undefined && roles[c.name] !== original[c.name]}
              kind={kind}
              ontology={ontology}
              editable={editable}
              onRole={(r) => onRole?.(c.name, r)}
            />
          ))}
        </ul>
      </details>

      {mode === "review" && onSkip && (
        <div className="flex justify-end">
          <Button variant="ghost" size="sm" className="text-muted-foreground" onClick={() => onSkip(!skipped)}>
            {skipped ? "Guardar esta hoja" : "No guardar esta hoja"}
          </Button>
        </div>
      )}

      {mode === "review" && sheet.mapping_source === "ai" && (
        <p className="flex items-center gap-1.5 text-xs text-muted-foreground">
          <Sparkles className="h-3.5 w-3.5 text-highlight-strong" aria-hidden="true" />
          Esta hoja traía nombres poco claros, así que la leí con ayuda de la IA.
        </p>
      )}
    </article>
  )
}

function DestinationBlock({
  uid,
  sheet,
  decision,
  newName,
  kindChanged,
  onRename,
  onDecide,
}: {
  uid: string
  sheet: IntakeSheet
  decision: Decision
  newName: string
  kindChanged: boolean
  onRename?: (name: string) => void
  onDecide?: (d: Decision) => void
}) {
  const dest = sheet.destination!
  if (dest.action === "ask" && !kindChanged) {
    return (
      <fieldset className="space-y-2">
        <legend className="mb-1 text-sm font-semibold">¿Qué hago con esta hoja?</legend>
        {(
          [
            ["append", `Sumarla a «${dest.display_name}»`, `Se parece en un ${Math.round((dest.similarity ?? 0) * 100)} %.`],
            ["create", `Guardarla aparte como «${newName}»`, "Es lo más seguro: no se mezcla con nada."],
          ] as const
        ).map(([value, title, hint]) => (
          <label
            key={value}
            htmlFor={`${uid}-${value}`}
            className={cn(
              "flex min-h-11 cursor-pointer items-start gap-3 rounded-xl border bg-card px-3.5 py-3 transition-colors",
              decision === value ? "border-primary bg-primary-soft/40 ring-2 ring-primary/20" : "hover:border-foreground/25"
            )}
          >
            <input
              id={`${uid}-${value}`}
              type="radio"
              name={`${uid}-dest`}
              className="mt-1 h-4 w-4 accent-[hsl(var(--primary))]"
              checked={decision === value}
              onChange={() => onDecide?.(value)}
            />
            <span className="text-sm">
              <span className="block font-semibold">{title}</span>
              <span className="text-muted-foreground">{hint}</span>
            </span>
          </label>
        ))}
      </fieldset>
    )
  }
  const appending = decision === "append" && !kindChanged && dest.action === "append"
  if (appending) {
    return (
      <p className="flex items-start gap-2 text-sm text-foreground/85">
        <ArrowRight className="mt-0.5 h-4 w-4 shrink-0 text-primary" aria-hidden="true" />
        <span>{dest.text}</span>
      </p>
    )
  }
  return (
    <div className="space-y-1.5">
      <label htmlFor={`${uid}-name`} className="flex items-center gap-2 text-sm font-semibold">
        <ArrowRight className="h-4 w-4 text-primary" aria-hidden="true" />
        Se guardará como una hoja nueva. ¿Cómo la llamamos?
      </label>
      <input
        id={`${uid}-name`}
        value={newName}
        maxLength={150}
        onChange={(e) => onRename?.(e.target.value)}
        className="h-11 w-full rounded-xl border border-input bg-card px-3.5 text-[15px] hover:border-foreground/25 focus:border-ring focus:outline-none focus:ring-4 focus:ring-ring/15 sm:h-10 sm:text-sm"
      />
    </div>
  )
}
