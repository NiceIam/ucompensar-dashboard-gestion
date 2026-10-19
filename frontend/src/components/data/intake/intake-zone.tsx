"use client"

import { useCallback, useEffect, useReducer, useRef, useState } from "react"
import { FileWarning, RotateCcw, Save, Upload, X } from "lucide-react"
import { Button } from "@/components/ui/button"
import { DotsLoader } from "@/components/kit/dots"
import { FileDrop } from "@/components/kit/file-drop"
import { ProgressBar } from "@/components/kit/progress-bar"
import { FileCard } from "@/components/data/intake/file-card"
import { IntakeResult } from "@/components/data/intake/intake-result"
import { SheetCard } from "@/components/data/intake/sheet-card"
import { useOntology, analyzeIntake, commitIntake } from "@/hooks/use-intake"
import { useInvalidateData } from "@/hooks/use-data"
import type { OrgTable } from "@/hooks/use-templates"
import { humanizeError } from "@/lib/errors"
import { pluralize } from "@/lib/format"
import { buildPlan, defaultDecision, plannedCount, readySheets } from "@/lib/intake/plan"
import { initialIntakeState, intakeMessage, intakeReducer, validEntries } from "@/lib/intake/state"
import { looksLikeZip, validateLocalFile } from "@/lib/upload/local-file"
import { cn } from "@/lib/utils"

/** Lo que el servidor puede tardar: mensajes que cambian para que la espera no se sienta muerta. */
const SAVING_HINTS = ["Guardando tus datos…", "Organizando las columnas…", "Ya casi…"]

/**
 * UNA sola zona de carga para todo: la persona suelta lo que tenga (uno o varios Excel, CSV o JSON, en desorden)
 * y el sistema lo entiende solo. Cada archivo muestra su estado (leyendo → entendiendo → listo). Solo pide ayuda
 * cuando hay baja confianza o duda de mezcla; si todo es claro, guarda directo con «Deshacer».
 */
export function IntakeZone({
  tables,
  hero,
  onViewTable,
  onAsk,
}: {
  tables: OrgTable[]
  hero: boolean
  onViewTable: (tableId: string) => void
  onAsk: (question: string) => void
}) {
  const [state, dispatch] = useReducer(intakeReducer, initialIntakeState)
  const invalidate = useInvalidateData()
  const { data: ontology } = useOntology()
  const started = useRef<string | null>(null)
  const containerRef = useRef<HTMLDivElement>(null)
  const [savingHint, setSavingHint] = useState(0)

  useEffect(() => {
    if (state.phase !== "saving") return
    setSavingHint(0)
    const id = window.setInterval(() => setSavingHint((h) => Math.min(h + 1, SAVING_HINTS.length - 1)), 2600)
    return () => window.clearInterval(id)
  }, [state.phase])

  const choose = useCallback((files: File[]) => {
    dispatch({
      type: "add",
      entries: files.map((file) => {
        const check = validateLocalFile(file)
        return check.ok
          ? { file, kind: check.kind }
          : { file, kind: null, problem: { title: check.title, description: check.description } }
      }),
    })
  }, [])

  // Cada fase con trabajo asíncrono se ejecuta una sola vez por intento (también en modo estricto).
  useEffect(() => {
    const key = `${state.run}:${state.phase}`
    if (started.current === key) return
    const { run } = state

    if (state.phase === "analyzing") {
      started.current = key
      const entries = state.entries
      void (async () => {
        // 1. Leer: lo barato se revisa aquí mismo (un .xlsx que por dentro no es Excel).
        const problems: Record<string, { title: string; description: string }> = {}
        await Promise.all(
          validEntries(entries)
            .filter((e) => e.kind === "xlsx")
            .map(async (e) => {
              if (!(await looksLikeZip(e.file))) {
                problems[e.id] = {
                  title: "Este archivo dice ser Excel, pero por dentro no lo es.",
                  description: "Puede que le hayan cambiado la extensión. Ábrelo en Excel y guárdalo como Libro de Excel (.xlsx).",
                }
              }
            })
        )
        if (Object.keys(problems).length > 0) dispatch({ type: "problems", run, problems })
        const valid = validEntries(entries).filter((e) => !problems[e.id])
        if (valid.length === 0) return
        // 2. Entender (una sola llamada con todos los archivos: así junta lo que va junto).
        dispatch({ type: "understanding", run })
        try {
          const proposal = await analyzeIntake(valid.map((e) => ({ file: e.file, kind: e.kind! })))
          dispatch({ type: "analyzed", run, proposal })
        } catch (err) {
          dispatch({ type: "fail", run, at: "analyzing", error: humanizeError(err, "analyze") })
        }
      })()
    }

    if (state.phase === "saving" && state.proposal) {
      started.current = key
      const plan = buildPlan(state.proposal, state.edits, state.decisions)
      const items = validEntries(state.entries).map((e) => ({ file: e.file, kind: e.kind! }))
      void (async () => {
        try {
          const result = await commitIntake(items, plan)
          await invalidate()
          dispatch({ type: "saved", run, result })
        } catch (err) {
          dispatch({ type: "fail", run, at: "saving", error: humanizeError(err, "upload") })
        }
      })()
    }
  }, [state, invalidate])

  // Al cambiar de fase, mantener el bloque a la vista (sobre todo en el celular).
  useEffect(() => {
    if (state.phase === "review" || state.phase === "done" || state.phase === "failed") {
      containerRef.current?.scrollIntoView?.({ behavior: "smooth", block: "start" })
    }
  }, [state.phase])

  const phase = state.phase
  const message = intakeMessage(state)
  const showDrop = phase === "idle" || phase === "rejected"
  const sheets = readySheets(state.proposal)
  const plan = state.proposal ? buildPlan(state.proposal, state.edits, state.decisions) : []
  const toSave = plannedCount(plan)
  const summaries = new Map<string, string>()
  for (const f of state.proposal?.files ?? []) {
    const ready = f.sheets.filter((s) => s.status === "ready")
    if (ready.length === 1) summaries.set(f.file_name, `${ready[0].kind_phrase?.replace(/^tus? /, "") ?? "datos"} · ${ready[0].stats ?? ""}`)
    else if (ready.length > 1) summaries.set(f.file_name, `${ready.length} hojas`)
  }

  return (
    <div ref={containerRef} className="scroll-mt-24">
      <p className="sr-only" role="status" aria-live="polite">
        {message}
      </p>

      {showDrop && (
        <div className="space-y-3">
          {phase === "rejected" && state.entries.length > 0 && (
            <div className="space-y-2">
              <ul className="space-y-2" aria-label="Archivos que no pude usar">
                {state.entries.map((e) => (
                  <FileCard key={e.id} entry={e} onRemove={() => dispatch({ type: "remove", id: e.id })} />
                ))}
              </ul>
              <Button variant="ghost" size="sm" onClick={() => dispatch({ type: "reset" })}>
                <X aria-hidden="true" />
                Quitar estos avisos
              </Button>
            </div>
          )}
          <FileDrop onFiles={choose} compact={!hero} />
        </div>
      )}

      {!showDrop && (
        <div className={cn("surface overflow-hidden rounded-3xl p-4 sm:p-8", phase === "done" && "border-success/30")}>
          {phase === "analyzing" && (
            <div className="space-y-6">
              <div className="flex flex-col items-center gap-4 text-center">
                <DotsLoader size="lg" />
                <div className="space-y-1">
                  <p className="font-display text-2xl font-semibold" aria-hidden="true">
                    {message}
                  </p>
                  <p className="text-sm text-muted-foreground">Todavía no se guarda nada. Primero entiendo qué es cada cosa.</p>
                </div>
                <ProgressBar label={message} className="max-w-sm" />
              </div>
              <ul className="mx-auto max-w-xl space-y-2" aria-label="Tus archivos">
                {state.entries.map((e) => (
                  <FileCard key={e.id} entry={e} />
                ))}
              </ul>
              <div className="flex justify-center">
                <Button variant="ghost" onClick={() => dispatch({ type: "reset" })}>
                  <X aria-hidden="true" />
                  Cancelar
                </Button>
              </div>
            </div>
          )}

          {phase === "review" && state.proposal && (
            <div className="space-y-6">
              <div className="space-y-1.5">
                <h3 className="font-display text-[28px] font-semibold leading-tight text-balance sm:text-[32px]">Esto es lo que entendí</h3>
                <p className="text-[15px] text-muted-foreground">
                  Revisé {pluralize(validEntries(state.entries).length, "archivo", "archivos")}. Solo te pido ayuda con lo que no tengo claro; lo demás
                  ya lo organicé.
                </p>
              </div>

              <ul className="grid gap-2 lg:grid-cols-2" aria-label="Tus archivos">
                {state.entries.map((e) => (
                  <FileCard
                    key={e.id}
                    entry={e}
                    summary={summaries.get(e.file.name)}
                    onRemove={() => dispatch({ type: "remove", id: e.id })}
                  />
                ))}
              </ul>

              <div className="space-y-3">
                {sheets.map(({ file, sheet }) => (
                  <SheetCard
                    key={sheet.key}
                    fileName={file.file_name}
                    sheet={sheet}
                    edit={state.edits[sheet.key]}
                    decision={state.decisions[sheet.key] ?? defaultDecision(sheet)}
                    ontology={ontology}
                    mode="review"
                    onRole={(column, role) => dispatch({ type: "edit-role", key: sheet.key, column, role })}
                    onKind={(kind) => dispatch({ type: "edit-kind", key: sheet.key, kind, ontology })}
                    onRename={(name) => dispatch({ type: "rename", key: sheet.key, name })}
                    onDecide={(decision) => dispatch({ type: "decide", key: sheet.key, decision })}
                    onSkip={(skip) => dispatch({ type: "decide", key: sheet.key, decision: skip ? "skip" : defaultDecision(sheet) })}
                  />
                ))}
              </div>

              <div className="sticky bottom-3 z-10 flex flex-col gap-2 rounded-2xl border bg-card/95 p-3 shadow-raised backdrop-blur sm:flex-row sm:items-center">
                <Button size="lg" disabled={toSave === 0} onClick={() => dispatch({ type: "confirm" })}>
                  <Save aria-hidden="true" />
                  {toSave === 0 ? "No hay nada para guardar" : `Guardar ${pluralize(toSave, "hoja", "hojas")}`}
                </Button>
                <Button variant="ghost" onClick={() => dispatch({ type: "reset" })}>
                  <X aria-hidden="true" />
                  Cancelar
                </Button>
              </div>

              <FileDrop onFiles={choose} compact title="Agrega más archivos" />
            </div>
          )}

          {phase === "saving" && (
            <div className="flex flex-col items-center gap-5 py-6 text-center sm:py-10">
              <DotsLoader size="lg" />
              <div className="space-y-1">
                <p className="font-display text-2xl font-semibold" aria-hidden="true">
                  {SAVING_HINTS[savingHint]}
                </p>
                <p className="text-sm text-muted-foreground">No cierres esta pestaña; con archivos grandes puede tardar unos segundos.</p>
              </div>
              <ProgressBar label={message} className="max-w-sm" />
              <ul className="w-full max-w-xl space-y-2" aria-label="Tus archivos">
                {state.entries.map((e) => (
                  <FileCard key={e.id} entry={e} summary={summaries.get(e.file.name)} />
                ))}
              </ul>
            </div>
          )}

          {phase === "failed" && state.error && (
            <div className="flex flex-col items-center gap-5 py-4 text-center sm:py-8">
              <span className="flex h-14 w-14 items-center justify-center rounded-2xl bg-danger-soft text-danger-strong">
                <FileWarning className="h-6 w-6" aria-hidden="true" />
              </span>
              <div className="max-w-lg space-y-1.5">
                <p className="font-display text-2xl font-semibold">{state.error.title}</p>
                <p className="text-[15px] text-muted-foreground">{state.error.description}</p>
              </div>
              <ul className="w-full max-w-xl space-y-2" aria-label="Tus archivos">
                {state.entries.map((e) => (
                  <FileCard key={e.id} entry={e} />
                ))}
              </ul>
              <div className="flex flex-col gap-2 sm:flex-row">
                {state.error.action !== "choose-file" && (
                  <Button onClick={() => dispatch({ type: "retry" })}>
                    <RotateCcw aria-hidden="true" />
                    Intentar de nuevo
                  </Button>
                )}
                <Button variant={state.error.action === "choose-file" ? "default" : "outline"} onClick={() => dispatch({ type: "reset" })}>
                  <Upload aria-hidden="true" />
                  Elegir otros archivos
                </Button>
              </div>
              {state.error.technical && (
                <details className="max-w-lg text-left text-xs text-muted-foreground">
                  <summary className="cursor-pointer select-none py-2 font-medium">Detalle técnico (para soporte)</summary>
                  <p className="break-words rounded-lg bg-muted px-3 py-2 font-mono">{state.error.technical}</p>
                </details>
              )}
            </div>
          )}

          {phase === "done" && state.result && (
            <IntakeResult
              state={state}
              tables={tables}
              ontology={ontology}
              onReset={() => dispatch({ type: "reset" })}
              onViewTable={onViewTable}
              onAsk={onAsk}
              onUndone={() => dispatch({ type: "reset" })}
            />
          )}
        </div>
      )}
    </div>
  )
}
