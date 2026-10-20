import { cloneElement, type ReactElement } from "react"
import { describe, expect, test, vi } from "vitest"
import { fireEvent, render, screen, within } from "@testing-library/react"
import userEvent from "@testing-library/user-event"

// jsdom no mide: se le da un tamaño fijo al contenedor para que Recharts dibuje las barras, puntos y porciones.
vi.mock("recharts", async () => {
  const actual = await vi.importActual<typeof import("recharts")>("recharts")
  return {
    ...actual,
    ResponsiveContainer: ({ children }: { children: ReactElement }) => (
      <div style={{ width: 600, height: 300 }}>{cloneElement(children, { width: 600, height: 300 } as object)}</div>
    ),
  }
})

import { SimpleChart, type ChartPoint } from "./simple-chart"

const POINTS: ChartPoint[] = [
  { name: "Cemento", value: 300 },
  { name: "Pintura", value: 200 },
  { name: "(sin dato)", value: 50, empty: true },
]

function datumButtons(container: HTMLElement) {
  return Array.from(container.querySelectorAll<SVGElement>('[role="button"][data-datum]'))
}

describe.each([["bar"], ["line"], ["pie"]] as const)("datos clicables de un gráfico de %s", (form) => {
  test("sin onSelectPoint el gráfico es solo de lectura (sin botones)", () => {
    const { container } = render(<SimpleChart form={form} points={POINTS} label="Ventas" />)
    expect(datumButtons(container)).toHaveLength(0)
    expect(container.querySelector('[role="img"]')).not.toBeNull()
  })

  test("cada dato es un botón con nombre accesible, foco rodante y activa con clic, Enter y Espacio", async () => {
    const onSelect = vi.fn()
    const { container } = render(<SimpleChart form={form} points={POINTS} label="Ventas" onSelectPoint={onSelect} unit="money" />)
    // con detalle el contenedor deja de ser una imagen (sus hijos serían invisibles para el lector de pantalla)
    expect(container.querySelector('[role="img"]')).toBeNull()
    const buttons = datumButtons(container)
    expect(buttons).toHaveLength(3)
    expect(buttons[0]).toHaveAttribute("aria-label", expect.stringMatching(/^Cemento: \$[\s ]300\. Ver el detalle$/))
    // una sola parada de Tab por gráfico
    expect(buttons.map((b) => b.getAttribute("tabindex"))).toEqual(["0", "-1", "-1"])

    fireEvent.click(buttons[0])
    expect(onSelect).toHaveBeenLastCalledWith(expect.objectContaining({ name: "Cemento", value: 300 }))

    buttons[0].focus()
    await userEvent.keyboard("{Enter}")
    expect(onSelect).toHaveBeenCalledTimes(2)
    await userEvent.keyboard(" ")
    expect(onSelect).toHaveBeenCalledTimes(3)

    // flechas: el foco se mueve entre datos y el «rodante» lo sigue
    await userEvent.keyboard("{ArrowRight}")
    expect(document.activeElement).toBe(datumButtons(container)[1])
    expect(datumButtons(container).map((b) => b.getAttribute("tabindex"))).toEqual(["-1", "0", "-1"])
    await userEvent.keyboard("{End}")
    expect(document.activeElement).toBe(datumButtons(container)[2])
    await userEvent.keyboard("{Enter}")
    expect(onSelect).toHaveBeenLastCalledWith(expect.objectContaining({ name: "(sin dato)", empty: true }))
    await userEvent.keyboard("{Home}")
    expect(document.activeElement).toBe(datumButtons(container)[0])
  })
})

describe("el clic no se pierde cuando el foco cambia de dato", () => {
  test.each([["bar"], ["line"], ["pie"]] as const)(
    "%s: bajar y soltar sobre un dato que NO era la parada de Tab abre ese dato (el foco no repinta el gráfico)",
    async (form) => {
      const onSelect = vi.fn()
      const { container } = render(<SimpleChart form={form} points={POINTS} label="Ventas" onSelectPoint={onSelect} />)
      const nodes = Array.from(container.querySelectorAll<SVGElement>('[role="button"][data-datum]'))
      await userEvent.click(nodes[2])
      expect(onSelect).toHaveBeenCalledTimes(1)
      expect(onSelect).toHaveBeenCalledWith(expect.objectContaining({ name: "(sin dato)" }))
      // los mismos nodos siguen en el DOM (nada se recreó) y la parada de Tab pasó al dato tocado
      expect(Array.from(container.querySelectorAll('[role="button"][data-datum]'))).toEqual(nodes)
      expect(nodes.map((n) => n.getAttribute("tabindex"))).toEqual(["-1", "-1", "0"])
    }
  )
})

describe("zona tocable y tooltip", () => {
  test("cada barra tiene una zona tocable de al menos 24 px", () => {
    const { container } = render(<SimpleChart form="bar" points={POINTS} label="Ventas" onSelectPoint={() => undefined} />)
    for (const g of datumButtons(container)) {
      const hit = g.querySelector('rect[fill="transparent"]')!
      expect(Number(hit.getAttribute("width"))).toBeGreaterThanOrEqual(24)
      expect(Number(hit.getAttribute("height"))).toBeGreaterThanOrEqual(24)
    }
  })

  test("la torta con detalle no vuelve a agrupar «Otros» (el del servidor es el que tiene detalle) y lo pinta neutro", () => {
    const many: ChartPoint[] = [
      ...Array.from({ length: 8 }, (_, i) => ({ name: `p${i}`, value: 10 - i })),
      { name: "Otros (42)", value: 5, other: true },
    ]
    const { container } = render(<SimpleChart form="pie" points={many} label="x" onSelectPoint={() => undefined} />)
    expect(datumButtons(container)).toHaveLength(9)
    const legend = screen.getAllByRole("button", { name: /Ver el detalle/ }).filter((b) => b.tagName === "BUTTON")
    expect(legend).toHaveLength(9)
    expect(within(legend[8]).getByText("Otros (42)")).toBeInTheDocument()
  })

  test("las filas de la leyenda de la torta son botones", () => {
    const onSelect = vi.fn()
    render(<SimpleChart form="pie" points={POINTS} label="Ventas" onSelectPoint={onSelect} />)
    const row = screen.getAllByRole("button", { name: /Pintura: 200\. Ver el detalle/ }).find((b) => b.tagName === "BUTTON")!
    fireEvent.click(row)
    expect(onSelect).toHaveBeenCalledWith(expect.objectContaining({ name: "Pintura" }))
  })

  test("la vista de tabla sigue funcionando y ofrece un botón de detalle por fila con los encabezados legibles", async () => {
    const onSelect = vi.fn()
    render(<SimpleChart form="bar" points={POINTS} label="Ventas por producto" onSelectPoint={onSelect} xLabel="Producto" yLabel="Ventas" />)
    await userEvent.click(screen.getByRole("button", { name: "Ver tabla" }))
    expect(screen.getByRole("columnheader", { name: "Producto" })).toBeInTheDocument()
    expect(screen.getByRole("columnheader", { name: "Ventas" })).toBeInTheDocument()
    await userEvent.click(screen.getByRole("button", { name: "Ver el detalle de Pintura" }))
    expect(onSelect).toHaveBeenCalledWith(expect.objectContaining({ name: "Pintura" }))
    await userEvent.click(screen.getByRole("button", { name: "Ver gráfico" }))
    expect(datumButtonsCount()).toBe(3)
  })

  test("sin encabezados del servidor la tabla conserva «Categoría» y «Valor»", async () => {
    render(<SimpleChart form="bar" points={POINTS} label="x" />)
    await userEvent.click(screen.getByRole("button", { name: "Ver tabla" }))
    expect(screen.getByRole("columnheader", { name: "Categoría" })).toBeInTheDocument()
    expect(screen.getByRole("columnheader", { name: "Valor" })).toBeInTheDocument()
  })
})

function datumButtonsCount() {
  return document.querySelectorAll('[role="button"][data-datum]').length
}
