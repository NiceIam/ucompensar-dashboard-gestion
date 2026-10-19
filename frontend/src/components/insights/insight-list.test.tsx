import { describe, expect, test } from "vitest"
import { render, screen, within } from "@testing-library/react"
import { InsightList } from "./insight-list"
import type { Insight } from "@/types/insights"

const SHARED = "Tu última venta registrada es del 8 de octubre de 2025: si ya vendiste después, sube el archivo actualizado."

function item(id: string, notes: string[]): Insight {
  return {
    id,
    kind: "money",
    severity: "attention",
    title: `Título ${id}`,
    sentence: `Frase ${id}`,
    metrics: [],
    action: null,
    ask: null,
    how: { steps: ["Paso"], tables: ["ventas"], rows_used: 3, notes },
  }
}

describe("InsightList: avisos repetidos", () => {
  test("el aviso común sale una sola vez, antes de las tarjetas, y cada tarjeta deja solo los suyos", () => {
    const { container } = render(
      <InsightList items={[item("a", [SHARED, "Propio de A"]), item("b", [SHARED]), item("c", [SHARED, "Propio de C"])]} />
    )
    expect(screen.getAllByText(SHARED)).toHaveLength(1)
    const note = screen.getByRole("note", { name: "Avisos que aplican a todos los hallazgos" })
    expect(within(note).getByText(SHARED)).toBeInTheDocument()

    // orden de lectura: la franja va antes del primer hallazgo
    const first = screen.getByRole("article", { name: "Título a" })
    expect(note.compareDocumentPosition(first) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
    expect(container.firstElementChild?.firstElementChild).toBe(note)

    expect(within(first).getByText("Propio de A")).toBeInTheDocument()
    expect(within(screen.getByRole("article", { name: "Título c" })).getByText("Propio de C")).toBeInTheDocument()
    expect(within(screen.getByRole("article", { name: "Título b" })).queryByRole("list", { name: "Avisos sobre esta cifra" })).toBeNull()
  })

  test("con un solo hallazgo no hay franja y el aviso se queda en su tarjeta", () => {
    render(<InsightList items={[item("a", [SHARED])]} />)
    expect(screen.queryByRole("note")).toBeNull()
    expect(within(screen.getByRole("article", { name: "Título a" })).getByText(SHARED)).toBeInTheDocument()
  })

  test("avisos distintos: sin franja, cada uno en su tarjeta", () => {
    render(<InsightList items={[item("a", ["Uno"]), item("b", ["Dos"])]} />)
    expect(screen.queryByRole("note")).toBeNull()
    expect(screen.getByText("Uno")).toBeInTheDocument()
    expect(screen.getByText("Dos")).toBeInTheDocument()
  })

  test("varios avisos comunes se listan en el orden de aparición y los hallazgos conservan su orden", () => {
    render(<InsightList items={[item("a", ["Zeta", "Alfa"]), item("b", ["Alfa", "Zeta"])]} />)
    const note = screen.getByRole("note")
    expect(within(note).getAllByRole("listitem").map((l) => l.textContent)).toEqual(["Zeta", "Alfa"])
    expect(screen.getAllByRole("article").map((a) => a.getAttribute("aria-labelledby") && a.querySelector("h3")?.textContent)).toEqual([
      "Título a",
      "Título b",
    ])
  })
})
