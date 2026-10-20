"use client"

import { useId, useMemo, useState, type Key, type KeyboardEvent, type ReactNode } from "react"
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
  Rectangle,
  ResponsiveContainer,
  Sector,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts"
import { Table2, BarChart3, ChevronRight } from "lucide-react"
import { formatCompact, formatMoney, formatNumber, formatShare } from "@/lib/format"
import { cn } from "@/lib/utils"

export type ChartForm = "bar" | "line" | "pie" | "area"
export type ChartUnit = "money" | "number" | "count"

export interface ChartPoint {
  name: string
  value: number
  /** Valor exacto de la celda cuando `name` es una versión recortada (sirve para abrir el detalle). */
  key?: string
  /** El grupo «(sin dato)». */
  empty?: boolean
  /** La porción «Otros (n)» que armó el servidor. */
  other?: boolean
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

/** Lado mínimo (px) de lo que se puede tocar: WCAG 2.2 (2.5.8) pide 24 px. */
const HIT = 28

/** Color de una porción: el gris neutro para «Otros», los categóricos en orden fijo para el resto. */
function sliceColor(p: ChartPoint, i: number): string {
  return p.other ? "hsl(var(--muted-foreground))" : SERIES_COLORS[i % SERIES_COLORS.length]
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
  onSelectPoint,
  xLabel,
  yLabel,
}: {
  form: ChartForm
  points: ChartPoint[]
  unit?: ChartUnit
  height?: number
  /** Resumen para lectores de pantalla, por ejemplo "Ventas por mes". */
  label: string
  className?: string
  allowTable?: boolean
  /**
   * Si se pasa, cada dato (barra, punto, porción, fila de la leyenda o de la tabla) se puede tocar: es un botón
   * con foco por teclado (flechas para moverse, Enter o Espacio para abrir). Sin esto el gráfico es solo de lectura.
   */
  onSelectPoint?: (point: ChartPoint) => void
  /** Encabezados legibles de la vista de tabla («Mes», «Ventas»). */
  xLabel?: string
  yLabel?: string
}) {
  const [asTable, setAsTable] = useState(false)
  const [rove, setRove] = useState(0)
  const chartId = useId().replace(/:/g, "")
  const gradientId = chartId
  const interactive = Boolean(onSelectPoint)
  // Con detalle, el servidor ya agrupa «Otros»: no se vuelve a agrupar aquí (el detalle de «Otros» sería otro).
  const data = useMemo(() => (form === "pie" && !onSelectPoint ? foldPie(points) : points), [form, points, onSelectPoint])
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

  const select = (index: number) => {
    const p = data[index]
    if (p && onSelectPoint) onSelectPoint(p)
  }

  /** Atributos de un dato tocable: botón con foco "rodante" (una sola parada de Tab por gráfico). */
  const datum = (index: number) => ({
    role: "button" as const,
    tabIndex: rove === index ? 0 : -1,
    "aria-label": `${data[index]?.name ?? ""}: ${formatValue(data[index]?.value ?? 0, unit, true)}. Ver el detalle`,
    "data-datum": chartId,
    "data-index": index,
    className: "drill-datum",
    onClick: () => select(index),
    onFocus: () => setRove(index),
    onKeyDown: (e: KeyboardEvent<SVGElement | HTMLElement>) => onDatumKey(e, index),
  })

  const onDatumKey = (e: KeyboardEvent<SVGElement | HTMLElement>, index: number) => {
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault()
      select(index)
      return
    }
    const move: Record<string, number> = {
      ArrowRight: index + 1, ArrowDown: index + 1, ArrowLeft: index - 1, ArrowUp: index - 1, Home: 0, End: data.length - 1,
    }
    if (!(e.key in move)) return
    e.preventDefault()
    const next = Math.max(0, Math.min(data.length - 1, move[e.key]))
    setRove(next)
    const root = (e.currentTarget as Element).closest("[data-chart-root]")
    root?.querySelector<HTMLElement>(`[data-datum="${chartId}"][data-index="${next}"]`)?.focus()
  }

  // Zona tocable de al menos HIT x HIT alrededor de un dato (los más pequeños son difíciles de acertar con el dedo).
  const hit = (x: number, y: number, w: number, h: number) => {
    const padX = Math.max(0, (HIT - w) / 2)
    const padY = Math.max(0, (HIT - h) / 2)
    return <rect x={x - padX} y={y - padY} width={w + 2 * padX} height={h + 2 * padY} fill="transparent" />
  }

  const barShape = (radius: [number, number, number, number]) =>
    interactive
      ? (props: { x?: number; y?: number; width?: number; height?: number; fill?: string; index?: number }) => {
          const { x = 0, y = 0, width = 0, height: h = 0, index = 0 } = props
          return (
            <g {...datum(index)}>
              <Rectangle x={x} y={y} width={width} height={h} fill={props.fill ?? SERIES_COLORS[0]} radius={radius} className="datum-mark" />
              {hit(x, y, width, h)}
            </g>
          )
        }
      : undefined

  const lineDot = (props: { cx?: number; cy?: number; index?: number; key?: Key | null }) => {
    const { cx = 0, cy = 0, index = 0 } = props
    const visible = data.length <= 16
    return (
      <g key={props.key ?? index} {...datum(index)}>
        <circle cx={cx} cy={cy} r={visible ? 4 : 3} fill={SERIES_COLORS[0]} stroke="hsl(var(--card))" strokeWidth={2} className={cn("datum-mark", !visible && "datum-dot-hidden")} />
        <circle cx={cx} cy={cy} r={HIT / 2} fill="transparent" />
      </g>
    )
  }

  const rowButton = (index: number, children: ReactNode, extra = "") => (
    <button
      type="button"
      onClick={() => select(index)}
      className={cn(
        "flex min-h-11 w-full items-center gap-2.5 rounded-lg px-1.5 text-left transition hover:bg-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
        extra
      )}
      aria-label={`${data[index].name}: ${formatValue(data[index].value, unit, true)}. Ver el detalle`}
    >
      {children}
    </button>
  )

  return (
    <div className={cn("relative", className)} data-chart-root="">
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
        <div className="relative max-h-[320px] overflow-auto rounded-xl border" style={{ minHeight: Math.min(height, 200) }}>
          <table className="w-full text-sm">
            <caption className="sr-only">{label}</caption>
            <thead className="sticky top-0 bg-muted/80 backdrop-blur">
              <tr>
                <th scope="col" className="px-3 py-2 text-left font-semibold">{xLabel ?? "Categoría"}</th>
                <th scope="col" className="px-3 py-2 text-right font-semibold">{yLabel ?? "Valor"}</th>
                {form === "pie" && <th scope="col" className="px-3 py-2 text-right font-semibold">Parte</th>}
                {interactive && <th scope="col" className="w-12 px-1 py-2"><span className="sr-only">Detalle</span></th>}
              </tr>
            </thead>
            <tbody>
              {data.map((p, i) => (
                <tr key={`${p.name}-${i}`} className="border-t">
                  <td className="px-3 py-2">{p.name}</td>
                  <td className="px-3 py-2 text-right tabular">{formatValue(p.value, unit)}</td>
                  {form === "pie" && <td className="px-3 py-2 text-right tabular">{total ? formatShare(p.value / total) : "—"}</td>}
                  {interactive && (
                    <td className="px-1 py-0.5 text-right">
                      <button
                        type="button"
                        onClick={() => select(i)}
                        className="inline-flex h-11 w-11 items-center justify-center rounded-lg text-muted-foreground transition hover:bg-accent hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                        aria-label={`Ver el detalle de ${p.name}`}
                      >
                        <ChevronRight className="h-4 w-4" aria-hidden="true" />
                      </button>
                    </td>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : form === "pie" ? (
        <div role={interactive ? "group" : "img"} aria-label={summary} className="flex flex-col items-center gap-4 pt-6 sm:flex-row sm:items-center">
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
                  shape={
                    interactive
                      ? (props: { cx?: number; cy?: number; innerRadius?: number; outerRadius?: number; startAngle?: number; endAngle?: number; index?: number; fill?: string }) => (
                          <g {...datum(props.index ?? 0)}>
                            <Sector
                              cx={props.cx}
                              cy={props.cy}
                              innerRadius={props.innerRadius}
                              outerRadius={props.outerRadius}
                              startAngle={props.startAngle}
                              endAngle={props.endAngle}
                              fill={props.fill}
                              stroke="hsl(var(--card))"
                              strokeWidth={2}
                              className="datum-mark"
                            />
                          </g>
                        )
                      : undefined
                  }
                >
                  {data.map((p, i) => (
                    <Cell key={`${p.name}-${i}`} fill={sliceColor(p, i)} />
                  ))}
                </Pie>
                <Tooltip content={<ChartTooltip unit={unit} />} />
              </PieChart>
            </ResponsiveContainer>
          </div>
          <ul className="w-full min-w-0 flex-1 space-y-1 text-sm">
            {data.map((p, i) => {
              const row = (
                <>
                  <span className="h-3 w-3 shrink-0 rounded-sm" style={{ background: sliceColor(p, i) }} aria-hidden="true" />
                  <span className="min-w-0 flex-1 truncate">{p.name}</span>
                  <span className="tabular text-muted-foreground">{total ? formatShare(p.value / total) : ""}</span>
                  <span className="tabular font-semibold">{formatValue(p.value, unit, true)}</span>
                  {interactive && <ChevronRight className="h-4 w-4 shrink-0 text-muted-foreground" aria-hidden="true" />}
                </>
              )
              return (
                <li key={`${p.name}-${i}`} className={interactive ? undefined : "flex items-center gap-2.5 py-1"}>
                  {interactive ? rowButton(i, row) : row}
                </li>
              )
            })}
          </ul>
        </div>
      ) : (
        <div role={interactive ? "group" : "img"} aria-label={summary} className="pt-8" style={{ height: horizontal ? Math.max(height, data.length * 34 + 40) : height }}>
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
                  dot={interactive ? lineDot : false}
                  activeDot={interactive ? false : { r: 5, stroke: "hsl(var(--card))", strokeWidth: 2 }}
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
                  dot={
                    interactive
                      ? lineDot
                      : data.length <= 16
                        ? { r: 4, fill: SERIES_COLORS[0], stroke: "hsl(var(--card))", strokeWidth: 2 }
                        : false
                  }
                  activeDot={interactive ? false : { r: 5, stroke: "hsl(var(--card))", strokeWidth: 2 }}
                  isAnimationActive={false}
                />
              </LineChart>
            ) : horizontal ? (
              <BarChart data={data} layout="vertical" margin={{ top: 0, right: 16, bottom: 0, left: 0 }}>
                <CartesianGrid horizontal={false} stroke="hsl(var(--chart-grid))" />
                <XAxis type="number" tick={axisTick} tickLine={false} axisLine={false} tickFormatter={(v: number) => formatValue(v, unit, true)} />
                <YAxis type="category" dataKey="name" tick={axisTick} tickLine={false} axisLine={false} width={120} />
                <Tooltip content={<ChartTooltip unit={unit} />} cursor={{ fill: "hsl(var(--muted))" }} />
                <Bar dataKey="value" fill={SERIES_COLORS[0]} radius={[0, 4, 4, 0]} maxBarSize={22} isAnimationActive={false} shape={barShape([0, 4, 4, 0])} />
              </BarChart>
            ) : (
              <BarChart data={data} margin={{ top: 8, right: 8, bottom: 0, left: 0 }}>
                <CartesianGrid vertical={false} stroke="hsl(var(--chart-grid))" />
                <XAxis dataKey="name" tick={axisTick} tickLine={false} axisLine={{ stroke: "hsl(var(--chart-grid))" }} interval={data.length <= 8 ? 0 : "preserveStartEnd"} minTickGap={4} tickFormatter={(v: string) => shortLabel(String(v), data.length)} />
                <YAxis tick={axisTick} tickLine={false} axisLine={false} width={yWidth} interval={0} tickCount={5} tickFormatter={(v: number) => formatValue(v, unit, true)} />
                <Tooltip content={<ChartTooltip unit={unit} />} cursor={{ fill: "hsl(var(--muted))" }} />
                <Bar dataKey="value" fill={SERIES_COLORS[0]} radius={[4, 4, 0, 0]} maxBarSize={24} isAnimationActive={false} shape={barShape([4, 4, 0, 0])} />
              </BarChart>
            )}
          </ResponsiveContainer>
        </div>
      )}
    </div>
  )
}
