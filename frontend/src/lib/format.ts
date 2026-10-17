/**
 * Formatos en español de Colombia (es-CO): miles con punto, decimales con coma,
 * fechas en palabras. Todo número o fecha que vea la persona pasa por aquí.
 */

const LOCALE = "es-CO"

const numberFmt = new Intl.NumberFormat(LOCALE, { maximumFractionDigits: 2 })
const integerFmt = new Intl.NumberFormat(LOCALE, { maximumFractionDigits: 0 })

/** Espacios del motor Intl (no separables) a espacios normales: más fácil de leer y de probar. */
function plainSpaces(text: string): string {
  return text.replace(/[  ]/g, " ")
}

/** 1234567.891 -> "1.234.567,89" */
export function formatNumber(value: number, maximumFractionDigits = 2): string {
  if (!Number.isFinite(value)) return "—"
  const fmt =
    maximumFractionDigits === 2
      ? numberFmt
      : maximumFractionDigits === 0
        ? integerFmt
        : new Intl.NumberFormat(LOCALE, { maximumFractionDigits })
  return plainSpaces(fmt.format(value))
}

/**
 * Cifra corta para titulares y ejes: 850 -> "850", 12_400 -> "12,4 mil",
 * 12_400_000 -> "12,4 M", 3_200_000_000 -> "3.200 M" (en Colombia "mil millones"
 * se lee mejor así que con "B").
 */
export function formatCompact(value: number): string {
  if (!Number.isFinite(value)) return "—"
  const abs = Math.abs(value)
  const sign = value < 0 ? "-" : ""
  const one = (n: number) => formatNumber(n, n < 10 ? 1 : n < 100 ? 1 : 0)
  if (abs >= 1_000_000) return `${sign}${one(abs / 1_000_000)} M`
  if (abs >= 10_000) return `${sign}${one(abs / 1_000)} mil`
  return `${sign}${formatNumber(abs, abs < 100 ? 2 : 0)}`
}

/** Dinero en pesos: completo ("$ 12.400.000") o compacto ("$ 12,4 M"). */
export function formatMoney(value: number, options: { compact?: boolean } = {}): string {
  if (!Number.isFinite(value)) return "—"
  const sign = value < 0 ? "-" : ""
  const abs = Math.abs(value)
  if (options.compact) return `${sign}$ ${formatCompact(abs)}`
  return `${sign}$ ${formatNumber(abs, abs >= 1000 ? 0 : 2)}`
}

/** Proporción (0..1) como porcentaje: 0.183 -> "18 %", 0.0042 -> "0,4 %". */
export function formatShare(ratio: number): string {
  if (!Number.isFinite(ratio)) return "—"
  const pct = ratio * 100
  const digits = Math.abs(pct) < 10 && pct !== Math.round(pct) ? 1 : 0
  return `${formatNumber(pct, digits)} %`
}

/** Cambio relativo con signo: 0.18 -> "+18 %", -0.05 -> "-5 %". */
export function formatChange(ratio: number): string {
  if (!Number.isFinite(ratio)) return "—"
  const text = formatShare(Math.abs(ratio))
  if (ratio > 0) return `+${text}`
  if (ratio < 0) return `-${text}`
  return text
}

/** "1 fila" / "300 filas" con miles formateados. */
export function pluralize(count: number, singular: string, plural: string): string {
  return `${formatNumber(count, 0)} ${count === 1 ? singular : plural}`
}

function toDate(value: string | number | Date): Date | null {
  const d = value instanceof Date ? value : new Date(value)
  return Number.isNaN(d.getTime()) ? null : d
}

const MONTHS = [
  "enero", "febrero", "marzo", "abril", "mayo", "junio",
  "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
]

/** Nombre del mes en minúscula: 0 -> "enero". */
export function monthName(monthIndex: number): string {
  return MONTHS[((monthIndex % 12) + 12) % 12]
}

/**
 * Fecha legible.
 *  - "short":  "16 oct 2026"
 *  - "long":   "16 de octubre de 2026"
 *  - "month":  "octubre de 2026"
 */
export function formatDate(
  value: string | number | Date,
  style: "short" | "long" | "month" = "short"
): string {
  const d = toDate(value)
  if (!d) return "—"
  if (style === "long") return `${d.getDate()} de ${monthName(d.getMonth())} de ${d.getFullYear()}`
  if (style === "month") return `${monthName(d.getMonth())} de ${d.getFullYear()}`
  return `${d.getDate()} ${monthName(d.getMonth()).slice(0, 3)} ${d.getFullYear()}`
}

/** Rango legible: "del 3 de enero al 28 de marzo de 2026" (o "el 3 de enero de 2026" si es un día). */
export function formatDateRange(from: Date, to: Date): string {
  const sameDay = from.toDateString() === to.toDateString()
  if (sameDay) return `el ${formatDate(from, "long")}`
  const sameYear = from.getFullYear() === to.getFullYear()
  const start = sameYear
    ? `${from.getDate()} de ${monthName(from.getMonth())}`
    : formatDate(from, "long")
  return `del ${start} al ${formatDate(to, "long")}`
}

function startOfDay(d: Date): number {
  return new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime()
}

/** "hoy", "ayer", "hace 3 días", "hace 2 semanas", "hace 4 meses", "hace 1 año". */
export function formatRelative(value: string | number | Date, now: Date = new Date()): string {
  const d = toDate(value)
  if (!d) return "—"
  const days = Math.round((startOfDay(now) - startOfDay(d)) / 86_400_000)
  if (days <= 0) return "hoy"
  if (days === 1) return "ayer"
  if (days < 7) return `hace ${days} días`
  if (days < 30) {
    const w = Math.floor(days / 7)
    return `hace ${w} ${w === 1 ? "semana" : "semanas"}`
  }
  if (days < 365) {
    const m = Math.floor(days / 30)
    return `hace ${m} ${m === 1 ? "mes" : "meses"}`
  }
  const y = Math.floor(days / 365)
  return `hace ${y} ${y === 1 ? "año" : "años"}`
}

/** 0 -> "0 B", 1536 -> "1,5 KB". */
export function formatFileSize(bytes: number): string {
  if (!Number.isFinite(bytes) || bytes <= 0) return "0 B"
  const units = ["B", "KB", "MB", "GB"]
  const i = Math.min(units.length - 1, Math.floor(Math.log(bytes) / Math.log(1024)))
  const value = bytes / Math.pow(1024, i)
  return `${formatNumber(value, i === 0 ? 0 : 1)} ${units[i]}`
}

/** Saludo según la hora local. */
export function greeting(now: Date = new Date()): string {
  const h = now.getHours()
  if (h < 5) return "Hola"
  if (h < 12) return "Buenos días"
  if (h < 19) return "Buenas tardes"
  return "Buenas noches"
}
