/**
 * Lógica PURA de los filtros del tablero (sin React): leer y escribir la URL (el filtro se puede compartir),
 * armar lo que se manda al servidor y decir en lenguaje del dueño qué filtros están activos.
 *
 * URL (todo opcional; lo que no se reconoce se ignora, nunca rompe la página):
 *   ?periodo=ultimos-30        atajo: ultimos-7, ultimos-30, ultimos-90, este-mes, mes-anterior, este-anio, todo
 *   ?desde=2026-09-01&hasta=2026-09-30   rango (uno solo de los dos también vale)
 *   ?f_producto=Cemento&f_producto=Pintura   categorías (la clave viene del servidor), un parámetro por valor
 */

import { formatDate, formatDateRange } from "@/lib/format"
import type {
  CategoryFilter,
  DashboardFilters,
  FilterDimension,
  FiltersRequest,
  PeriodFilter,
  PeriodPresetId,
} from "@/types/dashboard-filters"

export const MAX_CATEGORIES = 3
export const MAX_VALUES_PER_CATEGORY = 25
const MAX_VALUE_CHARS = 200
const CATEGORY_PREFIX = "f_"

export const EMPTY_FILTERS: DashboardFilters = { period: null, where: [] }

export interface PresetInfo {
  id: PeriodPresetId
  label: string
  slug: string
}

/** Atajos de periodo en el orden en que se muestran. */
export const PRESETS: PresetInfo[] = [
  { id: "last_7", label: "Últimos 7 días", slug: "ultimos-7" },
  { id: "last_30", label: "Últimos 30 días", slug: "ultimos-30" },
  { id: "last_90", label: "Últimos 90 días", slug: "ultimos-90" },
  { id: "this_month", label: "Este mes", slug: "este-mes" },
  { id: "last_month", label: "Mes anterior", slug: "mes-anterior" },
  { id: "this_year", label: "Este año", slug: "este-anio" },
  { id: "all", label: "Todo", slug: "todo" },
]
const BY_SLUG = new Map(PRESETS.map((p) => [p.slug, p]))
const BY_ID = new Map(PRESETS.map((p) => [p.id, p]))

const ISO_DAY = /^\d{4}-\d{2}-\d{2}$/

/** "2026-09-15" -> Date en hora LOCAL (new Date("2026-09-15") es UTC y en Colombia mostraría el día anterior). */
export function parseIsoDay(value: string | null | undefined): Date | null {
  if (!value || !ISO_DAY.test(value)) return null
  const [y, m, d] = value.split("-").map(Number)
  const date = new Date(y, m - 1, d)
  if (date.getFullYear() !== y || date.getMonth() !== m - 1 || date.getDate() !== d) return null
  if (y < 1900 || y > 2100) return null
  return date
}

export function toIsoDay(date: Date): string {
  const pad = (n: number) => String(n).padStart(2, "0")
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`
}

/** Mensaje en lenguaje llano si el rango no sirve; null si está bien. */
export function validateRange(from: string | undefined, to: string | undefined): string | null {
  if (!from && !to) return "Elige al menos una fecha."
  const a = from ? parseIsoDay(from) : null
  const b = to ? parseIsoDay(to) : null
  if ((from && !a) || (to && !b)) return "Esa fecha no es válida."
  if (a && b && a.getTime() > b.getTime()) return "La fecha inicial es posterior a la final."
  return null
}

// ─── URL <-> filtros ─────────────────────────────────────────────────────────

export function filtersFromParams(params: URLSearchParams): DashboardFilters {
  let period: PeriodFilter | null = null
  const slug = params.get("periodo")
  const preset = slug ? BY_SLUG.get(slug) : undefined
  if (preset) {
    period = preset.id === "all" ? null : { preset: preset.id }
  } else {
    const from = params.get("desde") ?? undefined
    const to = params.get("hasta") ?? undefined
    if ((from || to) && validateRange(from, to) === null) {
      period = { ...(from ? { from } : {}), ...(to ? { to } : {}) }
    }
  }

  const where: CategoryFilter[] = []
  const seen = new Set<string>()
  for (const name of Array.from(new Set(params.keys()))) {
    if (!name.startsWith(CATEGORY_PREFIX)) continue
    const key = name.slice(CATEGORY_PREFIX.length).trim()
    if (!key || key.length > 60 || seen.has(key) || where.length >= MAX_CATEGORIES) continue
    const values = Array.from(
      new Set(
        params
          .getAll(name)
          .map((v) => v.trim())
          .filter((v) => v && v.length <= MAX_VALUE_CHARS)
      )
    ).slice(0, MAX_VALUES_PER_CATEGORY)
    if (values.length) {
      seen.add(key)
      where.push({ key, values })
    }
  }
  return { period, where }
}

/** Escribe los filtros en una copia de `base` (conserva los demás parámetros de la URL). */
export function filtersToParams(filters: DashboardFilters, base?: URLSearchParams): URLSearchParams {
  const out = new URLSearchParams()
  base?.forEach((value, name) => {
    if (name === "periodo" || name === "desde" || name === "hasta" || name.startsWith(CATEGORY_PREFIX)) return
    out.append(name, value)
  })
  const { period } = filters
  if (period?.preset && period.preset !== "all") {
    out.set("periodo", BY_ID.get(period.preset)?.slug ?? "")
  } else if (period && (period.from || period.to)) {
    if (period.from) out.set("desde", period.from)
    if (period.to) out.set("hasta", period.to)
  }
  for (const { key, values } of filters.where) {
    for (const v of values) out.append(`${CATEGORY_PREFIX}${key}`, v)
  }
  return out
}

/** Lo que se manda al servidor; undefined si no hay nada activo (el tablero se calcula como siempre). */
export function filtersToRequest(filters: DashboardFilters): FiltersRequest | undefined {
  const request: FiltersRequest = {}
  const { period } = filters
  if (period?.preset && period.preset !== "all") request.period = { preset: period.preset }
  else if (period && (period.from || period.to)) request.period = { ...(period.from ? { from: period.from } : {}), ...(period.to ? { to: period.to } : {}) }
  if (filters.where.length) request.where = filters.where.map((w) => ({ key: w.key, values: [...w.values] }))
  return request.period || request.where ? request : undefined
}

/** Clave estable para la caché de consultas. */
export function filtersKey(filters: DashboardFilters): string {
  const request = filtersToRequest(filters)
  return request ? JSON.stringify(request) : ""
}

export function hasActiveFilters(filters: DashboardFilters): boolean {
  return filtersToRequest(filters) !== undefined
}

// ─── Textos en lenguaje del dueño ────────────────────────────────────────────

/** "Últimos 30 días" · "Del 3 de enero al 28 de marzo de 2026" · "Desde el 3 de enero de 2026". */
export function periodLabel(period: PeriodFilter | null): string {
  if (!period) return "Todo"
  if (period.preset) return BY_ID.get(period.preset)?.label ?? "Todo"
  const from = parseIsoDay(period.from)
  const to = parseIsoDay(period.to)
  if (from && to) {
    const text = formatDateRange(from, to)
    return text.charAt(0).toUpperCase() + text.slice(1)
  }
  if (from) return `Desde el ${formatDate(from, "long")}`
  if (to) return `Hasta el ${formatDate(to, "long")}`
  return "Todo"
}

export interface FilterChip {
  /** "period" o la clave de la categoría. */
  id: string
  /** Nombre corto: «Período», «Producto». */
  name: string
  /** Valor: «Últimos 30 días», «Cemento, Pintura (+1)». */
  text: string
}

function categoryLabel(key: string, dims: FilterDimension[] | undefined): string {
  const found = dims?.find((d) => d.key === key)
  if (found) return found.label
  const plain = key.replace(/_/g, " ")
  return plain.charAt(0).toUpperCase() + plain.slice(1)
}

export function describeFilters(filters: DashboardFilters, dims?: FilterDimension[]): FilterChip[] {
  const chips: FilterChip[] = []
  if (filters.period) chips.push({ id: "period", name: "Período", text: periodLabel(filters.period) })
  for (const { key, values } of filters.where) {
    const shown = values.slice(0, 2).join(", ")
    chips.push({
      id: key,
      name: categoryLabel(key, dims),
      text: values.length > 2 ? `${shown} (+${values.length - 2})` : shown,
    })
  }
  return chips
}

export function removeFilter(filters: DashboardFilters, id: string): DashboardFilters {
  if (id === "period") return { ...filters, period: null }
  return { ...filters, where: filters.where.filter((w) => w.key !== id) }
}

/** Cambia los valores de una categoría; sin valores la quita; respeta el máximo de categorías. */
export function setCategory(filters: DashboardFilters, key: string, values: string[]): DashboardFilters {
  const clean = Array.from(new Set(values)).slice(0, MAX_VALUES_PER_CATEGORY)
  const rest = filters.where.filter((w) => w.key !== key)
  if (clean.length === 0) return { ...filters, where: rest }
  const exists = filters.where.some((w) => w.key === key)
  if (!exists && filters.where.length >= MAX_CATEGORIES) return filters
  const next = exists ? filters.where.map((w) => (w.key === key ? { key, values: clean } : w)) : [...filters.where, { key, values: clean }]
  return { ...filters, where: next }
}

export function setPeriod(filters: DashboardFilters, period: PeriodFilter | null): DashboardFilters {
  if (period?.preset === "all") return { ...filters, period: null }
  return { ...filters, period }
}

export function sameFilters(a: DashboardFilters, b: DashboardFilters): boolean {
  return filtersKey(a) === filtersKey(b)
}
