"use client"

import Link from "next/link"
import { usePathname, useParams, useRouter, useSearchParams } from "next/navigation"
import { Suspense, useCallback, useEffect, useMemo, useState } from "react"
import {
  ArrowLeft,
  CircleDollarSign,
  Database,
  Hash,
  RefreshCw,
  ShoppingCart,
  Sparkles,
  TrendingUp,
  Users,
  type LucideIcon,
} from "lucide-react"
import { Button } from "@/components/ui/button"
import { Skeleton } from "@/components/ui/skeleton"
import { ChartRenderer } from "@/components/charts/chart-renderer"
import { EditWithAssistantButton } from "@/components/dashboards/edit-with-assistant-button"
import { DrillPanel, captureFocus, type DrillTarget } from "@/components/dashboards/drill-panel"
import { FilterBar } from "@/components/dashboards/filter-bar"
import { EmptyState, ErrorState } from "@/components/kit/empty-state"
import { MetricTile } from "@/components/kit/metric-tile"
import { Notice } from "@/components/kit/notice"
import { ChartSkeleton, MetricRowSkeleton } from "@/components/kit/skeletons"
import { useDashboardExecute, useDashboardFilterOptions, useDashboardMeta, type ChartConfig } from "@/hooks/use-dashboards"
import { usePageTitle } from "@/hooks/use-page-title"
import { useChat } from "@/providers/chat-provider"
import { humanizeError } from "@/lib/errors"
import { filtersFromParams, filtersToParams, hasActiveFilters } from "@/lib/dashboard-filters"
import { formatKpiValue, kpiUnit, type KpiLike, type KpiUnit } from "@/lib/kpi"
import type { DashboardFilters } from "@/types/dashboard-filters"
import type { WidgetConfig } from "@/types/api"

/** Icono del KPI: primero la pista del backend; el de dinero solo si la cifra es en pesos. */
function kpiIcon(kpi: KpiLike, unit: KpiUnit): LucideIcon {
  if (unit === "money") return CircleDollarSign
  const hint = (kpi.icon ?? "").toLowerCase()
  if (/database|rows|table/.test(hint)) return Database
  if (/trending|activity/.test(hint)) return TrendingUp
  if (/cart|pedido|orden/.test(hint)) return ShoppingCart
  if (/user|cliente/.test(hint)) return Users
  const label = kpi.label.toLowerCase()
  if (/pedido|orden|compra/.test(label)) return ShoppingCart
  if (/cliente|persona|usuario/.test(label)) return Users
  return Hash
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

/** Los gráficos del servidor ({ type, title, data, x, y, color, unit }) se adaptan al contrato WidgetConfig. */
function toWidget(dashboardId: string, chart: ChartConfig, i: number): WidgetConfig {
  return {
    id: chart.id ?? `${dashboardId}-chart-${i}`,
    dashboard_id: dashboardId,
    title: chart.title,
    chart_type: chart.type,
    data_key: chart.y || "value",
    x_key: chart.x || "name",
    y_keys: [chart.y || "value"],
    color: chart.color,
    unit: chart.unit,
    width: 2,
    height: 1,
    position: i,
    data: chart.data,
    created_at: new Date().toISOString(),
  }
}

/** Un gráfico que no se pudo calcular: el resto del tablero sigue funcionando. */
function ChartError({ title, message }: { title: string; message: string }) {
  return (
    <article className="surface flex h-full flex-col gap-3 p-5">
      <h3 className="font-display text-lg font-semibold leading-snug">{title}</h3>
      <Notice tone="warning" title="No pudimos calcular este gráfico">
        {message}. Los demás gráficos de este tablero no se afectan.
      </Notice>
    </article>
  )
}

export default function DashboardDetailPage() {
  // useSearchParams necesita un límite de Suspense (el estado de los filtros vive en la URL).
  return (
    <Suspense fallback={null}>
      <DashboardDetail />
    </Suspense>
  )
}

function DashboardDetail() {
  const params = useParams<{ id: string }>()
  const id = params.id
  const { ask } = useChat()
  const router = useRouter()
  const pathname = usePathname()
  const searchParams = useSearchParams()
  const filters = useMemo(() => filtersFromParams(new URLSearchParams(searchParams?.toString() ?? "")), [searchParams])
  const setFilters = useCallback(
    (next: DashboardFilters) => {
      const qs = filtersToParams(next, new URLSearchParams(searchParams?.toString() ?? "")).toString()
      router.replace(qs ? `${pathname}?${qs}` : pathname, { scroll: false })
    },
    [router, pathname, searchParams]
  )
  const [drillTarget, setDrillTarget] = useState<DrillTarget | null>(null)

  const { data: meta, isLoading: metaLoading } = useDashboardMeta(id)
  const { data: options, isLoading: optionsLoading } = useDashboardFilterOptions(id)
  const { data, isLoading, isFetching, isStale, isError, error, updatedAt, refetch } = useDashboardExecute(id, filters)
  const ago = useSecondsAgo(updatedAt || undefined)
  usePageTitle(meta?.name ?? "Tablero")

  const charts = data?.charts ?? []
  const kpis = data?.kpis ?? []
  const nothing = charts.length === 0 && kpis.length === 0

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
        {/* Responde al ANCHO DEL CONTENIDO (no al de la pantalla): con el chat abierto el contenido es angosto. */}
        <div className="[container-type:inline-size]">
        <header className="flex flex-col gap-4 [@container(min-width:44rem)]:flex-row [@container(min-width:44rem)]:items-end [@container(min-width:44rem)]:justify-between">
          <div className="min-w-0 flex-1 space-y-2">
            {metaLoading ? (
              <Skeleton className="h-10 w-72 max-w-full" />
            ) : (
              <h1 className="break-words font-display text-[30px] font-semibold leading-tight text-balance sm:text-[36px]">{meta?.name ?? "Tablero"}</h1>
            )}
            <p className="max-w-2xl text-[15px] text-muted-foreground">
              {meta?.description?.trim() || "Gráficos calculados con tus datos de este momento."}
              {ago && !isFetching && <span className="text-muted-foreground"> · Actualizado {ago}.</span>}
              {isFetching && !isLoading && <span className="text-muted-foreground"> · Actualizando…</span>}
            </p>
            <EditWithAssistantButton name={meta?.name ?? ""} />
          </div>
          <div className="flex shrink-0 flex-wrap items-center gap-2">
            <Button variant="outline" onClick={() => void refetch()} disabled={isFetching}>
              <RefreshCw className={isFetching ? "animate-spin" : ""} aria-hidden="true" />
              Actualizar
            </Button>
            <Button variant="soft" onClick={() => ask(`Cuéntame lo más importante del tablero «${meta?.name ?? "este tablero"}»`)}>
              <Sparkles aria-hidden="true" />
              Pregúntale
            </Button>
          </div>
        </header>
        </div>
      </div>

      {!isLoading && !isError && (options?.dimensions.length || options?.date || hasActiveFilters(filters)) ? (
        <FilterBar dashboardId={id} options={options} loading={optionsLoading} filters={filters} onChange={setFilters} busy={isFetching} />
      ) : null}

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
        <div className={isFetching || isStale ? "opacity-70 transition-opacity" : "transition-opacity"} aria-busy={isFetching}>
          {kpis.length > 0 && (
            <section aria-label="Cifras principales" className="auto-grid mb-6 gap-4 [--auto-grid-min:13rem]">
              {kpis.map((kpi, i) => {
                const unit = kpiUnit(kpi)
                return (
                  <MetricTile
                    key={`${kpi.id ?? kpi.label}-${i}`}
                    label={kpi.label}
                    value={formatKpiValue(kpi)}
                    context={
                      kpi.error
                        ? `No pudimos calcular esta cifra: ${kpi.error}`
                        : kpi.empty
                          ? (kpi.message ?? "Sin datos con estos filtros.")
                          : kpi.notes?.[0]?.message
                    }
                    icon={kpiIcon(kpi, unit)}
                    // El naranja solo en la primera cifra: guía la atención sin saturar.
                    tone={kpi.error ? "warning" : i === 0 ? "primary" : "neutral"}
                  />
                )
              })}
            </section>
          )}

          {nothing ? (
            <div className="surface">
              <EmptyState
                illustration="chart"
                title="Este tablero todavía no tiene gráficos"
                description="Puede pasar cuando aún no hay datos con fechas o cifras. Sube un archivo y vuelve a abrirlo, o pídele al asistente que arme uno."
                actions={
                  <>
                    <Button asChild>
                      <Link href="/data">Ir a Mis datos</Link>
                    </Button>
                    <Button variant="soft" onClick={() => ask("Quiero un tablero con mis ventas por mes y por producto", { send: false })}>
                      <Sparkles aria-hidden="true" />
                      Pídele un tablero al asistente
                    </Button>
                  </>
                }
              />
            </div>
          ) : (
            charts.length > 0 && (
              <section aria-label="Gráficos" className="auto-grid gap-5 [--auto-grid-min:22rem]">
                {charts.map((chart, i) =>
                  chart.error ? (
                    <ChartError key={`${chart.id ?? chart.title}-${i}`} title={chart.title} message={chart.error} />
                  ) : (
                    <ChartRenderer
                      key={`${chart.id ?? chart.title}-${i}`}
                      widget={toWidget(id, chart, i)}
                      xLabel={chart.x_label}
                      yLabel={chart.y_label}
                      notes={chart.notes?.map((n) => n.message)}
                      emptyMessage={chart.empty ? (chart.message ?? "Sin datos con estos filtros.") : undefined}
                      onSelectPoint={
                        chart.drillable && chart.id
                          ? (point) =>
                              setDrillTarget({
                                widgetId: chart.id as string,
                                chartTitle: chart.title,
                                point: { name: point.name, value: point.value, key: point.key, empty: point.empty, other: point.other },
                                restoreFocus: captureFocus(),
                              })
                          : undefined
                      }
                    />
                  )
                )}
              </section>
            )
          )}
        </div>
      )}

      <DrillPanel
        dashboardId={id}
        target={drillTarget}
        filters={filters}
        onClose={() => setDrillTarget(null)}
        onAsk={(question) => {
          setDrillTarget(null)
          ask(question, { send: false })
        }}
      />
    </div>
  )
}
