/**
 * Pedidos de ejemplo para crear un tablero con el asistente, generados SOLO con plantillas locales a partir de
 * las columnas reales de las hojas (sin llamar a ninguna IA). Sirven para el estado vacío de Tableros y para la
 * pregunta guía del botón «Pídele un tablero al asistente».
 */

import {
  columnLabel,
  humanizeName,
  pickCategory,
  pickDate,
  pickMeasure,
} from "@/lib/data-vocabulary"
import { measurePhrase, type SuggestTable } from "@/lib/suggestions"

function lower(text: string): string {
  return text.charAt(0).toLowerCase() + text.slice(1)
}

/** Pedidos candidatos para una hoja, de más a menos útiles. */
export function dashboardRequestsForTable(table: SuggestTable): string[] {
  const cols = table.columns
  const date = pickDate(cols)
  const measure = pickMeasure(cols)
  const category = pickCategory(cols, table.rowCount)
  const name = humanizeName(table.name)
  const out: string[] = []

  if (measure && date) {
    out.push(`Quiero un tablero con ${measurePhrase(measure).phrase} mes a mes`)
  }
  if (measure && category) {
    out.push(`Quiero un tablero con ${measurePhrase(measure).phrase} por ${lower(columnLabel(category))}`)
  }
  if (date && !measure) {
    out.push(`Quiero un tablero de cuántos registros de ${name} hay por mes`)
  }
  if (category) {
    out.push(`Quiero ver cómo van mis datos de ${name} por ${lower(columnLabel(category))}`)
  }
  out.push(`Hazme un tablero con un resumen de ${name}`)
  return out
}

/** Hasta `max` pedidos variados: las hojas con más filas primero, alternando entre hojas. */
export function dashboardRequests(tables: SuggestTable[], max = 3): string[] {
  const pool = tables
    .filter((t) => (t.rowCount ?? 1) > 0 && t.columns.length > 0)
    .sort((a, b) => (b.rowCount ?? 0) - (a.rowCount ?? 0))
  const perTable = pool.map(dashboardRequestsForTable)
  const result: string[] = []
  for (let round = 0; result.length < max && perTable.some((q) => q.length > round); round++) {
    for (const requests of perTable) {
      const request = requests[round]
      if (request && !result.includes(request)) result.push(request)
      if (result.length >= max) break
    }
  }
  return result
}

/** Pedido que el botón deja ESCRITO en el chat (sin enviarlo) para que la persona lo ajuste. */
export const GENERIC_DASHBOARD_REQUEST = "Quiero un tablero con mis ventas por mes y por producto"
