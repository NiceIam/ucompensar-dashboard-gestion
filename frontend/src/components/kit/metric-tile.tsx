import type { ReactNode } from "react"
import type { LucideIcon } from "lucide-react"
import { Skeleton } from "@/components/ui/skeleton"
import { TONE, type Tone } from "@/components/kit/tone"
import { cn } from "@/lib/utils"

/**
 * Tarjeta de cifra: etiqueta, número grande en el serif y una línea que
 * explica la cifra en lenguaje llano. El color solo aparece si hay algo que decir.
 */
export function MetricTile({
  label,
  value,
  context,
  icon: Icon,
  tone = "primary",
  loading = false,
  className,
}: {
  label: ReactNode
  value: ReactNode
  context?: ReactNode
  icon?: LucideIcon
  tone?: Tone
  loading?: boolean
  className?: string
}) {
  return (
    <div className={cn("surface flex flex-col gap-3 p-5", className)}>
      <div className="flex items-start justify-between gap-3">
        <p className="text-sm font-medium text-muted-foreground">{label}</p>
        {Icon && (
          <span className={cn("flex h-9 w-9 shrink-0 items-center justify-center rounded-xl", TONE[tone].iconWrap)}>
            <Icon className="h-[18px] w-[18px]" aria-hidden="true" />
          </span>
        )}
      </div>
      {loading ? (
        <div className="space-y-2">
          <Skeleton className="h-9 w-28" />
          <Skeleton className="h-4 w-40" />
        </div>
      ) : (
        <div className="space-y-1">
          <p className="font-display text-[34px] font-semibold leading-none tracking-tight">{value}</p>
          {context && <p className="text-[13px] leading-snug text-muted-foreground">{context}</p>}
        </div>
      )}
    </div>
  )
}
