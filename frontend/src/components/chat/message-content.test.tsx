import { describe, expect, test } from "vitest"
import { render, screen } from "@testing-library/react"
import { MessageContent, plainText, prettyLabel } from "./message-content"
import { foldPie, shortLabel } from "@/components/charts/simple-chart"

describe("contenido de los mensajes del asistente", () => {
  test("etiquetas de fecha del servidor en español", () => {
    expect(prettyLabel("2026-07")).toBe("jul 2026")
    expect(prettyLabel("2026-07-05")).toBe("5 jul 2026")
    expect(prettyLabel("Chapinero")).toBe("Chapinero")
  })

  test("el texto para copiar no lleva bloques de gráfico ni asteriscos", () => {
    const text = 'Ganó **Chapinero**.\n```chart\n{"type":"bar","title":"x","data":[]}\n```'
    expect(plainText(text)).toBe("Ganó Chapinero.")
  })

  test("renderiza negritas, listas y tablas en vez de mostrar los símbolos", () => {
    render(<MessageContent text={"Hola **mundo**\n- uno\n- dos\n\n| Mes | Total |\n| --- | --- |\n| Julio | 10 |"} />)
    expect(screen.getByText("mundo").tagName).toBe("STRONG")
    expect(screen.getAllByRole("listitem")).toHaveLength(2)
    expect(screen.getByRole("table")).toBeInTheDocument()
    expect(screen.queryByText(/\*\*/)).toBeNull()
  })

  test("un bloque de gráfico dañado no rompe el mensaje", () => {
    render(<MessageContent text={"Antes\n```chart\n{no es json}\n```\nDespués"} />)
    expect(screen.getByText("Antes")).toBeInTheDocument()
    expect(screen.getByText("Después")).toBeInTheDocument()
  })
})

describe("utilidades de gráficos", () => {
  test("shortLabel recorta según cuántas categorías hay", () => {
    expect(shortLabel("Torta de zanahoria", 3)).toBe("Torta de zanaho…")
    expect(shortLabel("Torta de zanahoria", 8)).toBe("Torta de…")
    expect(shortLabel("Café", 8)).toBe("Café")
  })

  test("foldPie agrupa lo pequeño en Otros", () => {
    const pts = Array.from({ length: 8 }, (_, i) => ({ name: `c${i}`, value: 10 - i }))
    const folded = foldPie(pts)
    expect(folded).toHaveLength(6)
    expect(folded[5]).toEqual({ name: "Otros (3)", value: 5 + 4 + 3 })
  })
})
