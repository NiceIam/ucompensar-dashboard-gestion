"use client"

import Link from "next/link"
import { useParams } from "next/navigation"
import { useEffect, useState } from "react"
import { toast } from "sonner"
import {
  ArrowLeft,
  CircleDollarSign,
  Code2,
  Hash,
  MoreHorizontal,
  RefreshCw,
  ShoppingCart,
  Sparkles,
  Users,
  type LucideIcon,
} from "lucide-react"
import { Button } from "@/components/ui/button"
import { Skeleton } from "@/components/ui/skeleton"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import { ChartRenderer } from "@/components/charts/chart-renderer"
import { EmptyState, ErrorState } from "@/components/kit/empty-state"
import { MetricTile } from "@/components/kit/metric-tile"
import { ChartSkeleton, MetricRowSkeleton } from "@/components/kit/skeletons"
import { useDashboardExecute, useDashboardMeta, useDownloadDashboardScript } from "@/hooks/use-dashboards"
import { usePageTitle } from "@/hooks/use-page-title"
import { useChat } from "@/providers/chat-provider"
import { isMoneyLike } from "@/lib/data-vocabulary"
import { humanizeError } from "@/lib/errors"
import { formatCompact, formatMoney, formatNumber } from "@/lib/format"
import type { WidgetConfig } from "@/types/api"

/** Icono del KPI según la pista del backend ("dollar", "cart", "users"…). */
function kpiIcon(hint: string | undefined, label: string): LucideIcon {
  const h = `${hint ?? ""} ${label}`.toLowerCase()
  if (/dollar|money|cash|peso|venta|ingreso|valor|total/.test(h)) return CircleDollarSign
  if (/cart|pedido|orden|compra/.test(h)) return ShoppingCart
  if (/user|cliente|persona/.test(h)) return Users
  return Hash
}

function kpiValue(value: number, hint: string | undefined, label: string): string {
  if (!Number.isFinite(value)) return "—"
  const money = /dollar|money|cash|peso|receipt/.test(hint ?? "") || isMoneyLike(label)
  if (money) return Math.abs(value) >= 1_000_000 ? formatMoney(value, { compact: true }) : formatMoney(value)
  return Math.abs(value) >= 100_000 ? formatCompact(value) : formatNumber(value)
}

function useSecondsAgo(timestamp: number | undefined) {
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => {
    const id = window.setInterval(() => setNow(Date.now()), 15_000)
    return () => window.clearInterval(id)
  }, [])
  if (!timestamp) return null
  const s = Math.max(0, Math.round((now - timestamp) / 1000))
  if (s < 60) return "hace un momento"
  const m = Math.round(s / 60)
  return `hace ${m} ${m === 1 ? "minuto" : "minutos"}`
}

export default function DashboardDetailPage() {
  const params = useParams<{ id: string }>()
  const id = params.id
  const { ask } = useChat()

  const { data: meta, isLoading: metaLoading } = useDashboardMeta(id)
  const { data, isLoading, isFetching, isError, error, updatedAt, refetch } = useDashboardExecute(id)
  const downloadMutation = useDownloadDashboardScript()
  const ago = useSecondsAgo(updatedAt || undefined)
  usePageTitle(meta?.name ?? "Tablero")

  // Los gráficos del script vienen como { type, title, data, x, y, color }: se adaptan al
  // contrato WidgetConfig que entiende ChartRenderer (sin cambiar la API).
  const widgets: WidgetConfig[] = (data?.charts ?? []).map((chart, i) => ({
    id: `${id}-chart-${i}`,
    dashboard_id: id,
    title: chart.title,
    chart_type: chart.type,
    data_key: chart.y || "value",
    x_key: chart.x || "name",
    y_keys: [chart.y || "value"],
    color: chart.color,
    width: 2,
    height: 1,
    position: i,
    data: chart.data,
    created_at: new Date().toISOString(),
  }))

  async function download() {
    try {
      await downloadMutation.mutateAsync({ id })
    } catch (err) {
      const h = humanizeError(err, "download")
      toast.error(h.title, { description: h.description })
    }
  }

  return (
    <div className="space-y-8">
      <div className="space-y-4">
        <Link
          href="/dashboards"
          className="inline-flex min-h-11 items-center gap-1.5 rounded-lg pr-2 text-sm font-semibold text-muted-foreground transition hover:text-foreground"
        >
          <ArrowLeft className="h-4 w-4" aria-hidden="true" />
          Tableros
        </Link>
        <header className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
          <div className="min-w-0 space-y-2">
            {metaLoading ? (
              <Skeleton className="h-10 w-72 max-w-full" />
            ) : (
              <h1 className="font-display text-[30px] font-semibold leading-tight text-balance sm:text-[36px]">{meta?.name ?? "Tablero"}</h1>
            )}
            <p className="max-w-2xl text-[15px] text-muted-foreground">
              {meta?.description?.trim() || "Gráficos calculados con tus datos de este momento."}
              {ago && !isFetching && <span className="text-muted-foreground/80"> · Actualizado {ago}.</span>}
              {isFetching && !isLoading && <span className="text-muted-foreground/80"> · Actualizando…</span>}
            </p>
          </div>
          <div className="flex shrink-0 items-center gap-2">
            <Button variant="outline" onClick={() => void refetch()} disabled={isFetching}>
              <RefreshCw className={isFetching ? "animate-spin" : ""} aria-hidden="true" />
              Actualizar
            </Button>
            <Button variant="soft" onClick={() => ask(`Cuéntame lo más importante del tablero «${meta?.name ?? "este tablero"}»`)}>
              <Sparkles aria-hidden="true" />
              Pregúntale
            </Button>
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button variant="ghost" size="icon" aria-label="Más opciones del tablero">
                  <MoreHorizontal aria-hidden="true" />
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end" className="w-64">
                <DropdownMenuItem onClick={() => void download()} className="cursor-pointer">
                  <Code2 className="h-4 w-4" aria-hidden="true" />
                  Descargar su código (avanzado)
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          </div>
        </header>
      </div>

      {isLoading ? (
        <div className="space-y-5" aria-busy="true">
          <MetricRowSkeleton count={3} />
          <div className="auto-grid gap-5 [--auto-grid-min:22rem]">
            <ChartSkeleton />
            <ChartSkeleton />
          </div>
        </div>
      ) : isError ? (
        <div className="surface">
          <ErrorState error={humanizeError(error, "load")} onRetry={() => void refetch()} retrying={isFetching} />
        </div>
      ) : (
        <div className={isFetching ? "opacity-70 transition-opacity" : "transition-opacity"}>
          {data?.kpis && data.kpis.length > 0 && (
            <section aria-label="Cifras principales" className="auto-grid mb-6 gap-4 [--auto-grid-min:13rem]">
              {data.kpis.map((kpi, i) => (
                <MetricTile
                  key={`${kpi.label}-${i}`}
                  label={kpi.label}
                  value={kpiValue(Number(kpi.value), kpi.icon, kpi.label)}
                  icon={kpiIcon(kpi.icon, kpi.label)}
                  tone={i === 0 ? "primary" : i === 1 ? "highlight" : "info"}
                />
              ))}
            </section>
          )}

          {widgets.length === 0 ? (
            <div className="surface">
              <EmptyState
                illustration="chart"
                title="Este tablero todavía no tiene gráficos"
                description="Puede pasar cuando aún no hay datos con fechas o cifras. Sube un archivo y vuelve a abrirlo."
                actions={
                  <Button asChild>
                    <Link href="/data">Ir a Mis datos</Link>
                  </Button>
                }
              />
            </div>
          ) : (
            <section aria-label="Gráficos" className="auto-grid gap-5 [--auto-grid-min:22rem]">
              {widgets.map((widget) => (
                <ChartRenderer key={widget.id} widget={widget} />
              ))}
            </section>
          )}
        </div>
      )}
    </div>
  )
}
