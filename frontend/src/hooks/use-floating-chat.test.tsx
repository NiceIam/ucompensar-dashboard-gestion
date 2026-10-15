import { beforeEach, describe, expect, test, vi } from "vitest"
import { act, renderHook, waitFor } from "@testing-library/react"

const { get, post } = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn() }))

vi.mock("@/lib/api", () => ({ api: { get, post, upload: vi.fn() } }))
vi.mock("next/navigation", () => ({ usePathname: () => "/" }))

import { useFloatingChat } from "./use-floating-chat"

const apiError = (body: unknown) => new Error(JSON.stringify(body))

async function setup() {
  const hook = renderHook(() => useFloatingChat())
  await waitFor(() => expect(hook.result.current.isLoading).toBe(false))
  return hook
}

describe("useFloatingChat.sendMessage ante límites del backend", () => {
  beforeEach(() => {
    get.mockReset().mockResolvedValue({ messages: [], total: 0 })
    post.mockReset()
  })

  test("429 por usuario: muestra el mensaje en español, quita el mensaje optimista y avisa rateLimited", async () => {
    post.mockRejectedValue(
      apiError({ detail: { code: "rate_limit_user", message: "x", retry_after_seconds: 30, retry_at: "2026-01-01T00:00:30Z" } })
    )
    const { result } = await setup()

    let outcome: { rateLimited: boolean } | undefined
    await act(async () => {
      outcome = await result.current.sendMessage("hola")
    })

    expect(outcome).toEqual({ rateLimited: true })
    expect(result.current.error).toBe(
      "Alcanzaste el límite de mensajes del asistente; intenta de nuevo en 30 segundos."
    )
    expect(result.current.messages).toEqual([])
    expect(result.current.isSending).toBe(false)
  })

  test("429 por cuota de la organización también es rateLimited", async () => {
    post.mockRejectedValue(apiError({ detail: { code: "quota_org_daily", retry_after_seconds: 3600 } }))
    const { result } = await setup()

    let outcome: { rateLimited: boolean } | undefined
    await act(async () => {
      outcome = await result.current.sendMessage("hola")
    })

    expect(outcome).toEqual({ rateLimited: true })
    expect(result.current.error).toContain("límite diario")
  })

  test("otros errores NO son rateLimited y conservan su mensaje original", async () => {
    post.mockRejectedValue(new Error("Failed to fetch"))
    const { result } = await setup()

    let outcome: { rateLimited: boolean } | undefined
    await act(async () => {
      outcome = await result.current.sendMessage("hola")
    })

    expect(outcome).toEqual({ rateLimited: false })
    expect(result.current.error).toBe("Failed to fetch")
  })

  test("envío exitoso: rateLimited false y mensajes agregados", async () => {
    post.mockResolvedValue({ message_id: "m1", role: "assistant", content: "ok", created_at: "2026-01-01T00:00:00Z" })
    const { result } = await setup()

    let outcome: { rateLimited: boolean } | undefined
    await act(async () => {
      outcome = await result.current.sendMessage("hola")
    })

    expect(outcome).toEqual({ rateLimited: false })
    expect(result.current.error).toBeNull()
    expect(result.current.messages.map((m) => m.content)).toEqual(["hola", "ok"])
  })
})
