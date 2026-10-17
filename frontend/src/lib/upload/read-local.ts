/**
 * Lectura local del archivo elegido: hojas, encabezados y filas. Nunca lanza:
 * si algo no se puede leer en el navegador, devuelve `null` y el flujo sigue
 * solo con lo que diga el servidor.
 */
import { decodeText, detectSeparator, isBlankRow, parseCsv } from "@/lib/upload/csv"
import { readXlsx, type Cell } from "@/lib/upload/xlsx"
import type { LocalFileKind } from "@/lib/upload/local-file"

export type { Cell }

export interface LocalSheet {
  /** Nombre de la hoja (null en CSV/JSON). */
  name: string | null
  header: string[]
  /** Filas de datos (sin encabezado ni filas vacías). */
  rows: Cell[][]
}

export interface LocalRead {
  sheets: LocalSheet[]
}

const MAX_ROWS = 20_000

function toSheet(name: string | null, raw: Cell[][]): LocalSheet {
  const firstIdx = raw.findIndex((r) => !isBlankRow(r))
  if (firstIdx < 0) return { name, header: [], rows: [] }
  const header = raw[firstIdx].map((c) => (c === null || c === undefined ? "" : c instanceof Date ? c.toISOString() : String(c)))
  const rows = raw.slice(firstIdx + 1).filter((r) => !isBlankRow(r))
  return { name, header, rows }
}

function readJson(text: string): LocalSheet {
  const data: unknown = JSON.parse(text)
  const list = Array.isArray(data) ? data : [data]
  const keys: string[] = []
  for (const item of list) {
    if (item && typeof item === "object" && !Array.isArray(item)) {
      for (const k of Object.keys(item)) if (!keys.includes(k)) keys.push(k)
    }
  }
  const rows: Cell[][] = list.slice(0, MAX_ROWS).map((item) =>
    keys.map((k) => {
      const v = item && typeof item === "object" ? (item as Record<string, unknown>)[k] : undefined
      if (v === undefined || v === null) return null
      if (typeof v === "number" || typeof v === "boolean" || typeof v === "string") return v
      return JSON.stringify(v)
    })
  )
  return { name: null, header: keys, rows }
}

/** Blob -> ArrayBuffer (con respaldo para entornos sin Blob.arrayBuffer). */
export function blobToArrayBuffer(blob: Blob): Promise<ArrayBuffer> {
  if (typeof blob.arrayBuffer === "function") return blob.arrayBuffer()
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => resolve(reader.result as ArrayBuffer)
    reader.onerror = () => reject(reader.error)
    reader.readAsArrayBuffer(blob)
  })
}

export async function readLocalFile(file: Blob, kind: LocalFileKind): Promise<LocalRead | null> {
  try {
    const buffer = await blobToArrayBuffer(file)
    if (kind === "xlsx") {
      const sheets = await readXlsx(buffer, { maxRows: MAX_ROWS + 1 })
      return { sheets: sheets.map((s) => toSheet(s.name, s.rows)) }
    }
    const text = decodeText(new Uint8Array(buffer))
    if (kind === "json") return { sheets: [readJson(text)] }
    const raw = parseCsv(text, detectSeparator(text), MAX_ROWS + 1)
    return { sheets: [toSheet(null, raw)] }
  } catch {
    return null
  }
}

/** Hojas con al menos una fila de datos. */
export function sheetsWithData(read: LocalRead | null): LocalSheet[] {
  return read ? read.sheets.filter((s) => s.rows.length > 0) : []
}
