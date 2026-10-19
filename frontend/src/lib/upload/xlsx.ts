/**
 * Lector mínimo de Excel (.xlsx) en el navegador, sin dependencias.
 *
 * Un .xlsx es un ZIP con XML adentro. Aquí se lee el directorio del ZIP, se
 * descomprime cada parte con DecompressionStream("deflate-raw") (nativo de los
 * navegadores modernos) y se interpretan las hojas con DOMParser. Solo se usa
 * para mostrar una vista previa y calcular un primer vistazo: la carga real
 * la hace el servidor con el archivo original.
 */

export type Cell = string | number | boolean | Date | null

export interface XlsxSheet {
  name: string
  /** Filas tal cual (incluye la de encabezados). */
  rows: Cell[][]
}

interface ZipEntry {
  name: string
  method: number
  compressedSize: number
  localOffset: number
}

function u16(view: DataView, at: number) {
  return view.getUint16(at, true)
}
function u32(view: DataView, at: number) {
  return view.getUint32(at, true)
}

/** Índice del ZIP (directorio central). */
export function readZipIndex(buffer: ArrayBuffer): ZipEntry[] {
  const view = new DataView(buffer)
  const min = Math.max(0, buffer.byteLength - 65_557)
  let eocd = -1
  for (let i = buffer.byteLength - 22; i >= min; i--) {
    if (u32(view, i) === 0x06054b50) {
      eocd = i
      break
    }
  }
  if (eocd < 0) throw new Error("El archivo no es un ZIP válido")
  const total = u16(view, eocd + 10)
  let offset = u32(view, eocd + 16)
  const decoder = new TextDecoder("utf-8")
  const entries: ZipEntry[] = []
  for (let k = 0; k < total; k++) {
    if (u32(view, offset) !== 0x02014b50) break
    const method = u16(view, offset + 10)
    const compressedSize = u32(view, offset + 20)
    const nameLen = u16(view, offset + 28)
    const extraLen = u16(view, offset + 30)
    const commentLen = u16(view, offset + 32)
    const localOffset = u32(view, offset + 42)
    const name = decoder.decode(new Uint8Array(buffer, offset + 46, nameLen))
    entries.push({ name, method, compressedSize, localOffset })
    offset += 46 + nameLen + extraLen + commentLen
  }
  return entries
}

async function inflateRaw(data: Uint8Array): Promise<Uint8Array> {
  if (typeof DecompressionStream === "undefined") throw new Error("Este navegador no puede descomprimir")
  const stream = new Response(data as unknown as BodyInit).body!.pipeThrough(new DecompressionStream("deflate-raw"))
  return new Uint8Array(await new Response(stream).arrayBuffer())
}

async function readEntry(buffer: ArrayBuffer, entry: ZipEntry): Promise<Uint8Array> {
  const view = new DataView(buffer)
  const at = entry.localOffset
  if (u32(view, at) !== 0x04034b50) throw new Error(`Parte dañada: ${entry.name}`)
  const start = at + 30 + u16(view, at + 26) + u16(view, at + 28)
  const raw = new Uint8Array(buffer, start, entry.compressedSize)
  if (entry.method === 0) return raw
  if (entry.method === 8) return inflateRaw(raw)
  throw new Error(`Compresión no soportada (${entry.method})`)
}

function parseXml(text: string): Document {
  return new DOMParser().parseFromString(text, "application/xml")
}

/** Elementos por nombre local, sin importar el prefijo de espacio de nombres. */
function byTag(node: Document | Element, tag: string): Element[] {
  return Array.from(node.getElementsByTagNameNS("*", tag))
}

function attr(el: Element, name: string): string | null {
  return el.getAttribute(name) ?? el.getAttributeNS("http://schemas.openxmlformats.org/officeDocument/2006/relationships", name.replace(/^r:/, ""))
}

/** Formatos de número de Excel que representan fechas. */
const BUILTIN_DATE_FORMATS = new Set([14, 15, 16, 17, 18, 19, 20, 21, 22, 27, 30, 36, 45, 46, 47, 50, 57])

export function isDateFormatCode(code: string): boolean {
  const cleaned = code
    .replace(/"[^"]*"/g, "")
    .replace(/\[[^\]]*\]/g, "")
    .replace(/\\./g, "")
    .toLowerCase()
  return /[dmy]/.test(cleaned) && !/^[#0.,%\s]*$/.test(cleaned)
}

/**
 * Número de serie de Excel (sistema 1900) -> fecha en hora LOCAL. Excel no
 * guarda zona horaria: el 1 de marzo debe seguir siendo 1 de marzo en Bogotá.
 */
export function excelSerialToDate(serial: number): Date {
  const utc = new Date(Math.round((serial - 25569) * 86_400_000))
  return new Date(
    utc.getUTCFullYear(),
    utc.getUTCMonth(),
    utc.getUTCDate(),
    utc.getUTCHours(),
    utc.getUTCMinutes(),
    utc.getUTCSeconds()
  )
}

function isoToLocalDate(text: string): Date | null {
  const m = text.match(/^(\d{4})-(\d{2})-(\d{2})(?:[T ](\d{2}):(\d{2})(?::(\d{2}))?)?/)
  if (!m) return null
  return new Date(Number(m[1]), Number(m[2]) - 1, Number(m[3]), Number(m[4] ?? 0), Number(m[5] ?? 0), Number(m[6] ?? 0))
}

/** "AB12" -> 27 (índice de columna desde 0). */
export function columnIndex(ref: string): number {
  const letters = ref.replace(/[^A-Z]/gi, "").toUpperCase()
  let n = 0
  for (const ch of letters) n = n * 26 + (ch.charCodeAt(0) - 64)
  return n - 1
}

export interface ReadXlsxOptions {
  /** Máximo de filas por hoja que se leen (incluye encabezado). */
  maxRows?: number
}

/** Lee todas las hojas de un .xlsx (nombre + filas). */
export async function readXlsx(buffer: ArrayBuffer, options: ReadXlsxOptions = {}): Promise<XlsxSheet[]> {
  const maxRows = options.maxRows ?? 20_001
  const entries = readZipIndex(buffer)
  const find = (name: string) => entries.find((e) => e.name.toLowerCase() === name.toLowerCase())
  const text = async (name: string) => {
    const e = find(name)
    return e ? new TextDecoder("utf-8").decode(await readEntry(buffer, e)) : null
  }

  const workbookXml = await text("xl/workbook.xml")
  if (!workbookXml) throw new Error("No encontramos las hojas del libro")
  const relsXml = await text("xl/_rels/workbook.xml.rels")
  const targets = new Map<string, string>()
  if (relsXml) {
    for (const rel of byTag(parseXml(relsXml), "Relationship")) {
      const id = rel.getAttribute("Id")
      const target = rel.getAttribute("Target")
      if (id && target) {
        const path = target.startsWith("/") ? target.slice(1) : `xl/${target.replace(/^\.\//, "")}`
        targets.set(id, path)
      }
    }
  }

  const shared: string[] = []
  const sharedXml = await text("xl/sharedStrings.xml")
  if (sharedXml) {
    for (const si of byTag(parseXml(sharedXml), "si")) {
      shared.push(byTag(si, "t").map((t) => t.textContent ?? "").join(""))
    }
  }

  // Estilos: índice de estilo de celda -> ¿es fecha?
  const dateStyles: boolean[] = []
  const stylesXml = await text("xl/styles.xml")
  if (stylesXml) {
    const doc = parseXml(stylesXml)
    const custom = new Map<number, string>()
    for (const f of byTag(doc, "numFmt")) custom.set(Number(f.getAttribute("numFmtId")), f.getAttribute("formatCode") ?? "")
    const cellXfs = byTag(doc, "cellXfs")[0]
    if (cellXfs) {
      for (const xf of Array.from(cellXfs.children).filter((c) => c.localName === "xf")) {
        const id = Number(xf.getAttribute("numFmtId") ?? 0)
        dateStyles.push(BUILTIN_DATE_FORMATS.has(id) || (custom.has(id) && isDateFormatCode(custom.get(id)!)))
      }
    }
  }

  const sheets: XlsxSheet[] = []
  const workbook = parseXml(workbookXml)
  let index = 0
  for (const sheetEl of byTag(workbook, "sheet")) {
    index++
    const name = sheetEl.getAttribute("name") ?? `Hoja ${index}`
    const rid = attr(sheetEl, "r:id")
    const path = (rid && targets.get(rid)) || `xl/worksheets/sheet${index}.xml`
    const xml = await text(path)
    if (!xml) {
      sheets.push({ name, rows: [] })
      continue
    }
    const doc = parseXml(xml)
    const rows: Cell[][] = []
    for (const rowEl of byTag(doc, "row")) {
      if (rows.length >= maxRows) break
      const r = Number(rowEl.getAttribute("r") ?? rows.length + 1) - 1
      const cells: Cell[] = []
      let col = 0
      for (const c of Array.from(rowEl.children).filter((x) => x.localName === "c")) {
        const ref = c.getAttribute("r")
        if (ref) col = columnIndex(ref)
        const t = c.getAttribute("t")
        const v = byTag(c, "v")[0]?.textContent ?? null
        let value: Cell = null
        if (t === "s") value = v !== null ? shared[Number(v)] ?? "" : null
        else if (t === "inlineStr") value = byTag(c, "t").map((x) => x.textContent ?? "").join("")
        else if (t === "str") value = v
        else if (t === "b") value = v === "1"
        else if (t === "e") value = null
        else if (t === "d") value = v ? isoToLocalDate(v) : null
        else if (v !== null && v !== "") {
          const num = Number(v)
          const style = Number(c.getAttribute("s") ?? 0)
          value = dateStyles[style] ? excelSerialToDate(num) : num
        }
        cells[col] = value
        col++
      }
      // Filas saltadas en el XML: se completan para conservar la posición
      while (rows.length < r && rows.length < maxRows) rows.push([])
      if (rows.length < maxRows) rows.push(Array.from(cells, (x) => (x === undefined ? null : x)))
    }
    sheets.push({ name, rows })
  }
  return sheets
}
