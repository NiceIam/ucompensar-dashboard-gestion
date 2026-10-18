import { TrendingDown, TrendingUp, Minus } from "lucide-react"
import { formatChange, formatNumber } from "@/lib/format"
import { cn } from "@/lib/utils"

interface MetricCardProps {
  label: string
  value: number | string
  /** Cambio relativo en porcentaje (12.5 = +12,5 %). */
  change?: number
  unit?: string
  className?: string
}

/** Cifra sola dentro de un widget: etiqueta, número grande en la letra de cifras y cambio opcional. */
export function MetricCard({ label, value, change, unit, className }: MetricCardProps) {
  const formattedValue = typeof value === "number" ? formatNumber(value) : value
  const trend = change === undefined ? null : change > 0 ? "up" : change < 0 ? "down" : "neutral"

  return (
    <div className={cn("space-y-1.5", className)}>
      <p className="text-sm font-medium text-muted-foreground">{label}</p>
      <div className="flex items-end gap-2">
        <span className="font-display text-[40px] font-semibold leading-none tabular">{formattedValue}</span>
        {unit && <span className="mb-1 text-sm text-muted-foreground">{unit}</span>}
      </div>
      {change !== undefined && (
        <p
          className={cn(
            "inline-flex items-center gap-1 text-xs font-semibold",
            trend === "up" && "text-success-strong",
            trend === "down" && "text-danger-strong",
            trend === "neutral" && "text-muted-foreground"
          )}
        >
          {trend === "up" && <TrendingUp className="h-3.5 w-3.5" aria-hidden="true" />}
          {trend === "down" && <TrendingDown className="h-3.5 w-3.5" aria-hidden="true" />}
          {trend === "neutral" && <Minus className="h-3.5 w-3.5" aria-hidden="true" />}
          {formatChange(change / 100)} frente al período anterior
        </p>
      )}
    </div>
  )
}
