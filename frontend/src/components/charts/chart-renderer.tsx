"use client"

import {
  BarChart,
  Bar,
  LineChart,
  Line,
  PieChart,
  Pie,
  Cell,
  AreaChart,
  Area,
  RadarChart,
  Radar,
  PolarGrid,
  PolarAngleAxis,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
} from "recharts"
import {
  ChartContainer,
  ChartTooltip,
  ChartTooltipContent,
  type ChartConfig,
} from "@/components/ui/chart"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { MetricCard } from "@/components/charts/metric-card"
import type { WidgetConfig } from "@/types/api"

const CHART_COLORS = [
  "hsl(var(--chart-1))",
  "hsl(var(--chart-2))",
  "hsl(var(--chart-3))",
  "hsl(var(--chart-4))",
  "hsl(var(--chart-5))",
]

interface ChartRendererProps {
  widget: WidgetConfig
}

function EmptyState() {
  return (
    <div className="flex h-40 items-center justify-center text-muted-foreground text-sm">
      Sin datos disponibles
    </div>
  )
}

export function ChartRenderer({ widget }: ChartRendererProps) {
  const { title, chart_type, data = [], x_key, y_keys } = widget

  const chartConfig: ChartConfig = y_keys.reduce((acc, key, i) => {
    acc[key] = {
      label: key,
      color: CHART_COLORS[i % CHART_COLORS.length],
    }
    return acc
  }, {} as ChartConfig)

  const renderChart = () => {
    if (!data.length) return <EmptyState />

    switch (chart_type) {
      case "bar":
        return (
          <ChartContainer config={chartConfig} className="h-56 w-full">
            <BarChart data={data}>
              <CartesianGrid strokeDasharray="3 3" vertical={false} />
              <XAxis
                dataKey={x_key}
                tick={{ fontSize: 11 }}
                tickLine={false}
                axisLine={false}
              />
              <YAxis tick={{ fontSize: 11 }} tickLine={false} axisLine={false} />
              <ChartTooltip content={<ChartTooltipContent />} />
              <Legend />
              {y_keys.map((key, i) => (
                <Bar
                  key={key}
                  dataKey={key}
                  fill={CHART_COLORS[i % CHART_COLORS.length]}
                  radius={[4, 4, 0, 0]}
                />
              ))}
            </BarChart>
          </ChartContainer>
        )

      case "line":
        return (
          <ChartContainer config={chartConfig} className="h-56 w-full">
            <LineChart data={data}>
              <CartesianGrid strokeDasharray="3 3" vertical={false} />
              <XAxis
                dataKey={x_key}
                tick={{ fontSize: 11 }}
                tickLine={false}
                axisLine={false}
              />
              <YAxis tick={{ fontSize: 11 }} tickLine={false} axisLine={false} />
              <ChartTooltip content={<ChartTooltipContent />} />
              <Legend />
              {y_keys.map((key, i) => (
                <Line
                  key={key}
                  type="monotone"
                  dataKey={key}
                  stroke={CHART_COLORS[i % CHART_COLORS.length]}
                  strokeWidth={2}
                  dot={false}
                />
              ))}
            </LineChart>
          </ChartContainer>
        )

      case "area":
        return (
          <ChartContainer config={chartConfig} className="h-56 w-full">
            <AreaChart data={data}>
              <CartesianGrid strokeDasharray="3 3" vertical={false} />
              <XAxis
                dataKey={x_key}
                tick={{ fontSize: 11 }}
                tickLine={false}
                axisLine={false}
              />
              <YAxis tick={{ fontSize: 11 }} tickLine={false} axisLine={false} />
              <ChartTooltip content={<ChartTooltipContent />} />
              <Legend />
              {y_keys.map((key, i) => (
                <Area
                  key={key}
                  type="monotone"
                  dataKey={key}
                  stroke={CHART_COLORS[i % CHART_COLORS.length]}
                  fill={CHART_COLORS[i % CHART_COLORS.length]}
                  fillOpacity={0.15}
                  strokeWidth={2}
                />
              ))}
            </AreaChart>
          </ChartContainer>
        )

      case "pie":
        return (
          <ChartContainer config={chartConfig} className="h-56 w-full">
            <PieChart>
              <Pie
                data={data}
                nameKey={x_key}
                dataKey={y_keys[0] ?? "value"}
                cx="50%"
                cy="50%"
                outerRadius={80}
                label={({ name, percent }) =>
                  `${String(name)} ${((percent ?? 0) * 100).toFixed(0)}%`
                }
                labelLine={false}
              >
                {data.map((_, i) => (
                  <Cell
                    key={i}
                    fill={CHART_COLORS[i % CHART_COLORS.length]}
                  />
                ))}
              </Pie>
              <Tooltip />
            </PieChart>
          </ChartContainer>
        )

      case "radar":
        return (
          <ChartContainer config={chartConfig} className="h-56 w-full">
            <RadarChart data={data}>
              <PolarGrid />
              <PolarAngleAxis dataKey={x_key} tick={{ fontSize: 11 }} />
              {y_keys.map((key, i) => (
                <Radar
                  key={key}
                  name={key}
                  dataKey={key}
                  stroke={CHART_COLORS[i % CHART_COLORS.length]}
                  fill={CHART_COLORS[i % CHART_COLORS.length]}
                  fillOpacity={0.2}
                />
              ))}
              <Legend />
              <Tooltip />
            </RadarChart>
          </ChartContainer>
        )

      case "metric":
        return (
          <div className="flex h-40 items-center justify-center">
            <MetricCard
              label={y_keys[0] ?? title}
              value={
                data[0]?.[y_keys[0] as keyof (typeof data)[0]] !== undefined
                  ? Number(data[0][y_keys[0] as keyof (typeof data)[0]])
                  : 0
              }
            />
          </div>
        )

      case "table":
        if (!data.length) return <EmptyState />
        const keys = Object.keys(data[0])
        return (
          <div className="overflow-x-auto">
            <Table>
              <TableHeader>
                <TableRow>
                  {keys.map((k) => (
                    <TableHead key={k}>{k}</TableHead>
                  ))}
                </TableRow>
              </TableHeader>
              <TableBody>
                {data.slice(0, 20).map((row, i) => (
                  <TableRow key={i}>
                    {keys.map((k) => (
                      <TableCell key={k} className="text-xs">
                        {String(row[k as keyof typeof row] ?? "—")}
                      </TableCell>
                    ))}
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        )

      default:
        return <EmptyState />
    }
  }

  return (
    <Card className="h-full">
      <CardHeader className="pb-2">
        <CardTitle className="text-sm font-medium">{title}</CardTitle>
      </CardHeader>
      <CardContent>{renderChart()}</CardContent>
    </Card>
  )
}
