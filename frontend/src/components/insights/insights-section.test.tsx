import { describe, expect, test, vi } from "vitest"
import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { InsightsSection, type InsightsQueryLike } from "./insights-section"
import { ApiError } from "@/lib/errors"
import type { Insight, InsightSeverity, InsightsResponse } from "@/types/insights"

function item(id: string, severity: InsightSeverity): Insight {
  return {
    id,
    kind: "money",
    severity,
    title: `Título ${id}`,
    sentence: `Frase ${id}`,
    metrics: [{ label: "Cifra", value: 1_000_000, unit: "money" }],
    action: null,
    ask: `Pregunta ${id}`,
    how: { steps: ["Paso"], tables: ["ventas"], rows_used: 3, notes: [] },
  }
}

const DATA = (over: Partial<InsightsResponse> = {}): InsightsResponse => ({
  generated_at: "2026-10-19T14:05:00Z",
  period: { from: "2025-07-02", to: "2025-10-08", days: 98 },
  items: [],
  missing: [],
  summary_text: null,
  ...over,
})

function query(over: Partial<InsightsQueryLike> = {}): InsightsQueryLike {
  return { data: DATA(), isLoading: false, isError: false, error: null, isFetching: false, refetch: vi.fn(), ...over }
}

describe("InsightsSection (inicio)", () => {
  test("cargando: esqueletos y aviso de que se está buscando", () => {
    render(<InsightsSection query={query({ isLoading: true, data: undefined })} onAsk={vi.fn()} />)
    expect(screen.getByRole("heading", { name: "Esta semana en tu negocio" })).toBeInTheDocument()
    expect(screen.getByLabelText("Buscando tus hallazgos")).toHaveAttribute("aria-busy", "true")
    expect(screen.queryByRole("article")).toBeNull()
  })

  test("muestra los 3 primeros tal como llegan (sin reordenar) y enlaza a /resumen con el total", () => {
    const items = [item("a", "info"), item("b", "attention"), item("c", "important"), item("d", "info"), item("e", "important")]
    render(<InsightsSection query={query({ data: DATA({ items }) })} onAsk={vi.fn()} />)
    const titles = screen.getAllByRole("heading", { level: 3 }).map((h) => h.textContent)
    expect(titles).toEqual(["Título a", "Título b", "Título c"])
    const link = screen.getByRole("link", { name: /Ver todos \(5\)/ })
    expect(link).toHaveAttribute("href", "/resumen")
    expect(screen.getByText("Ventas del 2 de julio al 8 de octubre de 2025")).toBeInTheDocument()
  })

  test("preguntar al asistente desde una tarjeta llama a onAsk con su pregunta", async () => {
    const onAsk = vi.fn()
    render(<InsightsSection query={query({ data: DATA({ items: [item("a", "important")] }) })} onAsk={onAsk} />)
    await userEvent.setup().click(screen.getByRole("button", { name: /Preguntar al asistente/ }))
    expect(onAsk).toHaveBeenCalledWith("Pregunta a")
  })

  test("sin hallazgos pero con faltantes: invitación amable a subir datos", () => {
    const missing = [{ id: "cartera", title: "Cuánto te deben tus clientes", needs: "Una hoja con cliente y valor." }]
    render(<InsightsSection query={query({ data: DATA({ missing }) })} onAsk={vi.fn()} />)
    expect(screen.getByText("Para decirte cuánta plata tienes parada necesito tus productos y tus ventas")).toBeInTheDocument()
    expect(screen.getByText(/Cuánto te deben tus clientes/)).toBeInTheDocument()
    expect(screen.getByRole("link", { name: "Subir mis datos" })).toHaveAttribute("href", "/data")
    expect(screen.queryByRole("link", { name: /Ver todos/ })).toBeNull()
  })

  test("sin nada que mostrar: mensaje tranquilo, sin error", () => {
    render(<InsightsSection query={query()} onAsk={vi.fn()} />)
    expect(screen.getByText("Todavía no hay hallazgos para mostrarte")).toBeInTheDocument()
  })

  test("error: aviso humano (sin JSON crudo) y reintentar", async () => {
    const refetch = vi.fn()
    render(
      <InsightsSection
        query={query({ data: undefined, isError: true, error: new ApiError(500, '{"detail":"Traceback: boom"}'), refetch })}
        onAsk={vi.fn()}
      />
    )
    expect(screen.getByText("No pudimos armar tus hallazgos")).toBeInTheDocument()
    expect(document.body.textContent).not.toMatch(/Traceback|detail|\{/)
    await userEvent.setup().click(screen.getByRole("button", { name: /Intentar de nuevo/ }))
    expect(refetch).toHaveBeenCalledTimes(1)
  })
})
