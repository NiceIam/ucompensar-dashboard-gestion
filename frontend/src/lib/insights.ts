/**
 * Lógica pura de "Esta semana en tu negocio": formato de las cifras según su
 * unidad, orden y selección de hallazgos, periodo legible y texto para
 * compartir. Sin React: se prueba aislada.
 */
import { NBSP, formatCompact, formatDateRange, formatNumber, monthName } from "@/lib/format"
import type { Insight, InsightMetric, InsightPeriod, InsightSeverity, InsightsResponse } from "@/types/insights"

/* ── Severidad ─────────────────────────────────────────── */

export const SEVERITY_RANK: Record<InsightSeverity, number> = { important: 3, attention: 2, info: 1 }

/** Etiqueta visible de cada severidad (el color siempre va acompañado de este texto y de un icono). */
export const SEVERITY_LABEL: Record<InsightSeverity, string> = {
  important: "Importante",
  attention: "Ojo",
  info: "Dato",
}

/** Más importante primero; a igual severidad se respeta el orden del servidor (impacto). */
export function sortInsights(items: Insight[]): Insight[] {
  return items
    .map((item, index) => ({ item, index }))
    .sort((a, b) => (SEVERITY_RANK[b.item.severity] ?? 0) - (SEVERITY_RANK[a.item.severity] ?? 0) || a.index - b.index)
    .map(({ item }) => item)
}

/** Los N hallazgos más importantes (3 en el inicio). */
export function topInsights(items: Insight[], n = 3): Insight[] {
  return sortInsights(items).slice(0, n)
}

/* ── Cifras ────────────────────────────────────────────── */

/** Dinero para titulares: "$47,6 M" desde un millón, "$360.000" por debajo. */
export function formatMoneyShort(value: number): string {
  if (!Number.isFinite(value)) return "—"
  const sign = value < 0 ? "-" : ""
  const abs = Math.abs(value)
  if (abs >= 1_000_000) return `${sign}$${formatCompact(abs)}`
  return `${sign}$${formatNumber(abs, abs >= 1000 ? 0 : 2)}`
}

/** Una cifra del hallazgo, lista para mostrar según su unidad. */
export function formatMetric(metric: Pick<InsightMetric, "value" | "unit">): string {
  const { value, unit } = metric
  if (unit === "text") return String(value ?? "")
  const n = typeof value === "number" ? value : Number(value)
  if (!Number.isFinite(n)) return "—"
  switch (unit) {
    case "money":
      return formatMoneyShort(n)
    case "percent":
      return `${formatNumber(n, 1)}${NBSP}%`
    case "count":
      return formatNumber(n, 0)
    case "days": {
      const d = Math.round(n)
      if (d === 0 && n > 0) return `menos de${NBSP}1${NBSP}día`
      return `${formatNumber(d, 0)}${NBSP}${Math.abs(d) === 1 ? "día" : "días"}`
    }
    case "months": {
      const text = formatNumber(n, Math.abs(n) >= 10 ? 0 : 1)
      return `${text}${NBSP}${text === "1" ? "mes" : "meses"}`
    }
    default:
      return String(value)
  }
}

/* ── Fechas ────────────────────────────────────────────── */

/** "2025-07-02" como fecha LOCAL (new Date("2025-07-02") sería UTC y en Colombia caería el día anterior). */
export function parseIsoDate(iso: string): Date | null {
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso)
  if (!m) return null
  const d = new Date(Number(m[1]), Number(m[2]) - 1, Number(m[3]))
  return Number.isNaN(d.getTime()) ? null : d
}

/** "Ventas del 2 de julio al 8 de octubre de 2025". */
export function periodLabel(period?: InsightPeriod | null): string | null {
  if (!period) return null
  const from = parseIsoDate(period.from)
  const to = parseIsoDate(period.to)
  if (!from || !to) return null
  return `Ventas ${formatDateRange(from, to)}`
}

const WEEKDAYS = ["domingo", "lunes", "martes", "miércoles", "jueves", "viernes", "sábado"]

/** "lunes 19 de octubre" */
export function dayLabel(date: Date): string {
  return `${WEEKDAYS[date.getDay()]} ${date.getDate()} de ${monthName(date.getMonth())}`
}

/* ── Hojas usadas ──────────────────────────────────────── */

/** "ventas_2025" -> "Ventas 2025". */
export function prettyTable(name: string): string {
  const t = name.replace(/[_-]+/g, " ").trim()
  return t.charAt(0).toUpperCase() + t.slice(1)
}

/** ["Productos", "Ventas"] -> "Productos y Ventas"; tres o más con comas. */
export function joinNames(names: string[]): string {
  if (names.length <= 1) return names[0] ?? ""
  return `${names.slice(0, -1).join(", ")} y ${names[names.length - 1]}`
}

/* ── Compartir ─────────────────────────────────────────── */

/**
 * Texto del resumen para compartir. Si el servidor lo manda, se usa tal cual;
 * si no, se arma con los hallazgos para que compartir nunca quede roto.
 */
export function buildSummaryText(data: Pick<InsightsResponse, "items" | "summary_text" | "generated_at">): string {
  const fromServer = data.summary_text?.trim()
  if (fromServer) return fromServer
  const when = new Date(data.generated_at)
  const header = Number.isNaN(when.getTime()) ? "Resumen de tu negocio" : `Resumen de tu negocio (${dayLabel(when)})`
  const lines = sortInsights(data.items).map((i) => `• ${i.sentence}`)
  return [header, ...lines].join("\n")
}

/** Enlace de WhatsApp (sin número: la persona elige el contacto) con el texto ya escrito. */
export function whatsappUrl(text: string): string {
  return `https://wa.me/?text=${encodeURIComponent(text)}`
}

/* ── Respuesta del servidor ────────────────────────────── */

/** Rellena lo que pueda faltar para que la pantalla nunca se rompa por un campo ausente. */
export function normalizeInsights(raw: Partial<InsightsResponse> | null | undefined): InsightsResponse {
  const data = raw ?? {}
  return {
    generated_at: data.generated_at ?? new Date().toISOString(),
    recipe_pack: data.recipe_pack ?? null,
    period: data.period ?? null,
    summary_text: data.summary_text ?? null,
    missing: Array.isArray(data.missing) ? data.missing : [],
    items: (Array.isArray(data.items) ? data.items : []).map((item) => ({
      ...item,
      metrics: Array.isArray(item.metrics) ? item.metrics : [],
      how: {
        steps: item.how?.steps ?? [],
        tables: item.how?.tables ?? [],
        rows_used: item.how?.rows_used ?? 0,
        notes: item.how?.notes ?? [],
      },
    })),
  }
}
