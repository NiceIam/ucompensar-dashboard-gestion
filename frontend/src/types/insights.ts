/**
 * Contrato de `GET /api/v1/insights` ("Esta semana en tu negocio").
 * Todo viene calculado de forma exacta por el servidor (sin IA); aquí solo
 * se describe la forma y se normaliza lo que pueda faltar.
 */

export type InsightKind = "money" | "risk" | "opportunity" | "info"

/** Para ordenar y dar tono. Nunca se muestra solo con color: siempre icono + texto. */
export type InsightSeverity = "info" | "attention" | "important"

/** Cómo formatear el valor de una cifra. `percent` viene en escala 0–100 (12,5 = 12,5 %). */
export type MetricUnit = "money" | "count" | "percent" | "days" | "months" | "text"

export interface InsightMetric {
  label: string
  /** Número crudo; con `unit: "text"` llega como texto. */
  value: number | string
  unit: MetricUnit
}

/** La transparencia del hallazgo: de dónde sale la cifra. */
export interface InsightHow {
  steps: string[]
  tables: string[]
  rows_used: number
  /** Avisos honestos de calidad o límites ("el periodo es corto"). */
  notes: string[]
}

export interface Insight {
  id: string
  kind: InsightKind
  severity: InsightSeverity
  title: string
  sentence: string
  metrics: InsightMetric[]
  /** Siguiente paso concreto (opcional). */
  action?: string | null
  /** Pregunta lista para abrir en el chat (opcional). */
  ask?: string | null
  how: InsightHow
}

/** Algo que no se pudo calcular y lo que falta para poder hacerlo. */
export interface MissingInsight {
  id: string
  title: string
  needs: string
}

export interface InsightPeriod {
  /** Fechas ISO "AAAA-MM-DD". */
  from: string
  to: string
  days: number
}

export interface InsightsResponse {
  generated_at: string
  recipe_pack?: string | null
  period?: InsightPeriod | null
  items: Insight[]
  missing: MissingInsight[]
  /** Texto plano listo para compartir por WhatsApp o correo. */
  summary_text?: string | null
}
