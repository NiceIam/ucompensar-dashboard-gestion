"use client"

import { useId, useMemo, useState } from "react"
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Line,
  LineChart,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts"
import { Table2, BarChart3 } from "lucide-react"
import { formatCompact, formatMoney, formatNumber, formatShare } from "@/lib/format"
import { cn } from "@/lib/utils"

export type ChartForm = "bar" | "line" | "pie" | "area"
export type ChartUnit = "money" | "number" | "count"

export interface ChartPoint {
  name: string
  value: number
}

/** Colores categóricos en orden fijo (validados para daltonismo en claro y oscuro). */
export const SERIES_COLORS = Array.from({ length: 8 }, (_, i) => `hsl(var(--chart-${i + 1}))`)

export function formatValue(value: number, unit: ChartUnit, compact = false): string {
  if (unit === "money") return formatMoney(value, { compact })
  return compact ? formatCompact(value) : formatNumber(value)
}

/** Etiqueta del eje recortada según cuántas categorías hay (la completa sale en el tooltip y la tabla). */
export function shortLabel(label: string, count: number): string {
  const max = count <= 3 ? 16 : count <= 5 ? 12 : 9
  return label.length > max ? `${label.slice(0, max - 1).trimEnd()}…` : label
}

/** Pie con máximo 6 porciones: el resto se agrupa en "Otros". */
export function foldPie(points: ChartPoint[], max = 6): ChartPoint[] {
  const sorted = [...points].sort((a, b) => b.value - a.value)
  if (sorted.length <= max) return sorted
  const head = sorted.slice(0, max - 1)
  const rest = sorted.slice(max - 1).reduce((s, p) => s + p.value, 0)
  return [...head, { name: `Otros (${sorted.length - head.length})`, value: rest }]
}

interface TooltipContentProps {
  active?: boolean
  payload?: Array<{ value?: number | string; payload?: unknown }>
  label?: string | number
  unit: ChartUnit
}

function ChartTooltip({ active, payload, label, unit }: TooltipContentProps) {
  if (!active || !payload?.length) return null
  const p = payload[0]
  const name = (p.payload as ChartPoint | undefined)?.name ?? label
  return (
    <div className="rounded-xl border bg-popover px-3 py-2 text-sm shadow-float">
      <p className="text-xs font-medium text-muted-foreground">{name}</p>
      <p className="font-semibold tabular">{formatValue(Number(p.value ?? 0), unit)}</p>
    </div>
  )
}

const axisTick = { fill: "hsl(var(--chart-axis))", fontSize: 12 }

/**
 * Gráfico sencillo de una serie con la paleta de la marca: barras finas con
 * extremo redondeado, líneas de 2 px, rejilla de una línea y tooltip legible.
 * Siempre ofrece la vista de tabla (el gemelo accesible).
 */
export function SimpleChart({
  form,
  points,
  unit = "number",
  height = 220,
  label,
  className,
  allowTable = true,
}: {
  form: ChartForm
  points: ChartPoint[]
  unit?: ChartUnit
  height?: number
  /** Resumen para lectores de pantalla, por ejemplo "Ventas por mes". */
  label: string
  className?: string
  allowTable?: boolean
}) {
  const [asTable, setAsTable] = useState(false)
  const gradientId = useId().replace(/:/g, "")
  const data = useMemo(() => (form === "pie" ? foldPie(points) : points), [form, points])
  const total = useMemo(() => data.reduce((s, p) => s + p.value, 0), [data])
  const longLabels = data.some((p) => p.name.length > 10)
  const horizontal = form === "bar" && (longLabels || data.length > 8) && data.length <= 12
  // Ancho del eje Y según la etiqueta más larga (evita cifras recortadas como "$ 800 mil").
  const maxValue = Math.max(0, ...data.map((p) => Math.abs(p.value)))
  const yWidth = Math.min(96, 18 + 7 * formatValue(maxValue, unit, true).length)

  if (data.length === 0) {
    return (
      <div className={cn("flex items-center justify-center rounded-xl bg-muted/50 text-sm text-muted-foreground", className)} style={{ height }}>
        No hay datos para mostrar.
      </div>
    )
  }

  const summary = `${label}: ${data
    .slice(0, 6)
    .map((p) => `${p.name} ${formatValue(p.value, unit, true)}`)
    .join(", ")}${data.length > 6 ? "…" : ""}`

  return (
    <div className={cn("relative", className)}>
      {allowTable && (
        <button
          type="button"
          onClick={() => setAsTable((v) => !v)}
          className="absolute -top-2 right-0 z-10 inline-flex h-11 items-center gap-1.5 rounded-lg px-2.5 text-xs font-semibold text-muted-foreground transition hover:bg-accent hover:text-foreground sm:-top-1 sm:h-9"
          aria-pressed={asTable}
        >
          {asTable ? <BarChart3 className="h-3.5 w-3.5" aria-hidden="true" /> : <Table2 className="h-3.5 w-3.5" aria-hidden="true" />}
          {asTable ? "Ver gráfico" : "Ver tabla"}
        </button>
      )}

      {asTable ? (
        <div className="max-h-[320px] overflow-auto rounded-xl border" style={{ minHeight: Math.min(height, 200) }}>
          <table className="w-full text-sm">
            <caption className="sr-only">{label}</caption>
            <thead className="sticky top-0 bg-muted/80 backdrop-blur">
              <tr>
                <th scope="col" className="px-3 py-2 text-left font-semibold">Categoría</th>
                <th scope="col" className="px-3 py-2 text-right font-semibold">Valor</th>
                {form === "pie" && <th scope="col" className="px-3 py-2 text-right font-semibold">Parte</th>}
              </tr>
            </thead>
            <tbody>
              {data.map((p) => (
                <tr key={p.name} className="border-t">
                  <td className="px-3 py-2">{p.name}</td>
                  <td className="px-3 py-2 text-right tabular">{formatValue(p.value, unit)}</td>
                  {form === "pie" && <td className="px-3 py-2 text-right tabular">{total ? formatShare(p.value / total) : "—"}</td>}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : form === "pie" ? (
        <div role="img" aria-label={summary} className="flex flex-col items-center gap-4 pt-6 sm:flex-row sm:items-center">
          <div className="h-[200px] w-[200px] shrink-0">
            <ResponsiveContainer width="100%" height="100%">
              <PieChart>
                <Pie
                  data={data}
                  dataKey="value"
                  nameKey="name"
                  innerRadius={56}
                  outerRadius={92}
                  paddingAngle={1.5}
                  stroke="hsl(var(--card))"
                  strokeWidth={2}
                  isAnimationActive={false}
                >
                  {data.map((p, i) => (
                    <Cell key={p.name} fill={SERIES_COLORS[i % SERIES_COLORS.length]} />
                  ))}
                </Pie>
                <Tooltip content={<ChartTooltip unit={unit} />} />
              </PieChart>
            </ResponsiveContainer>
          </div>
          <ul className="w-full min-w-0 flex-1 space-y-2 text-sm">
            {data.map((p, i) => (
              <li key={p.name} className="flex items-center gap-2.5">
                <span className="h-3 w-3 shrink-0 rounded-sm" style={{ background: SERIES_COLORS[i % SERIES_COLORS.length] }} aria-hidden="true" />
                <span className="min-w-0 flex-1 truncate">{p.name}</span>
                <span className="tabular text-muted-foreground">{total ? formatShare(p.value / total) : ""}</span>
                <span className="tabular font-semibold">{formatValue(p.value, unit, true)}</span>
              </li>
            ))}
          </ul>
        </div>
      ) : (
        <div role="img" aria-label={summary} className="pt-8" style={{ height: horizontal ? Math.max(height, data.length * 34 + 40) : height }}>
          <ResponsiveContainer width="100%" height="100%">
            {form === "area" ? (
              <AreaChart data={data} margin={{ top: 8, right: 12, bottom: 0, left: 0 }}>
                <defs>
                  <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor={SERIES_COLORS[0]} stopOpacity={0.22} />
                    <stop offset="100%" stopColor={SERIES_COLORS[0]} stopOpacity={0.02} />
                  </linearGradient>
                </defs>
                <CartesianGrid vertical={false} stroke="hsl(var(--chart-grid))" />
                <XAxis dataKey="name" tick={axisTick} tickLine={false} axisLine={{ stroke: "hsl(var(--chart-grid))" }} minTickGap={16} />
                <YAxis tick={axisTick} tickLine={false} axisLine={false} width={yWidth} interval={0} tickCount={5} tickFormatter={(v: number) => formatValue(v, unit, true)} />
                <Tooltip content={<ChartTooltip unit={unit} />} cursor={{ stroke: "hsl(var(--chart-axis))", strokeWidth: 1 }} />
                <Area
                  type="monotone"
                  dataKey="value"
                  stroke={SERIES_COLORS[0]}
                  strokeWidth={2}
                  fill={`url(#${gradientId})`}
                  activeDot={{ r: 5, stroke: "hsl(var(--card))", strokeWidth: 2 }}
                  isAnimationActive={false}
                />
              </AreaChart>
            ) : form === "line" ? (
              <LineChart data={data} margin={{ top: 8, right: 12, bottom: 0, left: 0 }}>
                <CartesianGrid vertical={false} stroke="hsl(var(--chart-grid))" />
                <XAxis dataKey="name" tick={axisTick} tickLine={false} axisLine={{ stroke: "hsl(var(--chart-grid))" }} minTickGap={16} />
                <YAxis tick={axisTick} tickLine={false} axisLine={false} width={yWidth} interval={0} tickCount={5} tickFormatter={(v: number) => formatValue(v, unit, true)} />
                <Tooltip content={<ChartTooltip unit={unit} />} cursor={{ stroke: "hsl(var(--chart-axis))", strokeWidth: 1 }} />
                <Line
                  type="monotone"
                  dataKey="value"
                  stroke={SERIES_COLORS[0]}
                  strokeWidth={2}
                  dot={data.length <= 16 ? { r: 4, fill: SERIES_COLORS[0], stroke: "hsl(var(--card))", strokeWidth: 2 } : false}
                  activeDot={{ r: 5, stroke: "hsl(var(--card))", strokeWidth: 2 }}
                  isAnimationActive={false}
                />
              </LineChart>
            ) : horizontal ? (
              <BarChart data={data} layout="vertical" margin={{ top: 0, right: 16, bottom: 0, left: 0 }}>
                <CartesianGrid horizontal={false} stroke="hsl(var(--chart-grid))" />
                <XAxis type="number" tick={axisTick} tickLine={false} axisLine={false} tickFormatter={(v: number) => formatValue(v, unit, true)} />
                <YAxis type="category" dataKey="name" tick={axisTick} tickLine={false} axisLine={false} width={120} />
                <Tooltip content={<ChartTooltip unit={unit} />} cursor={{ fill: "hsl(var(--muted))" }} />
                <Bar dataKey="value" fill={SERIES_COLORS[0]} radius={[0, 4, 4, 0]} maxBarSize={22} isAnimationActive={false} />
              </BarChart>
            ) : (
              <BarChart data={data} margin={{ top: 8, right: 8, bottom: 0, left: 0 }}>
                <CartesianGrid vertical={false} stroke="hsl(var(--chart-grid))" />
                <XAxis dataKey="name" tick={axisTick} tickLine={false} axisLine={{ stroke: "hsl(var(--chart-grid))" }} interval={data.length <= 8 ? 0 : "preserveStartEnd"} minTickGap={4} tickFormatter={(v: string) => shortLabel(String(v), data.length)} />
                <YAxis tick={axisTick} tickLine={false} axisLine={false} width={yWidth} interval={0} tickCount={5} tickFormatter={(v: number) => formatValue(v, unit, true)} />
                <Tooltip content={<ChartTooltip unit={unit} />} cursor={{ fill: "hsl(var(--muted))" }} />
                <Bar dataKey="value" fill={SERIES_COLORS[0]} radius={[4, 4, 0, 0]} maxBarSize={24} isAnimationActive={false} />
              </BarChart>
            )}
          </ResponsiveContainer>
        </div>
      )}
    </div>
  )
}
