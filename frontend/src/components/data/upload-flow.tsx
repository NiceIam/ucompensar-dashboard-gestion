"use client"

import { useCallback, useEffect, useReducer, useRef, useState } from "react"
import { FileJson, FileSpreadsheet, FileText, FileWarning, RotateCcw, Upload, X } from "lucide-react"
import { Button } from "@/components/ui/button"
import { FileDrop } from "@/components/kit/file-drop"
import { DotsLoader } from "@/components/kit/dots"
import { Notice } from "@/components/kit/notice"
import { ProgressBar } from "@/components/kit/progress-bar"
import { Steps } from "@/components/kit/steps"
import { UploadReview } from "@/components/data/upload-review"
import { UploadResult } from "@/components/data/upload-result"
import { analyzeFile, smartUpload, useInvalidateData } from "@/hooks/use-data"
import type { OrgTable } from "@/hooks/use-templates"
import { humanizeError } from "@/lib/errors"
import { formatFileSize } from "@/lib/format"
import { assessUpload } from "@/lib/upload/assess"
import { initialUploadState, phaseMessage, stepIndex, stepsFor, uploadReducer } from "@/lib/upload/flow"
import { looksLikeZip, validateLocalFile, withExplicitType, type LocalFileKind } from "@/lib/upload/local-file"
import { readLocalFile } from "@/lib/upload/read-local"
import { cn } from "@/lib/utils"

const KIND_ICON: Record<LocalFileKind, typeof FileText> = {
  xlsx: FileSpreadsheet,
  csv: FileText,
  json: FileJson,
}

/** Lo que el servidor puede tardar: mensajes que cambian para que la espera no se sienta muerta. */
const SAVING_HINTS = ["Guardando tus datos…", "Organizando las columnas…", "Ya casi…"]

function FileChip({ file, kind }: { file: File; kind: LocalFileKind | null }) {
  const Icon = kind ? KIND_ICON[kind] : FileText
  return (
    <div className="flex min-w-0 items-center gap-3 rounded-xl border bg-card px-3.5 py-2.5">
      <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-primary-soft text-primary-strong">
        <Icon className="h-5 w-5" aria-hidden="true" />
      </span>
      <div className="min-w-0">
        <p className="truncate text-sm font-semibold" title={file.name}>
          {file.name}
        </p>
        <p className="text-xs text-muted-foreground">{formatFileSize(file.size)}</p>
      </div>
    </div>
  )
}

/**
 * Flujo de cargue completo: elegir → leer → entender → (revisar) → guardar → listo.
 * `hero`: zona de arrastre grande (cuando aún no hay datos); si no, compacta.
 */
export function UploadFlow({
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
  const [state, dispatch] = useReducer(uploadReducer, initialUploadState)
  const invalidate = useInvalidateData()
  const started = useRef<string | null>(null)
  const tablesRef = useRef(tables)
  tablesRef.current = tables
  const containerRef = useRef<HTMLDivElement>(null)
  const [savingHint, setSavingHint] = useState(0)

  useEffect(() => {
    if (state.phase !== "saving") return
    setSavingHint(0)
    const id = window.setInterval(() => setSavingHint((h) => Math.min(h + 1, SAVING_HINTS.length - 1)), 2600)
    return () => window.clearInterval(id)
  }, [state.phase])

  const choose = useCallback((file: File) => {
    const check = validateLocalFile(file)
    if (!check.ok) {
      dispatch({ type: "reject", file, problem: { title: check.title, description: check.description } })
      return
    }
    dispatch({ type: "select", file, kind: check.kind })
  }, [])

  // Cada fase con trabajo asíncrono se ejecuta una sola vez por intento (también en modo estricto).
  useEffect(() => {
    const key = `${state.run}:${state.phase}`
    if (started.current === key) return
    const { file, kind, run } = state
    if (!file || !kind) return

    if (state.phase === "reading") {
      started.current = key
      void (async () => {
        if (kind === "xlsx" && !(await looksLikeZip(file))) {
          dispatch({
            type: "reject",
            file,
            problem: {
              title: "Este archivo dice ser Excel, pero por dentro no lo es",
              description: "Puede que le hayan cambiado la extensión. Ábrelo en Excel y guárdalo como Libro de Excel (.xlsx).",
            },
          })
          return
        }
        const local = await readLocalFile(file, kind)
        dispatch({ type: "local-read", run, local })
      })()
    }

    if (state.phase === "understanding") {
      started.current = key
      void (async () => {
        try {
          const analysis = await analyzeFile(withExplicitType(file, kind))
          const assessment = assessUpload({
            analysis,
            tables: tablesRef.current.map((t) => ({ id: t.id, table_name: t.table_name, display_name: t.display_name, row_count: t.row_count })),
            local: state.local,
            kind,
          })
          dispatch({ type: "analyzed", run, analysis, assessment })
        } catch (err) {
          dispatch({ type: "fail", run, at: "understanding", error: humanizeError(err, "analyze") })
        }
      })()
    }

    if (state.phase === "saving") {
      started.current = key
      void (async () => {
        try {
          const result = await smartUpload(withExplicitType(file, kind))
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
      containerRef.current?.scrollIntoView({ behavior: "smooth", block: "start" })
    }
  }, [state.phase])

  const busy = state.phase === "reading" || state.phase === "understanding" || state.phase === "saving"
  const showDrop = state.phase === "idle" || state.phase === "rejected"
  const message = phaseMessage(state)

  return (
    <div ref={containerRef} className="scroll-mt-24">
      <p className="sr-only" role="status" aria-live="polite">
        {message}
      </p>

      {showDrop && (
        <div className="space-y-3">
          {state.phase === "rejected" && state.problem && (
            <Notice tone="danger" title={state.problem.title} onDismiss={() => dispatch({ type: "reset" })}>
              {state.problem.description}
            </Notice>
          )}
          <FileDrop onFile={choose} compact={!hero} />
        </div>
      )}

      {!showDrop && (
        <div
          className={cn(
            "surface overflow-hidden rounded-3xl p-5 sm:p-8",
            state.phase === "done" && "border-success/30"
          )}
        >
          {state.phase !== "done" && (
            <div className="mb-6 space-y-5">
              <Steps steps={stepsFor(state)} current={stepIndex(state)} failed={state.phase === "failed"} />
            </div>
          )}

          {busy && state.file && (
            <div className="flex flex-col items-center gap-5 py-6 text-center sm:py-10">
              <DotsLoader size="lg" />
              <div className="space-y-1">
                <p className="font-display text-2xl font-semibold" aria-hidden="true">
                  {state.phase === "saving" ? SAVING_HINTS[savingHint] : message}
                </p>
                <p className="text-sm text-muted-foreground">
                  {state.phase === "saving"
                    ? "No cierres esta pestaña; con archivos grandes puede tardar unos segundos."
                    : state.phase === "understanding"
                      ? "Revisamos qué hay en cada columna. Todavía no se guarda nada."
                      : "Esto toma un instante."}
                </p>
              </div>
              <ProgressBar label={message} className="max-w-sm" />
              <div className="flex w-full max-w-sm flex-col items-stretch gap-3">
                <FileChip file={state.file} kind={state.kind} />
                {state.phase !== "saving" && (
                  <Button variant="ghost" onClick={() => dispatch({ type: "reset" })}>
                    <X aria-hidden="true" />
                    Cancelar
                  </Button>
                )}
              </div>
            </div>
          )}

          {state.phase === "review" && state.file && state.assessment && (
            <UploadReview
              file={state.file}
              analysis={state.analysis}
              assessment={state.assessment}
              local={state.local}
              onConfirm={() => dispatch({ type: "confirm" })}
              onCancel={() => dispatch({ type: "reset" })}
            />
          )}

          {state.phase === "failed" && state.file && state.error && (
            <div className="flex flex-col items-center gap-5 py-4 text-center sm:py-8">
              <span className="flex h-14 w-14 items-center justify-center rounded-2xl bg-danger-soft text-danger-strong">
                <FileWarning className="h-6 w-6" aria-hidden="true" />
              </span>
              <div className="max-w-lg space-y-1.5">
                <p className="font-display text-2xl font-semibold">{state.error.title}</p>
                <p className="text-[15px] text-muted-foreground">{state.error.description}</p>
              </div>
              <FileChip file={state.file} kind={state.kind} />
              <div className="flex flex-col gap-2 sm:flex-row">
                {state.error.action !== "choose-file" && (
                  <Button onClick={() => dispatch({ type: "retry" })}>
                    <RotateCcw aria-hidden="true" />
                    Intentar de nuevo
                  </Button>
                )}
                <Button variant={state.error.action === "choose-file" ? "default" : "outline"} onClick={() => dispatch({ type: "reset" })}>
                  <Upload aria-hidden="true" />
                  Elegir otro archivo
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

          {state.phase === "done" && state.file && state.result && (
            <UploadResult
              file={state.file}
              analysis={state.analysis}
              assessment={state.assessment}
              local={state.local}
              result={state.result}
              autoSaved={state.autoSaved}
              tables={tables}
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
