/**
 * Tabla única de "tono" -> clases. Avisos, insignias, métricas y barras la
 * consumen para que todo se vea como un solo sistema. Regla: el color nunca
 * va solo; siempre acompaña a un icono y a un texto.
 */
export type Tone = "neutral" | "primary" | "success" | "warning" | "danger" | "info" | "highlight"

interface ToneClasses {
  /** Caja suave con borde: avisos. */
  box: string
  /** Píldora: insignias. */
  badge: string
  /** Punto o icono sólido. */
  dot: string
  /** Icono sobre fondo suave (cuadrito de métrica). */
  iconWrap: string
  /** Texto con contraste AA sobre la superficie. */
  text: string
  /** Relleno sólido de barras. */
  bar: string
}

export const TONE: Record<Tone, ToneClasses> = {
  neutral: {
    box: "border-border bg-muted/60 text-foreground",
    badge: "bg-secondary text-secondary-foreground",
    dot: "bg-muted-foreground",
    iconWrap: "bg-secondary text-foreground/80",
    text: "text-muted-foreground",
    bar: "bg-muted-foreground",
  },
  primary: {
    box: "border-primary/25 bg-primary-soft text-primary-strong",
    badge: "bg-primary-soft text-primary-strong",
    dot: "bg-primary",
    iconWrap: "bg-primary-soft text-primary-strong",
    text: "text-primary-strong",
    bar: "bg-primary",
  },
  success: {
    box: "border-success/30 bg-success-soft text-success-strong",
    badge: "bg-success-soft text-success-strong",
    dot: "bg-success",
    iconWrap: "bg-success-soft text-success-strong",
    text: "text-success-strong",
    bar: "bg-success",
  },
  warning: {
    box: "border-warning/35 bg-warning-soft text-warning-strong",
    badge: "bg-warning-soft text-warning-strong",
    dot: "bg-warning",
    iconWrap: "bg-warning-soft text-warning-strong",
    text: "text-warning-strong",
    bar: "bg-warning",
  },
  danger: {
    box: "border-destructive/30 bg-danger-soft text-danger-strong",
    badge: "bg-danger-soft text-danger-strong",
    dot: "bg-destructive",
    iconWrap: "bg-danger-soft text-danger-strong",
    text: "text-danger-strong",
    bar: "bg-destructive",
  },
  info: {
    box: "border-info/30 bg-info-soft text-info-strong",
    badge: "bg-info-soft text-info-strong",
    dot: "bg-info",
    iconWrap: "bg-info-soft text-info-strong",
    text: "text-info-strong",
    bar: "bg-info",
  },
  highlight: {
    box: "border-highlight/40 bg-highlight-soft text-highlight-strong",
    badge: "bg-highlight-soft text-highlight-strong",
    dot: "bg-highlight",
    iconWrap: "bg-highlight-soft text-highlight-strong",
    text: "text-highlight-strong",
    bar: "bg-highlight",
  },
}
