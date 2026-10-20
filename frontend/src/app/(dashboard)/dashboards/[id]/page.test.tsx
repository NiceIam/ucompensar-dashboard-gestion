import { beforeEach, describe, expect, test, vi } from "vitest"
import { render, screen } from "@testing-library/react"
import type { ExecuteResult } from "@/hooks/use-dashboards"

const state = vi.hoisted(() => ({
  execute: { data: undefined, isLoading: false, isFetching: false, isError: false, error: null, updatedAt: 0, refetch: () => undefined } as Record<string, unknown>,
}))

vi.mock("next/navigation", () => ({
  useParams: () => ({ id: "3f2c1f7e-1111-4222-8333-444455556666" }),
  useRouter: () => ({ replace: vi.fn() }),
  usePathname: () => "/dashboards/3f2c1f7e-1111-4222-8333-444455556666",
  useSearchParams: () => new URLSearchParams(),
}))
vi.mock("@/hooks/use-page-title", () => ({ usePageTitle: () => undefined }))
vi.mock("@/providers/chat-provider", () => ({ useChat: () => ({ ask: vi.fn() }) }))
vi.mock("@/hooks/use-dashboards", () => ({
  useDashboardMeta: () => ({ data: { dashboard_id: "x", name: "Ventas del mes", description: "Creado por el asistente a tu pedido.", created_at: "" }, isLoading: false }),
  useDashboardExecute: () => state.execute,
  useDashboardFilterOptions: () => ({ data: undefined, isLoading: false }),
  useFilterValueSearch: () => ({ data: undefined, isFetching: false }),
  useDrill: () => ({ data: undefined, isError: false, isFetching: false, isPlaceholderData: false }),
}))
// El dibujo de Recharts no aporta aquí: se verifica qué recibe cada gráfico (título y unidad).
vi.mock("@/components/charts/chart-renderer", () => ({
  ChartRenderer: ({ widget }: { widget: { title: string; unit?: string; data?: unknown[] } }) => (
    <div data-testid="chart" data-unit={widget.unit ?? ""}>
      {widget.title} ({widget.data?.length} puntos)
    </div>
  ),
}))

import DashboardDetailPage from "./page"

function show(data: ExecuteResult) {
  state.execute = { ...state.execute, data, isLoading: false, isError: false }
  return render(<DashboardDetailPage />)
}

beforeEach(() => {
  state.execute = { data: undefined, isLoading: false, isFetching: false, isError: false, error: null, updatedAt: 0, refetch: () => undefined }
})

describe("detalle del tablero", () => {
  test("las cifras salen con la UNIDAD del servidor: dinero en pesos, cantidad sin $ aunque se llame «Total»", () => {
    show({
      charts: [],
      kpis: [
        { label: "Suma de total", value: 10234700, unit: "money", icon: "DollarSign", column: "total" },
        { label: "Total Ventas", value: 731, unit: "count", icon: "DollarSign" },
        { label: "Promedio de edad", value: 36.5, unit: "number", icon: "TrendingUp" },
      ],
    })
    expect(screen.getByText("$ 10,2 M")).toBeInTheDocument()
    expect(screen.getByText("731")).toBeInTheDocument()
    expect(screen.queryByText(/\$ ?731/)).toBeNull()
    expect(screen.getByText("36,5")).toBeInTheDocument()
  })

  test("un gráfico con error no tumba el tablero: avisa en ese gráfico y dibuja los demás", () => {
    show({
      charts: [
        { type: "bar", title: "Suma de total por producto", data: [{ name: "a", value: 1 }], x: "name", y: "value", color: "#000", unit: "money" },
        { type: "pie", title: "Suma de total por metodo_pago", data: [], x: "name", y: "value", color: "#000", error: "la columna 'metodo_pago' no existe en ventas" },
      ],
      kpis: [],
    })
    expect(screen.getAllByTestId("chart")).toHaveLength(1)
    expect(screen.getByTestId("chart")).toHaveAttribute("data-unit", "money")
    expect(screen.getByText("No pudimos calcular este gráfico")).toBeInTheDocument()
    expect(screen.getByText(/la columna 'metodo_pago' no existe en ventas/)).toBeInTheDocument()
    expect(screen.getByText("Suma de total por metodo_pago")).toBeInTheDocument()
  })

  test("una cifra que falla se ve con raya y explicación, sin $ ni 0 inventado", () => {
    show({
      charts: [],
      kpis: [{ label: "Suma de total", value: null, unit: "money", icon: "DollarSign", error: "la columna 'total' no existe en ventas" }],
    })
    expect(screen.getByText("—")).toBeInTheDocument()
    expect(screen.getByText(/No pudimos calcular esta cifra: la columna 'total' no existe/)).toBeInTheDocument()
  })

  test("no hay botón de código/script", () => {
    show({ charts: [], kpis: [] })
    expect(screen.queryByText(/código|script|\.py/i)).toBeNull()
    expect(screen.queryByRole("button", { name: /más opciones/i })).toBeNull()
  })

  test("tablero sin nada: explica y ofrece pedírselo al asistente", () => {
    show({ charts: [], kpis: [] })
    expect(screen.getByText("Este tablero todavía no tiene gráficos")).toBeInTheDocument()
    expect(screen.getByRole("button", { name: /Pídele un tablero al asistente/ })).toBeInTheDocument()
  })

  test("estado de carga y de error", () => {
    state.execute = { ...state.execute, isLoading: true }
    const { unmount } = render(<DashboardDetailPage />)
    expect(document.querySelector('[aria-busy="true"]')).not.toBeNull()
    unmount()
    state.execute = { ...state.execute, isLoading: false, isError: true, error: new Error("x") }
    render(<DashboardDetailPage />)
    expect(screen.getByRole("button", { name: /Intentar de nuevo/ })).toBeInTheDocument()
  })
})
