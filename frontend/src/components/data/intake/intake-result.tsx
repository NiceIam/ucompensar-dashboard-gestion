"use client"

import { useState } from "react"
import { toast } from "sonner"
import { CheckCircle2, CircleAlert, Eye, Undo2, Upload } from "lucide-react"
import { Button } from "@/components/ui/button"
import { ConfirmDialog } from "@/components/kit/confirm-dialog"
import { Notice } from "@/components/kit/notice"
import { FileCard } from "@/components/data/intake/file-card"
import { RolesDialog } from "@/components/data/intake/roles-dialog"
import { SheetCard } from "@/components/data/intake/sheet-card"
import { UnlocksPanel } from "@/components/data/intake/unlocks-panel"
import { useUndoIntake } from "@/hooks/use-intake"
import type { OrgTable } from "@/hooks/use-templates"
import { humanizeError } from "@/lib/errors"
import { formatNumber, pluralize } from "@/lib/format"
import { defaultDecision, readySheets } from "@/lib/intake/plan"
import type { IntakeState } from "@/lib/intake/state"
import type { CommitResult, Ontology } from "@/types/intake"

/** Qué se guardó, lo que entendí de cada hoja, qué ya puedo decirte y cómo deshacerlo. */
export function IntakeResult({
  state,
  tables,
  ontology,
  onReset,
  onViewTable,
  onAsk,
  onUndone,
}: {
  state: IntakeState
  tables: OrgTable[]
  ontology?: Ontology
  onReset: () => void
  onViewTable: (tableId: string) => void
  onAsk: (question: string) => void
  onUndone: () => void
}) {
  const result = state.result!
  const undo = useUndoIntake()
  const [confirmUndo, setConfirmUndo] = useState(false)
  const [fixing, setFixing] = useState<string | null>(null)
  const { totals } = result
  const saved = totals.created + totals.appended
  const undoable = result.results.filter((r) => r.undo.action !== "none")
  const failed = result.results.filter((r) => r.status === "error")
  const byKey = new Map(result.results.map((r) => [r.key, r]))
  const sheets = readySheets(state.proposal)
  const problems = state.entries.filter((e) => e.status === "problem")
  const fixTable = tables.find((t) => t.id === fixing) ?? null

  async function doUndo() {
    try {
      await undo.mutateAsync(undoable)
      setConfirmUndo(false)
      toast.success("Listo, deshicimos la carga", { description: "Tus archivos no cambiaron; puedes volver a subirlos cuando quieras." })
      onUndone()
    } catch (err) {
      const h = humanizeError(err, "delete")
      toast.error(h.title, { description: h.description })
    }
  }

  const headline =
    saved === 0
      ? totals.duplicates > 0
        ? "Esos datos ya estaban guardados."
        : "No pude guardar tus archivos."
      : `Listo. Guardé ${pluralize(totals.rows_inserted, "fila", "filas")} en ${pluralize(saved, "hoja", "hojas")}.`

  return (
    <div className="space-y-7">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-start">
        <span
          className={
            saved > 0
              ? "flex h-14 w-14 shrink-0 items-center justify-center rounded-2xl bg-success-soft text-success-strong"
              : "flex h-14 w-14 shrink-0 items-center justify-center rounded-2xl bg-warning-soft text-warning-strong"
          }
        >
          {saved > 0 ? <CheckCircle2 className="h-7 w-7" aria-hidden="true" /> : <CircleAlert className="h-7 w-7" aria-hidden="true" />}
        </span>
        <div className="space-y-1.5">
          <h3 className="font-display text-[28px] font-semibold leading-tight text-balance sm:text-[32px]">{headline}</h3>
          <p className="text-[15px] text-muted-foreground">
            {state.autoSaved && saved > 0
              ? "Todo se veía claro, así que lo guardé de una vez. Si algo no es como lo entendí, lo corriges abajo o deshaces la carga."
              : saved > 0
                ? "Quedó guardado como me lo confirmaste."
                : "Revisa lo que te cuento abajo."}
            {totals.duplicates > 0 && saved > 0 ? ` ${pluralize(totals.duplicates, "hoja ya estaba", "hojas ya estaban")} cargada${totals.duplicates === 1 ? "" : "s"}: no las dupliqué.` : ""}
          </p>
        </div>
      </div>

      {failed.length > 0 && (
        <div className="space-y-2">
          {failed.map((r) => (
            <Notice key={r.key} tone="danger" title={`No pude guardar «${r.sheet_name ?? r.file_name}»`}>
              {r.message}
            </Notice>
          ))}
        </div>
      )}

      {problems.length > 0 && (
        <ul className="space-y-2" aria-label="Archivos que no pude usar">
          {problems.map((e) => (
            <FileCard key={e.id} entry={e} />
          ))}
        </ul>
      )}

      {sheets.length > 0 && (
        <section aria-labelledby="understood-title" className="space-y-3">
          <h4 id="understood-title" className="font-display text-xl font-semibold">
            Esto es lo que entendí
          </h4>
          <div className="space-y-3">
            {sheets.map(({ file, sheet }) => {
              const r: CommitResult | undefined = byKey.get(sheet.key)
              return (
                <SheetCard
                  key={sheet.key}
                  fileName={file.file_name}
                  sheet={sheet}
                  edit={state.edits[sheet.key]}
                  decision={state.decisions[sheet.key] ?? defaultDecision(sheet)}
                  ontology={ontology}
                  mode="saved"
                  result={r}
                  onView={onViewTable}
                  onFix={(res) => setFixing(res.table_id)}
                />
              )
            })}
          </div>
        </section>
      )}

      {saved > 0 && <UnlocksPanel onAsk={onAsk} />}

      <div className="flex flex-col gap-2 border-t pt-5 sm:flex-row sm:items-center">
        {saved > 0 && result.results.find((r) => r.table_id) && (
          <Button onClick={() => onViewTable(result.results.find((r) => r.table_id)!.table_id!)}>
            <Eye aria-hidden="true" />
            Ver mis datos
          </Button>
        )}
        <Button variant="outline" onClick={onReset}>
          <Upload aria-hidden="true" />
          Subir más archivos
        </Button>
        <div className="flex-1" />
        {undoable.length > 0 && (
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
        description={`Quitaremos las ${formatNumber(totals.rows_inserted)} filas que acabamos de guardar${
          totals.created > 0 ? ` (y las hojas nuevas que se crearon)` : ""
        }. Lo que ya tenías antes no se toca y tus archivos no cambian.`}
        confirmLabel="Sí, deshacer"
        loading={undo.isPending}
        onConfirm={doUndo}
        icon={Undo2}
      />

      <RolesDialog table={fixTable} open={Boolean(fixTable)} onOpenChange={(o) => !o && setFixing(null)} />
    </div>
  )
}
