"use client"

import Link from "next/link"
import { useRef, useState } from "react"
import { toast } from "sonner"
import { ArrowRight, ArrowRightLeft, Check, Minus, Pencil, Plus, SquarePen, Undo2, type LucideIcon } from "lucide-react"
import { Button } from "@/components/ui/button"
import { ConfirmDialog } from "@/components/kit/confirm-dialog"
import { useDashboards, useUndoDashboardEdit } from "@/hooks/use-dashboards"
import { dashboardHref } from "@/lib/dashboard-block"
import { editHeadline, newerEditsInfo, newerEditsMessage, type ChatDashboardEdit } from "@/lib/dashboard-edit-block"
import { ApiError, humanizeError } from "@/lib/errors"
import { pluralize } from "@/lib/format"
import { cn } from "@/lib/utils"

/** Una línea de «qué cambió»: icono + palabra + título. Nunca solo color. */
interface ChangeRow {
  key: string
  icon: LucideIcon
  verb: string
  text: string
  muted?: boolean
}

function changeRows(edit: ChatDashboardEdit): ChangeRow[] {
  const rows: ChangeRow[] = []
  if (edit.renamed) {
    rows.push({ key: "renamed", icon: Pencil, verb: "Cambié el nombre", text: `de «${edit.renamed.from}» a «${edit.renamed.to}»` })
  }
  edit.added.forEach((t, i) => rows.push({ key: `add-${i}`, icon: Plus, verb: "Agregué", text: `«${t}»` }))
  edit.replaced.forEach((p, i) => rows.push({ key: `rep-${i}`, icon: ArrowRightLeft, verb: "Reemplacé", text: `«${p.from}» por «${p.to}»` }))
  edit.removed.forEach((t, i) => rows.push({ key: `rem-${i}`, icon: Minus, verb: "Quité", text: `«${t}»` }))
  edit.unchanged.forEach((t, i) => rows.push({ key: `same-${i}`, icon: Check, verb: "Ya estaba", text: `«${t}»`, muted: true }))
  return rows
}

type CardState = "active" | "undone" | "stale"

/**
 * Al cerrar el diálogo, Radix (AlertDialog) devuelve el foco al «Trigger»; como aquí el diálogo es controlado y
 * no tiene Trigger, el foco se perdería en el <body>. Mientras el diálogo sigue en pantalla (animación de
 * salida) su trampa de foco deshace cualquier intento, así que se espera a que desaparezca para devolverlo.
 */
function focusSoon(getEl: () => HTMLElement | null) {
  let tries = 0
  const tick = () => {
    if (document.querySelector('[role="alertdialog"]') && tries++ < 40) {
      window.setTimeout(tick, 25)
      return
    }
    window.setTimeout(() => getEl()?.focus(), 40)
  }
  window.setTimeout(tick, 30)
}

/**
 * Tarjeta de un tablero que el asistente acaba de EDITAR (bloque ```dashboard_edit del servidor). Dice qué
 * cambió, ofrece abrirlo y «Deshacer» (con confirmación). Estados: normal, deshaciendo, deshecho, error (la
 * tarjeta sigue usable), ediciones más recientes (segunda confirmación), cambio que ya no se puede deshacer,
 * tablero eliminado y sin cambios.
 *
 * El bloque ya vino validado de `parseDashboardEditBlock`; el enlace solo se arma con un UUID válido y todo
 * texto se pinta como texto de React.
 */
export function DashboardEditCard({ edit }: { edit: ChatDashboardEdit }) {
  const href = dashboardHref(edit.id)
  const { data: dashboards, isFetching } = useDashboards()
  const undoEdit = useUndoDashboardEdit()
  const [state, setState] = useState<CardState>("active")
  const [restoredName, setRestoredName] = useState<string | null>(null)
  const [confirming, setConfirming] = useState(false)
  /** null: confirmación normal. Con valor: el servidor avisó de ediciones más recientes y se pide confirmar otra vez. */
  const [newer, setNewer] = useState<{ count: number | null } | null>(null)
  const undoButton = useRef<HTMLButtonElement>(null)
  const actions = useRef<HTMLDivElement>(null)
  const openLinkEl = () => actions.current?.querySelector<HTMLElement>("a") ?? null

  if (!href) return null

  // El mensaje queda en el historial: si el tablero ya se borró (aquí o en otra pantalla), no se ofrece abrirlo.
  const gone = !isFetching && Array.isArray(dashboards) && !dashboards.some((d) => d.dashboard_id === edit.id)
  if (gone) {
    return (
      <div className="my-2 break-words rounded-xl border border-dashed px-3 py-2.5 text-[13px] text-muted-foreground">
        Ya no existe el tablero «{edit.name}».
      </div>
    )
  }

  const canUndo = state === "active" && !edit.noop && edit.version !== null
  const rows = changeRows(edit)
  const shownName = state === "undone" && restoredName ? restoredName : edit.name

  async function undo(includeNewer: boolean) {
    if (!edit.version) return
    try {
      const result = await undoEdit.mutateAsync({ id: edit.id, version: edit.version, includeNewer })
      const name = typeof result?.name === "string" && result.name.trim() ? result.name.trim().slice(0, 120) : edit.name
      setRestoredName(name)
      setState("undone")
      setConfirming(false)
      setNewer(null)
      toast.success(`Restauramos «${name}»`)
      focusSoon(openLinkEl)
      return
    } catch (err) {
      const more = newerEditsInfo(err)
      if (more) {
        // El diálogo sigue abierto y cambia de contenido: la persona decide con la información completa.
        setNewer(more)
        return
      }
      setConfirming(false)
      setNewer(null)
      if (err instanceof ApiError && err.status === 404) {
        setState("stale")
        focusSoon(openLinkEl)
        return
      }
      const h = humanizeError(err, "save")
      toast.error(h.title, { description: h.description })
      focusSoon(() => undoButton.current)
    }
  }

  const label = state === "undone" ? "Cambio deshecho" : state === "stale" ? "Cambio guardado" : edit.noop ? "Sin cambios" : "Tablero editado"
  const headline =
    state === "undone"
      ? `Deshiciste este cambio en «${shownName}».`
      : state === "stale"
        ? "Este cambio ya no se puede deshacer."
        : editHeadline(edit)
  const dimmed = state !== "active"

  return (
    <section
      aria-label={`Tablero editado: ${edit.name}`}
      className={cn("my-2 rounded-xl border p-3", dimmed ? "border-dashed bg-muted/50" : "bg-primary-soft/50")}
    >
      <div className="flex items-start gap-2.5">
        <span
          className={cn(
            "flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-card shadow-card",
            dimmed ? "text-muted-foreground" : "text-primary-strong"
          )}
        >
          <SquarePen className="h-[18px] w-[18px]" aria-hidden="true" />
        </span>
        <div className="min-w-0 flex-1">
          <p className={cn("text-[12px] font-semibold uppercase tracking-[0.06em]", dimmed ? "text-muted-foreground" : "text-primary-strong")}>
            {label}
          </p>
          <p className="break-words font-display text-base font-semibold leading-snug">{shownName}</p>
          {/* Región viva siempre montada: al cambiar de estado, el lector de pantalla anuncia la frase nueva. */}
          <div aria-live="polite" aria-atomic="true">
            <p className="mt-0.5 break-words text-[13px] leading-snug text-muted-foreground">{headline}</p>
          </div>
        </div>
      </div>

      {state === "active" && rows.length > 0 && (
        <ul aria-label="Qué cambió" className="mt-2.5 space-y-1.5 rounded-lg bg-card/70 px-2.5 py-2">
          {rows.map(({ key, icon: Icon, verb, text, muted }) => (
            <li key={key} className="flex items-start gap-2 text-[13px] leading-snug">
              <Icon className={cn("mt-px h-4 w-4 shrink-0", muted ? "text-muted-foreground" : "text-primary-strong")} aria-hidden="true" />
              <span className={cn("min-w-0 break-words", muted && "text-muted-foreground")}>
                <span className="font-semibold">{verb}</span> {text}
              </span>
            </li>
          ))}
        </ul>
      )}

      {state === "active" && !edit.noop && edit.widgets !== null && (
        <p className="mt-2 text-[13px] leading-snug text-muted-foreground">
          Ahora tiene {pluralize(edit.widgets, "gráfico o cifra", "gráficos y cifras")}.
        </p>
      )}

      <div ref={actions} className="mt-3 flex flex-wrap items-center gap-2">
        <Button asChild size="sm" variant={dimmed || edit.noop ? "outline" : "default"}>
          <Link href={href}>
            Abrir tablero
            <ArrowRight aria-hidden="true" />
          </Link>
        </Button>
        {canUndo && (
          <Button ref={undoButton} variant="outline" size="sm" onClick={() => setConfirming(true)}>
            <Undo2 aria-hidden="true" />
            Deshacer
          </Button>
        )}
      </div>

      {canUndo && (
        // El diálogo va en un portal, pero los eventos de React suben por el árbol de componentes: sin esto,
        // Escape (que lo cierra) también cerraría el panel del chat que lo contiene.
        <div className="contents" onKeyDown={(e) => e.key === "Escape" && e.stopPropagation()}>
          <ConfirmDialog
            open={confirming}
            onOpenChange={(next) => {
              setConfirming(next)
              if (!next) {
                setNewer(null)
                focusSoon(() => undoButton.current)
              }
            }}
            tone={newer ? "danger" : "primary"}
            icon={newer ? undefined : Undo2}
            title={newer ? "¿Deshacer también los cambios más recientes?" : `¿Deshacer el cambio en «${edit.name}»?`}
            description={newer ? newerEditsMessage(newer.count) : "El tablero vuelve a como estaba antes."}
            confirmLabel={newer ? "Sí, deshacer todo" : "Sí, deshacer"}
            loading={undoEdit.isPending}
            onConfirm={() => undo(newer !== null)}
          />
        </div>
      )}
    </section>
  )
}
