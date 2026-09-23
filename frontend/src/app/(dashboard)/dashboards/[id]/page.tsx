"use client"

import Link from "next/link"
import { useParams } from "next/navigation"
import { ArrowLeft, Download, RefreshCw, AlertTriangle } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { Skeleton } from "@/components/ui/skeleton"
import { MetricCard } from "@/components/charts/metric-card"
import { ChartRenderer } from "@/components/charts/chart-renderer"
import {
  useDashboardMeta,
  useDashboardExecute,
  useDownloadDashboardScript,
} from "@/hooks/use-dashboards"
import type { WidgetConfig } from "@/types/api"

export default function DashboardDetailPage() {
  const params = useParams<{ id: string }>()
  const id = params.id

  const { data: meta, isLoading: metaLoading } = useDashboardMeta(id)
  const { data, isLoading, isFetching, isError, refetch } = useDashboardExecute(id)
  const downloadMutation = useDownloadDashboardScript()

  // El script del tablero devuelve charts en el formato { type, title, data, x, y, color }
  // (el mismo que usa el chat). ChartRenderer espera WidgetConfig — se adapta aquí.
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

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-center gap-3">
          <Button asChild variant="ghost" size="icon" className="h-8 w-8 shrink-0">
            <Link href="/dashboards">
              <ArrowLeft className="h-4 w-4" />
            </Link>
          </Button>
          <div>
            {metaLoading ? (
              <Skeleton className="h-7 w-40" />
            ) : (
              <h1 className="text-2xl font-bold tracking-tight">
                {meta?.name ?? "Tablero"}
              </h1>
            )}
            {meta?.description && (
              <p className="text-sm text-muted-foreground">{meta.description}</p>
            )}
          </div>
        </div>
        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={() => refetch()}
            disabled={isFetching}
          >
            <RefreshCw
              className={`mr-2 h-3.5 w-3.5 ${isFetching ? "animate-spin" : ""}`}
            />
            Actualizar
          </Button>
          <Button
            variant="outline"
            size="sm"
            onClick={() => downloadMutation.mutate({ id })}
            disabled={downloadMutation.isPending}
          >
            <Download className="mr-2 h-3.5 w-3.5" />
            Script .py
          </Button>
        </div>
      </div>

      {isLoading ? (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {Array.from({ length: 4 }).map((_, i) => (
            <Skeleton key={i} className="h-56 rounded-xl" />
          ))}
        </div>
      ) : isError ? (
        <Card className="border-destructive/40 bg-destructive/5">
          <CardContent className="flex flex-col items-center gap-3 py-10 text-center">
            <AlertTriangle className="h-6 w-6 text-destructive" />
            <p className="text-sm font-medium text-destructive">
              No se pudo ejecutar el script de este tablero
            </p>
            <Button size="sm" variant="outline" onClick={() => refetch()}>
              Reintentar
            </Button>
          </CardContent>
        </Card>
      ) : (
        <>
          {data?.kpis && data.kpis.length > 0 && (
            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
              {data.kpis.map((kpi, i) => (
                <Card key={i}>
                  <CardContent className="pt-6">
                    <MetricCard label={kpi.label} value={kpi.value} />
                  </CardContent>
                </Card>
              ))}
            </div>
          )}

          {widgets.length === 0 ? (
            <Card className="border-dashed bg-muted/20">
              <CardContent className="flex flex-col items-center justify-center py-16 text-center">
                <p className="text-sm text-muted-foreground">
                  Este tablero no generó gráficas todavía.
                </p>
              </CardContent>
            </Card>
          ) : (
            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
              {widgets.map((widget) => (
                <ChartRenderer key={widget.id} widget={widget} />
              ))}
            </div>
          )}
        </>
      )}
    </div>
  )
}
