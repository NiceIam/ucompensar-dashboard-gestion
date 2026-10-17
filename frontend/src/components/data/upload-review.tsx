"use client"

import { useMemo, useState } from "react"
import { ArrowRight, FilePlus2, Layers, Merge, RotateCcw } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Notice } from "@/components/kit/notice"
import { ColumnKindIcon } from "@/components/data/column-kind"
import { KIND_INFO, columnKind, columnLabel, type ColumnKind } from "@/lib/data-vocabulary"
import { formatDate, formatMoney, formatNumber, pluralize } from "@/lib/format"
import { parseDateCell, parseNumberCell } from "@/lib/upload/insights"
import type { Assessment } from "@/lib/upload/assess"
import type { Cell, LocalRead, LocalSheet } from "@/lib/upload/read-local"
import { sheetsWithData } from "@/lib/upload/read-local"
import type { AnalysisColumn, FileAnalysis } from "@/lib/upload/types"
import { cn } from "@/lib/utils"

const MAX_PREVIEW_COLUMNS = 8

export function cellText(cell: Cell | unknown): string {
  if (cell === null || cell === undefined || cell === "") return ""
  if (cell instanceof Date) {
    const hasTime = cell.getHours() + cell.getMinutes() > 0
    return cell.toLocaleDateString("es-CO", { day: "numeric", month: "short", year: "numeric" }) + (hasTime ? ` ${cell.toLocaleTimeString("es-CO", { hour: "2-digit", minute: "2-digit" })}` : "")
  }
  if (typeof cell === "number") return formatNumber(cell)
  if (typeof cell === "boolean") return cell ? "Sí" : "No"
  return String(cell)
}

/** Lista legible: "fecha, producto, región y total". */
function humanList(items: string[], max = 4): string {
  const shown = items.slice(0, max)
  const rest = items.length - shown.length
  if (rest > 0) return `${shown.join(", ")} y ${rest} más`
  if (shown.length <= 1) return shown.join("")
  return `${shown.slice(0, -1).join(", ")} y ${shown[shown.length - 1]}`
}

/** Frase de cabecera: "Encontramos 300 filas de «Ventas»: fecha, producto, región y total." */
export function headlineFor(analysis: FileAnalysis | null, assessment: Assessment | null): string {
  if (assessment && assessment.sheets.length > 1) {
    return `Tu Excel tiene ${assessment.sheets.length} hojas con datos: ${humanList(assessment.sheets.map((s) => `«${s.name}»`), 5)}.`
  }
  if (!analysis) return "Esto es lo que encontramos en tu archivo."
  const name = assessment?.destination?.name ?? analysis.suggested_display_name
  const cols = analysis.columns.map((c) => columnLabel({ name: c.clean_name, label: c.original_name }).toLowerCase())
  return `Encontramos ${pluralize(analysis.row_count, "fila", "filas")} de «${name}»: ${humanList(cols)}.`
}

/** Ejemplo de valor mostrado como lo leería una persona (fechas, pesos, sí/no). */
export function friendlySample(value: string, kind: ColumnKind): string {
  if (kind === "date") {
    const d = parseDateCell(value)
    return d ? formatDate(d) : value
  }
  if (kind === "money" || kind === "number") {
    const n = parseNumberCell(value)
    if (n === null) return value
    return kind === "money" ? formatMoney(n) : formatNumber(n)
  }
  if (kind === "boolean") {
    const v = value.trim().toLowerCase()
    if (["true", "si", "sí", "1", "yes"].includes(v)) return "Sí"
    if (["false", "no", "0"].includes(v)) return "No"
  }
  return value
}

function ColumnCard({ column }: { column: AnalysisColumn }) {
  const like = { name: column.clean_name, label: column.original_name, type: column.inferred_type }
  const kind = columnKind(like)
  const examples = Array.from(new Set(column.sample_values.filter(Boolean).map((v) => friendlySample(v, kind)))).slice(0, 3)
  return (
    <li className="flex min-w-0 gap-3 rounded-xl border bg-card p-3.5">
      <ColumnKindIcon kind={kind} className="h-9 w-9 rounded-xl [&>svg]:h-4 [&>svg]:w-4" />
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-baseline gap-x-2">
          <p className="truncate font-semibold">{columnLabel(like)}</p>
          <p className="text-xs font-medium text-muted-foreground">{KIND_INFO[kind].label}</p>
        </div>
        {examples.length > 0 ? (
          <p className="mt-0.5 truncate text-[13px] text-muted-foreground" title={examples.join(" · ")}>
            Ej.: {examples.join(" · ")}
          </p>
        ) : (
          <p className="mt-0.5 text-[13px] text-muted-foreground">Sin datos todavía</p>
        )}
        {column.null_count > 0 && column.non_null_count > 0 && (
          <p className="mt-1 text-xs font-medium text-warning-strong">{pluralize(column.null_count, "celda vacía", "celdas vacías")}</p>
        )}
      </div>
    </li>
  )
}

/** Tabla con las primeras filas tal como vienen en el archivo. */
export function SampleTable({
  header,
  rows,
  caption,
  kinds,
}: {
  header: string[]
  rows: (Cell | unknown)[][]
  caption: string
  /** Clase de cada columna (si se conoce) para mostrar fechas, pesos y sí/no legibles. */
  kinds?: ColumnKind[]
}) {
  const cols = header.slice(0, MAX_PREVIEW_COLUMNS)
  const hidden = header.length - cols.length
  return (
    <div className="space-y-2">
      <div className="overflow-x-auto rounded-xl border bg-card">
        <table className="w-full min-w-max text-sm">
          <caption className="sr-only">{caption}</caption>
          <thead>
            <tr className="border-b bg-muted/60">
              {cols.map((h, i) => (
                <th key={`${h}-${i}`} scope="col" className="whitespace-nowrap px-3 py-2.5 text-left text-[13px] font-semibold">
                  {h || <span className="italic text-muted-foreground">sin título</span>}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((r, ri) => (
              <tr key={ri} className="border-b last:border-0">
                {cols.map((_, ci) => {
                  const raw = r[ci]
                  const kind = kinds?.[ci]
                  const text = kind && typeof raw === "string" && raw !== "" ? friendlySample(raw, kind) : cellText(raw)
                  return (
                    <td key={ci} className="max-w-[220px] truncate whitespace-nowrap px-3 py-2.5 tabular" title={text}>
                      {text || <span className="text-muted-foreground/60">—</span>}
                    </td>
                  )
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {hidden > 0 && (
        <p className="text-xs text-muted-foreground">
          Y {pluralize(hidden, "columna más", "columnas más")} que también se guardarán.
        </p>
      )}
    </div>
  )
}

/** Primeras filas: del archivo leído en el navegador o, si no, de los ejemplos del servidor. */
function previewRows(sheet: LocalSheet | undefined, analysis: FileAnalysis | null): { header: string[]; rows: (Cell | unknown)[][] } | null {
  if (sheet && sheet.rows.length > 0) return { header: sheet.header, rows: sheet.rows.slice(0, 5) }
  if (!analysis) return null
  // Los ejemplos del servidor solo forman filas reales si ninguna columna tiene vacíos.
  if (analysis.columns.some((c) => c.null_count > 0)) return null
  const n = Math.min(5, ...analysis.columns.map((c) => c.sample_values.length))
  if (!Number.isFinite(n) || n <= 0) return null
  return {
    header: analysis.columns.map((c) => c.original_name),
    rows: Array.from({ length: n }, (_, i) => analysis.columns.map((c) => c.sample_values[i])),
  }
}

export function UploadReview({
  file,
  analysis,
  assessment,
  local,
  onConfirm,
  onCancel,
}: {
  file: File
  analysis: FileAnalysis | null
  assessment: Assessment
  local: LocalRead | null
  onConfirm: () => void
  onCancel: () => void
}) {
  const sheets = useMemo(() => sheetsWithData(local), [local])
  const multi = assessment.sheets.length > 1
  const [sheetIndex, setSheetIndex] = useState(0)
  const activeSheet = sheets[sheetIndex]
  const sample = previewRows(multi ? activeSheet : sheets[0], sheetIndex === 0 ? analysis : null)
  const dest = assessment.destination
  const rows = analysis?.row_count ?? 0

  const primaryLabel = multi
    ? `Guardar las ${assessment.sheets.length} hojas`
    : dest?.kind === "existing"
      ? `Agregar ${pluralize(rows, "fila", "filas")} a «${dest.name}»`
      : `Guardar ${pluralize(rows, "fila", "filas")}`

  const consequence = multi
    ? `Cada hoja se guardará por separado (${humanList(assessment.sheets.map((s) => `${s.name}: ${formatNumber(s.rows)}`), 4)} filas).`
    : dest?.kind === "existing"
      ? `Las filas se sumarán a las ${dest.existingRows !== undefined ? formatNumber(dest.existingRows) : ""} que ya tiene «${dest.name}».`
      : `Crearemos «${dest?.name ?? "tus datos"}» con ${pluralize(rows, "fila", "filas")}. Si no te convence, podrás deshacerlo.`

  return (
    <div className="space-y-6">
      <div className="space-y-2">
        <p className="text-[13px] font-semibold uppercase tracking-[0.08em] text-highlight-strong">Revisemos juntos</p>
        <h3 className="font-display text-[26px] font-semibold leading-tight text-balance sm:text-3xl">
          {headlineFor(analysis, assessment)}
        </h3>
        {assessment.reviewReasons.length > 0 && (
          <p className="text-[15px] text-muted-foreground">
            Antes de guardar queremos que lo veas: {assessment.reviewReasons.map((r) => r.charAt(0).toLowerCase() + r.slice(1)).join(" ")}
          </p>
        )}
      </div>

      {/* Destino */}
      {!multi && dest && (
        <div className={cn("flex items-start gap-3 rounded-2xl border p-4", dest.kind === "existing" ? "border-highlight/40 bg-highlight-soft/60" : "bg-primary-soft/50 border-primary/20")}>
          <span className={cn("flex h-10 w-10 shrink-0 items-center justify-center rounded-xl", dest.kind === "existing" ? "bg-highlight text-highlight-foreground" : "bg-primary text-primary-foreground")}>
            {dest.kind === "existing" ? <Merge className="h-5 w-5" aria-hidden="true" /> : <FilePlus2 className="h-5 w-5" aria-hidden="true" />}
          </span>
          <div className="space-y-0.5 text-[15px]">
            {dest.kind === "existing" ? (
              <>
                <p className="font-semibold">Se parece a tus datos de «{dest.name}»</p>
                <p className="text-foreground/80">
                  Agregaremos estas filas allí{dest.existingRows !== undefined ? `, junto a las ${formatNumber(dest.existingRows)} que ya tienes` : ""}. Esto no se puede deshacer con un clic, por eso te preguntamos primero.
                </p>
              </>
            ) : (
              <>
                <p className="font-semibold">Crearemos «{dest.name}» para ti</p>
                <p className="text-foreground/80">Será una hoja nueva; no toca nada de lo que ya tienes.</p>
              </>
            )}
          </div>
        </div>
      )}

      {/* Avisos */}
      {assessment.issues.length > 0 && (
        <div className="space-y-2.5">
          {assessment.issues.map((issue) => (
            <Notice key={issue.id} tone={issue.tone} title={issue.title}>
              {issue.detail}
            </Notice>
          ))}
        </div>
      )}

      {/* Hojas */}
      {multi && (
        <div className="space-y-3">
          <div className="flex items-center gap-2 text-sm font-semibold">
            <Layers className="h-4 w-4 text-primary" aria-hidden="true" />
            Mira cada hoja
          </div>
          <div role="tablist" aria-label="Hojas del archivo" className="flex gap-2 overflow-x-auto pb-1 scrollbar-none">
            {sheets.map((s, i) => (
              <button
                key={`${s.name}-${i}`}
                role="tab"
                type="button"
                aria-selected={i === sheetIndex}
                onClick={() => setSheetIndex(i)}
                className={cn(
                  "inline-flex min-h-11 shrink-0 items-center gap-2 rounded-xl border px-3.5 text-sm font-semibold transition",
                  i === sheetIndex ? "border-primary bg-primary text-primary-foreground" : "bg-card hover:border-primary/40"
                )}
              >
                {s.name}
                <span className={cn("rounded-full px-2 py-0.5 text-xs", i === sheetIndex ? "bg-primary-foreground/15" : "bg-muted text-muted-foreground")}>
                  {formatNumber(s.rows.length)}
                </span>
              </button>
            ))}
          </div>
          <p className="text-sm text-muted-foreground">
            Al guardar cargaremos todas las hojas con datos (las vacías se omiten). Si solo quieres algunas, quita las demás del Excel antes de subirlo.
          </p>
        </div>
      )}

      {/* Columnas explicadas (análisis del servidor: primera hoja) */}
      {analysis && (sheetIndex === 0 || !multi) && (
        <section aria-labelledby="cols-title" className="space-y-3">
          <h4 id="cols-title" className="text-sm font-semibold">
            Lo que entendimos de cada columna
          </h4>
          <ul className="auto-grid gap-2.5 [--auto-grid-min:15rem]">
            {analysis.columns.slice(0, 12).map((c) => (
              <ColumnCard key={c.clean_name} column={c} />
            ))}
          </ul>
          {analysis.columns.length > 12 && (
            <p className="text-xs text-muted-foreground">Y {pluralize(analysis.columns.length - 12, "columna más", "columnas más")}.</p>
          )}
        </section>
      )}

      {/* Muestra */}
      {sample && (
        <section aria-labelledby="sample-title" className="space-y-3">
          <h4 id="sample-title" className="text-sm font-semibold">
            Así se ven las primeras filas{multi && activeSheet?.name ? ` de «${activeSheet.name}»` : ""}
          </h4>
          <SampleTable
            header={sample.header}
            rows={sample.rows}
            caption={`Primeras filas de ${file.name}`}
            kinds={
              analysis && (!multi || sheetIndex === 0) && sample.header.length === analysis.columns.length
                ? analysis.columns.map((c) => columnKind({ name: c.clean_name, label: c.original_name, type: c.inferred_type }))
                : undefined
            }
          />
        </section>
      )}

      {/* Barra de decisión */}
      <div className="sticky bottom-[calc(76px+env(safe-area-inset-bottom))] z-10 -mx-5 -mb-5 flex flex-col gap-3 rounded-b-3xl border-t bg-card/95 p-4 backdrop-blur-md sm:-mx-8 sm:-mb-8 sm:flex-row sm:items-center sm:justify-between sm:px-8 lg:bottom-0">
        <p className={cn("text-sm", assessment.blocked ? "font-medium text-danger-strong" : "text-muted-foreground")} id="decision-help">
          {assessment.blocked ? "No hay filas para guardar. Revisa el archivo y vuelve a subirlo." : consequence}
        </p>
        <div className="flex flex-col-reverse gap-2 sm:flex-row sm:items-center">
          <Button variant="ghost" onClick={onCancel}>
            <RotateCcw aria-hidden="true" />
            Elegir otro archivo
          </Button>
          <Button size="lg" onClick={onConfirm} disabled={assessment.blocked} aria-describedby="decision-help">
            {primaryLabel}
            <ArrowRight aria-hidden="true" />
          </Button>
        </div>
      </div>
    </div>
  )
}
