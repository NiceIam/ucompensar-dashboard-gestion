import { cn } from "@/lib/utils"

/*
 * Motivo firma de Proyecto PI0320251: la retícula de puntos del logo de la Fundación
 * Universitaria Compensar, usada como textura y como animación de carga.
 * Todo aquí es decorativo (aria-hidden): el significado siempre lo da el texto.
 */

const FADES = {
  /** Se desvanece hacia abajo a la izquierda (paneles con contenido a la izquierda). */
  "top-right": "[mask-image:radial-gradient(120%_90%_at_100%_0%,#000_10%,transparent_62%)]",
  "bottom-right": "[mask-image:radial-gradient(120%_100%_at_100%_100%,#000_8%,transparent_60%)]",
  /** Banda centrada: separadores y estados vacíos. */
  center: "[mask-image:radial-gradient(60%_70%_at_50%_50%,#000_20%,transparent_75%)]",
  none: "",
} as const

/** Capa de puntos en retícula para el fondo de un contenedor `relative`. */
export function DotField({
  fade = "top-right",
  className,
}: {
  fade?: keyof typeof FADES
  className?: string
}) {
  return <div aria-hidden="true" className={cn("bg-dots pointer-events-none absolute inset-0", FADES[fade], className)} />
}

/** Línea de puntos para separar secciones con un guiño de marca. */
export function DotRule({ className }: { className?: string }) {
  return (
    <div
      aria-hidden="true"
      className={cn(
        "bg-dots h-2 w-full [--dots-alpha:0.45] [--dots-gap:12px] [--dots-size:1.6px] [background-position:0_50%] [background-repeat:repeat-x]",
        FADES.center,
        className
      )}
    />
  )
}

const SIZES = {
  sm: { dot: "h-1.5 w-1.5", gap: "gap-1" },
  md: { dot: "h-2.5 w-2.5", gap: "gap-1.5" },
  lg: { dot: "h-3.5 w-3.5", gap: "gap-2" },
} as const

/** Con movimiento reducido la retícula queda quieta, con una diagonal encendida. */
const STILL = [1, 0.5, 0.22, 0.5, 1, 0.5, 0.22, 0.5, 1]

/**
 * "Puntos que se encienden": retícula de 3 × 3 cuyos puntos se prenden en ola
 * diagonal. Úsalo junto a un texto que diga qué está pasando (role="status").
 */
export function DotsLoader({ size = "md", className }: { size?: keyof typeof SIZES; className?: string }) {
  const s = SIZES[size]
  return (
    <span aria-hidden="true" className={cn("inline-grid shrink-0 grid-cols-3", s.gap, className)}>
      {STILL.map((opacity, i) => {
        const wave = (i % 3) + Math.floor(i / 3)
        return (
          <span
            key={i}
            className={cn("rounded-full bg-highlight animate-dot-light motion-reduce:animate-none", s.dot)}
            style={{ animationDelay: `${wave * 150}ms`, opacity }}
          />
        )
      })}
    </span>
  )
}

/**
 * Racimo de puntos grandes para paneles de marca: una retícula donde algunos
 * puntos están "encendidos" en naranja y el resto apenas se insinúa.
 */
const CLUSTER = [
  [0, 0, 1, 0, 0],
  [0, 1, 2, 1, 0],
  [1, 2, 3, 2, 1],
  [0, 1, 2, 3, 2],
  [0, 0, 1, 2, 3],
]
const CLUSTER_ALPHA = ["opacity-[0.07]", "opacity-[0.16]", "opacity-[0.4]", "opacity-100"]

export function DotCluster({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 250 250" aria-hidden="true" focusable="false" className={cn("pointer-events-none", className)}>
      {CLUSTER.flatMap((row, y) =>
        row.map((level, x) => (
          <circle key={`${x}-${y}`} cx={25 + x * 50} cy={25 + y * 50} r="23" className={cn("fill-highlight", CLUSTER_ALPHA[level])} />
        ))
      )}
    </svg>
  )
}
