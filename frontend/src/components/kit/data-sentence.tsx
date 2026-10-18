import type { ReactNode } from "react"
import type { LucideIcon } from "lucide-react"
import { TONE, type Tone } from "@/components/kit/tone"
import { cn } from "@/lib/utils"

/**
 * "Frase de dato": un hallazgo contado en una frase, con la cifra destacada.
 * Ejemplo: <DataSentence icon={TrendingUp}>Marzo cerró en <Figure>$ 12,4 M</Figure>,
 * 18 % más que febrero.</DataSentence>
 */
export function DataSentence({
  children,
  icon: Icon,
  tone = "primary",
  className,
}: {
  children: ReactNode
  icon?: LucideIcon
  tone?: Tone
  className?: string
}) {
  return (
    <div className={cn("flex items-start gap-3", className)}>
      {Icon && (
        <span className={cn("mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-lg", TONE[tone].iconWrap)}>
          <Icon className="h-4 w-4" aria-hidden="true" />
        </span>
      )}
      <p className="min-w-0 text-[16px] leading-relaxed text-foreground/90 text-pretty">{children}</p>
    </div>
  )
}

/** Cifra destacada dentro de una frase: letra de cifras, peso alto y resaltado naranja suave. */
export function Figure({ children, className }: { children: ReactNode; className?: string }) {
  // Cifras cortas no se parten; frases largas (un rango de fechas) sí pueden bajar de línea.
  const short = typeof children !== "string" || children.length <= 18
  return (
    <strong
      className={cn(
        short && "whitespace-nowrap",
        "font-display text-[1.12em] font-semibold [box-decoration-break:clone] text-foreground [background-image:linear-gradient(transparent_62%,hsl(var(--highlight)/0.35)_62%)]",
        className
      )}
    >
      {children}
    </strong>
  )
}
