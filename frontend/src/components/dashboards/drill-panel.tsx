"use client"

import { useState } from "react"
import { Sparkles } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Sheet, SheetContent, SheetDescription, SheetTitle } from "@/components/ui/sheet"
import { DotsLoader } from "@/components/kit/dots"
import { ErrorState } from "@/components/kit/empty-state"
import { NativeSelect } from "@/components/kit/native-select"
import { Notice } from "@/components/kit/notice"
import { useDrill } from "@/hooks/use-dashboards"
import { useIsMobile } from "@/hooks/use-mobile"
import { barWidth, drillAnnouncement, drillRequestFor, formatByUnit, rowName, shareText, type PointRef } from "@/lib/drill"
import { humanizeError } from "@/lib/errors"
import { formatNumber, pluralize } from "@/lib/format"
import { cn } from "@/lib/utils"
import type { DashboardFilters, DrillResponse } from "@/types/dashboard-filters"

/** Qué dato tocó la persona. */
export interface DrillTarget {
  widgetId: string
  chartTitle: string
  point: PointRef
  /** Devuelve el foco al dato que se tocó (los dibujos de Recharts se recrean, así que no basta la referencia). */
  restoreFocus?: () => void
}

/** Guarda a qué dato volver al cerrar el panel: el botón enfocado ahora (dato del gráfico, fila de leyenda o de tabla). */
export function captureFocus(): (() => void) | undefined {
  const el = document.activeElement
  if (!(el instanceof HTMLElement || el instanceof SVGElement)) return undefined
  const chart = el.getAttribute("data-datum")
  const index = el.getAttribute("data-index")
  const label = el.getAttribute("aria-label")
  return () => {
    const next =
      chart && index !== null
        ? document.querySelector<HTMLElement | SVGElement>(`[data-datum="${chart}"][data-index="${index}"]`)
        : el.isConnected
          ? el
          : label
            ? Array.from(document.querySelectorAll<HTMLElement>("button[aria-label]")).find((b) => b.getAttribute("aria-label") === label)
            : null
    next?.focus()
  }
}

interface DrillPanelProps {
  dashboardId: string
  target: DrillTarget | null
  filters: DashboardFilters
  onClose: () => void
  /** Abre el chat con una pregunta ya escrita con este contexto. */
  onAsk: (question: string) => void
}

/** Cuerpo: la tabla de detalle con barras de proporción. */
export function DrillTable({ data }: { data: DrillResponse }) {
  const unit = data.measure.unit
  const by = data.by?.label ?? "Detalle"
  return (
    <div className="space-y-3">
      <div className="relative overflow-x-auto rounded-xl border">
        <table className="w-full table-fixed text-sm">
          <caption className="sr-only">{`${data.title}, por ${by.toLowerCase()}`}</caption>
          <thead className="bg-muted/70">
            <tr>
              <th scope="col" className="px-3 py-2 text-left font-semibold">{by}</th>
              <th scope="col" className="w-[6.5rem] px-3 py-2 text-right font-semibold">{data.measure.label}</th>
              {data.additive && <th scope="col" className="w-14 px-2 py-2 text-right font-semibold">Parte</th>}
            </tr>
          </thead>
          <tbody>
            {data.rows.map((row, i) => (
              <tr key={`${row.name}-${i}`} className="border-t align-top">
                <td className="min-w-0 px-3 py-2">
                  <span className="block break-words leading-snug" title={row.name}>{rowName(row)}</span>
                  <span className="mt-1.5 block h-1.5 overflow-hidden rounded-full bg-muted" aria-hidden="true">
                    <span className="block h-full rounded-full bg-[hsl(var(--chart-1))]" style={{ width: `${barWidth(row, data.rows, data.additive)}%` }} />
                  </span>
                </td>
                <td className="px-3 py-2 text-right font-semibold tabular">{formatByUnit(row.value, unit, true)}</td>
                {data.additive && <td className="px-2 py-2 text-right tabular text-muted-foreground">{shareText(row)}</td>}
              </tr>
            ))}
            {data.rest && data.rest.groups > 0 && (
              <tr className="border-t bg-muted/40 text-muted-foreground">
                <td className="px-3 py-2">{`Otros ${pluralize(data.rest.groups, "grupo", "grupos")}`}</td>
                <td className="px-3 py-2 text-right tabular">{data.rest.value === null ? "—" : formatByUnit(data.rest.value, unit, true)}</td>
                {data.additive && (
                  <td className="px-2 py-2 text-right tabular">
                    {data.total && data.rest.value !== null ? shareText({ name: "", value: 0, share: data.rest.value / data.total }) : ""}
                  </td>
                )}
              </tr>
            )}
          </tbody>
        </table>
      </div>
      {data.message && <p className="text-[13px] text-muted-foreground">{data.message}. Filtra o cambia «Ver por» para ver otras.</p>}
    </div>
  )
}

/**
 * Detalle de un dato tocado en un gráfico: panel lateral en pantallas grandes y hoja inferior casi a pantalla
 * completa en el celular. Cierra con Escape, la X o tocando fuera; el foco vuelve al dato que se tocó.
 */
export function DrillPanel({ dashboardId, target: openTarget, filters, onClose, onAsk }: DrillPanelProps) {
  const isMobile = useIsMobile()
  const [by, setBy] = useState<string | undefined>(undefined)
  // Al cerrar se conserva el último dato mientras dura la animación (el contenido no parpadea).
  const [target, setTarget] = useState(openTarget)
  if (openTarget && openTarget !== target) {
    setTarget(openTarget)
    // Otro dato = otra mirada: «Ver por» vuelve a la elección automática.
    setBy(undefined)
  }
  const request = target ? drillRequestFor(target.point, filters, by) : null
  const query = useDrill(dashboardId, target?.widgetId ?? null, request)
  const data = query.data
  const stale = query.isPlaceholderData

  return (
    <Sheet open={openTarget !== null} onOpenChange={(open) => !open && onClose()}>
      <SheetContent
        side={isMobile ? "bottom" : "right"}
        aria-describedby="drill-description"
        onCloseAutoFocus={(e) => {
          // Radix devolvería el foco a un nodo que Recharts ya recreó: se devuelve al dato por su posición.
          e.preventDefault()
          target?.restoreFocus?.()
        }}
        className={cn(
          "flex flex-col gap-0 p-0",
          isMobile ? "h-[92dvh] rounded-t-2xl" : "w-full sm:max-w-lg"
        )}
      >
        <div className="space-y-1 border-b px-5 pb-4 pt-5 pr-16">
          <p className="text-xs font-semibold uppercase tracking-[0.08em] text-primary">{target?.chartTitle ?? "Detalle"}</p>
          <SheetTitle className="font-display text-[22px] font-semibold leading-snug text-balance">
            {data && !stale ? data.title : target ? `Detalle de ${target.point.name}` : "Detalle"}
          </SheetTitle>
          <SheetDescription id="drill-description" className="sr-only">
            Detalle de lo que suma este dato del gráfico, con la proporción de cada parte.
          </SheetDescription>
          {data && !stale && data.total !== null && (
            <p className="flex flex-wrap items-baseline gap-x-2 pt-1">
              <span className="font-display text-[32px] font-semibold leading-none tabular">{formatByUnit(data.total, data.measure.unit)}</span>
              <span className="text-sm text-muted-foreground">
                {data.measure.label} · {pluralize(data.records, "registro", "registros")}
              </span>
            </p>
          )}
        </div>

        <div className={cn("min-h-0 flex-1 space-y-4 overflow-y-auto px-5 py-4", stale && "opacity-60 transition-opacity")} aria-busy={query.isFetching}>
          {query.isError && !data ? (
            <ErrorState error={humanizeError(query.error, "load")} onRetry={() => void query.refetch()} retrying={query.isFetching} compact />
          ) : !data ? (
            <div className="flex flex-col items-center gap-3 py-12 text-center" role="status" aria-live="polite">
              <DotsLoader size="lg" />
              <p className="text-sm text-muted-foreground">Buscando el detalle…</p>
            </div>
          ) : (
            <>
              <p className="sr-only" role="status" aria-live="polite">{stale ? "" : drillAnnouncement(data)}</p>
              {data.filters && (
                <p className="text-[13px] text-muted-foreground">Con los filtros que tienes activos en el tablero.</p>
              )}
              {data.dimensions.length > 0 && (
                <div className="flex items-center gap-3">
                  <label htmlFor="drill-by" className="shrink-0 text-sm font-semibold">Ver por</label>
                  <NativeSelect
                    id="drill-by"
                    label="Ver por"
                    className="min-w-0 flex-1"
                    value={data.by?.by ?? data.dimensions[0].by}
                    onChange={(value) => setBy(value)}
                    options={data.dimensions.map((d) => ({ value: d.by, label: d.label }))}
                  />
                </div>
              )}
              {data.empty ? (
                <Notice tone="info" title="No hay datos para esto">
                  Con los filtros que tienes activos no quedan registros. Quita algún filtro del tablero para ver más.
                </Notice>
              ) : data.rows.length === 0 ? (
                <Notice tone="info" title="No hay otra forma de desglosarlo">
                  Esta hoja no tiene otra columna por la que separar este dato. El total de arriba ({formatNumber(data.records, 0)} registros) es todo el detalle.
                </Notice>
              ) : (
                <DrillTable data={data} />
              )}
              {data.notes.length > 0 && (
                <ul className="space-y-1 text-xs text-muted-foreground">
                  {data.notes.map((n) => (
                    <li key={n}>{n}</li>
                  ))}
                </ul>
              )}
              {query.isError && <p className="text-sm text-danger-strong">No pudimos actualizar el detalle. Intenta de nuevo.</p>}
            </>
          )}
        </div>

        <div className="border-t bg-card px-5 py-4 pb-[max(1rem,env(safe-area-inset-bottom))]">
          <Button
            variant="soft"
            className="w-full"
            disabled={!data}
            onClick={() => data && onAsk(data.question ?? data.title)}
          >
            <Sparkles aria-hidden="true" />
            Preguntar al asistente sobre esto
          </Button>
        </div>
      </SheetContent>
    </Sheet>
  )
}
