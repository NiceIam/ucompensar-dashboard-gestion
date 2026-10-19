import { beforeEach, describe, expect, test, vi } from "vitest"
import { render, screen, waitFor, within } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { commitResponse, file as ifile, ONTOLOGY, column, proposal, sheet } from "@/lib/intake/test-fixtures"
import type { PlanSheet } from "@/types/intake"

const analyzeIntake = vi.fn()
const commitIntake = vi.fn()
const undoMutate = vi.fn()

vi.mock("@/hooks/use-intake", () => ({
  analyzeIntake: (...a: unknown[]) => analyzeIntake(...a),
  commitIntake: (...a: unknown[]) => commitIntake(...a),
  useOntology: () => ({ data: ONTOLOGY, isLoading: false }),
  useUndoIntake: () => ({ mutateAsync: undoMutate, isPending: false }),
  useUpdateRoles: () => ({ mutateAsync: vi.fn(), isPending: false }),
}))
vi.mock("@/hooks/use-data", () => ({ useInvalidateData: () => async () => {} }))
vi.mock("@/hooks/use-insights", () => ({
  useInsights: () => ({
    isLoading: false,
    isError: false,
    refetch: vi.fn(),
    data: {
      generated_at: "x",
      items: [{ id: "capital_inventario", kind: "money", severity: "info", title: "Tienes $30.000 en mercancía", sentence: "", metrics: [], ask: "¿Qué tengo en mercancía?", how: { steps: [], tables: [], rows_used: 0, notes: [] } }],
      missing: [{ id: "cartera", title: "Cuánto te deben tus clientes", needs: "Una hoja con cliente, valor y fecha de vencimiento de cada cuenta por cobrar." }],
    },
  }),
}))
vi.mock("next/link", () => ({ default: ({ href, children }: { href: string; children: React.ReactNode }) => <a href={href}>{children}</a> }))
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }))

import { IntakeZone } from "./intake-zone"

const csv = (name: string) => new File(["a,b\n1,2\n"], name, { type: "text/csv" })

function renderZone() {
  const onViewTable = vi.fn()
  const onAsk = vi.fn()
  render(<IntakeZone tables={[]} hero onViewTable={onViewTable} onAsk={onAsk} />)
  return { onViewTable, onAsk }
}

async function drop(...files: File[]) {
  const input = document.querySelector('input[type="file"]') as HTMLInputElement
  await userEvent.upload(input, files)
}

beforeEach(() => {
  analyzeIntake.mockReset()
  commitIntake.mockReset()
  undoMutate.mockReset()
})

describe("zona de carga única", () => {
  test("invita a soltar lo que tenga, varios a la vez, sin pedir el tipo de archivo", () => {
    renderZone()
    expect(screen.getByText("Suelta aquí lo que tengas")).toBeInTheDocument()
    expect(screen.getByText(/varios a la vez/i)).toBeInTheDocument()
    expect(document.querySelector('input[type="file"]')).toHaveAttribute("multiple")
    expect(screen.queryByText(/tipo de archivo/i)).not.toBeInTheDocument()
  })

  test("todo claro: guarda directo y muestra lo que entendió, lo que ya puede decir y «Deshacer»", async () => {
    analyzeIntake.mockResolvedValue(proposal(ifile("ventas.csv", [sheet({ key: "ventas.csv::" })])))
    commitIntake.mockResolvedValue(commitResponse())
    renderZone()
    await drop(csv("ventas.csv"))

    expect(await screen.findByRole("heading", { name: /Listo\. Guardé 731 filas en 1 hoja\./ })).toBeInTheDocument()
    // se guardó SIN pedir revisión
    expect(screen.queryByRole("button", { name: /Guardar 1 hoja/ })).not.toBeInTheDocument()
    expect(commitIntake).toHaveBeenCalledTimes(1)
    const plan: PlanSheet[] = commitIntake.mock.calls[0][1]
    expect(plan[0]).toMatchObject({ file_name: "ventas.csv", action: "create", display_name: "Ventas octubre", kind: "ventas" })
    expect(screen.getByText("Todo se veía claro, así que lo guardé de una vez.", { exact: false })).toBeInTheDocument()

    // «Esto es lo que entendí»
    expect(screen.getByRole("heading", { name: "Esto es lo que entendí" })).toBeInTheDocument()
    expect(screen.getByRole("heading", { level: 4, name: /Encontré tus ventas\s*:\s*731 filas, de mayo a octubre de 2026/ })).toBeInTheDocument()
    // «Con esto ya puedo decirte»
    expect(screen.getByRole("heading", { name: "Con esto ya puedo decirte" })).toBeInTheDocument()
    expect(screen.getByText("Tienes $30.000 en mercancía")).toBeInTheDocument()
    expect(screen.getByText(/Para decirte cuánto te deben tus clientes necesito: una hoja con cliente/)).toBeInTheDocument()
    expect(screen.getByRole("button", { name: /Deshacer esta carga/ })).toBeInTheDocument()
  })

  test("deshacer pide confirmación y manda lo que se guardó", async () => {
    analyzeIntake.mockResolvedValue(proposal(ifile("ventas.csv", [sheet({ key: "ventas.csv::" })])))
    commitIntake.mockResolvedValue(commitResponse())
    undoMutate.mockResolvedValue(undefined)
    renderZone()
    await drop(csv("ventas.csv"))
    await userEvent.click(await screen.findByRole("button", { name: /Deshacer esta carga/ }))
    const dialog = await screen.findByRole("alertdialog")
    expect(within(dialog).getByText(/Quitaremos las 731 filas/)).toBeInTheDocument()
    await userEvent.click(within(dialog).getByRole("button", { name: "Sí, deshacer" }))
    await waitFor(() => expect(undoMutate).toHaveBeenCalledTimes(1))
    expect(undoMutate.mock.calls[0][0][0].undo).toEqual({ action: "delete_table", table_id: "t1" })
    // vuelve al inicio
    expect(await screen.findByText("Suelta aquí lo que tengas")).toBeInTheDocument()
  })

  test("baja confianza: pide ayuda, deja corregir un rol y el tipo, y guarda lo confirmado", async () => {
    const dudosa = sheet({
      key: "hoja.csv::",
      kind_confidence: 0.55,
      needs_review: true,
      review_reasons: ["No estoy del todo seguro de que sean ventas."],
      columns: [column(0, "C1", "fecha", 0.5, "el día en que se hizo la venta"), column(1, "C2", "otro", 0.2)],
    })
    analyzeIntake.mockResolvedValue(proposal(ifile("hoja.csv", [dudosa])))
    commitIntake.mockResolvedValue(commitResponse())
    renderZone()
    await drop(csv("hoja.csv"))

    expect(await screen.findByRole("heading", { name: "Esto es lo que entendí" })).toBeInTheDocument()
    expect(commitIntake).not.toHaveBeenCalled()                       // NO guarda sin que la persona confirme
    expect(screen.getByText("Necesito tu ayuda")).toBeInTheDocument()
    expect(screen.getByText("No estoy del todo seguro de que sean ventas.")).toBeInTheDocument()

    // corrige el rol de C2
    const select = screen.getByRole("combobox", { name: "Qué es la columna «C2»" })
    await userEvent.selectOptions(select, "producto")
    expect(select).toHaveValue("producto")
    expect(screen.getByText("Lo elegiste tú")).toBeInTheDocument()

    await userEvent.click(screen.getByRole("button", { name: /Guardar 1 hoja/ }))
    await screen.findByRole("heading", { name: /Listo\./ })
    const plan: PlanSheet[] = commitIntake.mock.calls[0][1]
    expect(plan[0].columns).toEqual([
      { name: "c1", role: "fecha", confidence: 0.5, edited: false },
      { name: "c2", role: "producto", confidence: 1, edited: true },
    ])
  })

  test("duda de mezcla: por omisión la guarda aparte y deja elegir sumarla", async () => {
    const ask = sheet({
      key: "norte.csv::",
      destination: { action: "ask", table_id: "t9", into_sheet: null, display_name: "Ventas", similarity: 0.67, new_display_name: "Ventas norte", text: "" },
    })
    analyzeIntake.mockResolvedValue(proposal(ifile("norte.csv", [ask])))
    commitIntake.mockResolvedValue(commitResponse())
    renderZone()
    await drop(csv("norte.csv"))
    await screen.findByRole("heading", { name: "Esto es lo que entendí" })
    const aparte = screen.getByRole("radio", { name: /Guardarla aparte como «Ventas norte»/ })
    expect(aparte).toBeChecked()
    await userEvent.click(screen.getByRole("radio", { name: /Sumarla a «Ventas»/ }))
    await userEvent.click(screen.getByRole("button", { name: /Guardar 1 hoja/ }))
    await screen.findByRole("heading", { name: /Listo\./ })
    expect(commitIntake.mock.calls[0][1][0]).toMatchObject({ action: "append", table_id: "t9" })
  })

  test("varios archivos: cada uno con su estado y un archivo roto no impide guardar los demás", async () => {
    analyzeIntake.mockResolvedValue(
      proposal(
        { file_name: "roto.xlsx", status: "error", error: { code: "unreadable", message: "Error al procesar el archivo. Verifique el formato." }, sheets: [] },
        ifile("ventas.csv", [sheet({ key: "ventas.csv::" })])
      )
    )
    commitIntake.mockResolvedValue(commitResponse())
    renderZone()
    const xlsx = new File([new Uint8Array([0x50, 0x4b, 0x03, 0x04])], "roto.xlsx")
    await drop(xlsx, csv("ventas.csv"))
    await screen.findByRole("heading", { name: /Listo\. Guardé/ })
    expect(commitIntake.mock.calls[0][0]).toHaveLength(1)           // el archivo roto no se reenvia
    expect(screen.getByText("No pude usarlo")).toBeInTheDocument()
  })

  test("un archivo de un tipo que no se puede leer se rechaza con su motivo, sin llamar al servidor", async () => {
    renderZone()
    const input = document.querySelector('input[type="file"]') as HTMLInputElement
    await userEvent.setup({ applyAccept: false }).upload(input, new File(["x"], "foto.png", { type: "image/png" }))
    expect(await screen.findByText("No pude usarlo")).toBeInTheDocument()
    expect(screen.getByText(/Ese tipo de archivo no lo podemos leer/)).toBeInTheDocument()
    expect(analyzeIntake).not.toHaveBeenCalled()
  })

  test("si el servidor falla al entender, lo dice en palabras simples y deja reintentar", async () => {
    analyzeIntake.mockRejectedValueOnce(new TypeError("Failed to fetch"))
    renderZone()
    await drop(csv("ventas.csv"))
    expect(await screen.findByRole("button", { name: "Intentar de nuevo" })).toBeInTheDocument()
    analyzeIntake.mockResolvedValue(proposal(ifile("ventas.csv", [sheet({ key: "ventas.csv::" })])))
    commitIntake.mockResolvedValue(commitResponse())
    await userEvent.click(screen.getByRole("button", { name: "Intentar de nuevo" }))
    expect(await screen.findByRole("heading", { name: /Listo\./ })).toBeInTheDocument()
  })
})
