import { describe, expect, test, vi } from "vitest"
import { render, screen, within } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { InsightCard } from "./insight-card"
import type { Insight } from "@/types/insights"

const plain = (s: string | null) => (s ?? "").replace(/[  ]/g, " ")

const BASE: Insight = {
  id: "capital_inventario",
  kind: "money",
  severity: "attention",
  title: "Tienes $47,6 M en mercancía",
  sentence: "Tienes $47,6 M en mercancía (a costo). A ese ritmo, tu inventario tardaría más de un año en venderse.",
  metrics: [
    { label: "Mercancía a costo", value: 47620000, unit: "money" },
    { label: "Vendido en el periodo", value: 360000, unit: "money" },
    { label: "Meses de inventario", value: 20.1, unit: "months" },
    { label: "Productos sin ventas", value: 42, unit: "count" },
    { label: "De tu inventario", value: 38.7, unit: "percent" },
    { label: "Le quedan", value: 6, unit: "days" },
    { label: "El más urgente", value: "Cemento gris", unit: "text" },
  ],
  action: "Revisa qué productos compraste de más antes de volver a pedir.",
  ask: "¿Qué productos tengo con más mercancía comprada?",
  how: {
    steps: ["Multipliqué las existencias por su costo.", "Sumé lo vendido."],
    tables: ["productos", "ventas"],
    rows_used: 70,
    notes: ["El periodo de ventas es corto (98 días): la cifra puede cambiar con más historia."],
  },
}

describe("InsightCard", () => {
  test("es un artículo con su título como nombre y la frase legible", () => {
    render(<InsightCard insight={BASE} />)
    const card = screen.getByRole("article", { name: BASE.title })
    expect(within(card).getByRole("heading", { level: 3, name: BASE.title })).toBeInTheDocument()
    expect(within(card).getByText(BASE.sentence)).toBeInTheDocument()
  })

  test("la severidad se dice con palabras, no solo con color", () => {
    const { rerender } = render(<InsightCard insight={{ ...BASE, severity: "important" }} />)
    expect(screen.getByText("Importante")).toBeInTheDocument()
    rerender(<InsightCard insight={{ ...BASE, severity: "attention" }} />)
    expect(screen.getByText("Ojo")).toBeInTheDocument()
    rerender(<InsightCard insight={{ ...BASE, severity: "info", kind: "info" }} />)
    expect(screen.getByText("Dato")).toBeInTheDocument()
  })

  test("las cifras salen formateadas según su unidad", () => {
    render(<InsightCard insight={BASE} />)
    const values = screen.getAllByRole("definition").map((d) => plain(d.textContent))
    expect(values).toEqual(["$47,6 M", "$360.000", "20 meses", "42", "38,7 %", "6 días", "Cemento gris"])
    // cada cifra tiene su etiqueta (lista de definiciones)
    expect(screen.getAllByRole("term")).toHaveLength(7)
  })

  test("muestra Qué hacer y los avisos de la cifra sin abrir nada", () => {
    render(<InsightCard insight={BASE} />)
    expect(screen.getByText("Qué hacer")).toBeInTheDocument()
    expect(screen.getByText(BASE.action as string)).toBeInTheDocument()
    expect(screen.getByRole("list", { name: "Avisos sobre esta cifra" })).toHaveTextContent("El periodo de ventas es corto")
  })

  test("sin acción ni avisos no se inventa nada", () => {
    render(<InsightCard insight={{ ...BASE, action: null, how: { ...BASE.how, notes: [] } }} />)
    expect(screen.queryByText("Qué hacer")).toBeNull()
    expect(screen.queryByRole("list", { name: "Avisos sobre esta cifra" })).toBeNull()
  })

  test("«Ver cómo lo calculé» abre y cierra el cálculo con aria-expanded", async () => {
    const user = userEvent.setup()
    render(<InsightCard insight={BASE} />)
    const toggle = screen.getByRole("button", { name: /Ver cómo lo calculé/ })
    expect(toggle).toHaveAttribute("aria-expanded", "false")
    expect(screen.queryByRole("region", { name: /Ver cómo lo calculé/ })).toBeNull() // oculta: fuera del árbol de accesibilidad

    await user.click(toggle)
    expect(toggle).toHaveAttribute("aria-expanded", "true")
    const panel = screen.getByRole("region", { name: /Ver cómo lo calculé/ })
    expect(panel).toBeVisible()
    expect(toggle).toHaveAttribute("aria-controls", panel.id)
    expect(within(panel).getByText("Multipliqué las existencias por su costo.")).toBeInTheDocument()
    expect(within(panel).getByText("Sumé lo vendido.")).toBeInTheDocument()
    expect(plain(panel.textContent)).toContain("Productos y Ventas")
    expect(plain(panel.textContent)).toContain("70 filas")

    await user.click(toggle)
    expect(toggle).toHaveAttribute("aria-expanded", "false")
    expect(panel).not.toBeVisible()
  })

  test("«Preguntar al asistente» manda la pregunta del hallazgo", async () => {
    const user = userEvent.setup()
    const onAsk = vi.fn()
    render(<InsightCard insight={BASE} onAsk={onAsk} />)
    await user.click(screen.getByRole("button", { name: /Preguntar al asistente/ }))
    expect(onAsk).toHaveBeenCalledWith("¿Qué productos tengo con más mercancía comprada?")
  })

  test("sin pregunta (o sin quien la reciba) no hay botón de asistente", () => {
    const { rerender } = render(<InsightCard insight={{ ...BASE, ask: null }} onAsk={vi.fn()} />)
    expect(screen.queryByRole("button", { name: /Preguntar al asistente/ })).toBeNull()
    rerender(<InsightCard insight={BASE} />)
    expect(screen.queryByRole("button", { name: /Preguntar al asistente/ })).toBeNull()
  })

  test("el título puede ser h2 cuando la sección no tiene título propio", () => {
    render(<InsightCard insight={BASE} as="h2" />)
    expect(screen.getByRole("heading", { level: 2, name: BASE.title })).toBeInTheDocument()
  })

  test("la versión protagonista conserva las mismas cifras y botones", () => {
    render(<InsightCard insight={BASE} featured onAsk={vi.fn()} />)
    expect(screen.getAllByRole("definition")).toHaveLength(7)
    expect(screen.getByRole("button", { name: /Ver cómo lo calculé/ })).toBeInTheDocument()
    expect(screen.getByRole("button", { name: /Preguntar al asistente/ })).toBeInTheDocument()
  })

  test("nunca aparece jerga técnica en la tarjeta", () => {
    const { container } = render(<InsightCard insight={BASE} onAsk={vi.fn()} defaultOpen />)
    expect(container.textContent).not.toMatch(/json|receta|pack|undefined|null|NaN/i)
  })
})
