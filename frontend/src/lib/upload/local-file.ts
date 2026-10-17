/**
 * Validación local de archivos, sin red: lo barato se revisa en el navegador
 * antes de subir, y cada problema trae una instrucción concreta.
 */
import { formatFileSize } from "@/lib/format"
import { blobToArrayBuffer } from "@/lib/upload/read-local"

export type LocalFileKind = "xlsx" | "csv" | "json"

export const MAX_FILE_BYTES = 10 * 1024 * 1024

/** Atributo `accept` del selector de archivos. */
export const ACCEPT_ATTR =
  ".xlsx,.csv,.json,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet,text/csv,application/json"

const MIME: Record<LocalFileKind, string> = {
  xlsx: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
  csv: "text/csv",
  json: "application/json",
}

export interface LocalProblem {
  title: string
  description: string
}

export type LocalCheck = { ok: true; kind: LocalFileKind } | ({ ok: false } & LocalProblem)

export function extensionOf(name: string): string {
  const i = name.lastIndexOf(".")
  return i >= 0 ? name.slice(i + 1).toLowerCase() : ""
}

export function fileKind(name: string): LocalFileKind | null {
  const ext = extensionOf(name)
  if (ext === "xlsx" || ext === "xlsm") return "xlsx"
  if (ext === "csv" || ext === "txt" || ext === "tsv") return "csv"
  if (ext === "json") return "json"
  return null
}

/** Revisa extensión, tamaño y que no esté vacío. */
export function validateLocalFile(file: { name: string; size: number }): LocalCheck {
  const ext = extensionOf(file.name)
  if (ext === "xls") {
    return {
      ok: false,
      title: "Ese Excel es de una versión antigua (.xls)",
      description: "Ábrelo en Excel y elige Archivo › Guardar como › Libro de Excel (.xlsx). Luego súbelo de nuevo.",
    }
  }
  if (ext === "numbers" || ext === "ods") {
    return {
      ok: false,
      title: "Ese formato no lo podemos leer todavía",
      description: "Expórtalo como Excel (.xlsx) o CSV desde tu programa de hojas de cálculo y súbelo de nuevo.",
    }
  }
  const kind = fileKind(file.name)
  if (!kind) {
    return {
      ok: false,
      title: "Ese tipo de archivo no lo podemos leer",
      description: "Sube un Excel (.xlsx), un CSV o un JSON. Si tus datos están en un PDF o en Word, cópialos a una hoja de Excel primero.",
    }
  }
  if (file.size === 0) {
    return {
      ok: false,
      title: "El archivo está vacío",
      description: "Revisa que hayas guardado los cambios antes de subirlo.",
    }
  }
  if (file.size > MAX_FILE_BYTES) {
    return {
      ok: false,
      title: `Tu archivo pesa ${formatFileSize(file.size)} y el máximo es 10 MB`,
      description: "Prueba dividiéndolo en partes (por ejemplo, un archivo por año) o quitando columnas que no uses.",
    }
  }
  return { ok: true, kind }
}

/**
 * Copia del archivo con el tipo MIME explícito según la extensión. Windows suele
 * marcar los .csv como "application/vnd.ms-excel" y el servidor los trataría
 * como Excel; así siempre llegan con el tipo correcto.
 */
export function withExplicitType(file: File, kind: LocalFileKind): File {
  if (file.type === MIME[kind]) return file
  return new File([file], file.name, { type: MIME[kind], lastModified: file.lastModified })
}

/** Los .xlsx son ZIP: deben empezar por "PK\x03\x04". */
export async function looksLikeZip(file: Blob): Promise<boolean> {
  try {
    const head = new Uint8Array(await blobToArrayBuffer(file.slice(0, 4)))
    return head[0] === 0x50 && head[1] === 0x4b && head[2] === 0x03 && head[3] === 0x04
  } catch {
    return true // si no podemos revisarlo, que decida el servidor
  }
}

/** Nombre del archivo sin extensión y legible: "ventas_marzo-2026.xlsx" -> "Ventas marzo 2026". */
export function friendlyFileName(name: string): string {
  const base = name.replace(/\.[^.]+$/, "").replace(/[_\-.]+/g, " ").replace(/\s+/g, " ").trim()
  if (!base) return "Mis datos"
  return base.charAt(0).toUpperCase() + base.slice(1)
}
