import { cn, formatNumber } from "@/lib/utils"
import { TrendingUp, TrendingDown, Minus } from "lucide-react"

interface MetricCardProps {
  label: string
  value: number | string
  change?: number
  unit?: string
  className?: string
}

export function MetricCard({
  label,
  value,
  change,
  unit,
  className,
}: MetricCardProps) {
  const formattedValue =
    typeof value === "number" ? formatNumber(value) : value

  const trend =
    change === undefined ? null : change > 0 ? "up" : change < 0 ? "down" : "neutral"

  return (
    <div className={cn("space-y-1", className)}>
      <p className="text-xs font-medium text-muted-foreground uppercase tracking-wide">
        {label}
      </p>
      <div className="flex items-end gap-2">
        <span className="text-3xl font-bold tabular-nums">
          {formattedValue}
        </span>
        {unit && (
          <span className="text-sm text-muted-foreground mb-1">{unit}</span>
        )}
      </div>
      {change !== undefined && (
        <div
          className={cn(
            "flex items-center gap-1 text-xs font-medium",
            trend === "up" && "text-emerald-600",
            trend === "down" && "text-destructive",
            trend === "neutral" && "text-muted-foreground"
          )}
        >
          {trend === "up" && <TrendingUp className="h-3 w-3" />}
          {trend === "down" && <TrendingDown className="h-3 w-3" />}
          {trend === "neutral" && <Minus className="h-3 w-3" />}
          <span>
            {change >= 0 ? "+" : ""}
            {change.toFixed(1)}% vs período anterior
          </span>
        </div>
      )}
    </div>
  )
}
