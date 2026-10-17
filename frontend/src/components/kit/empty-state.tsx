import type { ReactNode } from "react"
import { RotateCcw } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Illustration, type IllustrationName } from "@/components/kit/illustrations"
import type { HumanError } from "@/lib/errors"
import { cn } from "@/lib/utils"

/**
 * Estado vacío que guía: ilustración, qué pasará cuando haya datos y el botón
 * de la acción siguiente. `compact` para usar dentro de tarjetas.
 */
export function EmptyState({
  illustration = "empty",
  title,
  description,
  actions,
  compact = false,
  className,
  children,
}: {
  illustration?: IllustrationName
  title: ReactNode
  description?: ReactNode
  actions?: ReactNode
  compact?: boolean
  className?: string
  children?: ReactNode
}) {
  return (
    <div
      className={cn(
        "flex flex-col items-center text-center",
        compact ? "gap-3 px-4 py-8" : "gap-4 px-6 py-12 sm:py-16",
        className
      )}
    >
      <Illustration name={illustration} className={compact ? "h-20" : "h-28 sm:h-32"} />
      <div className="max-w-md space-y-1.5">
        <h3 className={cn("font-display font-semibold leading-tight text-balance", compact ? "text-lg" : "text-2xl")}>
          {title}
        </h3>
        {description && <p className="text-[15px] leading-relaxed text-muted-foreground text-pretty">{description}</p>}
      </div>
      {children}
      {actions && <div className="mt-1 flex flex-wrap items-center justify-center gap-2">{actions}</div>}
    </div>
  )
}

/** Estado de error con mensaje humano y botón para reintentar. */
export function ErrorState({
  error,
  onRetry,
  retrying = false,
  compact = false,
  className,
}: {
  error: HumanError
  onRetry?: () => void
  retrying?: boolean
  compact?: boolean
  className?: string
}) {
  return (
    <EmptyState
      illustration="error"
      compact={compact}
      title={error.title}
      description={error.description}
      className={className}
      actions={
        onRetry && error.action !== "login" ? (
          <Button variant="outline" onClick={onRetry} loading={retrying} loadingText="Intentando…">
            <RotateCcw aria-hidden="true" />
            Intentar de nuevo
          </Button>
        ) : error.action === "login" ? (
          <Button asChild>
            <a href="/login">Iniciar sesión</a>
          </Button>
        ) : undefined
      }
    />
  )
}
