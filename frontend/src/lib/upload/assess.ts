/**
 * Evaluación del archivo ANTES de guardarlo: a dónde irá, qué problemas tiene
 * y si conviene revisarlo con la persona o guardarlo de una vez.
 *
 * Decisión de UX: cargar datos propios es reversible (una hoja recién creada se
 * puede borrar con "Deshacer"), así que si todo se ve claro se guarda directo.
 * Se pide revisión solo cuando hay dudas reales: se mezclaría con datos que ya
 * existen (eso no se puede deshacer sin perderlos), hay varias hojas, la fila de
 * títulos parece mal o hay muchas celdas vacías.
 */
import { columnLabel, humanizeName } from "@/lib/data-vocabulary"
import { formatNumber, pluralize } from "@/lib/format"
import type { LocalRead } from "@/lib/upload/read-local"
import { sheetsWithData } from "@/lib/upload/read-local"
import { MATCH_THRESHOLD, type FileAnalysis } from "@/lib/upload/types"
import type { LocalFileKind } from "@/lib/upload/local-file"

export interface ExistingTableLite {
  id: string
  table_name: string
  display_name: string
  row_count: number
}

export interface Destination {
  kind: "new" | "existing"
  /** Nombre visible donde quedarán los datos. */
  name: string
  tableId?: string
  existingRows?: number
  /** Columnas nuevas que se agregarían a una hoja existente (nombres amables). */
  newColumns: string[]
}

export interface UploadIssue {
  id: string
  tone: "info" | "warning" | "danger"
  title: string
  detail: string
}

export interface Assessment {
  /** Destino según la primera hoja (null si no hay análisis). */
  destination: Destination | null
  /** Hojas con datos detectadas en el navegador (más de una = Excel con varias hojas). */
  sheets: { name: string; rows: number }[]
  /** No pudimos ver las hojas de un Excel en el navegador. */
  unknownSheets: boolean
  issues: UploadIssue[]
  needsReview: boolean
  /** Por qué pedimos revisión, en lenguaje humano. */
  reviewReasons: string[]
  /** Nada que guardar (sin filas). */
  blocked: boolean
}

const UNNAMED = /^unnamed:\s*\d+/i

export function predictDestination(analysis: FileAnalysis, tables: ExistingTableLite[]): Destination {
  const match = analysis.matching_table
  if (match && match.match_score >= MATCH_THRESHOLD) {
    const existing = tables.find((t) => t.id === match.table_id)
    return {
      kind: "existing",
      name: existing?.display_name ?? match.display_name,
      tableId: match.table_id,
      existingRows: existing?.row_count,
      newColumns: match.missing_in_table.map((c) => humanizeName(c)),
    }
  }
  // El servidor intenta crear una hoja con el nombre sugerido; si ya existe una
  // con ese nombre, agrega los datos ahí (y las columnas que falten).
  const sameName = tables.find((t) => t.table_name === analysis.suggested_table_name)
  if (sameName) {
    return {
      kind: "existing",
      name: sameName.display_name,
      tableId: sameName.id,
      existingRows: sameName.row_count,
      newColumns: [],
    }
  }
  return { kind: "new", name: analysis.suggested_display_name || humanizeName(analysis.suggested_table_name), newColumns: [] }
}

function listNames(names: string[], max = 3): string {
  const shown = names.slice(0, max).map((n) => `«${n}»`)
  const rest = names.length - shown.length
  if (rest > 0) return `${shown.join(", ")} y ${rest} más`
  if (shown.length <= 1) return shown.join("")
  return `${shown.slice(0, -1).join(", ")} y ${shown[shown.length - 1]}`
}

export function assessUpload(input: {
  analysis: FileAnalysis | null
  tables: ExistingTableLite[]
  local: LocalRead | null
  kind: LocalFileKind
}): Assessment {
  const { analysis, tables, local, kind } = input
  const issues: UploadIssue[] = []
  const reasons: string[] = []

  const sheets = sheetsWithData(local).map((s, i) => ({ name: s.name ?? `Hoja ${i + 1}`, rows: s.rows.length }))
  const unknownSheets = kind === "xlsx" && local === null
  const multi = sheets.length > 1

  if (multi) {
    reasons.push(`Tu Excel tiene ${sheets.length} hojas con datos; cada una se guardará por separado.`)
  }
  if (unknownSheets) {
    reasons.push("No pudimos ver por adelantado si tu Excel tiene varias hojas.")
  }

  const destination = analysis ? predictDestination(analysis, tables) : null
  let blocked = false

  if (analysis) {
    const cols = analysis.columns
    if (analysis.row_count === 0) {
      blocked = true
      issues.push({
        id: "no-rows",
        tone: "danger",
        title: "No encontramos filas con datos",
        detail: "Solo vimos los títulos de las columnas. Revisa que debajo de la primera fila haya información.",
      })
      reasons.push("El archivo no tiene filas con datos.")
    }

    const unnamed = cols.filter((c) => UNNAMED.test(c.original_name))
    if (unnamed.length > 0) {
      issues.push({
        id: "header",
        tone: "warning",
        title:
          unnamed.length >= cols.length / 2
            ? "Parece que la primera fila no tiene los títulos de las columnas"
            : `${pluralize(unnamed.length, "columna no tiene", "columnas no tienen")} título`,
        detail:
          "Los títulos deben estar en la fila 1, sin títulos de reporte ni celdas combinadas arriba. Si lo guardas así, esas columnas quedarán con nombres genéricos.",
      })
      reasons.push("Algunas columnas no tienen título.")
    }

    const empty = cols.filter((c) => c.non_null_count === 0 && !UNNAMED.test(c.original_name))
    if (empty.length > 0) {
      issues.push({
        id: "empty-cols",
        tone: "warning",
        title: `${pluralize(empty.length, "columna está vacía", "columnas están vacías")}`,
        detail: `${listNames(empty.map((c) => columnLabel({ name: c.original_name })))} no ${empty.length === 1 ? "tiene" : "tienen"} ningún dato. Las guardaremos igual, por si las llenas después.`,
      })
      reasons.push("Hay columnas sin ningún dato.")
    }

    const partial = cols.filter((c) => c.null_count > 0 && c.non_null_count > 0)
    if (partial.length > 0 && analysis.row_count > 0) {
      const totalCells = analysis.row_count * Math.max(cols.length, 1)
      const blanks = cols.reduce((sum, c) => sum + c.null_count, 0)
      const ratio = blanks / totalCells
      const detail = partial
        .slice(0, 3)
        .map((c) => `${columnLabel({ name: c.original_name })}: ${pluralize(c.null_count, "celda", "celdas")}`)
        .join(" · ")
      issues.push({
        id: "blanks",
        tone: ratio > 0.2 ? "warning" : "info",
        title: `Hay celdas vacías en ${pluralize(partial.length, "columna", "columnas")}`,
        detail: `${detail}${partial.length > 3 ? " · y más" : ""}. Quedarán en blanco; no inventamos datos.`,
      })
      if (ratio > 0.2) reasons.push("Más de una de cada cinco celdas está vacía.")
    }

    const renamed = cols.filter((c) => /_\d+$/.test(c.clean_name) && cols.some((o) => o !== c && c.clean_name.startsWith(`${o.clean_name}_`)))
    if (renamed.length > 0) {
      issues.push({
        id: "dupes",
        tone: "info",
        title: "Hay columnas con el mismo título",
        detail: `Para no mezclarlas, ${listNames(renamed.map((c) => humanizeName(c.clean_name)))} ${renamed.length === 1 ? "quedará" : "quedarán"} con un número al final.`,
      })
    }

    if (destination?.kind === "existing") {
      reasons.push(
        `Se agregarán a «${destination.name}», que ya tiene ${destination.existingRows !== undefined ? pluralize(destination.existingRows, "fila", "filas") : "datos"}.`
      )
      if (destination.newColumns.length > 0) {
        issues.push({
          id: "new-cols",
          tone: "info",
          title: `«${destination.name}» ganará ${pluralize(destination.newColumns.length, "columna nueva", "columnas nuevas")}`,
          detail: `${listNames(destination.newColumns)}. Las filas que ya tenías quedarán en blanco en ${destination.newColumns.length === 1 ? "esa columna" : "esas columnas"}.`,
        })
      }
    }

    if (cols.length > 40) {
      issues.push({
        id: "wide",
        tone: "info",
        title: `Tu archivo tiene ${formatNumber(cols.length)} columnas`,
        detail: "Todo se guardará; en la vista previa solo mostramos algunas para que se lea mejor.",
      })
    }
  }

  return {
    destination,
    sheets,
    unknownSheets,
    issues,
    needsReview: reasons.length > 0,
    reviewReasons: reasons,
    blocked,
  }
}
