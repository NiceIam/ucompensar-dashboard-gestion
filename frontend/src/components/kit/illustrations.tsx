import { cn } from "@/lib/utils"

/**
 * Ilustraciones propias en SVG (sin imágenes externas). Usan los tokens de
 * color, así que se ven bien en claro y en oscuro. Son decorativas: siempre
 * van acompañadas de un título y un texto que dicen lo mismo.
 */
export type IllustrationName = "upload" | "chart" | "chat" | "empty" | "compass" | "error" | "sheets"

const common = "fill-none stroke-[1.5] [stroke-linecap:round] [stroke-linejoin:round]"

function Upload() {
  return (
    <>
      <ellipse cx="80" cy="108" rx="54" ry="6" className="fill-foreground/5" />
      <g transform="rotate(-8 62 58)">
        <rect x="30" y="22" width="62" height="74" rx="9" className="fill-card stroke-border" strokeWidth="1.5" />
        {[38, 50, 62, 74].map((y) => (
          <line key={y} x1="40" y1={y} x2="82" y2={y} className="stroke-border" strokeWidth="1.5" />
        ))}
      </g>
      <rect x="58" y="18" width="66" height="80" rx="10" className="fill-card stroke-primary/40" strokeWidth="1.5" />
      <rect x="58" y="18" width="66" height="16" rx="10" className="fill-primary-soft" />
      <rect x="58" y="28" width="66" height="6" className="fill-primary-soft" />
      {[46, 58, 70, 82].map((y, i) => (
        <g key={y}>
          <rect x="68" y={y - 3} width={i % 2 ? 18 : 26} height="6" rx="3" className="fill-muted" />
          <rect x="100" y={y - 3} width="14" height="6" rx="3" className={i === 1 ? "fill-highlight/70" : "fill-muted"} />
        </g>
      ))}
      <circle cx="124" cy="92" r="17" className="fill-primary" />
      <path d="M124 100 V84 M117 90 L124 83 L131 90" className={cn(common, "stroke-primary-foreground")} strokeWidth="2.5" />
      <path d="M36 16 l2 5 5 2 -5 2 -2 5 -2 -5 -5 -2 5 -2 z" className="fill-highlight" />
    </>
  )
}

function Chart() {
  const bars = [34, 52, 44, 68, 58]
  return (
    <>
      <ellipse cx="80" cy="108" rx="58" ry="6" className="fill-foreground/5" />
      <rect x="22" y="16" width="116" height="84" rx="12" className="fill-card stroke-border" strokeWidth="1.5" />
      <line x1="34" y1="86" x2="126" y2="86" className="stroke-border" strokeWidth="1.5" />
      {bars.map((h, i) => (
        <rect
          key={i}
          x={40 + i * 17}
          y={86 - h}
          width="10"
          height={h}
          rx="3"
          className={i === 3 ? "fill-highlight" : "fill-primary/80"}
        />
      ))}
      <path d="M38 62 C 56 56, 66 40, 84 44 S 112 24, 124 22" className={cn(common, "stroke-primary-strong/50")} strokeDasharray="0" />
      <circle cx="124" cy="22" r="3.5" className="fill-highlight stroke-card" strokeWidth="2" />
      <circle cx="132" cy="96" r="13" className="fill-primary-soft stroke-primary/40" strokeWidth="1.5" />
      <path d="M132 87 L135 96 L132 105 L129 96 Z" className="fill-primary" transform="rotate(35 132 96)" />
    </>
  )
}

function Chat() {
  return (
    <>
      <ellipse cx="80" cy="108" rx="52" ry="6" className="fill-foreground/5" />
      <path d="M24 26 h70 a10 10 0 0 1 10 10 v26 a10 10 0 0 1 -10 10 h-46 l-14 12 v-12 h-10 a10 10 0 0 1 -10 -10 v-26 a10 10 0 0 1 10 -10 z" className="fill-card stroke-border" strokeWidth="1.5" />
      <rect x="34" y="38" width="48" height="6" rx="3" className="fill-muted" />
      <rect x="34" y="51" width="32" height="6" rx="3" className="fill-muted" />
      <path d="M70 52 h62 a10 10 0 0 1 10 10 v24 a10 10 0 0 1 -10 10 h-8 v12 l-14 -12 h-40 a10 10 0 0 1 -10 -10 v-24 a10 10 0 0 1 10 -10 z" className="fill-primary" />
      {[14, 22, 18, 28].map((h, i) => (
        <rect key={i} x={84 + i * 11} y={88 - h} width="7" height={h} rx="2" className={i === 3 ? "fill-highlight" : "fill-primary-foreground/85"} />
      ))}
      <path d="M140 22 l2 5 5 2 -5 2 -2 5 -2 -5 -5 -2 5 -2 z" className="fill-highlight" />
    </>
  )
}

function Empty() {
  return (
    <>
      <ellipse cx="80" cy="108" rx="50" ry="6" className="fill-foreground/5" />
      <path d="M34 50 L80 30 L126 50 L80 70 Z" className="fill-primary-soft stroke-primary/40" strokeWidth="1.5" />
      <path d="M34 50 V88 L80 106 V70 Z" className="fill-card stroke-border" strokeWidth="1.5" />
      <path d="M126 50 V88 L80 106 V70 Z" className="fill-muted stroke-border" strokeWidth="1.5" />
      <path d="M58 22 C 60 14, 70 12, 74 18" className={cn(common, "stroke-highlight")} strokeDasharray="3 5" />
      <circle cx="80" cy="16" r="4" className="fill-highlight" />
    </>
  )
}

function Compass() {
  return (
    <>
      <ellipse cx="80" cy="110" rx="46" ry="5" className="fill-foreground/5" />
      <circle cx="80" cy="60" r="44" className="fill-card stroke-border" strokeWidth="1.5" />
      <circle cx="80" cy="60" r="34" className="fill-none stroke-primary/25" strokeWidth="1.5" strokeDasharray="2 6" />
      {Array.from({ length: 12 }).map((_, i) => (
        <line
          key={i}
          x1="80"
          y1="19"
          x2="80"
          y2={i % 3 === 0 ? "26" : "23"}
          className="stroke-muted-foreground/50"
          strokeWidth="1.5"
          transform={`rotate(${i * 30} 80 60)`}
        />
      ))}
      <g transform="rotate(35 80 60)">
        <path d="M80 26 L88 60 L72 60 Z" className="fill-primary" />
        <path d="M80 94 L88 60 L72 60 Z" className="fill-highlight" />
      </g>
      <circle cx="80" cy="60" r="5" className="fill-card stroke-primary" strokeWidth="2" />
      <text x="80" y="14" textAnchor="middle" className="fill-muted-foreground font-sans text-[9px] font-bold">N</text>
    </>
  )
}

function ErrorArt() {
  return (
    <>
      <ellipse cx="80" cy="108" rx="50" ry="6" className="fill-foreground/5" />
      <rect x="30" y="22" width="100" height="74" rx="12" className="fill-card stroke-border" strokeWidth="1.5" />
      <rect x="30" y="22" width="100" height="16" rx="12" className="fill-muted" />
      <rect x="30" y="32" width="100" height="6" className="fill-muted" />
      <circle cx="42" cy="30" r="2.5" className="fill-destructive/70" />
      <circle cx="51" cy="30" r="2.5" className="fill-highlight/80" />
      <path d="M58 58 l10 10 m0 -10 l-10 10 M92 58 l10 10 m0 -10 l-10 10" className={cn(common, "stroke-muted-foreground/60")} strokeWidth="2.5" />
      <path d="M66 84 C 74 78, 86 78, 94 84" className={cn(common, "stroke-muted-foreground/60")} strokeWidth="2.5" />
      <circle cx="128" cy="92" r="14" className="fill-danger-soft stroke-destructive/50" strokeWidth="1.5" />
      <path d="M128 85 V94 M128 99 v0.5" className={cn(common, "stroke-destructive")} strokeWidth="2.5" />
    </>
  )
}

function Sheets() {
  return (
    <>
      <ellipse cx="80" cy="108" rx="56" ry="6" className="fill-foreground/5" />
      {[0, 1, 2].map((i) => (
        <g key={i} transform={`translate(${i * 26} ${i * -6})`}>
          <rect x="24" y="34" width="60" height="70" rx="10" className={i === 2 ? "fill-card stroke-primary/40" : "fill-card stroke-border"} strokeWidth="1.5" />
          <rect x="34" y="46" width={i === 2 ? 30 : 24} height="6" rx="3" className={i === 2 ? "fill-primary/80" : "fill-muted"} />
          <rect x="34" y="60" width="40" height="5" rx="2.5" className="fill-muted" />
          <rect x="34" y="71" width="34" height="5" rx="2.5" className="fill-muted" />
          <rect x="34" y="82" width="38" height="5" rx="2.5" className="fill-muted" />
        </g>
      ))}
      <circle cx="128" cy="30" r="10" className="fill-highlight" />
      <path d="M123.5 30 l3 3 6 -6" className={cn(common, "stroke-highlight-foreground")} strokeWidth="2.25" />
    </>
  )
}

const ART: Record<IllustrationName, () => JSX.Element> = {
  upload: Upload,
  chart: Chart,
  chat: Chat,
  empty: Empty,
  compass: Compass,
  error: ErrorArt,
  sheets: Sheets,
}

export function Illustration({ name, className }: { name: IllustrationName; className?: string }) {
  const Art = ART[name]
  return (
    <svg viewBox="0 0 160 120" className={cn("h-28 w-auto", className)} aria-hidden="true" focusable="false">
      <Art />
    </svg>
  )
}
