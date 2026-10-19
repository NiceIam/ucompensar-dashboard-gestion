import { describe, expect, it } from "vitest"
import { commitResponse, file as ifile, ONTOLOGY, column, proposal, sheet } from "@/lib/intake/test-fixtures"
import { MAX_FILES, initialIntakeState, intakeMessage, intakeReducer, validEntries, type IntakeAction, type IntakeState } from "@/lib/intake/state"

function f(name: string, size = 100): File {
  return new File([new Uint8Array(size)], name)
}
const ok = (name: string) => ({ file: f(name), kind: "csv" as const })
const bad = (name: string) => ({ file: f(name), kind: null, problem: { title: "No lo puedo leer", description: "Usa Excel o CSV." } })

function run(actions: IntakeAction[], from: IntakeState = initialIntakeState): IntakeState {
  return actions.reduce(intakeReducer, from)
}

const clara = proposal(ifile("ventas.csv", [sheet({ key: "ventas.csv::" })]))
const dudosa = proposal(
  ifile("hoja.csv", [
    sheet({ key: "hoja.csv::", needs_review: true, kind_confidence: 0.5, review_reasons: ["No estoy seguro."], columns: [column(0, "C1", "fecha", 0.4)] }),
  ])
)

describe("soltar archivos", () => {
  it("uno o varios archivos válidos empiezan a leerse", () => {
    const s = run([{ type: "add", entries: [ok("a.csv"), ok("b.csv")] }])
    expect(s.phase).toBe("analyzing")
    expect(s.entries.map((e) => e.status)).toEqual(["reading", "reading"])
    expect(s.run).toBe(1)
  })

  it("si ninguno sirve se rechaza con el motivo de cada uno", () => {
    const s = run([{ type: "add", entries: [bad("a.pdf"), bad("b.docx")] }])
    expect(s.phase).toBe("rejected")
    expect(s.entries.every((e) => e.status === "problem" && e.problem?.title)).toBe(true)
  })

  it("uno malo no tumba a los buenos", () => {
    const s = run([{ type: "add", entries: [bad("a.pdf"), ok("b.csv")] }])
    expect(s.phase).toBe("analyzing")
    expect(validEntries(s.entries).map((e) => e.file.name)).toEqual(["b.csv"])
  })

  it(`pasados ${MAX_FILES} archivos, el resto se avisa en lenguaje simple`, () => {
    const s = run([{ type: "add", entries: Array.from({ length: MAX_FILES + 2 }, (_, i) => ok(`f${i}.csv`)) }])
    const rest = s.entries.filter((e) => e.status === "problem")
    expect(rest).toHaveLength(2)
    expect(rest[0].problem?.title).toContain(`${MAX_FILES} archivos`)
  })

  it("estados por archivo: leyendo -> entendiendo -> listo", () => {
    let s = run([{ type: "add", entries: [ok("ventas.csv")] }])
    expect(s.entries[0].status).toBe("reading")
    s = run([{ type: "understanding", run: s.run }], s)
    expect(s.entries[0].status).toBe("understanding")
    s = run([{ type: "analyzed", run: s.run, proposal: clara }], s)
    expect(s.entries[0].status).toBe("ready")
  })
})

describe("entender", () => {
  it("todo claro: guarda directo, sin pasar por revisión", () => {
    const s = run([{ type: "add", entries: [ok("ventas.csv")] }, { type: "analyzed", run: 1, proposal: clara }])
    expect(s.phase).toBe("saving")
    expect(s.autoSaved).toBe(true)
    expect(s.decisions["ventas.csv::"]).toBe("create")
  })

  it("baja confianza: se queda en revisión y el archivo dice «necesita tu ayuda»", () => {
    const s = run([{ type: "add", entries: [ok("hoja.csv")] }, { type: "analyzed", run: 1, proposal: dudosa }])
    expect(s.phase).toBe("review")
    expect(s.autoSaved).toBe(false)
    expect(s.entries[0].status).toBe("attention")
  })

  it("una respuesta de un intento viejo se ignora", () => {
    const s = run([{ type: "add", entries: [ok("a.csv")] }, { type: "reset" }, { type: "analyzed", run: 1, proposal: clara }])
    expect(s.phase).toBe("idle")
  })

  it("si ninguna hoja sirve, se rechaza en vez de guardar nada", () => {
    const vacio = proposal(ifile("x.csv", [sheet({ key: "x.csv::", status: "empty", destination: undefined, columns: undefined })]))
    const s = run([{ type: "add", entries: [ok("x.csv")] }, { type: "analyzed", run: 1, proposal: vacio }])
    expect(s.phase).toBe("rejected")
    expect(s.entries[0].status).toBe("problem")
  })

  it("el archivo con error del servidor queda marcado y los demás siguen", () => {
    const mixto = proposal(
      { file_name: "roto.xlsx", status: "error", error: { code: "unreadable", message: "Error al procesar el archivo." }, sheets: [] },
      ifile("ventas.csv", [sheet({ key: "ventas.csv::" })])
    )
    const s = run([{ type: "add", entries: [ok("roto.xlsx"), ok("ventas.csv")] }, { type: "analyzed", run: 1, proposal: mixto }])
    expect(s.phase).toBe("saving")
    expect(s.entries.map((e) => e.status)).toEqual(["problem", "ready"])
  })
})

describe("revisión", () => {
  const review = () => run([{ type: "add", entries: [ok("hoja.csv")] }, { type: "analyzed", run: 1, proposal: dudosa }])

  it("corregir un rol y el tipo, renombrar y decidir", () => {
    let s = review()
    s = run([{ type: "edit-role", key: "hoja.csv::", column: "c1", role: "otro" }], s)
    expect(s.edits["hoja.csv::"].roles).toEqual({ c1: "otro" })
    s = run([{ type: "edit-kind", key: "hoja.csv::", kind: "compras", ontology: ONTOLOGY }], s)
    expect(s.edits["hoja.csv::"].kind).toBe("compras")
    s = run([{ type: "rename", key: "hoja.csv::", name: "Mis compras" }, { type: "decide", key: "hoja.csv::", decision: "skip" }], s)
    expect(s.edits["hoja.csv::"].displayName).toBe("Mis compras")
    expect(s.decisions["hoja.csv::"]).toBe("skip")
  })

  it("las ediciones solo valen en revisión", () => {
    const s = run([{ type: "add", entries: [ok("ventas.csv")] }, { type: "analyzed", run: 1, proposal: clara }, { type: "edit-role", key: "ventas.csv::", column: "total", role: "otro" }])
    expect(s.edits).toEqual({})
  })

  it("cambiar el tipo saca a la hoja de «sumar a una existente»", () => {
    const append = proposal(
      ifile("v2.csv", [
        sheet({
          key: "v2.csv::", needs_review: true,
          destination: { action: "append", table_id: "t1", into_sheet: null, display_name: "Ventas", similarity: 1, new_display_name: "Ventas nov", text: "" },
        }),
      ])
    )
    let s = run([{ type: "add", entries: [ok("v2.csv")] }, { type: "analyzed", run: 1, proposal: append }])
    expect(s.decisions["v2.csv::"]).toBe("append")
    s = run([{ type: "edit-kind", key: "v2.csv::", kind: "compras", ontology: ONTOLOGY }], s)
    expect(s.decisions["v2.csv::"]).toBe("create")
  })

  it("confirmar guarda; quitar un archivo vuelve a entender el resto", () => {
    let s = run([{ type: "confirm" }], review())
    expect(s.phase).toBe("saving")
    s = review()
    s = run([{ type: "add", entries: [ok("otra.csv")] }], s)          // agregar en revisión: suma y vuelve a entender
    expect(s.phase).toBe("analyzing")
    expect(s.entries.map((e) => e.file.name)).toEqual(["hoja.csv", "otra.csv"])
    s = run([{ type: "remove", id: s.entries[1].id }], s)
    expect(s.entries).toHaveLength(1)
    expect(s.phase).toBe("analyzing")
  })

  it("quitar el último archivo vuelve al inicio", () => {
    const s0 = review()
    expect(run([{ type: "remove", id: s0.entries[0].id }], s0).phase).toBe("idle")
  })
})

describe("guardar y terminar", () => {
  const saving = () => run([{ type: "add", entries: [ok("ventas.csv")] }, { type: "analyzed", run: 1, proposal: clara }])

  it("saved -> done con el resultado", () => {
    const s = run([{ type: "saved", run: 1, result: commitResponse() }], saving())
    expect(s.phase).toBe("done")
    expect(s.result?.totals.rows_inserted).toBe(731)
    expect(intakeMessage(s)).toBe("¡Listo! Tus datos quedaron guardados.")
  })

  it("si falla guardando, se puede reintentar la misma fase", () => {
    let s = run([{ type: "fail", run: 1, at: "saving", error: { title: "No pudimos guardar tu archivo", description: "x", retryable: true, action: "retry" } }], saving())
    expect(s.phase).toBe("failed")
    expect(intakeMessage(s)).toBe("No pudimos guardar tu archivo")
    s = run([{ type: "retry" }], s)
    expect(s.phase).toBe("saving")
  })

  it("una tanda nueva después de terminar empieza de cero", () => {
    const done = run([{ type: "saved", run: 1, result: commitResponse() }], saving())
    const s = run([{ type: "add", entries: [ok("otro.csv")] }], done)
    expect(s.phase).toBe("analyzing")
    expect(s.result).toBeNull()
    expect(s.entries).toHaveLength(1)
  })

  it("mensajes en vivo", () => {
    expect(intakeMessage(run([{ type: "add", entries: [ok("a.csv"), ok("b.csv")] }]))).toBe("Leyendo y entendiendo tus 2 archivos…")
    expect(intakeMessage(run([{ type: "add", entries: [ok("a.csv")] }]))).toBe("Leyendo y entendiendo tu archivo…")
    expect(intakeMessage(saving())).toBe("Guardando tus datos…")
  })
})
