import type { ReactNode } from "react"
import { cn } from "@/lib/utils"

/**
 * Encabezado de página: una línea pequeña de contexto, el título en el serif
 * de display, una frase que explica la página y las acciones a la derecha
 * (que bajan a su propia línea en pantallas angostas).
 */
export function PageHeader({
  eyebrow,
  title,
  description,
  actions,
  className,
  children,
}: {
  eyebrow?: ReactNode
  title: ReactNode
  description?: ReactNode
  actions?: ReactNode
  className?: string
  children?: ReactNode
}) {
  return (
    <header className={cn("flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between", className)}>
      <div className="min-w-0 space-y-2">
        {eyebrow && (
          <p className="text-[13px] font-semibold uppercase tracking-[0.08em] text-primary">
            {eyebrow}
          </p>
        )}
        <h1 className="font-display text-[30px] font-semibold leading-[1.1] text-balance sm:text-[36px]">{title}</h1>
        {description && (
          <p className="max-w-2xl text-[15px] leading-relaxed text-muted-foreground text-pretty">{description}</p>
        )}
        {children}
      </div>
      {actions && <div className="flex shrink-0 flex-wrap items-center gap-2">{actions}</div>}
    </header>
  )
}

/** Título de sección dentro de una página. */
export function SectionHeader({
  title,
  description,
  action,
  className,
  id,
}: {
  title: ReactNode
  description?: ReactNode
  action?: ReactNode
  className?: string
  id?: string
}) {
  return (
    <div className={cn("flex flex-wrap items-end justify-between gap-x-4 gap-y-2", className)}>
      <div className="min-w-0">
        <h2 id={id} className="font-display text-[22px] font-semibold leading-tight">
          {title}
        </h2>
        {description && <p className="mt-1 text-sm text-muted-foreground">{description}</p>}
      </div>
      {action}
    </div>
  )
}
