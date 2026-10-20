import { beforeEach, describe, expect, test, vi } from "vitest"
import { render, screen, waitFor, within } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import type { ReactNode } from "react"

const { get, post } = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn() }))
vi.mock("@/lib/api", () => ({ api: { get, post, delete: vi.fn() } }))
const { toastSuccess, toastError } = vi.hoisted(() => ({ toastSuccess: vi.fn(), toastError: vi.fn() }))
vi.mock("sonner", () => ({ toast: { success: toastSuccess, error: toastError, info: vi.fn() } }))

import { ApiError } from "@/lib/errors"
import { MessageContent, plainText } from "./message-content"

const ID = "3f2c1f7e-1111-4222-8333-444455556666"
const VERSION = "9a1b2c3d-5555-4666-8777-888899990000"
const block = (obj: unknown) => `\`\`\`dashboard_edit\n${JSON.stringify(obj)}\n\`\`\``
const edit = {
  id: ID,
  name: "Ventas por día",
  widgets: 4,
  version: VERSION,
  noop: false,
  renamed: null,
  added: ["Suma de total por método de pago"],
  replaced: [],
  removed: ["Promedio de precio"],
  unchanged: [],
}

function wrap(ui: ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })
  return { client, ...render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>) }
}

const card = (over: Record<string, unknown> = {}) => wrap(<MessageContent text={`Listo.\n${block({ ...edit, ...over })}`} />)
const apiError = (status: number, body: unknown) => new ApiError(status, JSON.stringify(body))

beforeEach(() => {
  get.mockReset().mockResolvedValue([{ dashboard_id: ID, name: edit.name, created_at: "2026-10-16T10:00:00Z" }])
  post.mockReset()
  toastSuccess.mockReset()
  toastError.mockReset()
})

describe("tarjeta del tablero editado por el asistente", () => {
  test("dice qué cambió, con texto y no solo con color, y ofrece abrir y deshacer", () => {
    card()
    expect(screen.getByRole("region", { name: "Tablero editado: Ventas por día" })).toBeInTheDocument()
    expect(screen.getByText("Tablero editado")).toBeInTheDocument()
    expect(screen.getByText("Edité «Ventas por día»: agregué 1 gráfico, quité 1.")).toBeInTheDocument()
    const list = screen.getByRole("list", { name: "Qué cambió" })
    expect(within(list).getByText("Agregué")).toBeInTheDocument()
    expect(within(list).getByText(/«Suma de total por método de pago»/)).toBeInTheDocument()
    expect(within(list).getByText("Quité")).toBeInTheDocument()
    expect(within(list).getByText(/«Promedio de precio»/)).toBeInTheDocument()
    expect(screen.getByText("Ahora tiene 4 gráficos y cifras.")).toBeInTheDocument()
    expect(screen.getByRole("link", { name: /Abrir tablero/ })).toHaveAttribute("href", `/dashboards/${ID}`)
    expect(screen.getByRole("button", { name: /Deshacer/ })).toBeInTheDocument()
    expect(screen.getByText("Listo.")).toBeInTheDocument()
  })

  test("reemplazo, renombrar y lo que ya estaba", () => {
    card({
      added: [],
      removed: [],
      renamed: { from: "Ventas", to: "Ventas por día" },
      replaced: [{ from: "Cantidad por producto", to: "Suma de total por mes" }],
      unchanged: ["Promedio de edad"],
    })
    expect(screen.getByText("Edité «Ventas por día»: reemplacé 1 gráfico, cambié el nombre.")).toBeInTheDocument()
    const list = screen.getByRole("list", { name: "Qué cambió" })
    expect(within(list).getByText("Cambié el nombre")).toBeInTheDocument()
    expect(within(list).getByText(/de «Ventas» a «Ventas por día»/)).toBeInTheDocument()
    expect(within(list).getByText("Reemplacé")).toBeInTheDocument()
    expect(within(list).getByText(/«Cantidad por producto» por «Suma de total por mes»/)).toBeInTheDocument()
    expect(within(list).getByText("Ya estaba")).toBeInTheDocument()
  })

  test("sin cambios (noop): lo dice y no ofrece Deshacer", () => {
    card({ noop: true, version: null, added: [], removed: [], unchanged: ["Promedio de precio"] })
    expect(screen.getByText("Sin cambios")).toBeInTheDocument()
    expect(screen.getByText("No cambié nada: eso ya estaba en el tablero.")).toBeInTheDocument()
    expect(screen.getByText("Ya estaba")).toBeInTheDocument()
    expect(screen.queryByRole("button", { name: /Deshacer/ })).toBeNull()
    expect(screen.getByRole("link", { name: /Abrir tablero/ })).toBeInTheDocument()
  })

  test("sin versión válida tampoco se ofrece Deshacer", () => {
    card({ version: "no-es-uuid" })
    expect(screen.queryByRole("button", { name: /Deshacer/ })).toBeNull()
  })

  test("pedir deshacer abre una confirmación accesible y no llama al servidor hasta confirmar", async () => {
    card()
    const trigger = screen.getByRole("button", { name: /Deshacer/ })
    await userEvent.click(trigger)
    const dialog = await screen.findByRole("alertdialog")
    expect(within(dialog).getByText("¿Deshacer el cambio en «Ventas por día»?")).toBeInTheDocument()
    expect(within(dialog).getByText("El tablero vuelve a como estaba antes.")).toBeInTheDocument()
    expect(post).not.toHaveBeenCalled()
    // Cancelar devuelve el foco al botón que abrió el diálogo.
    await userEvent.click(within(dialog).getByRole("button", { name: "Cancelar" }))
    await waitFor(() => expect(screen.queryByRole("alertdialog")).toBeNull())
    await waitFor(() => expect(screen.getByRole("button", { name: /Deshacer/ })).toHaveFocus())
    expect(post).not.toHaveBeenCalled()
  })

  test("Escape cierra el diálogo pero no llega al panel que contiene la tarjeta (no cierra el chat)", async () => {
    const outer = vi.fn()
    wrap(
      <div onKeyDown={(e) => e.key === "Escape" && outer()}>
        <MessageContent text={block(edit)} />
      </div>
    )
    await userEvent.click(screen.getByRole("button", { name: /Deshacer/ }))
    await screen.findByRole("alertdialog")
    await userEvent.keyboard("{Escape}")
    await waitFor(() => expect(screen.queryByRole("alertdialog")).toBeNull())
    expect(outer).not.toHaveBeenCalled()
  })

  test("confirmar deshace: llama al servidor, invalida lista y detalle, avisa y atenúa la tarjeta", async () => {
    post.mockResolvedValue({ id: ID, name: "Ventas", widgets: 3, discarded_newer: 0 })
    const { client } = card()
    const invalidate = vi.spyOn(client, "invalidateQueries")
    await userEvent.click(screen.getByRole("button", { name: /Deshacer/ }))
    await userEvent.click(within(await screen.findByRole("alertdialog")).getByRole("button", { name: "Sí, deshacer" }))
    await waitFor(() => expect(post).toHaveBeenCalledWith(`/api/v1/dashboards/${ID}/undo-edit`, { version: VERSION, include_newer: false }))
    expect(await screen.findByText("Deshiciste este cambio en «Ventas».")).toBeInTheDocument()
    expect(screen.getByText("Cambio deshecho")).toBeInTheDocument()
    expect(toastSuccess).toHaveBeenCalledWith("Restauramos «Ventas»")
    expect(invalidate).toHaveBeenCalledWith({ queryKey: ["dashboards"] })
    expect(invalidate).toHaveBeenCalledWith({ queryKey: ["dashboard-meta", ID] })
    expect(invalidate).toHaveBeenCalledWith({ queryKey: ["dashboard-execute", ID] })
    // Deshecho: ya no hay Deshacer ni lista de cambios, pero sigue pudiendo abrirse.
    expect(screen.queryByRole("button", { name: /Deshacer/ })).toBeNull()
    expect(screen.queryByRole("list", { name: "Qué cambió" })).toBeNull()
    expect(screen.getByRole("link", { name: /Abrir tablero/ })).toHaveAttribute("href", `/dashboards/${ID}`)
    // El botón que tenía el foco desaparece: el foco pasa a «Abrir tablero» en vez de perderse.
    await waitFor(() => expect(screen.getByRole("link", { name: /Abrir tablero/ })).toHaveFocus())
  })

  test("el cambio de estado se anuncia en una región viva que ya estaba montada", async () => {
    post.mockResolvedValue({ id: ID, name: "Ventas por día", widgets: 3, discarded_newer: 0 })
    card()
    const live = screen.getByText(/^Edité «Ventas por día»/).closest("[aria-live]")
    expect(live).toHaveAttribute("aria-live", "polite")
    await userEvent.click(screen.getByRole("button", { name: /Deshacer/ }))
    await userEvent.click(within(await screen.findByRole("alertdialog")).getByRole("button", { name: "Sí, deshacer" }))
    await waitFor(() => expect(live).toHaveTextContent("Deshiciste este cambio en «Ventas por día»."))
  })

  test("mientras deshace, el botón de confirmar queda bloqueado y el diálogo no se cierra", async () => {
    let finish: (v: unknown) => void = () => undefined
    post.mockReturnValue(new Promise((resolve) => (finish = resolve)))
    card()
    await userEvent.click(screen.getByRole("button", { name: /Deshacer/ }))
    const dialog = await screen.findByRole("alertdialog")
    await userEvent.click(within(dialog).getByRole("button", { name: "Sí, deshacer" }))
    await waitFor(() => expect(within(dialog).getByRole("button", { name: "Cancelar" })).toBeDisabled())
    expect(screen.getByRole("alertdialog")).toBeInTheDocument()
    finish({ id: ID, name: "Ventas por día", widgets: 3, discarded_newer: 0 })
    await waitFor(() => expect(screen.queryByRole("alertdialog")).toBeNull())
  })

  test("un error cualquiera sale como aviso humano y la tarjeta sigue usable", async () => {
    post.mockRejectedValue(new ApiError(500, "Traceback (most recent call last) boom"))
    card()
    await userEvent.click(screen.getByRole("button", { name: /Deshacer/ }))
    await userEvent.click(within(await screen.findByRole("alertdialog")).getByRole("button", { name: "Sí, deshacer" }))
    await waitFor(() => expect(toastError).toHaveBeenCalled())
    const [title, opts] = toastError.mock.calls[0] as [string, { description: string }]
    expect(title).toBe("No pudimos guardar los cambios")
    expect(`${title} ${opts.description}`).not.toMatch(/Traceback|boom|HTTP|500/)
    await waitFor(() => expect(screen.queryByRole("alertdialog")).toBeNull())
    expect(screen.getByRole("button", { name: /Deshacer/ })).toBeEnabled()
    expect(screen.getByText(/^Edité «Ventas por día»/)).toBeInTheDocument()
  })

  test("404: ese cambio ya no se puede deshacer", async () => {
    post.mockRejectedValue(apiError(404, { detail: "La versión ya no existe" }))
    card()
    await userEvent.click(screen.getByRole("button", { name: /Deshacer/ }))
    await userEvent.click(within(await screen.findByRole("alertdialog")).getByRole("button", { name: "Sí, deshacer" }))
    expect(await screen.findByText("Este cambio ya no se puede deshacer.")).toBeInTheDocument()
    expect(screen.queryByRole("button", { name: /Deshacer/ })).toBeNull()
    expect(screen.getByRole("link", { name: /Abrir tablero/ })).toBeInTheDocument()
    expect(toastError).not.toHaveBeenCalled()
  })

  test("409 newer_edits: avisa de los cambios más recientes y pide confirmar de nuevo con include_newer", async () => {
    post.mockRejectedValueOnce(apiError(409, { detail: { code: "newer_edits", count: 2, message: "hay cambios más nuevos" } }))
    post.mockResolvedValueOnce({ id: ID, name: "Ventas", widgets: 3, discarded_newer: 2 })
    card()
    await userEvent.click(screen.getByRole("button", { name: /Deshacer/ }))
    await userEvent.click(within(await screen.findByRole("alertdialog")).getByRole("button", { name: "Sí, deshacer" }))
    expect(await screen.findByText("Este tablero tiene 2 cambios más recientes. Si deshaces este, también se pierden esos.")).toBeInTheDocument()
    expect(screen.getByRole("alertdialog")).toBeInTheDocument() // sigue abierto: la segunda confirmación vive ahí
    expect(post).toHaveBeenCalledTimes(1)
    expect(post).toHaveBeenLastCalledWith(`/api/v1/dashboards/${ID}/undo-edit`, { version: VERSION, include_newer: false })
    expect(toastError).not.toHaveBeenCalled()

    await userEvent.click(screen.getByRole("button", { name: "Sí, deshacer todo" }))
    await waitFor(() => expect(post).toHaveBeenCalledTimes(2))
    expect(post).toHaveBeenLastCalledWith(`/api/v1/dashboards/${ID}/undo-edit`, { version: VERSION, include_newer: true })
    expect(await screen.findByText("Deshiciste este cambio en «Ventas».")).toBeInTheDocument()
  })

  test("409 newer_edits: cancelar no deshace nada y la próxima vez vuelve a la pregunta normal", async () => {
    post.mockRejectedValue(apiError(409, { detail: { code: "newer_edits", count: 1, message: "x" } }))
    card()
    await userEvent.click(screen.getByRole("button", { name: /Deshacer/ }))
    await userEvent.click(within(await screen.findByRole("alertdialog")).getByRole("button", { name: "Sí, deshacer" }))
    expect(await screen.findByText(/1 cambio más reciente/)).toBeInTheDocument()
    await userEvent.click(screen.getByRole("button", { name: "Cancelar" }))
    await waitFor(() => expect(screen.queryByRole("alertdialog")).toBeNull())
    expect(post).toHaveBeenCalledTimes(1)
    await userEvent.click(screen.getByRole("button", { name: /Deshacer/ }))
    expect(await screen.findByText("¿Deshacer el cambio en «Ventas por día»?")).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "Sí, deshacer" })).toBeInTheDocument()
  })

  test("si el tablero ya no existe en la lista, no ofrece abrirlo ni deshacer", async () => {
    get.mockResolvedValue([])
    card()
    expect(await screen.findByText("Ya no existe el tablero «Ventas por día».")).toBeInTheDocument()
    expect(screen.queryByRole("link", { name: /Abrir tablero/ })).toBeNull()
    expect(screen.queryByRole("button", { name: /Deshacer/ })).toBeNull()
  })

  test("un id que no es UUID NO crea enlace ni tarjeta", () => {
    const { container } = card({ id: "../../settings" })
    expect(screen.getByText("Listo.")).toBeInTheDocument()
    expect(container.querySelector("a")).toBeNull()
    expect(screen.queryByText(edit.name)).toBeNull()
  })

  test("un bloque dañado no rompe el mensaje", () => {
    wrap(<MessageContent text={"Antes\n```dashboard_edit\n{roto\n```\nDespués"} />)
    expect(screen.getByText("Antes")).toBeInTheDocument()
    expect(screen.getByText("Después")).toBeInTheDocument()
    expect(screen.queryByRole("link")).toBeNull()
  })

  test("los textos se pintan como texto, nunca como HTML ni como enlace", () => {
    const { container } = card({
      name: "<b>Hola</b>",
      added: ["<img src=x onerror=alert(1)> [click](http://evil)"],
      renamed: { from: "<i>a</i>", to: "[b](http://evil)" },
    })
    expect(container.querySelector("img")).toBeNull()
    expect(container.querySelector("b")).toBeNull()
    expect(container.querySelector("i")).toBeNull()
    expect(container.querySelectorAll("a")).toHaveLength(1) // solo «Abrir tablero»
    expect(screen.getByText(/<img src=x/)).toBeInTheDocument()
  })

  test("nombres larguísimos se parten en lugar de desbordar", () => {
    card({ name: "N".repeat(110), added: ["x".repeat(80)] })
    expect(screen.getByText("N".repeat(110))).toHaveClass("break-words")
  })

  test("el bloque de edición no es un bloque de creación: no sale «Tablero creado»", () => {
    card()
    expect(screen.queryByText("Tablero creado")).toBeNull()
  })

  test("sin jerga: no aparece «versión», «snapshot» ni «endpoint»", () => {
    const { container } = card()
    expect(container.textContent).not.toMatch(/versi[oó]n|snapshot|endpoint|undo-edit/i)
  })

  test("el texto para copiar no lleva el bloque de edición", () => {
    expect(plainText(`Listo.\n${block(edit)}`)).toBe("Listo.")
  })
})
