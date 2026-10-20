/**
 * Bloque ```dashboard que el SERVIDOR agrega a la respuesta del asistente cuando crea un tablero.
 *
 * Es entrada no confiable: aunque el servidor descarta cualquier bloque equivalente que escriba el modelo, el
 * contenido se valida aquí antes de usarlo. El `id` debe ser un UUID (nunca se arma un enlace con otra cosa) y
 * el nombre solo se pinta como texto de React.
 */
import { dashboardEditBlocks } from "@/lib/dashboard-edit-block"
import { isUuid } from "@/lib/uuid"

export { isUuid }

export interface ChatDashboard {
  id: string
  name: string
  /** Gráficos y cifras que tiene (null si el servidor no lo sabe, p. ej. un tablero que ya existía). */
  widgets: number | null
  /** true: el pedido coincidía con un tablero que ya tenías; no se creó otro. */
  existing: boolean
}

/** Enlace interno al tablero, o null si el id no es un UUID válido. */
export function dashboardHref(id: unknown): string | null {
  return isUuid(id) ? `/dashboards/${id}` : null
}

/** Texto JSON del bloque -> datos validados, o null si algo no cuadra. */
export function parseDashboardBlock(json: string): ChatDashboard | null {
  let raw: unknown
  try {
    raw = JSON.parse(json)
  } catch {
    return null
  }
  if (!raw || typeof raw !== "object") return null
  const { id, name, widgets, existing } = raw as Record<string, unknown>
  if (!isUuid(id) || typeof name !== "string" || !name.trim()) return null
  return {
    id,
    name: name.trim().slice(0, 120),
    widgets: typeof widgets === "number" && Number.isInteger(widgets) && widgets >= 0 && widgets <= 50 ? widgets : null,
    existing: existing === true,
  }
}

/** Bloques ```chart, ```dashboard y ```dashboard_edit del contenido (para partir el texto del mensaje). */
export const MESSAGE_BLOCK = /(```(?:chart|dashboard_edit|dashboard)\s*\n[\s\S]*?\n```)/

/** Los mismos bloques, para quitarlos del texto (al copiar el mensaje). */
export const MESSAGE_BLOCK_GLOBAL = /```(?:chart|dashboard_edit|dashboard)\s*\n[\s\S]*?\n```/g

/**
 * true si el mensaje trae al menos un bloque de tablero válido, creado (```dashboard) o editado
 * (```dashboard_edit): el chat refresca entonces la lista de tableros.
 */
export function hasDashboardBlock(content: string): boolean {
  const re = /```dashboard\s*\n([\s\S]*?)\n```/g
  let match: RegExpExecArray | null
  while ((match = re.exec(content)) !== null) {
    if (parseDashboardBlock(match[1])) return true
  }
  return dashboardEditBlocks(content).length > 0
}
