"use client"

import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  PolarAngleAxis,
  PolarGrid,
  Radar,
  RadarChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts"
import { SERIES_COLORS, SimpleChart, formatValue, type ChartUnit } from "@/components/charts/simple-chart"
import { MetricCard } from "@/components/charts/metric-card"
import { prettyLabel } from "@/components/chat/message-content"
import { columnLabel, isMoneyLike } from "@/lib/data-vocabulary"
import { formatNumber } from "@/lib/format"
import { cn } from "@/lib/utils"
import type { WidgetConfig } from "@/types/api"

interface ChartRendererProps {
  widget: WidgetConfig
  className?: string
}

const axisTick = { fill: "hsl(var(--chart-axis))", fontSize: 12 }

function EmptyChart() {
  return (
    <div className="flex h-44 items-center justify-center rounded-xl bg-muted/50 px-6 text-center text-sm text-muted-foreground">
      Este gráfico todavía no tiene datos para mostrar.
    </div>
  )
}

function cellText(value: unknown): string {
  if (value === null || value === undefined || value === "") return "—"
  if (typeof value === "number") return formatNumber(value)
  if (typeof value === "boolean") return value ? "Sí" : "No"
  return String(value)
}

/** Varias series a la vez (y_keys > 1): colores categóricos en orden fijo y leyenda. */
function MultiSeries({ widget, unit }: { widget: WidgetConfig; unit: ChartUnit }) {
  const data = (widget.data ?? []).map((row) => ({ ...row, [widget.x_key]: prettyLabel(String(row[widget.x_key] ?? "")) }))
  const keys = widget.y_keys.slice(0, 8)
  const Chart = widget.chart_type === "line" || widget.chart_type === "area" ? LineChart : BarChart
  return (
    <div className="h-64" role="img" aria-label={`${widget.title}: ${keys.map((k) => columnLabel({ name: k })).join(", ")}`}>
      <ResponsiveContainer width="100%" height="100%">
        <Chart data={data} margin={{ top: 8, right: 8, bottom: 0, left: 0 }}>
          <CartesianGrid vertical={false} stroke="hsl(var(--chart-grid))" />
          <XAxis dataKey={widget.x_key} tick={axisTick} tickLine={false} axisLine={{ stroke: "hsl(var(--chart-grid))" }} />
          <YAxis tick={axisTick} tickLine={false} axisLine={false} width={64} tickFormatter={(v: number) => formatValue(v, unit, true)} />
          <Tooltip
            formatter={(v: unknown, name: unknown) => [formatValue(Number(v), unit), columnLabel({ name: String(name) })]}
            contentStyle={{
              background: "hsl(var(--popover))",
              border: "1px solid hsl(var(--border))",
              borderRadius: 12,
              color: "hsl(var(--popover-foreground))",
            }}
          />
          <Legend formatter={(value: string) => <span className="text-xs text-foreground/80">{columnLabel({ name: value })}</span>} />
          {keys.map((key, i) =>
            Chart === LineChart ? (
              <Line key={key} type="monotone" dataKey={key} stroke={SERIES_COLORS[i]} strokeWidth={2} dot={false} isAnimationActive={false} />
            ) : (
              <Bar key={key} dataKey={key} fill={SERIES_COLORS[i]} radius={[4, 4, 0, 0]} maxBarSize={24} isAnimationActive={false} />
            )
          )}
        </Chart>
      </ResponsiveContainer>
    </div>
  )
}

/**
 * Dibuja un widget de tablero a partir de su `WidgetConfig` (contrato sin
 * cambios): barras, líneas, áreas, torta, radar, cifra o tabla.
 */
export function ChartRenderer({ widget, className }: ChartRendererProps) {
  const { title, chart_type, data = [], x_key, y_keys } = widget
  const yKey = y_keys[0] ?? "value"
  // Solo se muestra "$" si la columna medida tiene nombre de dinero (no se adivina por el título).
  const unit: ChartUnit = isMoneyLike(yKey) ? "money" : "number"

  const body = () => {
    if (!data.length) return <EmptyChart />

    if (chart_type === "metric") {
      const raw = data[0]?.[yKey]
      return (
        <div className="flex h-36 items-center">
          <MetricCard label={columnLabel({ name: yKey })} value={typeof raw === "number" ? raw : Number(raw ?? 0)} />
        </div>
      )
    }

    if (chart_type === "table") {
      const keys = Object.keys(data[0] ?? {})
      return (
        <div className="max-h-80 overflow-auto rounded-xl border">
          <table className="w-full text-sm">
            <caption className="sr-only">{title}</caption>
            <thead className="sticky top-0 bg-muted/90 backdrop-blur">
              <tr>
                {keys.map((k) => (
                  <th key={k} scope="col" className="whitespace-nowrap px-3 py-2 text-left font-semibold">
                    {columnLabel({ name: k })}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {data.slice(0, 50).map((row, i) => (
                <tr key={i} className="border-t">
                  {keys.map((k) => (
                    <td key={k} className="whitespace-nowrap px-3 py-2 tabular">
                      {cellText(row[k as keyof typeof row])}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )
    }

    if (chart_type === "radar") {
      return (
        <div className="h-64" role="img" aria-label={title}>
          <ResponsiveContainer width="100%" height="100%">
            <RadarChart data={data}>
              <PolarGrid stroke="hsl(var(--chart-grid))" />
              <PolarAngleAxis dataKey={x_key} tick={axisTick} />
              {y_keys.slice(0, 3).map((key, i) => (
                <Radar key={key} name={columnLabel({ name: key })} dataKey={key} stroke={SERIES_COLORS[i]} fill={SERIES_COLORS[i]} fillOpacity={0.15} />
              ))}
              <Legend />
              <Tooltip />
            </RadarChart>
          </ResponsiveContainer>
        </div>
      )
    }

    if (y_keys.length > 1) return <MultiSeries widget={widget} unit={unit} />

    const points = data
      .map((row) => ({ name: prettyLabel(String(row[x_key] ?? "")), value: Number(row[yKey]) }))
      .filter((p) => Number.isFinite(p.value))
    const form = chart_type === "pie" ? "pie" : chart_type === "line" ? "line" : chart_type === "area" ? "area" : "bar"
    return <SimpleChart form={form} points={points} unit={unit} label={title} height={240} />
  }

  return (
    <article className={cn("surface flex h-full flex-col gap-3 p-5", className)}>
      <h3 className="pr-24 font-display text-lg font-semibold leading-snug">{title}</h3>
      <div className="min-w-0 flex-1">{body()}</div>
    </article>
  )
}
