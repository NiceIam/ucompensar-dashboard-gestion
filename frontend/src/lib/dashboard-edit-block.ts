/**
 * Bloque ```dashboard_edit que el SERVIDOR agrega a la respuesta del asistente cuando edita un tablero que ya
 * existía (agregar, reemplazar o quitar gráficos, renombrar).
 *
 * Es entrada no confiable, igual que el bloque ```dashboard: el `id` debe ser un UUID (nunca se arma un enlace
 * con otra cosa), todo texto se pinta solo como texto de React y las listas están acotadas.
 */
import { ApiError } from "@/lib/errors"
import { isUuid } from "@/lib/uuid"
import { pluralize } from "@/lib/format"

export interface ChatDashboardEdit {
  id: string
  name: string
  /** Gráficos y cifras que quedaron (null si el servidor no lo dijo o no es creíble). */
  widgets: number | null
  /**
   * Identificador de lo que «Deshacer» restaura. null cuando no hubo cambio (`noop`) o no es válido: sin él no
   * se ofrece deshacer.
   */
  version: string | null
  /** true: no cambió nada (todo lo pedido ya estaba en el tablero). */
  noop: boolean
  renamed: { from: string; to: string } | null
  added: string[]
  replaced: { from: string; to: string }[]
  removed: string[]
  /** Pedidos que «ya estaban» en el tablero: el servidor no los duplica. */
  unchanged: string[]
}

/** Máximo de títulos por lista y de caracteres por título (el servidor ya respeta lo mismo; aquí no se confía). */
export const EDIT_LIST_MAX = 6
export const EDIT_TEXT_MAX = 80
const NAME_MAX = 120
const WIDGETS_MAX = 50

function cleanText(value: unknown, max: number): string | null {
  if (typeof value !== "string") return null
  const text = value.trim()
  return text ? text.slice(0, max) : null
}

function titles(value: unknown): string[] {
  if (!Array.isArray(value)) return []
  const out: string[] = []
  // Se recorre solo un tramo: una lista enorme no se procesa completa.
  for (const item of value.slice(0, EDIT_LIST_MAX * 4)) {
    const t = cleanText(item, EDIT_TEXT_MAX)
    if (t) out.push(t)
    if (out.length === EDIT_LIST_MAX) break
  }
  return out
}

function pair(value: unknown): { from: string; to: string } | null {
  if (!value || typeof value !== "object" || Array.isArray(value)) return null
  const from = cleanText((value as Record<string, unknown>).from, EDIT_TEXT_MAX)
  const to = cleanText((value as Record<string, unknown>).to, EDIT_TEXT_MAX)
  return from && to ? { from, to } : null
}

function pairs(value: unknown): { from: string; to: string }[] {
  if (!Array.isArray(value)) return []
  const out: { from: string; to: string }[] = []
  for (const item of value.slice(0, EDIT_LIST_MAX * 4)) {
    const p = pair(item)
    if (p) out.push(p)
    if (out.length === EDIT_LIST_MAX) break
  }
  return out
}

/** Texto JSON del bloque -> datos validados, o null si algo no cuadra. */
export function parseDashboardEditBlock(json: string): ChatDashboardEdit | null {
  let raw: unknown
  try {
    raw = JSON.parse(json)
  } catch {
    return null
  }
  if (!raw || typeof raw !== "object" || Array.isArray(raw)) return null
  const r = raw as Record<string, unknown>
  const name = cleanText(r.name, NAME_MAX)
  if (!isUuid(r.id) || !name) return null
  const noop = r.noop === true
  return {
    id: r.id,
    name,
    widgets: typeof r.widgets === "number" && Number.isInteger(r.widgets) && r.widgets >= 0 && r.widgets <= WIDGETS_MAX ? r.widgets : null,
    // Sin cambio no hay nada que deshacer; un identificador que no es UUID tampoco se envía al servidor.
    version: !noop && isUuid(r.version) ? r.version : null,
    noop,
    renamed: pair(r.renamed),
    added: titles(r.added),
    replaced: pairs(r.replaced),
    removed: titles(r.removed),
    unchanged: titles(r.unchanged),
  }
}

/**
 * Lo que cambió, en una frase corta: «agregué 1 gráfico, quité 2, reemplacé 1, cambié el nombre».
 * El sustantivo va solo en el primer tramo para que se lea fluido. Cadena vacía si no hubo cambios.
 */
export function editSummary(edit: ChatDashboardEdit): string {
  const verbs: { verb: string; count: number }[] = [
    { verb: "agregué", count: edit.added.length },
    { verb: "quité", count: edit.removed.length },
    { verb: "reemplacé", count: edit.replaced.length },
  ]
  const parts: string[] = []
  for (const { verb, count } of verbs) {
    if (count === 0) continue
    parts.push(parts.length === 0 ? `${verb} ${pluralize(count, "gráfico", "gráficos")}` : `${verb} ${count}`)
  }
  if (edit.renamed) parts.push("cambié el nombre")
  return parts.join(", ")
}

/** Frase principal de la tarjeta: «Edité «Ventas»: agregué 1 gráfico.» o «No cambié nada: …». */
export function editHeadline(edit: ChatDashboardEdit): string {
  if (edit.noop) return "No cambié nada: eso ya estaba en el tablero."
  const summary = editSummary(edit)
  return summary ? `Edité «${edit.name}»: ${summary}.` : `Edité «${edit.name}».`
}

/** Aviso del servidor 409 `newer_edits`: hay ediciones más recientes que se perderían al deshacer esta. */
export function newerEditsInfo(err: unknown): { count: number | null } | null {
  if (!(err instanceof ApiError) || err.status !== 409) return null
  const body = err.body
  if (!body || typeof body !== "object") return null
  const detail = (body as { detail?: unknown }).detail
  if (!detail || typeof detail !== "object" || Array.isArray(detail)) return null
  const { code, count } = detail as { code?: unknown; count?: unknown }
  if (code !== "newer_edits") return null
  return { count: typeof count === "number" && Number.isInteger(count) && count > 0 && count < 1000 ? count : null }
}

/** «Este tablero tiene 2 cambios más recientes. Si deshaces este, también se pierden esos.» */
export function newerEditsMessage(count: number | null): string {
  if (count === 1) return "Este tablero tiene 1 cambio más reciente. Si deshaces este, también se pierde ese."
  if (count === null) return "Este tablero tiene cambios más recientes. Si deshaces este, también se pierden esos."
  return `Este tablero tiene ${pluralize(count, "cambio más reciente", "cambios más recientes")}. Si deshaces este, también se pierden esos.`
}

const EDIT_BLOCK = /```dashboard_edit\s*\n([\s\S]*?)\n```/g

/** Bloques de edición válidos del contenido (en orden). */
export function dashboardEditBlocks(content: string): ChatDashboardEdit[] {
  const out: ChatDashboardEdit[] = []
  const re = new RegExp(EDIT_BLOCK.source, "g")
  let match: RegExpExecArray | null
  while ((match = re.exec(content)) !== null) {
    const edit = parseDashboardEditBlock(match[1])
    if (edit) out.push(edit)
  }
  return out
}

/** Ids de los tableros que el mensaje realmente cambió (los `noop` no cambian nada: no hay nada que refrescar). */
export function editedDashboardIds(content: string): string[] {
  return Array.from(new Set(dashboardEditBlocks(content).filter((e) => !e.noop).map((e) => e.id)))
}
