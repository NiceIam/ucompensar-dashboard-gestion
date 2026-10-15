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

/**
 * Mensaje en español para los 429 del chat (POST /api/v1/chat/message):
 * - detail.code "rate_limit_user": límite de mensajes por usuario (slowapi o cuota en BD).
 * - detail.code "quota_org_daily": tope diario de la organización.
 * - cuerpo {"error": "Rate limit exceeded..."} de slowapi (respaldo).
 * Cualquier otro error conserva su mensaje original (`fallback` si no es un Error).
 */
export function getChatErrorMessage(err: unknown, fallback: string): string {
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
      ? `La organización alcanzó el límite diario de mensajes del asistente; se libera aproximadamente ${when}.`
      : "La organización alcanzó el límite diario de mensajes del asistente; intenta de nuevo más tarde."
  }

  if (typeof body?.error === "string" && body.error.startsWith("Rate limit exceeded")) {
    return "Estás enviando mensajes muy rápido; intenta de nuevo en unos segundos."
  }

  return err instanceof Error ? err.message : fallback
}

/** true si el error es un 429 de límite/cuota del chat (el texto escrito por el usuario conviene restaurarlo). */
export function isChatLimitError(err: unknown): boolean {
  const body = parseBody(err)
  const detail = body?.detail && typeof body.detail === "object" ? (body.detail as ChatLimitDetail) : null
  return (
    detail?.code === "rate_limit_user" ||
    detail?.code === "quota_org_daily" ||
    (typeof body?.error === "string" && body.error.startsWith("Rate limit exceeded"))
  )
}
