import { cn } from "@/lib/utils"
import type { Dashboard } from "@/types/api"

type Preview = NonNullable<Dashboard["preview"]>

/** Escala 0..1 de los puntos (el mínimo de las barras es 0 para que no engañe con las alturas). */
function scale(points: number[], fromZero: boolean): number[] {
  const min = fromZero ? Math.min(0, ...points) : Math.min(...points)
  const max = Math.max(...points)
  const span = max - min || 1
  return points.map((p) => (p - min) / span)
}

/**
 * Vista previa de la forma de un tablero (barras, línea o torta) con los NÚMEROS que el servidor guardó al
 * crearlo. Es decorativa (`aria-hidden`): no tiene ejes ni etiquetas y no representa los datos de hoy.
 */
export function DashboardPreview({ preview, className }: { preview: Preview; className?: string }) {
  const points = preview.points.filter((p) => Number.isFinite(p)).slice(0, 12)
  if (points.length === 0) return null

  return (
    <svg viewBox="0 0 200 80" preserveAspectRatio="xMidYMid meet" className={cn("h-full w-full", className)} aria-hidden="true" focusable="false">
      {preview.type === "line" ? (
        <LinePreview points={points} />
      ) : preview.type === "pie" ? (
        <PiePreview points={points} />
      ) : (
        <BarPreview points={points} />
      )}
    </svg>
  )
}

function BarPreview({ points }: { points: number[] }) {
  const heights = scale(points, true)
  const gap = 6
  const width = (200 - gap * (points.length + 1)) / points.length
  return (
    <g>
      {heights.map((h, i) => (
        <rect
          key={i}
          x={gap + i * (width + gap)}
          y={76 - Math.max(4, h * 68)}
          width={Math.max(3, width)}
          height={Math.max(4, h * 68)}
          rx={3}
          className={i === 0 ? "fill-primary" : "fill-primary/35"}
        />
      ))}
    </g>
  )
}

function LinePreview({ points }: { points: number[] }) {
  const ys = scale(points, false)
  const step = points.length > 1 ? 188 / (points.length - 1) : 0
  const coords = ys.map((y, i) => [6 + i * step, 72 - y * 60] as const)
  const path = coords.map(([x, y], i) => `${i === 0 ? "M" : "L"}${x.toFixed(1)} ${y.toFixed(1)}`).join(" ")
  const area = `${path} L${coords[coords.length - 1][0].toFixed(1)} 76 L${coords[0][0].toFixed(1)} 76 Z`
  return (
    <g>
      <path d={area} className="fill-primary/12" />
      <path d={path} fill="none" strokeWidth={2.5} strokeLinecap="round" strokeLinejoin="round" className="stroke-primary" />
      {coords.length === 1 && <circle cx={coords[0][0]} cy={coords[0][1]} r={3.5} className="fill-primary" />}
    </g>
  )
}

function PiePreview({ points }: { points: number[] }) {
  const positive = points.map((p) => Math.max(0, p))
  const total = positive.reduce((a, b) => a + b, 0) || 1
  const radius = 28
  const circumference = 2 * Math.PI * radius
  let offset = 0
  const shades = ["stroke-primary", "stroke-primary/70", "stroke-primary/50", "stroke-primary/35", "stroke-primary/25"]
  return (
    <g transform="translate(100 40) rotate(-90)">
      {positive.slice(0, 5).map((p, i) => {
        const length = (p / total) * circumference
        const circle = (
          <circle
            key={i}
            r={radius}
            fill="none"
            strokeWidth={14}
            strokeDasharray={`${Math.max(0, length - 1.5)} ${circumference}`}
            strokeDashoffset={-offset}
            className={shades[i]}
          />
        )
        offset += length
        return circle
      })}
    </g>
  )
}
