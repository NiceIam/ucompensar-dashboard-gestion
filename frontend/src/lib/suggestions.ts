/**
 * Preguntas sugeridas para el chat, generadas SOLO con plantillas locales a
 * partir de las columnas reales (sin llamar a ninguna IA). Las frases están
 * pensadas para sonar naturales en español sin equivocarse de género:
 * se usan artículos solo cuando conocemos la palabra, y si no, comillas « ».
 */

import {
  columnKind,
  columnLabel,
  humanizeName,
  nameTokens,
  pickCategory,
  pickDate,
  pickMeasure,
  type ColumnLike,
} from "@/lib/data-vocabulary"

export interface SuggestTable {
  /** Nombre visible de la tabla, por ejemplo "Ventas". */
  name: string
  columns: ColumnLike[]
  rowCount?: number
}

interface MeasureWord {
  phrase: string
  plural: boolean
}

/** Medidas frecuentes con su artículo correcto. */
const MEASURE_WORDS: Record<string, MeasureWord> = {
  total: { phrase: "el total", plural: false },
  totales: { phrase: "los totales", plural: true },
  valor: { phrase: "el valor", plural: false },
  precio: { phrase: "el precio", plural: false },
  monto: { phrase: "el monto", plural: false },
  costo: { phrase: "el costo", plural: false },
  costos: { phrase: "los costos", plural: true },
  cantidad: { phrase: "la cantidad", plural: false },
  unidades: { phrase: "las unidades", plural: true },
  subtotal: { phrase: "el subtotal", plural: false },
  descuento: { phrase: "el descuento", plural: false },
  iva: { phrase: "el IVA", plural: false },
  ingreso: { phrase: "el ingreso", plural: false },
  ingresos: { phrase: "los ingresos", plural: true },
  venta: { phrase: "la venta", plural: false },
  ventas: { phrase: "las ventas", plural: true },
  stock: { phrase: "el stock", plural: false },
  inventario: { phrase: "el inventario", plural: false },
  salario: { phrase: "el salario", plural: false },
  horas: { phrase: "las horas", plural: true },
  duracion: { phrase: "la duración", plural: false },
  gasto: { phrase: "el gasto", plural: false },
  gastos: { phrase: "los gastos", plural: true },
  utilidad: { phrase: "la utilidad", plural: false },
  saldo: { phrase: "el saldo", plural: false },
  pago: { phrase: "el pago", plural: false },
  pagos: { phrase: "los pagos", plural: true },
  tarifa: { phrase: "la tarifa", plural: false },
}

/** "precio_unitario" -> { phrase: "el precio unitario" }; desconocida -> «nombre». */
export function measurePhrase(col: ColumnLike): MeasureWord {
  const tokens = nameTokens(col.name)
  const head = tokens[0]
  const known = head ? MEASURE_WORDS[head] : undefined
  const label = columnLabel(col).toLowerCase()
  if (known) {
    const rest = label.split(" ").slice(1).join(" ")
    return { phrase: rest ? `${known.phrase} ${rest}` : known.phrase, plural: known.plural }
  }
  return { phrase: `«${label}»`, plural: false }
}

/** "de el total" -> "del total". */
function de(phrase: string): string {
  return phrase.startsWith("el ") ? `del ${phrase.slice(3)}` : `de ${phrase}`
}

function lower(text: string): string {
  return text.charAt(0).toLowerCase() + text.slice(1)
}

/** Preguntas candidatas para una tabla, de más a menos útiles. */
export function questionsForTable(table: SuggestTable): string[] {
  const cols = table.columns
  const rows = table.rowCount
  const date = pickDate(cols)
  const measure = pickMeasure(cols)
  const category = pickCategory(cols, rows)
  const tableName = humanizeName(table.name)
  const out: string[] = []

  if (date && measure) {
    const m = measurePhrase(measure)
    out.push(`¿Cómo ${m.plural ? "cambian" : "cambia"} ${m.phrase} mes a mes?`)
  }
  if (category && measure) {
    const m = measurePhrase(measure)
    out.push(`Muéstrame ${m.phrase} por ${lower(columnLabel(category))}`)
  }
  if (category) {
    out.push(`¿Qué ${lower(columnLabel(category))} aparece más en ${tableName}?`)
  }
  if (date && !measure) {
    out.push(`¿Cuántos registros de ${tableName} hay por mes?`)
  }
  if (measure && !date && !category) {
    const m = measurePhrase(measure)
    out.push(`Dame el total, el promedio y el máximo ${de(m.phrase)}`)
  }
  const flag = cols.find((c) => columnKind(c) === "boolean")
  if (flag) {
    out.push(`¿Cuántos registros de ${tableName} tienen «${lower(columnLabel(flag))}» en sí?`)
  }
  out.push(`Hazme un resumen de ${tableName}`)
  return out
}

/**
 * Hasta `max` preguntas variadas: se toman de las tablas con más filas primero,
 * alternando entre tablas para no repetir siempre la misma.
 */
export function suggestQuestions(tables: SuggestTable[], max = 3): string[] {
  const withData = tables.filter((t) => (t.rowCount ?? 1) > 0 && t.columns.length > 0)
  const pool = (withData.length > 0 ? withData : []).slice().sort((a, b) => (b.rowCount ?? 0) - (a.rowCount ?? 0))
  const perTable = pool.map(questionsForTable)
  const result: string[] = []
  // Primero la mejor pregunta de cada tabla, luego la segunda, etc.
  for (let round = 0; result.length < max && perTable.some((q) => q.length > round); round++) {
    for (const qs of perTable) {
      const q = qs[round]
      if (q && !result.includes(q)) result.push(q)
      if (result.length >= max) break
    }
  }
  return result
}
