import { humanizeError, humanizeErrorText } from "@/lib/errors"

interface ChatLimitDetail {
  code?: string
  message?: string
  retry_after_seconds?: number
  retry_at?: string
}

function parseBody(err: unknown): { detail?: unknown; error?: unknown } | null {
  // api.ts lanza Error(<texto crudo de la respuesta>): el cuerpo JSON del backend viene en message.
  if (!(err instanceof Error)) return null
  try {
    const body: unknown = JSON.parse(err.message)
    return body && typeof body === "object" ? (body as { detail?: unknown; error?: unknown }) : null
  } catch {
    return null
  }
}

function startOfDay(date: Date): number {
  return new Date(date.getFullYear(), date.getMonth(), date.getDate()).getTime()
}

// "a las 3:30 p. m." si es hoy, "mañana a las ..." si es mañana, "el 16 de octubre a las ..." si es más lejos.
function formatWhen(retryAt?: string, retryAfterSeconds?: number): string | null {
  const date = retryAt
    ? new Date(retryAt)
    : retryAfterSeconds !== undefined
      ? new Date(Date.now() + retryAfterSeconds * 1000)
      : null
  if (!date || Number.isNaN(date.getTime())) return null
  const time = date.toLocaleTimeString("es-CO", { hour: "2-digit", minute: "2-digit" })
  const days = Math.round((startOfDay(date) - startOfDay(new Date())) / 86_400_000)
  if (days <= 0) return `a las ${time}`
  if (days === 1) return `mañana a las ${time}`
  return `el ${date.toLocaleDateString("es-CO", { day: "numeric", month: "long" })} a las ${time}`
}

/** Mensaje de límite/cuota (429) del chat, o null si el error no es de ese tipo. */
function limitMessage(err: unknown): string | null {
  const body = parseBody(err)
  const detail = body?.detail && typeof body.detail === "object" ? (body.detail as ChatLimitDetail) : null

  if (detail?.code === "rate_limit_user") {
    const secs = detail.retry_after_seconds
    return typeof secs === "number"
      ? `Alcanzaste el límite de mensajes del asistente; intenta de nuevo en ${secs} ${secs === 1 ? "segundo" : "segundos"}.`
      : "Alcanzaste el límite de mensajes del asistente; intenta de nuevo en unos segundos."
  }

  if (detail?.code === "quota_org_daily") {
    const when = formatWhen(detail.retry_at, detail.retry_after_seconds)
    return when
      ? // "p. m." ya termina en punto: no se agrega otro ("p. m..").
        `La organización alcanzó el límite diario de mensajes del asistente; se libera aproximadamente ${when}${when.endsWith(".") ? "" : "."}`
      : "La organización alcanzó el límite diario de mensajes del asistente; intenta de nuevo más tarde."
  }

  if (typeof body?.error === "string" && body.error.startsWith("Rate limit exceeded")) {
    return "Estás enviando mensajes muy rápido; intenta de nuevo en unos segundos."
  }

  return null
}

/**
 * Mensaje en español para los errores del chat (POST /api/v1/chat/message):
 * - detail.code "rate_limit_user": límite de mensajes por usuario (slowapi o cuota en BD).
 * - detail.code "quota_org_daily": tope diario de la organización.
 * - cuerpo {"error": "Rate limit exceeded..."} de slowapi (respaldo).
 * Cualquier otro Error pasa por el traductor central (nunca JSON crudo);
 * `fallback` solo se usa si lo recibido no es un Error.
 */
export function getChatErrorMessage(err: unknown, fallback: string): string {
  const limit = limitMessage(err)
  if (limit) return limit
  return err instanceof Error ? humanizeErrorText(err, "chat") : fallback
}

/** true si el error es un 429 de límite/cuota del chat (el texto escrito por el usuario conviene restaurarlo). */
export function isChatLimitError(err: unknown): boolean {
  return limitMessage(err) !== null
}

export interface ChatErrorInfo {
  title: string
  description: string
  /** Reintentar el mismo mensaje tiene sentido (red, servidor); en límites no. */
  retryable: boolean
  rateLimited: boolean
}

/** Versión estructurada para la interfaz del chat (título + qué hacer + si se puede reintentar). */
export function describeChatError(err: unknown): ChatErrorInfo {
  const limit = limitMessage(err)
  if (limit) {
    const daily = limit.includes("límite diario")
    return {
      title: daily ? "Llegamos al tope de hoy" : "Una pausa breve",
      description: limit,
      retryable: false,
      rateLimited: true,
    }
  }
  const h = humanizeError(err, "chat")
  return { title: h.title, description: h.description, retryable: h.retryable, rateLimited: false }
}
