import Image from "next/image"
import { BRAND } from "@/config/brand"
import { cn } from "@/lib/utils"

/**
 * Isotipo propio: una aguja de brújula (rombo partido en dos) dentro de una
 * baldosa redondeada en el naranja de la universidad. La mitad que "apunta
 * adelante" va en blanco; la otra en tinta, como el nombre en el logo
 * institucional. Inclinada 35° para sugerir movimiento.
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
      <rect x="1" y="1" width="38" height="38" rx="11" className="fill-highlight" />
      <circle cx="20" cy="20" r="13" fill="none" className="stroke-white/35" strokeWidth="1.25" />
      {[0, 90, 180, 270].map((deg) => (
        <line
          key={deg}
          x1="20"
          y1="5.5"
          x2="20"
          y2="8"
          strokeWidth="1.5"
          strokeLinecap="round"
          className="stroke-white/60"
          transform={`rotate(${deg} 20 20)`}
        />
      ))}
      <g transform="rotate(35 20 20)">
        <g
          className={cn(animated && "origin-center animate-needle-sway")}
          style={{ transformBox: "fill-box" }}
        >
          <path d="M20 7.5 L24 20 L16 20 Z" className="fill-white" />
          <path d="M20 32.5 L24 20 L16 20 Z" className="fill-highlight-foreground" />
        </g>
      </g>
      <circle cx="20" cy="20" r="2" className="fill-highlight-foreground" />
      <circle cx="20" cy="20" r="0.9" className="fill-white" />
    </svg>
  )
}

/** Isotipo + nombre en la letra de titulares. */
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

/** Proporción del logo horizontal oficial (`/public/logo-ucompensar.png`, 1548 × 227). */
const UNIVERSITY_LOGO_RATIO = 1548 / 227

/**
 * Logo oficial de la Fundación Universitaria Compensar, sin recolorear ni
 * recortar. Sobre fondos oscuros va en una placa clara (el nombre del logo es
 * negro), para no alterar su identidad.
 */
export function UniversityLogo({ height = 28, className }: { height?: number; className?: string }) {
  return (
    <span className={cn("inline-flex shrink-0 rounded-lg dark:bg-white dark:px-2.5 dark:py-1.5", className)}>
      <Image
        src="/logo-ucompensar.png"
        alt={BRAND.institution}
        width={Math.round(height * UNIVERSITY_LOGO_RATIO)}
        height={height}
        style={{ height, width: "auto" }}
      />
    </span>
  )
}
