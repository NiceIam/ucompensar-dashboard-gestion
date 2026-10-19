import type { ReactNode } from "react"
import { Loader2, type LucideIcon } from "lucide-react"
import { TONE, type Tone } from "@/components/kit/tone"
import { cn } from "@/lib/utils"

/** Insignia de estado: icono + texto (el color nunca va solo). */
export function StatusBadge({
  tone = "neutral",
  icon: Icon,
  children,
  spinning = false,
  className,
  title,
}: {
  tone?: Tone
  icon?: LucideIcon
  children: ReactNode
  spinning?: boolean
  className?: string
  title?: string
}) {
  const Glyph = spinning ? Loader2 : Icon
  return (
    <span
      title={title}
      className={cn(
        "inline-flex h-7 items-center gap-1.5 whitespace-nowrap rounded-full px-2.5 text-xs font-semibold",
        TONE[tone].badge,
        className
      )}
    >
      {Glyph ? (
        <Glyph className={cn("h-3.5 w-3.5", spinning && "animate-spin")} aria-hidden="true" />
      ) : (
        <span className={cn("h-1.5 w-1.5 rounded-full", TONE[tone].dot)} aria-hidden="true" />
      )}
      {children}
    </span>
  )
}
