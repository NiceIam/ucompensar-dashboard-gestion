/**
 * "Primer vistazo" calculado en el navegador con el archivo que se acaba de
 * subir: periodo que cubre, total de la cifra principal, quién lidera y un
 * gráfico sugerido. Sin IA y sin inventar nada.
 *
 * Para no contradecir al asistente, los números y fechas se interpretan con
 * las MISMAS reglas que usa el motor de consultas del servidor
 * (backend/app/services/data_query_engine.py): números simples con punto
 * decimal y fechas AAAA-MM-DD, D/M/AAAA, D/M/AA, AAAA-MM o AAAAMMDD.
 */
import {
  columnKind,
  columnLabel,
  pickCategory,
  pickDate,
  pickMeasure,
  type ColumnLike,
} from "@/lib/data-vocabulary"
import {
  formatChange,
  formatCompact,
  formatDate,
  formatDateRange,
  formatMoney,
  formatShare,
  monthName,
  pluralize,
} from "@/lib/format"
import type { Cell, LocalSheet } from "@/lib/upload/read-local"
import type { AnalysisColumn } from "@/lib/upload/types"

const NUM_RE = /^ *[-+]?([0-9]+(\.[0-9]*)?|\.[0-9]+)([eE][-+]?[0-9]{1,3})? *$/

/** Número según las reglas del servidor (null si la celda no es numérica). */
export function parseNumberCell(cell: Cell): number | null {
  if (typeof cell === "number") return Number.isFinite(cell) ? cell : null
  if (typeof cell === "string" && cell.length <= 200 && NUM_RE.test(cell)) {
    const n = Number(cell.trim())
    return Number.isFinite(n) ? n : null
  }
  return null
}

function validDate(y: number, m: number, d: number): Date | null {
  if (m < 1 || m > 12 || d < 1) return null
  const last = new Date(y, m, 0).getDate()
  if (d > last) return null
  return new Date(y, m - 1, d)
}

/** Fecha según las reglas del servidor (null si no es fecha). */
export function parseDateCell(cell: Cell, now: Date = new Date()): Date | null {
  if (cell instanceof Date) return Number.isNaN(cell.getTime()) ? null : new Date(cell.getFullYear(), cell.getMonth(), cell.getDate())
  if (typeof cell !== "string") return null
  const t = cell
  let m = t.match(/^ *([0-9]{4})[-/.]([0-9]{1,2})[-/.]([0-9]{1,2})/)
  if (m) return validDate(+m[1], +m[2], +m[3])
  m = t.match(/^ *([0-9]{1,2})[-/.]([0-9]{1,2})[-/.]([0-9]{4})/)
  if (m) return validDate(+m[3], +m[2], +m[1])
  m = t.match(/^ *([0-9]{1,2})[-/.]([0-9]{1,2})[-/.]([0-9]{2})(?![0-9])/)
  if (m) {
    const yy = +m[3]
    const pivot = (now.getFullYear() % 100) + 5
    const century = Math.floor(now.getFullYear() / 100) * 100
    const year = yy <= pivot ? century + yy : century - 100 + yy
    return validDate(year, +m[2], +m[1])
  }
  m = t.match(/^ *([0-9]{4})[-/.]([0-9]{1,2}) *$/)
  if (m) return validDate(+m[1], +m[2], 1)
  m = t.match(/^ *([0-9]{4})([0-9]{2})([0-9]{2}) *$/)
  if (m) return validDate(+m[1], +m[2], +m[3])
  return null
}

export interface InsightPart {
  text: string
  /** Se muestra destacada (cifra). */
  figure?: boolean
}

export interface InsightFact {
  id: "period" | "total" | "leader" | "change" | "count"
  parts: InsightPart[]
}

export interface InsightChart {
  title: string
  form: "bar" | "line"
  /** Qué se mide, para formatear los valores. */
  unit: "money" | "number" | "count"
  points: { name: string; value: number }[]
}

export interface Insights {
  facts: InsightFact[]
  chart: InsightChart | null
}

interface ColumnRef extends ColumnLike {
  index: number
}

function monthKey(d: Date): string {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`
}

function monthLabel(key: string, withYear: boolean): string {
  const [y, m] = key.split("-").map(Number)
  const name = monthName(m - 1)
  return withYear ? `${name.slice(0, 3)} ${y}` : name
}

function fmt(value: number, unit: InsightChart["unit"]): string {
  return unit === "money" ? formatMoney(value, { compact: true }) : formatCompact(value)
}

const lowerFirst = (s: string) => s.charAt(0).toLowerCase() + s.slice(1)

/**
 * Calcula el primer vistazo. Devuelve null si las columnas del archivo no
 * coinciden con las que entendió el servidor (para no adivinar).
 */
export function computeInsights(sheet: LocalSheet, columns: AnalysisColumn[], now: Date = new Date()): Insights | null {
  if (sheet.rows.length === 0 || sheet.header.length !== columns.length) return null
  const refs: ColumnRef[] = columns.map((c, index) => ({
    index,
    name: c.clean_name,
    label: c.original_name,
    type: c.inferred_type,
    distinct: c.unique_count,
    filled: c.non_null_count,
  }))
  const rows = sheet.rows
  const facts: InsightFact[] = []

  // Fecha: se usa solo si al menos el 70 % de las celdas con valor se leen como fecha
  let date = pickDate(refs)
  let dates: (Date | null)[] = []
  if (date) {
    dates = rows.map((r) => parseDateCell(r[date!.index] ?? null, now))
    const filled = rows.filter((r) => r[date!.index] !== null && r[date!.index] !== "").length
    const ok = dates.filter(Boolean).length
    if (filled === 0 || ok / filled < 0.7) {
      date = undefined
      dates = []
    }
  }

  // Medida: número o dinero, con al menos 70 % de celdas numéricas
  let measure = pickMeasure(refs)
  let values: (number | null)[] = []
  if (measure) {
    values = rows.map((r) => parseNumberCell(r[measure!.index] ?? null))
    const filled = rows.filter((r) => r[measure!.index] !== null && r[measure!.index] !== "").length
    if (filled === 0 || values.filter((v) => v !== null).length / filled < 0.7) {
      measure = undefined
      values = []
    }
  }
  const unit: InsightChart["unit"] = measure ? (columnKind(measure) === "money" ? "money" : "number") : "count"
  const measureName = measure ? columnLabel(measure) : ""

  const category = pickCategory(refs, rows.length)

  // 1. Periodo cubierto
  const validDates = dates.filter((d): d is Date => d !== null)
  if (validDates.length > 0) {
    const min = new Date(Math.min(...validDates.map((d) => d.getTime())))
    const max = new Date(Math.max(...validDates.map((d) => d.getTime())))
    facts.push({
      id: "period",
      parts: [{ text: "Tus datos van " }, { text: formatDateRange(min, max), figure: true }, { text: "." }],
    })
  }

  // 2. Total de la medida principal
  if (measure) {
    const total = values.reduce<number>((s, v) => s + (v ?? 0), 0)
    facts.push({
      id: "total",
      parts: [
        { text: `En total, «${measureName}» suma ` },
        { text: fmt(total, unit), figure: true },
        { text: ` en ${pluralize(rows.length, "fila", "filas")}.` },
      ],
    })
  } else {
    facts.push({
      id: "count",
      parts: [{ text: "Guardamos " }, { text: pluralize(rows.length, "fila", "filas"), figure: true }, { text: " con datos." }],
    })
  }

  // 3. Quién lidera por categoría
  let byCategory: { name: string; value: number }[] = []
  if (category) {
    const acc = new Map<string, number>()
    rows.forEach((r, i) => {
      const raw = r[category.index]
      if (raw === null || raw === undefined || String(raw).trim() === "") return
      const key = String(raw).trim()
      const add = measure ? values[i] ?? 0 : 1
      acc.set(key, (acc.get(key) ?? 0) + add)
    })
    byCategory = Array.from(acc, ([name, value]) => ({ name, value })).sort((a, b) => b.value - a.value)
    const sum = byCategory.reduce((s, x) => s + x.value, 0)
    const top = byCategory[0]
    if (top && byCategory.length >= 2 && sum > 0) {
      facts.push({
        id: "leader",
        parts: [
          { text: `Por ${lowerFirst(columnLabel(category))}, lidera ${top.name}: ` },
          { text: measure ? fmt(top.value, unit) : pluralize(top.value, "fila", "filas"), figure: true },
          { text: `, el ${formatShare(top.value / sum)} del total.` },
        ],
      })
    }
  }

  // 4. Mes a mes
  let byMonth: { key: string; value: number }[] = []
  if (validDates.length > 0) {
    const acc = new Map<string, number>()
    dates.forEach((d, i) => {
      if (!d) return
      const add = measure ? values[i] ?? 0 : 1
      acc.set(monthKey(d), (acc.get(monthKey(d)) ?? 0) + add)
    })
    byMonth = Array.from(acc, ([key, value]) => ({ key, value })).sort((a, b) => a.key.localeCompare(b.key))
    if (byMonth.length >= 2) {
      const last = byMonth[byMonth.length - 1]
      const prev = byMonth[byMonth.length - 2]
      if (prev.value !== 0) {
        const lastDate = new Date(Math.max(...validDates.map((d) => d.getTime())))
        const partial = lastDate.getDate() < 20
        const [, m] = last.key.split("-").map(Number)
        const [, pm] = prev.key.split("-").map(Number)
        const change = (last.value - prev.value) / Math.abs(prev.value)
        facts.push({
          id: "change",
          parts: [
            { text: `${monthName(m - 1).charAt(0).toUpperCase()}${monthName(m - 1).slice(1)} ${measure ? "sumó" : "tuvo"} ` },
            { text: measure ? fmt(last.value, unit) : pluralize(last.value, "fila", "filas"), figure: true },
            {
              text: `, ${formatChange(change)} frente a ${monthName(pm - 1)}${
                partial ? ` (con datos hasta el ${formatDate(lastDate, "long").replace(/ de \d{4}$/, "")})` : ""
              }.`,
            },
          ],
        })
      }
    }
  }

  // Gráfico sugerido
  let chart: InsightChart | null = null
  if (byMonth.length >= 2) {
    const multiYear = new Set(byMonth.map((x) => x.key.slice(0, 4))).size > 1
    chart = {
      title: measure ? `${measureName} por mes` : "Registros por mes",
      form: byMonth.length <= 14 ? "bar" : "line",
      unit,
      points: byMonth.map((x) => ({ name: monthLabel(x.key, multiYear || byMonth.length > 12), value: x.value })),
    }
  } else if (byCategory.length >= 2) {
    const top = byCategory.slice(0, 8)
    chart = {
      title: measure ? `${measureName} por ${lowerFirst(columnLabel(category!))}` : `Filas por ${lowerFirst(columnLabel(category!))}`,
      form: "bar",
      unit,
      points: top,
    }
  }

  return { facts, chart }
}
