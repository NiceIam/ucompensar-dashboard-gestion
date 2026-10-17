/**
 * Vocabulario de datos en lenguaje de negocio: convierte nombres y tipos
 * técnicos ("precio_unitario", "integer") en algo que el dueño de una empresa
 * entiende de un vistazo ("Precio unitario", "Dinero").
 */

export type ColumnKind = "date" | "money" | "number" | "text" | "boolean" | "id"

export interface ColumnLike {
  /** Nombre técnico de la columna (por ejemplo "precio_unitario"). */
  name: string
  /** Tipo técnico del backend: text, integer, number, date, boolean... */
  type?: string
  /** Nombre amable si existe. */
  label?: string
  /** Valores distintos (si se conoce, p. ej. del análisis del archivo). */
  distinct?: number
  /** Filas con valor (si se conoce). */
  filled?: number
}

export interface KindInfo {
  label: string
  description: string
}

export const KIND_INFO: Record<ColumnKind, KindInfo> = {
  date: {
    label: "Fecha",
    description: "Días, meses o años. Sirve para ver cómo cambian las cosas con el tiempo.",
  },
  money: {
    label: "Dinero",
    description: "Valores en pesos que se pueden sumar, promediar y comparar.",
  },
  number: {
    label: "Número",
    description: "Cantidades que se pueden sumar, promediar y comparar.",
  },
  text: {
    label: "Texto",
    description: "Nombres, categorías o descripciones. Sirve para agrupar y filtrar.",
  },
  boolean: {
    label: "Sí / No",
    description: "Respuestas de dos opciones, como pagado o pendiente.",
  },
  id: {
    label: "Código",
    description: "Identifica cada fila (documento, referencia, teléfono). No se suma.",
  },
}

/** Separa un nombre técnico en palabras en minúscula. */
export function nameTokens(raw: string): string[] {
  return raw
    .replace(/([a-záéíóúñ])([A-ZÁÉÍÓÚÑ])/g, "$1 $2")
    .toLowerCase()
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "")
    .split(/[^a-z0-9]+/)
    .filter(Boolean)
}

const ACRONYMS = new Set(["iva", "nit", "sku", "ean", "id", "pdf", "url", "rut"])

/** Tildes que los nombres técnicos suelen perder ("region" -> "región"). */
const ACCENTS: Record<string, string> = {
  region: "región", categoria: "categoría", categorias: "categorías", telefono: "teléfono",
  codigo: "código", numero: "número", metodo: "método", pais: "país", area: "área", dia: "día",
  dias: "días", credito: "crédito", debito: "débito", ultimo: "último", ultima: "última",
  unico: "único", pagina: "página", linea: "línea", vehiculo: "vehículo", articulo: "artículo",
  articulos: "artículos", cedula: "cédula", genero: "género", razon: "razón", almacen: "almacén",
  cafe: "café", menu: "menú", periodo: "período", minimo: "mínimo", maximo: "máximo",
  rapido: "rápido", publico: "público", economico: "económico", basico: "básico", medico: "médico",
}

function accentWord(word: string): string {
  if (ACCENTS[word]) return ACCENTS[word]
  // "cotizacion" -> "cotización" (solo singular: el plural "cotizaciones" no lleva tilde)
  if (/[a-z]{2,}cion$/.test(word)) return word.replace(/cion$/, "ción")
  if (/[a-z]{2,}sion$/.test(word)) return word.replace(/sion$/, "sión")
  return word
}

/** "precio_unitario" -> "Precio unitario"; "fechaVenta" -> "Fecha venta"; "iva" -> "IVA". */
export function humanizeName(raw: string): string {
  const cleaned = raw
    .replace(/([a-záéíóúñ])([A-ZÁÉÍÓÚÑ])/g, "$1 $2")
    .replace(/[_\-.]+/g, " ")
    .replace(/\s+/g, " ")
    .trim()
  if (!cleaned) return raw
  const words = cleaned.split(" ").map((w) => {
    const plain = w.toLowerCase()
    return ACRONYMS.has(plain) ? plain.toUpperCase() : accentWord(plain)
  })
  const first = words[0]
  words[0] = first === first.toUpperCase() ? first : first.charAt(0).toUpperCase() + first.slice(1)
  return words.join(" ")
}

/** Nombre visible de una columna: la etiqueta si es amable, si no el nombre humanizado. */
export function columnLabel(col: ColumnLike): string {
  const label = col.label?.trim()
  if (label && !/[_]/.test(label) && label !== col.name) return label
  return humanizeName(col.name)
}

const ID_WORDS = new Set([
  "id", "uuid", "codigo", "cod", "nit", "cedula", "cc", "documento", "doc", "telefono", "tel",
  "celular", "movil", "email", "correo", "mail", "numero", "nro", "num", "no", "sku", "ean",
  "referencia", "ref", "consecutivo", "radicado", "placa", "serial", "url", "link",
])

const MONEY_WORDS = new Set([
  "precio", "precios", "valor", "valores", "costo", "costos", "monto", "montos", "ingreso", "ingresos",
  "venta", "ventas", "salario", "salarios", "pago", "pagos", "subtotal", "total", "totales", "iva",
  "descuento", "descuentos", "tarifa", "tarifas", "saldo", "deuda", "abono", "abonos", "utilidad",
  "ganancia", "ganancias", "gasto", "gastos", "presupuesto", "facturado", "recaudo",
])

/** true si el nombre sugiere un identificador (no se suma ni sirve para agrupar). */
export function isIdLike(name: string): boolean {
  const tokens = nameTokens(name)
  if (tokens.length === 0) return false
  return tokens.some((t) => ID_WORDS.has(t)) && !tokens.some((t) => MONEY_WORDS.has(t) && t !== "iva")
}

/** true si el nombre sugiere dinero (precio, valor, total, costo...). */
export function isMoneyLike(name: string): boolean {
  return nameTokens(name).some((t) => MONEY_WORDS.has(t))
}

/** Tipo técnico + nombre -> clase de columna en lenguaje de negocio. */
export function columnKind(col: ColumnLike): ColumnKind {
  const type = (col.type ?? "text").toLowerCase()
  if (/^(date|datetime|timestamp|time)/.test(type)) return "date"
  if (/^(bool)/.test(type)) return "boolean"
  if (/^(int|integer|bigint|smallint|float|double|decimal|numeric|number|real)/.test(type)) {
    if (isIdLike(col.name)) return "id"
    return isMoneyLike(col.name) ? "money" : "number"
  }
  if (isIdLike(col.name)) return "id"
  return "text"
}

/** Palabras que suelen ser buenas categorías para agrupar. */
const CATEGORY_WORDS = [
  "region", "ciudad", "departamento", "municipio", "sede", "sucursal", "zona", "pais", "barrio",
  "categoria", "linea", "marca", "producto", "servicio", "plato", "cliente", "proveedor", "vendedor",
  "asesor", "canal", "tipo", "estado", "metodo", "medio", "area", "cargo", "segmento", "mesa", "bodega",
]

/** Palabras de texto libre que no sirven para agrupar. */
const FREE_TEXT_WORDS = new Set([
  "descripcion", "detalle", "observacion", "observaciones", "comentario", "comentarios", "nota",
  "notas", "direccion", "mensaje", "texto",
])

/** Puntaje de qué tan buena categoría es una columna de texto (0 = no sirve). */
export function categoryScore(col: ColumnLike, rows?: number): number {
  if (columnKind(col) !== "text") return 0
  const tokens = nameTokens(col.name)
  if (tokens.some((t) => FREE_TEXT_WORDS.has(t))) return 0
  if (typeof col.distinct === "number") {
    if (col.distinct < 2) return 0
    const limit = Math.max(25, (rows ?? col.filled ?? 0) * 0.5)
    if (col.distinct > limit) return 0
  }
  const hint = CATEGORY_WORDS.findIndex((w) => tokens.includes(w))
  if (hint >= 0) return 100 - hint
  if (tokens.includes("nombre")) return 5
  return 10
}

/** Mejor columna para medir (dinero primero, luego números que no son códigos). */
export function pickMeasure<T extends ColumnLike>(cols: T[]): T | undefined {
  const money = cols.find((c) => columnKind(c) === "money")
  if (money) return money
  return cols.find((c) => columnKind(c) === "number")
}

export function pickDate<T extends ColumnLike>(cols: T[]): T | undefined {
  return cols.find((c) => columnKind(c) === "date")
}

export function pickCategory<T extends ColumnLike>(cols: T[], rows?: number): T | undefined {
  let best: T | undefined
  let bestScore = 0
  for (const c of cols) {
    const s = categoryScore(c, rows)
    if (s > bestScore) {
      best = c
      bestScore = s
    }
  }
  return best
}
