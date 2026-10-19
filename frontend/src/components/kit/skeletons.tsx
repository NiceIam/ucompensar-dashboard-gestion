import { Skeleton } from "@/components/ui/skeleton"
import { cn } from "@/lib/utils"

/** Esqueletos con la forma de lo que viene, para que nada "salte" al cargar. */
export function CardGridSkeleton({ count = 3, className }: { count?: number; className?: string }) {
  return (
    <div className={cn("auto-grid gap-4", className)} aria-busy="true" aria-label="Cargando">
      {Array.from({ length: count }).map((_, i) => (
        <div key={i} className="surface space-y-4 p-5">
          <div className="flex items-center gap-3">
            <Skeleton className="h-10 w-10 rounded-xl" />
            <div className="flex-1 space-y-2">
              <Skeleton className="h-4 w-2/3" />
              <Skeleton className="h-3 w-1/3" />
            </div>
          </div>
          <Skeleton className="h-3 w-full" />
          <Skeleton className="h-3 w-4/5" />
        </div>
      ))}
    </div>
  )
}

export function MetricRowSkeleton({ count = 3 }: { count?: number }) {
  return (
    <div className="auto-grid gap-4 [--auto-grid-min:12rem]" aria-busy="true" aria-label="Cargando">
      {Array.from({ length: count }).map((_, i) => (
        <div key={i} className="surface space-y-3 p-5">
          <Skeleton className="h-4 w-24" />
          <Skeleton className="h-9 w-28" />
          <Skeleton className="h-3 w-40" />
        </div>
      ))}
    </div>
  )
}

export function ChartSkeleton({ className }: { className?: string }) {
  const bars = [45, 70, 55, 85, 60, 75, 40]
  return (
    <div className={cn("surface p-5", className)} aria-busy="true" aria-label="Cargando gráfico">
      <Skeleton className="h-5 w-48" />
      <Skeleton className="mt-2 h-3 w-64" />
      <div className="mt-6 flex h-40 items-end gap-3">
        {bars.map((h, i) => (
          <Skeleton key={i} className="flex-1 rounded-b-none rounded-t-md" style={{ height: `${h}%` }} />
        ))}
      </div>
    </div>
  )
}

export function ListSkeleton({ rows = 4 }: { rows?: number }) {
  return (
    <div className="space-y-2" aria-busy="true" aria-label="Cargando">
      {Array.from({ length: rows }).map((_, i) => (
        <Skeleton key={i} className="h-14 w-full rounded-xl" />
      ))}
    </div>
  )
}

/** Esqueleto de una tarjeta de hallazgo: título, frase, tres cifras y botones. */
export function InsightCardSkeleton({ count = 3, className }: { count?: number; className?: string }) {
  return (
    <div className={cn("auto-grid gap-4 [--auto-grid-min:20rem]", className)} aria-busy="true" aria-label="Buscando tus hallazgos">
      {Array.from({ length: count }).map((_, i) => (
        <div key={i} className="surface space-y-4 overflow-hidden">
          <Skeleton className="h-1 w-full rounded-none" />
          <div className="space-y-4 p-5 sm:p-6">
            <Skeleton className="h-7 w-28 rounded-full" />
            <Skeleton className="h-7 w-4/5" />
            <div className="space-y-2">
              <Skeleton className="h-4 w-full" />
              <Skeleton className="h-4 w-11/12" />
              <Skeleton className="h-4 w-2/3" />
            </div>
            <div className="grid grid-cols-3 gap-2">
              <Skeleton className="h-16 rounded-xl" />
              <Skeleton className="h-16 rounded-xl" />
              <Skeleton className="h-16 rounded-xl" />
            </div>
            <Skeleton className="h-11 w-44 rounded-xl" />
          </div>
        </div>
      ))}
    </div>
  )
}
