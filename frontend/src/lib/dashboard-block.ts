/**
 * Bloque ```dashboard que el SERVIDOR agrega a la respuesta del asistente cuando crea un tablero.
 *
 * Es entrada no confiable: aunque el servidor descarta cualquier bloque equivalente que escriba el modelo, el
 * contenido se valida aquí antes de usarlo. El `id` debe ser un UUID (nunca se arma un enlace con otra cosa) y
 * el nombre solo se pinta como texto de React.
 */

export interface ChatDashboard {
  id: string
  name: string
  /** Gráficos y cifras que tiene (null si el servidor no lo sabe, p. ej. un tablero que ya existía). */
  widgets: number | null
  /** true: el pedido coincidía con un tablero que ya tenías; no se creó otro. */
  existing: boolean
}

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i

export function isUuid(value: unknown): value is string {
  return typeof value === "string" && UUID.test(value)
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

/** Bloques ```chart y ```dashboard del contenido (para partir el texto del mensaje). */
export const MESSAGE_BLOCK = /(```(?:chart|dashboard)\s*\n[\s\S]*?\n```)/

/** true si el mensaje trae al menos un bloque de tablero válido (el chat refresca la lista de tableros). */
export function hasDashboardBlock(content: string): boolean {
  const re = /```dashboard\s*\n([\s\S]*?)\n```/g
  let match: RegExpExecArray | null
  while ((match = re.exec(content)) !== null) {
    if (parseDashboardBlock(match[1])) return true
  }
  return false
}
