/**
 * Lector de CSV en el navegador, sin dependencias. Imita lo que hace el
 * servidor al leer: tolera UTF-8 (con o sin BOM), Windows-1252 (Excel en
 * Colombia), UTF-16 con BOM y separador "," ";" o tabulador.
 */

/** Bytes -> texto con la misma tolerancia del servidor. */
export function decodeText(bytes: Uint8Array): string {
  if (bytes.length >= 2 && bytes[0] === 0xff && bytes[1] === 0xfe) return new TextDecoder("utf-16le").decode(bytes.subarray(2))
  if (bytes.length >= 2 && bytes[0] === 0xfe && bytes[1] === 0xff) return new TextDecoder("utf-16be").decode(bytes.subarray(2))
  const body = bytes.length >= 3 && bytes[0] === 0xef && bytes[1] === 0xbb && bytes[2] === 0xbf ? bytes.subarray(3) : bytes
  try {
    return new TextDecoder("utf-8", { fatal: true }).decode(body)
  } catch {
    return new TextDecoder("windows-1252").decode(body)
  }
}

/** Separador más frecuente en la primera línea (fuera de comillas); en empate, coma. */
export function detectSeparator(text: string): string {
  const firstLine = text.replace(/^\s+/, "").split(/\r?\n/, 1)[0] ?? ""
  const unquoted = firstLine.replace(/"[^"]*"/g, "")
  const count = (ch: string) => unquoted.split(ch).length - 1
  let best = ","
  let bestCount = count(",")
  for (const sep of [";", "\t"]) {
    const c = count(sep)
    if (c > bestCount) {
      best = sep
      bestCount = c
    }
  }
  return best
}

/** Parte un CSV en filas y celdas (comillas, comillas dobles escapadas y saltos dentro de comillas). */
export function parseCsv(text: string, separator = detectSeparator(text), maxRows = Infinity): string[][] {
  const rows: string[][] = []
  let row: string[] = []
  let cell = ""
  let inQuotes = false
  let i = 0
  const n = text.length
  while (i < n) {
    const ch = text[i]
    if (inQuotes) {
      if (ch === '"') {
        if (text[i + 1] === '"') {
          cell += '"'
          i += 2
          continue
        }
        inQuotes = false
        i++
        continue
      }
      cell += ch
      i++
      continue
    }
    if (ch === '"' && cell === "") {
      inQuotes = true
      i++
      continue
    }
    if (ch === separator) {
      row.push(cell)
      cell = ""
      i++
      continue
    }
    if (ch === "\n" || ch === "\r") {
      row.push(cell)
      rows.push(row)
      if (rows.length >= maxRows) return rows
      row = []
      cell = ""
      if (ch === "\r" && text[i + 1] === "\n") i++
      i++
      continue
    }
    cell += ch
    i++
  }
  if (cell !== "" || row.length > 0) {
    row.push(cell)
    rows.push(row)
  }
  return rows
}

/** Filas vacías (como hace el servidor) se omiten. */
export function isBlankRow(row: unknown[]): boolean {
  return row.every((c) => c === null || c === undefined || (typeof c === "string" && c.trim() === ""))
}
