/**
 * Cifras principales (KPI) de un tablero: en qué unidad mostrarlas.
 *
 * Regla: el signo $ SOLO aparece con una pista monetaria clara DEL DATO
 * (unidad explícita, icono de dinero o columna de origen de dinero). La
 * etiqueta del KPI no cuenta: "Total Ventas" puede ser el número de filas de
 * la hoja «Ventas» (así lo manda hoy el backend, con icono "Database").
 */
import { columnKind } from "@/lib/data-vocabulary"
import { formatCompact, formatMoney, formatNumber } from "@/lib/format"

export type KpiUnit = "money" | "count" | "number"

export interface KpiLike {
  label: string
  value: number
  icon?: string
  unit?: string
  column?: string
}

const MONEY_ICON = /dollar|money|cash|peso|receipt|banknote|wallet|coins|currency|landmark|piggy/i
const COUNT_ICON = /database|hash|rows|table|list|count|users?|cart|package|box|file|layers|trending|activity|chart/i

export function kpiUnit(kpi: KpiLike): KpiUnit {
  // 1. Unidad explícita del backend: siempre gana.
  if (kpi.unit === "money" || kpi.unit === "count" || kpi.unit === "number") return kpi.unit
  const icon = kpi.icon ?? ""
  // 2. Pistas monetarias del dato.
  if (MONEY_ICON.test(icon)) return "money"
  if (kpi.column && columnKind({ name: kpi.column, type: "number" }) === "money") return "money"
  // 3. Sin pista de dinero: cantidad si es un conteo o un entero; si no, número.
  if (COUNT_ICON.test(icon) || Number.isInteger(kpi.value)) return "count"
  return "number"
}

/** Valor del KPI listo para mostrar ("$ 48,3 M", "1.284", "40"). */
export function formatKpiValue(kpi: KpiLike): string {
  const v = Number(kpi.value)
  if (!Number.isFinite(v)) return "—"
  if (kpiUnit(kpi) === "money") return Math.abs(v) >= 1_000_000 ? formatMoney(v, { compact: true }) : formatMoney(v)
  return Math.abs(v) >= 100_000 ? formatCompact(v) : formatNumber(v)
}
