import { BRAND } from "@/config/brand"
import { cn } from "@/lib/utils"

/**
 * Isotipo propio: una aguja de brújula (rombo partido en dos) dentro de una
 * baldosa redondeada. La mitad que "apunta adelante" va en papel; la otra en
 * azafrán. Inclinada 35° para sugerir movimiento.
 */
export function BrandMark({
  className,
  title,
  animated = false,
}: {
  className?: string
  title?: string
  /** Balanceo suave de la aguja (para estados de carga). */
  animated?: boolean
}) {
  return (
    <svg
      viewBox="0 0 40 40"
      className={cn("h-9 w-9 shrink-0", className)}
      role={title ? "img" : undefined}
      aria-hidden={title ? undefined : true}
      aria-label={title}
    >
      <rect x="1" y="1" width="38" height="38" rx="11" className="fill-primary" />
      <circle cx="20" cy="20" r="13" fill="none" className="stroke-primary-foreground/25" strokeWidth="1.25" />
      {[0, 90, 180, 270].map((deg) => (
        <line
          key={deg}
          x1="20"
          y1="5.5"
          x2="20"
          y2="8"
          strokeWidth="1.5"
          strokeLinecap="round"
          className="stroke-primary-foreground/45"
          transform={`rotate(${deg} 20 20)`}
        />
      ))}
      <g transform="rotate(35 20 20)">
        <g
          className={cn(animated && "origin-center animate-needle-sway")}
          style={{ transformBox: "fill-box" }}
        >
          <path d="M20 7.5 L24 20 L16 20 Z" className="fill-primary-foreground" />
          <path d="M20 32.5 L24 20 L16 20 Z" className="fill-highlight" />
        </g>
      </g>
      <circle cx="20" cy="20" r="2" className="fill-primary" />
      <circle cx="20" cy="20" r="0.9" className="fill-primary-foreground" />
    </svg>
  )
}

/** Isotipo + nombre en el serif de display. */
export function Wordmark({
  className,
  markClassName,
  showTagline = false,
}: {
  className?: string
  markClassName?: string
  showTagline?: boolean
}) {
  return (
    <span className={cn("inline-flex items-center gap-2.5", className)}>
      <BrandMark className={markClassName} />
      <span className="flex flex-col leading-none">
        <span className="font-display text-[22px] font-semibold tracking-tight">{BRAND.name}</span>
        {showTagline && (
          <span className="mt-1 text-xs font-medium text-muted-foreground">{BRAND.tagline}</span>
        )}
      </span>
    </span>
  )
}
