import { cn } from "@/lib/utils"

/**
 * Barra de progreso. Con `value` (0..100) es determinada; sin él muestra un
 * barrido indeterminado. La etiqueta se anuncia a lectores de pantalla.
 */
export function ProgressBar({
  value,
  label,
  className,
  size = "md",
}: {
  value?: number
  label: string
  className?: string
  size?: "sm" | "md"
}) {
  const determinate = typeof value === "number"
  const pct = determinate ? Math.max(0, Math.min(100, value)) : undefined
  return (
    <div
      role="progressbar"
      aria-label={label}
      aria-valuemin={determinate ? 0 : undefined}
      aria-valuemax={determinate ? 100 : undefined}
      aria-valuenow={determinate ? Math.round(pct!) : undefined}
      aria-valuetext={determinate ? `${Math.round(pct!)} %` : label}
      className={cn("relative w-full overflow-hidden rounded-full bg-muted", size === "sm" ? "h-1.5" : "h-2", className)}
    >
      {determinate ? (
        <div
          className="h-full rounded-full bg-primary transition-[width] duration-500 ease-out"
          style={{ width: `${pct}%` }}
        />
      ) : (
        <div className="absolute inset-y-0 left-0 w-2/5 animate-sweep rounded-full bg-gradient-to-r from-primary/0 via-primary to-primary/0" />
      )}
    </div>
  )
}
