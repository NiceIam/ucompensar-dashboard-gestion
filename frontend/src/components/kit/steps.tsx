import { Check, X } from "lucide-react"
import { cn } from "@/lib/utils"

export interface Step {
  id: string
  label: string
}

/**
 * Indicador de pasos accesible. En pantallas angostas se resume como
 * "Paso 2 de 4 · Entendiendo tus datos" con una barra; en anchas muestra
 * todos los pasos conectados.
 */
export function Steps({
  steps,
  current,
  failed = false,
  className,
}: {
  steps: Step[]
  /** Índice del paso actual (0..n-1). Si es >= n, todos están completos. */
  current: number
  /** Marca el paso actual como fallido. */
  failed?: boolean
  className?: string
}) {
  const total = steps.length
  const clamped = Math.min(current, total - 1)
  const allDone = current >= total
  return (
    <nav aria-label="Progreso" className={className}>
      {/* Versión compacta */}
      <div className="sm:hidden">
        <p className="text-sm font-medium">
          <span className="text-muted-foreground">
            Paso {Math.min(current + 1, total)} de {total} ·{" "}
          </span>
          {steps[clamped]?.label}
        </p>
        <div className="mt-2 flex gap-1.5" aria-hidden="true">
          {steps.map((s, i) => (
            <span
              key={s.id}
              className={cn(
                "h-1.5 flex-1 rounded-full transition-colors duration-300",
                i < current || allDone ? "bg-primary" : i === current ? (failed ? "bg-destructive" : "bg-highlight") : "bg-muted"
              )}
            />
          ))}
        </div>
      </div>

      {/* Versión completa */}
      <ol className="hidden items-center sm:flex">
        {steps.map((s, i) => {
          const done = i < current || allDone
          const active = i === current && !allDone
          return (
            <li key={s.id} className={cn("flex items-center", i < total - 1 && "flex-1")}>
              <div className="flex items-center gap-2.5" aria-current={active ? "step" : undefined}>
                <span
                  className={cn(
                    "flex h-8 w-8 shrink-0 items-center justify-center rounded-full border text-[13px] font-bold transition-colors duration-300",
                    done && "border-primary bg-primary text-primary-foreground",
                    active && !failed && "border-highlight bg-highlight-soft text-highlight-strong ring-4 ring-highlight/20",
                    active && failed && "border-destructive bg-danger-soft text-danger-strong",
                    !done && !active && "border-border bg-card text-muted-foreground"
                  )}
                >
                  {done ? (
                    <Check className="h-4 w-4" aria-hidden="true" />
                  ) : active && failed ? (
                    <X className="h-4 w-4" aria-hidden="true" />
                  ) : (
                    i + 1
                  )}
                </span>
                <span
                  className={cn(
                    "whitespace-nowrap text-sm",
                    active ? "font-semibold text-foreground" : done ? "font-medium text-foreground/80" : "text-muted-foreground"
                  )}
                >
                  {s.label}
                  <span className="sr-only">{done ? " (listo)" : active ? (failed ? " (con un problema)" : " (en curso)") : " (pendiente)"}</span>
                </span>
              </div>
              {i < total - 1 && (
                <span
                  aria-hidden="true"
                  className={cn("mx-3 h-px flex-1 transition-colors duration-300", done ? "bg-primary" : "bg-border")}
                />
              )}
            </li>
          )
        })}
      </ol>
    </nav>
  )
}
