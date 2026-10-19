import { beforeEach, describe, expect, test, vi } from "vitest"
import { render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import type { Dashboard } from "@/types/api"

const ask = vi.fn()
const suggestMutate = vi.fn()
const suggestMutateAsync = vi.fn()
const state = vi.hoisted(() => ({
  dashboards: [] as unknown[],
  loading: false,
  tables: [] as unknown[],
  suggestPending: false,
}))

vi.mock("@/hooks/use-page-title", () => ({ usePageTitle: () => undefined }))
vi.mock("@/providers/chat-provider", () => ({ useChat: () => ({ ask }) }))
vi.mock("@/hooks/use-templates", () => ({
  useOrgTables: () => ({ data: { tables: state.tables, total: state.tables.length }, isLoading: false }),
}))
vi.mock("@/hooks/use-dashboards", () => ({
  useDashboards: () => ({
    data: state.dashboards,
    isLoading: state.loading,
    isError: false,
    error: null,
    refetch: vi.fn(),
    isFetching: false,
  }),
  useDeleteDashboard: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useSuggestDashboards: () => ({
    mutate: suggestMutate,
    mutateAsync: suggestMutateAsync,
    isPending: state.suggestPending,
    isError: false,
    error: null,
  }),
}))
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn(), info: vi.fn() } }))

import DashboardsPage from "./page"

const ventas = {
  id: "t1",
  table_name: "ventas",
  display_name: "Ventas",
  row_count: 120,
  columns_definition: [
    { name: "fecha", type: "date", label: "fecha" },
    { name: "producto", type: "text", label: "producto" },
    { name: "total", type: "number", label: "total" },
  ],
}

const dashboard = (over: Partial<Dashboard> = {}): Dashboard => ({
  id: "d1",
  dashboard_id: "3f2c1f7e-1111-4222-8333-444455556666",
  org_id: "o",
  name: "Resumen de Ventas",
  description: "Sugerido a partir de tus datos.",
  file_id: null,
  widgets: [],
  created_at: "2026-10-16T10:00:00Z",
  updated_at: "2026-10-16T10:00:00Z",
  widget_count: 4,
  source: "rules",
  preview: { type: "line", points: [3, 5, 4, 9] },
  highlights: ["Suma de total por mes de fecha", "Suma de total por producto"],
  ...over,
})

beforeEach(() => {
  ask.mockReset()
  suggestMutate.mockReset()
  suggestMutateAsync.mockReset().mockResolvedValue({ status: "created", source: "rules", dashboards: [{ id: "x", name: "n", widgets: 3, existing: false }] })
  state.dashboards = []
  state.loading = false
  state.tables = [ventas]
  state.suggestPending = false
})

describe("página de tableros: los crea el asistente, ya no hay formulario manual", () => {
  test("no existe «Nuevo tablero» ni el formulario con nombre y descripción", async () => {
    state.dashboards = [dashboard()]
    render(<DashboardsPage />)
    expect(screen.queryByRole("button", { name: /nuevo tablero/i })).toBeNull()
    expect(screen.queryByText(/Crear mi primer tablero/i)).toBeNull()
    expect(screen.queryByLabelText(/nombre/i)).toBeNull()
    expect(screen.getByRole("button", { name: /Pídele un tablero al asistente/ })).toBeInTheDocument()
    expect(screen.getByRole("button", { name: /Sugerir tableros/ })).toBeInTheDocument()
    expect(screen.queryByText(/script|código/i)).toBeNull()
  })

  test("«Pídele un tablero al asistente» abre el chat con una pregunta guía SIN enviarla", async () => {
    state.dashboards = [dashboard()]
    render(<DashboardsPage />)
    await userEvent.click(screen.getByRole("button", { name: /Pídele un tablero al asistente/ }))
    expect(ask).toHaveBeenCalledTimes(1)
    expect(ask.mock.calls[0][0]).toMatch(/^Quiero un tablero con el total mes a mes/)
    expect(ask.mock.calls[0][1]).toEqual({ send: false })
  })

  test("«Sugerir tableros» pide sugerencias y avisa cuántos armó", async () => {
    state.dashboards = [dashboard()]
    render(<DashboardsPage />)
    await userEvent.click(screen.getByRole("button", { name: /Sugerir tableros/ }))
    expect(suggestMutateAsync).toHaveBeenCalledWith({ auto: false })
  })

  test("la tarjeta muestra vista previa, lo que contiene, quién lo creó y enlaza al tablero", () => {
    state.dashboards = [dashboard(), dashboard({ dashboard_id: "7f2c1f7e-1111-4222-8333-444455556666", name: "Ventas por mes", source: "assistant", preview: null, highlights: null })]
    const { container } = render(<DashboardsPage />)
    expect(screen.getByText("Suma de total por mes de fecha")).toBeInTheDocument()
    expect(screen.getByText(/Sugerido para ti/)).toBeInTheDocument()
    expect(screen.getByText(/Lo creó el asistente/)).toBeInTheDocument()
    expect(container.querySelector("svg path.stroke-primary")).not.toBeNull() // línea de la vista previa
    expect(screen.getByRole("link", { name: "Resumen de Ventas" })).toHaveAttribute("href", "/dashboards/3f2c1f7e-1111-4222-8333-444455556666")
    expect(screen.getByText("2 tableros en total.")).toBeInTheDocument()
  })
})

describe("estado vacío", () => {
  test("con datos pide sugerencias UNA vez (auto) y muestra 3 pedidos clicables hechos con las columnas reales", async () => {
    const { rerender } = render(<DashboardsPage />)
    await waitFor(() => expect(suggestMutate).toHaveBeenCalledTimes(1))
    expect(suggestMutate).toHaveBeenCalledWith({ auto: true })
    rerender(<DashboardsPage />)
    expect(suggestMutate).toHaveBeenCalledTimes(1) // no se repite en cada render

    const examples = screen.getAllByRole("listitem")
    expect(examples.length).toBeGreaterThanOrEqual(2)
    expect(screen.getByText("Quiero un tablero con el total mes a mes")).toBeInTheDocument()
    expect(screen.getByText("Quiero un tablero con el total por producto")).toBeInTheDocument()
    await userEvent.click(screen.getByText("Quiero un tablero con el total por producto"))
    expect(ask).toHaveBeenCalledWith("Quiero un tablero con el total por producto", { send: true })
  })

  test("mientras se arman los tableros muestra un estado de progreso, no una página vacía", () => {
    state.suggestPending = true
    render(<DashboardsPage />)
    expect(screen.getByRole("status")).toHaveTextContent(/Estamos armando tableros con tus datos/)
  })

  test("sin datos invita a subirlos y NO pide sugerencias", () => {
    state.tables = []
    render(<DashboardsPage />)
    expect(screen.getByText("Primero sube tus datos")).toBeInTheDocument()
    expect(screen.getByRole("link", { name: "Subir mis datos" })).toHaveAttribute("href", "/data")
    expect(suggestMutate).not.toHaveBeenCalled()
  })

  test("con tableros no pide sugerencias automáticas", () => {
    state.dashboards = [dashboard()]
    render(<DashboardsPage />)
    expect(suggestMutate).not.toHaveBeenCalled()
  })
})
