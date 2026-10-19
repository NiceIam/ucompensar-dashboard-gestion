"use client"

import Link from "next/link"
import { useState } from "react"
import { toast } from "sonner"
import { ArrowRight, LayoutDashboard, Trash2, Undo2 } from "lucide-react"
import { Button } from "@/components/ui/button"
import { ConfirmDialog } from "@/components/kit/confirm-dialog"
import { useDashboards, useDeleteDashboard } from "@/hooks/use-dashboards"
import { dashboardHref, type ChatDashboard } from "@/lib/dashboard-block"
import { humanizeError } from "@/lib/errors"
import { pluralize } from "@/lib/format"

/**
 * Tarjeta de un tablero que el asistente acaba de crear (bloque ```dashboard del servidor). Ofrece abrirlo y
 * deshacerlo (borrado lógico existente). El enlace solo se arma con un UUID válido: el bloque ya vino validado
 * de `parseDashboardBlock`, y aquí se vuelve a comprobar al construir el `href`.
 */
export function DashboardCard({ dashboard }: { dashboard: ChatDashboard }) {
  const href = dashboardHref(dashboard.id)
  const { data: dashboards, isFetching } = useDashboards()
  const remove = useDeleteDashboard()
  const [removed, setRemoved] = useState(false)
  const [confirming, setConfirming] = useState(false)

  if (!href) return null

  // El mensaje queda en el historial: si el tablero ya se borró (aquí o en otra pantalla), no se ofrece abrirlo.
  const gone = removed || (!isFetching && Array.isArray(dashboards) && !dashboards.some((d) => d.dashboard_id === dashboard.id))
  const graphics = dashboard.widgets === null ? null : pluralize(dashboard.widgets, "gráfico o cifra", "gráficos y cifras")

  async function undo() {
    try {
      await remove.mutateAsync(dashboard.id)
      setRemoved(true)
      setConfirming(false)
      toast.success(`Eliminamos «${dashboard.name}»`)
    } catch (err) {
      const h = humanizeError(err, "delete")
      toast.error(h.title, { description: h.description })
    }
  }

  if (gone) {
    return (
      <div className="my-2 rounded-xl border border-dashed px-3 py-2.5 text-[13px] text-muted-foreground">
        {removed ? "Eliminaste" : "Ya no existe"} el tablero «{dashboard.name}».
      </div>
    )
  }

  return (
    <section aria-label={`Tablero ${dashboard.existing ? "existente" : "creado"}: ${dashboard.name}`} className="my-2 rounded-xl border bg-primary-soft/50 p-3">
      <div className="flex items-start gap-2.5">
        <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-card text-primary-strong shadow-card">
          <LayoutDashboard className="h-[18px] w-[18px]" aria-hidden="true" />
        </span>
        <div className="min-w-0 flex-1">
          <p className="text-[12px] font-semibold uppercase tracking-[0.06em] text-primary-strong">
            {dashboard.existing ? "Ya tenías este tablero" : "Tablero creado"}
          </p>
          <p className="break-words font-display text-base font-semibold leading-snug">{dashboard.name}</p>
          <p className="mt-0.5 text-[13px] leading-snug text-muted-foreground">
            {graphics ? `${graphics}. ` : ""}Los datos se actualizan cada vez que lo abres.
          </p>
        </div>
      </div>
      <div className="mt-3 flex flex-wrap items-center gap-2">
        <Button asChild size="sm">
          <Link href={href}>
            Abrir tablero
            <ArrowRight aria-hidden="true" />
          </Link>
        </Button>
        {dashboard.existing ? (
          <Button variant="outline" size="sm" onClick={() => setConfirming(true)}>
            <Trash2 aria-hidden="true" />
            Eliminar
          </Button>
        ) : (
          <Button variant="outline" size="sm" onClick={() => void undo()} loading={remove.isPending} loadingText="Deshaciendo…">
            <Undo2 aria-hidden="true" />
            Deshacer
          </Button>
        )}
      </div>
      <ConfirmDialog
        open={confirming}
        onOpenChange={setConfirming}
        title={`¿Eliminar «${dashboard.name}»?`}
        description="Se borra el tablero. Tus datos no se tocan."
        confirmLabel="Sí, eliminar"
        loading={remove.isPending}
        onConfirm={undo}
      />
    </section>
  )
}
