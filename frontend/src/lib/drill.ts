/**
 * Lógica PURA del detalle al tocar un dato (sin React): qué se le pide al servidor, cómo se dibuja la barra de
 * proporción de cada fila y las frases para lectores de pantalla.
 */

import { prettyLabel } from "@/components/chat/message-content"
import { formatCompact, formatMoney, formatNumber, formatShare } from "@/lib/format"
import { filtersToRequest } from "@/lib/dashboard-filters"
import type { DashboardFilters, DrillRequest, DrillResponse, DrillRow } from "@/types/dashboard-filters"

/** Un dato del gráfico tal como lo entrega el servidor (con la clave exacta cuando el nombre se recorta). */
export interface PointRef {
  name: string
  value: number
  /** Valor EXACTO de la celda cuando `name` es una versión recortada. */
  key?: string
  /** El grupo «(sin dato)». */
  empty?: boolean
  /** La porción «Otros (n)» de una torta. */
  other?: boolean
}

export type Unit = "money" | "count" | "number"

/** Lo que se manda al tocar un dato: la clave exacta, o null para «(sin dato)», o `other` para «Otros». */
export function drillRequestFor(point: PointRef, filters: DashboardFilters, by?: string): DrillRequest {
  const request: DrillRequest = {}
  if (point.other) request.other = true
  else request.value = point.empty ? null : (point.key ?? point.name)
  if (by) request.by = by
  const applied = filtersToRequest(filters)
  if (applied) request.filters = applied
  return request
}

/** Qué dato se tocó (gráfico + valor). Si cambia, el detalle anterior no se muestra mientras carga el nuevo. */
export function drillTarget(widgetId: string, request: DrillRequest): string {
  return JSON.stringify([widgetId, request.other ? "other" : (request.value ?? null)])
}

/** Cómo se mira ese dato («Ver por» y filtros activos). Si solo cambia esto, la tabla anterior se queda a la vista. */
export function drillVariant(request: DrillRequest): string {
  return JSON.stringify([request.by ?? null, request.filters ?? null])
}

export function formatByUnit(value: number, unit: Unit, compact = false): string {
  if (unit === "money") return formatMoney(value, { compact })
  return compact ? formatCompact(value) : formatNumber(value)
}

/** Texto de un dato para lectores de pantalla y para el título del botón: «15 sep 2026: $ 1,0 M». */
export function pointLabel(point: PointRef, unit: Unit): string {
  return `${prettyLabel(point.name)}: ${formatByUnit(point.value, unit, true)}`
}

/** Ancho (0..100) de la barra de proporción de una fila: la parte del total si la medida se suma; si no, frente al mayor. */
export function barWidth(row: DrillRow, rows: DrillRow[], additive: boolean): number {
  if (additive && row.share !== null && Number.isFinite(row.share)) return Math.max(0, Math.min(100, row.share * 100))
  const max = Math.max(0, ...rows.map((r) => (Number.isFinite(r.value) ? r.value : 0)))
  if (max <= 0 || !Number.isFinite(row.value) || row.value < 0) return 0
  return Math.max(0, Math.min(100, (row.value / max) * 100))
}

export function shareText(row: DrillRow): string {
  return row.share === null ? "" : formatShare(row.share)
}

/** Frase que resume el detalle abierto, para anunciarla cuando termina de cargar. */
export function drillAnnouncement(data: DrillResponse): string {
  if (data.empty) return `${data.title}: sin datos con estos filtros.`
  const total = data.total === null ? "" : `, total ${formatByUnit(data.total, data.measure.unit)}`
  const by = data.by ? `, por ${data.by.label.toLowerCase()}` : ""
  return `${data.title}${total}${by}.`
}

/** Nombre legible de una fila del detalle (fechas ISO -> «15 sep 2026»). */
export function rowName(row: DrillRow): string {
  return prettyLabel(row.name)
}
