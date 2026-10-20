import { beforeEach, describe, expect, test, vi } from "vitest"
import { act, render, waitFor } from "@testing-library/react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"

const { get, post } = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn() }))
vi.mock("@/lib/api", () => ({ api: { get, post, upload: vi.fn() } }))
vi.mock("next/navigation", () => ({ usePathname: () => "/" }))

import { ChatProvider, useChat } from "./chat-provider"

const ID = "3f2c1f7e-1111-4222-8333-444455556666"
const OTHER = "11111111-2222-4333-8444-555566667777"
const editBlock = (id: string, noop = false) =>
  `\`\`\`dashboard_edit\n${JSON.stringify({ id, name: "Ventas", widgets: 3, version: noop ? null : OTHER, noop, renamed: null, added: ["a"], replaced: [], removed: [], unchanged: [] })}\n\`\`\``

function setup() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  const invalidate = vi.spyOn(client, "invalidateQueries")
  let ctx!: ReturnType<typeof useChat>
  function Probe() {
    ctx = useChat()
    return null
  }
  render(
    <QueryClientProvider client={client}>
      <ChatProvider>
        <Probe />
      </ChatProvider>
    </QueryClientProvider>
  )
  return { invalidate, ctx: () => ctx }
}

beforeEach(() => {
  get.mockReset().mockResolvedValue({ messages: [], total: 0 })
  post.mockReset()
  window.matchMedia = ((q: string) => ({ matches: false, media: q, addEventListener: () => undefined, removeEventListener: () => undefined })) as unknown as typeof window.matchMedia
})

describe("ChatProvider", () => {
  test("una pregunta solo escrita conserva el espacio final (la persona sigue escribiendo ahí)", () => {
    const { ctx } = setup()
    act(() => ctx().ask("Quiero editar el tablero «Ventas»: ", { send: false }))
    expect(ctx().pending?.text).toBe("Quiero editar el tablero «Ventas»: ")
    expect(ctx().pending?.send).toBe(false)
  })

  test("una pregunta que se envía sí se recorta, y una vacía se ignora", () => {
    const { ctx } = setup()
    act(() => ctx().ask("  hola  "))
    expect(ctx().pending?.text).toBe("hola")
    act(() => ctx().consumePending())
    act(() => ctx().ask("   ", { send: false }))
    expect(ctx().pending).toBeNull()
  })

  test("si el asistente EDITA un tablero se refresca la lista y el detalle de ese tablero", async () => {
    post.mockResolvedValue({ message_id: "m1", role: "assistant", content: `Listo.\n${editBlock(ID)}`, created_at: "2026-10-19T10:00:00Z" })
    const { ctx, invalidate } = setup()
    await act(async () => {
      await ctx().chat.sendMessage("agrégale un gráfico")
    })
    await waitFor(() => expect(invalidate).toHaveBeenCalledWith({ queryKey: ["dashboard-meta", ID] }))
    expect(invalidate).toHaveBeenCalledWith({ queryKey: ["dashboard-execute", ID] })
    expect(invalidate).toHaveBeenCalledWith({ queryKey: ["dashboards"] })
  })

  test("si no cambió nada (noop) no se toca el detalle, solo la lista", async () => {
    post.mockResolvedValue({ message_id: "m1", role: "assistant", content: editBlock(ID, true), created_at: "2026-10-19T10:00:00Z" })
    const { ctx, invalidate } = setup()
    await act(async () => {
      await ctx().chat.sendMessage("agrégale un gráfico")
    })
    await waitFor(() => expect(invalidate).toHaveBeenCalledWith({ queryKey: ["dashboards"] }))
    expect(invalidate).not.toHaveBeenCalledWith({ queryKey: ["dashboard-meta", ID] })
  })
})
