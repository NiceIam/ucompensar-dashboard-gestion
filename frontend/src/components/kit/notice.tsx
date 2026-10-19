import type { ReactNode } from "react"
import { AlertTriangle, CheckCircle2, Info, OctagonAlert, Sparkles, X, type LucideIcon } from "lucide-react"
import { TONE, type Tone } from "@/components/kit/tone"
import { cn } from "@/lib/utils"

const ICONS: Partial<Record<Tone, LucideIcon>> = {
  success: CheckCircle2,
  warning: AlertTriangle,
  danger: OctagonAlert,
  info: Info,
  primary: Sparkles,
  highlight: Sparkles,
  neutral: Info,
}

/**
 * Aviso en línea: icono + título + detalle + acción opcional a la derecha.
 * Solo los de peligro interrumpen al lector de pantalla (role="alert").
 */
export function Notice({
  tone = "info",
  title,
  children,
  action,
  icon,
  onDismiss,
  className,
}: {
  tone?: Tone
  title?: ReactNode
  children?: ReactNode
  action?: ReactNode
  icon?: LucideIcon
  onDismiss?: () => void
  className?: string
}) {
  const Icon = icon ?? ICONS[tone] ?? Info
  return (
    <div
      role={tone === "danger" ? "alert" : "status"}
      className={cn(
        "relative flex flex-wrap items-start gap-x-3 gap-y-3 rounded-xl border px-4 py-3.5",
        onDismiss && "pr-14",
        TONE[tone].box,
        className
      )}
    >
      <div className="flex min-w-[min(100%,16rem)] flex-1 gap-3">
        <Icon className="mt-0.5 h-5 w-5 shrink-0" aria-hidden="true" />
        <div className="min-w-0 flex-1 space-y-1 text-sm leading-relaxed">
          {title && <p className="font-semibold">{title}</p>}
          {children && <div className="text-foreground/85 dark:text-foreground/80">{children}</div>}
        </div>
      </div>
      {action && <div className="flex shrink-0 items-center gap-1 pl-8">{action}</div>}
      {onDismiss && (
        <button
          type="button"
          onClick={onDismiss}
          className="absolute right-1 top-1 inline-flex h-11 w-11 items-center justify-center rounded-lg opacity-70 transition hover:bg-foreground/5 hover:opacity-100"
          aria-label="Cerrar aviso"
        >
          <X className="h-4 w-4" aria-hidden="true" />
        </button>
      )}
    </div>
  )
}
