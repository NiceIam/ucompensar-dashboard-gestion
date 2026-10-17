import { afterEach, beforeEach, describe, expect, test, vi } from "vitest"
import { describeChatError, getChatErrorMessage, isChatLimitError } from "./chat-errors"

const FALLBACK = "Error al enviar el mensaje"
const apiError = (body: unknown) => new Error(typeof body === "string" ? body : JSON.stringify(body))

describe("getChatErrorMessage", () => {
  test("límite por usuario muestra los segundos de espera", () => {
    const err = apiError({
      detail: { code: "rate_limit_user", message: "x", retry_after_seconds: 42, retry_at: "2026-01-01T00:00:42Z" },
    })
    expect(getChatErrorMessage(err, FALLBACK)).toBe(
      "Alcanzaste el límite de mensajes del asistente; intenta de nuevo en 42 segundos."
    )
  })

  test("singular cuando falta 1 segundo", () => {
    const err = apiError({ detail: { code: "rate_limit_user", retry_after_seconds: 1 } })
    expect(getChatErrorMessage(err, FALLBACK)).toContain("en 1 segundo.")
  })

  describe("tope diario de la organización", () => {
    beforeEach(() => {
      vi.useFakeTimers()
      vi.setSystemTime(new Date(2026, 4, 1, 9, 0, 0)) // 1 de mayo 2026, 09:00 hora local
    })
    afterEach(() => {
      vi.useRealTimers()
    })

    const quotaError = (retryAt: Date) =>
      apiError({ detail: { code: "quota_org_daily", retry_after_seconds: 1, retry_at: retryAt.toISOString() } })
    const hhmm = (d: Date) => d.toLocaleTimeString("es-CO", { hour: "2-digit", minute: "2-digit" })

    test("si se libera hoy muestra solo la hora aproximada (HH:MM)", () => {
      const at = new Date(2026, 4, 1, 15, 30)
      const msg = getChatErrorMessage(quotaError(at), FALLBACK)

      expect(msg).toBe(
        `La organización alcanzó el límite diario de mensajes del asistente; se libera aproximadamente a las ${hhmm(at)}.`
      )
    })

    test("si se libera mañana lo dice", () => {
      const at = new Date(2026, 4, 2, 10, 30)
      expect(getChatErrorMessage(quotaError(at), FALLBACK)).toContain(`se libera aproximadamente mañana a las ${hhmm(at)}.`)
    })

    test("si es más lejos incluye la fecha", () => {
      const at = new Date(2026, 4, 5, 10, 30)
      const msg = getChatErrorMessage(quotaError(at), FALLBACK)
      expect(msg).toMatch(/aproximadamente el 5 de mayo a las /)
    })
  })

  test("tope diario sin retry_at usa retry_after_seconds, y sin ninguno degrada con gracia", () => {
    expect(getChatErrorMessage(apiError({ detail: { code: "quota_org_daily", retry_after_seconds: 60 } }), FALLBACK)).toMatch(
      /aproximadamente a las /
    )
    expect(getChatErrorMessage(apiError({ detail: { code: "quota_org_daily" } }), FALLBACK)).toContain("más tarde")
    expect(
      getChatErrorMessage(apiError({ detail: { code: "quota_org_daily", retry_at: "basura" } }), FALLBACK)
    ).toContain("más tarde")
  })

  test("cuerpo por defecto de slowapi también se traduce", () => {
    const err = apiError({ error: "Rate limit exceeded: 20 per 1 minute" })
    expect(getChatErrorMessage(err, FALLBACK)).toBe(
      "Estás enviando mensajes muy rápido; intenta de nuevo en unos segundos."
    )
  })

  // Cambio deliberado del rediseño: antes estos errores mostraban el texto crudo del
  // servidor (por ejemplo '{"detail":"Token invalido"}'); ahora pasan por el traductor
  // central y nunca llega JSON a la pantalla.
  test("otros errores se traducen a lenguaje humano (nunca JSON crudo)", () => {
    const tokenMsg = getChatErrorMessage(apiError({ detail: "Token invalido" }), FALLBACK)
    expect(tokenMsg).not.toContain("{")
    expect(tokenMsg).toContain("Token invalido")
    expect(getChatErrorMessage(new Error("Failed to fetch"), FALLBACK)).toBe(
      "No pudimos conectarnos. Revisa tu conexión a internet e inténtalo de nuevo en un momento."
    )
    expect(getChatErrorMessage(apiError("texto plano"), FALLBACK)).toBe(
      "El asistente no pudo responder. Texto plano."
    )
  })

  test("valores que no son Error usan el fallback", () => {
    expect(getChatErrorMessage("boom", FALLBACK)).toBe(FALLBACK)
    expect(getChatErrorMessage(undefined, FALLBACK)).toBe(FALLBACK)
  })
})

describe("describeChatError", () => {
  test("los límites no se reintentan y conservan el mensaje del 429", () => {
    const info = describeChatError(apiError({ detail: { code: "rate_limit_user", retry_after_seconds: 5 } }))
    expect(info.rateLimited).toBe(true)
    expect(info.retryable).toBe(false)
    expect(info.description).toContain("en 5 segundos")
  })

  test("un fallo de red se puede reintentar", () => {
    const info = describeChatError(new TypeError("Failed to fetch"))
    expect(info.rateLimited).toBe(false)
    expect(info.retryable).toBe(true)
    expect(info.title).toBe("No pudimos conectarnos")
  })
})

describe("isChatLimitError", () => {
  test("detecta los 429 de límite y cuota, y nada más", () => {
    expect(isChatLimitError(apiError({ detail: { code: "rate_limit_user" } }))).toBe(true)
    expect(isChatLimitError(apiError({ detail: { code: "quota_org_daily" } }))).toBe(true)
    expect(isChatLimitError(apiError({ error: "Rate limit exceeded: 20 per 1 minute" }))).toBe(true)
    expect(isChatLimitError(apiError({ detail: "Token invalido" }))).toBe(false)
    expect(isChatLimitError(new Error("Failed to fetch"))).toBe(false)
    expect(isChatLimitError("boom")).toBe(false)
  })
})
