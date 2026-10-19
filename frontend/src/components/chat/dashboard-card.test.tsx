import { beforeEach, describe, expect, test, vi } from "vitest"
import { render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import type { ReactNode } from "react"

const { get, del } = vi.hoisted(() => ({ get: vi.fn(), del: vi.fn() }))
vi.mock("@/lib/api", () => ({ api: { get, delete: del, post: vi.fn() } }))
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn(), info: vi.fn() } }))

import { MessageContent, plainText } from "./message-content"

const ID = "3f2c1f7e-1111-4222-8333-444455556666"
const block = (obj: unknown) => `\`\`\`dashboard\n${JSON.stringify(obj)}\n\`\`\``
const board = { id: ID, name: "Ventas por mes y por producto", widgets: 4, existing: false }

function wrap(ui: ReactNode, client = new QueryClient({ defaultOptions: { queries: { retry: false } } })) {
  return { client, ...render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>) }
}

describe("tarjeta del tablero creado por el asistente", () => {
  beforeEach(() => {
    get.mockReset().mockResolvedValue([{ dashboard_id: ID, name: board.name, created_at: "2026-10-16T10:00:00Z" }])
    del.mockReset().mockResolvedValue(undefined)
  })

  test("muestra el nombre, cuántos gráficos y el enlace a abrirlo", async () => {
    wrap(<MessageContent text={`Listo, ahí está.\n${block(board)}`} />)
    expect(screen.getByText("Listo, ahí está.")).toBeInTheDocument()
    expect(screen.getByText("Tablero creado")).toBeInTheDocument()
    expect(screen.getByText(board.name)).toBeInTheDocument()
    expect(screen.getByText(/4 gráficos y cifras\./)).toBeInTheDocument()
    expect(screen.getByText(/Los datos se actualizan cada vez que lo abres/)).toBeInTheDocument()
    const open = screen.getByRole("link", { name: /Abrir tablero/ })
    expect(open).toHaveAttribute("href", `/dashboards/${ID}`)
  })

  test("si el servidor dice que ya existía, lo avisa y ofrece Eliminar con confirmación", async () => {
    wrap(<MessageContent text={block({ ...board, existing: true })} />)
    expect(screen.getByText("Ya tenías este tablero")).toBeInTheDocument()
    await userEvent.click(screen.getByRole("button", { name: /Eliminar/ }))
    expect(await screen.findByText(`¿Eliminar «${board.name}»?`)).toBeInTheDocument()
    expect(del).not.toHaveBeenCalled()
  })

  test("Deshacer borra el tablero (borrado lógico existente), invalida la lista y lo confirma en la tarjeta", async () => {
    const { client } = wrap(<MessageContent text={block(board)} />)
    const invalidate = vi.spyOn(client, "invalidateQueries")
    await userEvent.click(screen.getByRole("button", { name: /Deshacer/ }))
    await waitFor(() => expect(del).toHaveBeenCalledWith(`/api/v1/dashboards/${ID}`))
    expect(await screen.findByText(/Eliminaste el tablero/)).toBeInTheDocument()
    expect(screen.queryByRole("link", { name: /Abrir tablero/ })).toBeNull()
    expect(invalidate).toHaveBeenCalledWith({ queryKey: ["dashboards"] })
  })

  test("si el tablero ya no existe en la lista (mensaje viejo), no ofrece abrirlo", async () => {
    get.mockResolvedValue([])
    wrap(<MessageContent text={block(board)} />)
    expect(await screen.findByText(/Ya no existe el tablero/)).toBeInTheDocument()
    expect(screen.queryByRole("link", { name: /Abrir tablero/ })).toBeNull()
  })

  test("un id que no es UUID NO crea enlace ni tarjeta", () => {
    const { container } = wrap(<MessageContent text={`Mira\n${block({ ...board, id: "../../settings" })}`} />)
    expect(screen.getByText("Mira")).toBeInTheDocument()
    expect(screen.queryByRole("link")).toBeNull()
    expect(container.querySelector("a")).toBeNull()
    expect(screen.queryByText(board.name)).toBeNull()
  })

  test("un bloque dañado no rompe el mensaje", () => {
    wrap(<MessageContent text={"Antes\n```dashboard\n{roto\n```\nDespués"} />)
    expect(screen.getByText("Antes")).toBeInTheDocument()
    expect(screen.getByText("Después")).toBeInTheDocument()
    expect(screen.queryByRole("link")).toBeNull()
  })

  test("el nombre se pinta como texto, nunca como HTML ni como enlace", () => {
    const { container } = wrap(<MessageContent text={block({ ...board, name: "<img src=x onerror=alert(1)> [click](http://evil)" })} />)
    expect(container.querySelector("img")).toBeNull()
    expect(container.querySelectorAll("a")).toHaveLength(1) // solo «Abrir tablero»
    expect(screen.getByText(/<img src=x/)).toBeInTheDocument()
  })

  test("texto copiado sin bloques de tablero", () => {
    expect(plainText(`Listo.\n${block(board)}`)).toBe("Listo.")
  })
})
