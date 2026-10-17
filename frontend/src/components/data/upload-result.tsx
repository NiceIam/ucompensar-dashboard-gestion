"use client"

import { useMemo, useState } from "react"
import { toast } from "sonner"
import {
  CalendarRange,
  CheckCircle2,
  CircleAlert,
  CircleMinus,
  Crown,
  Eye,
  Pencil,
  Sigma,
  TrendingUp,
  Undo2,
  Upload,
  type LucideIcon,
} from "lucide-react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { DataSentence, Figure } from "@/components/kit/data-sentence"
import { Notice } from "@/components/kit/notice"
import { StatusBadge } from "@/components/kit/status-badge"
import { SuggestionChips } from "@/components/kit/suggestion-chips"
import { ConfirmDialog } from "@/components/kit/confirm-dialog"
import { SimpleChart } from "@/components/charts/simple-chart"
import { useDeleteTable, useUpdateTable } from "@/hooks/use-data"
import type { OrgTable } from "@/hooks/use-templates"
import { humanizeError } from "@/lib/errors"
import { formatNumber, pluralize } from "@/lib/format"
import { suggestQuestions } from "@/lib/suggestions"
import type { Assessment } from "@/lib/upload/assess"
import { computeInsights, type InsightFact } from "@/lib/upload/insights"
import { friendlyFileName } from "@/lib/upload/local-file"
import { sheetsWithData, type LocalRead } from "@/lib/upload/read-local"
import type { FileAnalysis, SmartUploadResult } from "@/lib/upload/types"

const FACT_ICON: Record<InsightFact["id"], LucideIcon> = {
  period: CalendarRange,
  total: Sigma,
  count: Sigma,
  leader: Crown,
  change: TrendingUp,
}

const GENERIC_NAMES = new Set(["datos_importados"])

interface SheetOutcome {
  name: string
  tone: "success" | "neutral" | "danger"
  label: string
  detail: string
  tableId?: string
  created: boolean
}

function sheetOutcomes(result: SmartUploadResult, tables: OrgTable[]): SheetOutcome[] {
  return (result.sheets ?? []).map((s, i) => {
    const name = s.sheet_name ?? `Hoja ${i + 1}`
    const tableName = tables.find((t) => t.id === s.table_id)?.display_name ?? s.table_name
    if (s.status === "skipped_empty") return { name, tone: "neutral", label: "Vacía", detail: "No tenía datos; la omitimos.", created: false }
    if (s.status === "error") {
      const h = humanizeError(new Error(s.error ?? ""), "upload")
      return { name, tone: "danger", label: "No se pudo", detail: `${h.title}. ${h.description}`, created: false }
    }
    const created = s.status === "created_new_table"
    return {
      name,
      tone: "success",
      label: created ? "Nueva" : "Agregada",
      detail: `${pluralize(s.rows_inserted ?? 0, "fila", "filas")} ${created ? "en" : "sumadas a"} «${tableName ?? "tus datos"}».`,
      tableId: s.table_id,
      created,
    }
  })
}

export function UploadResult({
  file,
  analysis,
  assessment,
  local,
  result,
  autoSaved,
  tables,
  onReset,
  onViewTable,
  onAsk,
  onUndone,
}: {
  file: File
  analysis: FileAnalysis | null
  assessment: Assessment | null
  local: LocalRead | null
  result: SmartUploadResult
  autoSaved: boolean
  tables: OrgTable[]
  onReset: () => void
  onViewTable: (tableId: string) => void
  onAsk: (question: string) => void
  onUndone: () => void
}) {
  const deleteTable = useDeleteTable()
  const updateTable = useUpdateTable()
  const [confirmUndo, setConfirmUndo] = useState(false)
  const multi = Boolean(result.multi_sheet)
  const table = tables.find((t) => t.id === result.table_id)
  const displayName = table?.display_name ?? analysis?.suggested_display_name ?? "tus datos"
  const created = result.status === "created_new_table"
  const rowsSaved = multi ? result.total_rows_inserted ?? 0 : result.rows_inserted ?? 0
  const outcomes = useMemo(() => (multi ? sheetOutcomes(result, tables) : []), [multi, result, tables])

  // Tablas que se pueden borrar para deshacer: solo las recién creadas.
  const undoIds = multi
    ? outcomes.every((o) => o.tone !== "success" || o.created)
      ? outcomes.filter((o) => o.created && o.tableId).map((o) => o.tableId!)
      : []
    : created && result.table_id
      ? [result.table_id]
      : []

  const insights = useMemo(() => {
    if (multi || !analysis) return null
    const sheet = sheetsWithData(local)[0]
    return sheet ? computeInsights(sheet, analysis.columns) : null
  }, [multi, analysis, local])

  const questions = useMemo(() => {
    if (multi) {
      const ids = new Set(outcomes.map((o) => o.tableId).filter(Boolean))
      return suggestQuestions(
        tables
          .filter((t) => ids.has(t.id))
          .map((t) => ({ name: t.display_name, rowCount: t.row_count, columns: t.columns_definition ?? [] })),
        3
      )
    }
    if (!analysis) return []
    return suggestQuestions(
      [
        {
          name: displayName,
          rowCount: rowsSaved,
          columns: analysis.columns.map((c) => ({
            name: c.clean_name,
            label: c.original_name,
            type: c.inferred_type,
            distinct: c.unique_count,
            filled: c.non_null_count,
          })),
        },
      ],
      3
    )
  }, [multi, outcomes, tables, analysis, displayName, rowsSaved])

  const generic = !multi && created && GENERIC_NAMES.has(result.table_name ?? analysis?.suggested_table_name ?? "")
  const [name, setName] = useState(() => friendlyFileName(file.name))
  const [renamed, setRenamed] = useState(false)

  async function rename() {
    if (!result.table_id || !name.trim()) return
    try {
      await updateTable.mutateAsync({ tableId: result.table_id, newDisplayName: name.trim() })
      setRenamed(true)
      toast.success(`Listo, ahora se llama «${name.trim()}»`)
    } catch (err) {
      const h = humanizeError(err, "save")
      toast.error(h.title, { description: h.description })
    }
  }

  async function undo() {
    try {
      for (const id of undoIds) await deleteTable.mutateAsync(id)
      setConfirmUndo(false)
      toast.success("Listo, deshicimos la carga", { description: "Tu archivo no cambió; puedes volver a subirlo cuando quieras." })
      onUndone()
    } catch (err) {
      const h = humanizeError(err, "delete")
      toast.error(h.title, { description: h.description })
    }
  }

  const infoIssues = assessment?.issues.filter((i) => i.tone === "info") ?? []

  return (
    <div className="space-y-7">
      {/* Titular */}
      <div className="flex flex-col gap-4 sm:flex-row sm:items-start">
        <span className="flex h-14 w-14 shrink-0 items-center justify-center rounded-2xl bg-success-soft text-success-strong">
          <CheckCircle2 className="h-7 w-7" aria-hidden="true" />
        </span>
        <div className="space-y-1.5">
          <h3 className="font-display text-[28px] font-semibold leading-tight text-balance sm:text-[32px]">
            {multi
              ? `Listo. Guardamos ${pluralize(rowsSaved, "fila", "filas")} de ${pluralize(outcomes.filter((o) => o.tone === "success").length, "hoja", "hojas")}.`
              : `Listo. Guardamos ${pluralize(rowsSaved, "fila", "filas")} en «${renamed ? name.trim() : displayName}».`}
          </h3>
          <p className="text-[15px] text-muted-foreground">
            {multi
              ? "Cada hoja del Excel quedó guardada por separado."
              : created
                ? autoSaved
                  ? "Tu archivo se veía claro, así que lo guardamos de una vez en una hoja nueva."
                  : "Quedó en una hoja nueva, sin tocar lo que ya tenías."
                : `Las sumamos a lo que ya tenías: ahora son ${pluralize(result.total_rows ?? table?.row_count ?? rowsSaved, "fila", "filas")}.`}{" "}
            Ya puedes preguntarle a tus datos.
          </p>
        </div>
      </div>

      {/* Hojas (Excel con varias) */}
      {multi && (
        <ul className="divide-y rounded-2xl border bg-card">
          {outcomes.map((o) => (
            <li key={o.name} className="flex flex-col gap-2 p-4 sm:flex-row sm:items-center">
              <div className="flex min-w-0 flex-1 items-center gap-3">
                {o.tone === "success" ? (
                  <CheckCircle2 className="h-5 w-5 shrink-0 text-success" aria-hidden="true" />
                ) : o.tone === "danger" ? (
                  <CircleAlert className="h-5 w-5 shrink-0 text-destructive" aria-hidden="true" />
                ) : (
                  <CircleMinus className="h-5 w-5 shrink-0 text-muted-foreground" aria-hidden="true" />
                )}
                <div className="min-w-0">
                  <p className="font-semibold">{o.name}</p>
                  <p className="text-sm text-muted-foreground">{o.detail}</p>
                </div>
              </div>
              <div className="flex items-center gap-2 pl-8 sm:pl-0">
                <StatusBadge tone={o.tone === "success" ? "success" : o.tone === "danger" ? "danger" : "neutral"}>{o.label}</StatusBadge>
                {o.tableId && (
                  <Button variant="ghost" size="sm" onClick={() => onViewTable(o.tableId!)}>
                    Ver
                  </Button>
                )}
              </div>
            </li>
          ))}
        </ul>
      )}

      {/* Nombre genérico: ofrecer uno mejor */}
      {generic && !renamed && (
        <form
          onSubmit={(e) => {
            e.preventDefault()
            void rename()
          }}
          className="flex flex-col gap-3 rounded-2xl border border-highlight/40 bg-highlight-soft/50 p-4 sm:flex-row sm:items-end"
        >
          <div className="flex-1 space-y-1.5">
            <label htmlFor="rename-upload" className="flex items-center gap-2 text-sm font-semibold">
              <Pencil className="h-4 w-4 text-highlight-strong" aria-hidden="true" />
              ¿Cómo quieres llamar estos datos?
            </label>
            <Input id="rename-upload" value={name} onChange={(e) => setName(e.target.value)} maxLength={150} />
          </div>
          <Button type="submit" variant="outline" loading={updateTable.isPending} disabled={!name.trim()}>
            Guardar nombre
          </Button>
        </form>
      )}

      {/* Primer vistazo */}
      {insights && (insights.facts.length > 0 || insights.chart) && (
        <section aria-labelledby="first-look" className="grid grid-cols-1 gap-5 rounded-2xl border bg-card p-5 sm:p-6 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.15fr)]">
          <div className="space-y-4">
            <div>
              <h4 id="first-look" className="font-display text-xl font-semibold">
                Un primer vistazo
              </h4>
              <p className="text-[13px] text-muted-foreground">Calculado con el archivo que acabas de subir.</p>
            </div>
            <div className="space-y-3.5">
              {insights.facts.map((f) => (
                <DataSentence key={f.id} icon={FACT_ICON[f.id]}>
                  {f.parts.map((p, i) => (p.figure ? <Figure key={i}>{p.text}</Figure> : <span key={i}>{p.text}</span>))}
                </DataSentence>
              ))}
            </div>
          </div>
          {insights.chart && (
            <div className="min-w-0">
              <p className="mb-1 text-sm font-semibold">{insights.chart.title}</p>
              <SimpleChart
                form={insights.chart.form}
                points={insights.chart.points}
                unit={insights.chart.unit}
                label={insights.chart.title}
                height={230}
              />
            </div>
          )}
        </section>
      )}

      {/* Preguntas */}
      {questions.length > 0 && (
        <section aria-labelledby="ask-now" className="rounded-2xl bg-primary p-5 text-primary-foreground sm:p-6">
          <h4 id="ask-now" className="font-display text-xl font-semibold">
            Pregúntale a tus datos
          </h4>
          <p className="mb-4 mt-1 text-sm text-primary-foreground/80">Toca una pregunta y el asistente la responde con tus cifras.</p>
          <SuggestionChips questions={questions} onPick={onAsk} className="[&_button]:border-transparent" />
        </section>
      )}

      {infoIssues.length > 0 && (
        <div className="space-y-2">
          {infoIssues.map((i) => (
            <Notice key={i.id} tone="info" title={i.title}>
              {i.detail}
            </Notice>
          ))}
        </div>
      )}

      {/* Acciones */}
      <div className="flex flex-col gap-2 border-t pt-5 sm:flex-row sm:items-center">
        {!multi && result.table_id && (
          <Button onClick={() => onViewTable(result.table_id!)}>
            <Eye aria-hidden="true" />
            Ver mis datos
          </Button>
        )}
        <Button variant="outline" onClick={onReset}>
          <Upload aria-hidden="true" />
          Subir otro archivo
        </Button>
        <div className="flex-1" />
        {undoIds.length > 0 && (
          <Button variant="ghost" className="text-muted-foreground" onClick={() => setConfirmUndo(true)}>
            <Undo2 aria-hidden="true" />
            Deshacer esta carga
          </Button>
        )}
      </div>

      <ConfirmDialog
        open={confirmUndo}
        onOpenChange={setConfirmUndo}
        title="¿Deshacer esta carga?"
        description={
          undoIds.length === 1
            ? `Borraremos la hoja «${renamed ? name.trim() : displayName}», que acabamos de crear, con sus ${formatNumber(rowsSaved)} filas. Tu archivo no cambia.`
            : `Borraremos las ${undoIds.length} hojas que acabamos de crear, con sus ${formatNumber(rowsSaved)} filas. Tu archivo no cambia.`
        }
        confirmLabel="Sí, deshacer"
        loading={deleteTable.isPending}
        onConfirm={undo}
        icon={Undo2}
      />
    </div>
  )
}
