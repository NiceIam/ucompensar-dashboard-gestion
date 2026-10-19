import { describe, expect, it } from "vitest"
import {
  buildPlan,
  canAutoSave,
  confidenceLevel,
  currentRoles,
  isEdited,
  plannedCount,
  setKind,
  setRole,
  sheetHeadline,
  sheetNeedsAttention,
  unlockSentence,
  type Decision,
  type SheetEdit,
} from "@/lib/intake/plan"
import { ONTOLOGY, column, file, proposal, sheet } from "@/lib/intake/test-fixtures"

const clara = sheet({ key: "ventas.csv::" })
const dudosa = sheet({
  key: "hoja.csv::",
  kind_confidence: 0.55,
  needs_review: true,
  review_reasons: ["No estoy del todo seguro de que sean ventas."],
  kind_phrase: "tus ventas",
  columns: [column(0, "C1", "fecha", 0.5), column(1, "C2", "producto", 0.5), column(2, "C3", "otro", 0.2)],
})

describe("confianza en palabras", () => {
  it.each([
    [0.98, "high"],
    [0.85, "high"],
    [0.84, "medium"],
    [0.6, "medium"],
    [0.59, "low"],
    [0, "low"],
  ])("%s -> %s", (c, level) => expect(confidenceLevel(c)).toBe(level))
})

describe("¿se le pide algo a la persona?", () => {
  it("una hoja clara no necesita ayuda y se guarda directo", () => {
    expect(sheetNeedsAttention(clara)).toBe(false)
    expect(canAutoSave(proposal(file("ventas.csv", [clara])))).toBe(true)
  })

  it("baja confianza pide ayuda y frena el guardado directo", () => {
    expect(sheetNeedsAttention(dudosa)).toBe(true)
    expect(canAutoSave(proposal(file("a.csv", [clara]), file("hoja.csv", [dudosa])))).toBe(false)
  })

  it("duda de mezcla (ask) pide ayuda aunque la confianza sea alta", () => {
    const ask = sheet({
      key: "n.csv::",
      destination: { action: "ask", table_id: "t9", into_sheet: null, display_name: "Ventas", similarity: 0.67, new_display_name: "Ventas norte", text: "" },
    })
    expect(sheetNeedsAttention(ask)).toBe(true)
    expect(canAutoSave(proposal(file("n.csv", [ask])))).toBe(false)
  })

  it("sin hojas listas no hay nada que guardar", () => {
    expect(canAutoSave(proposal(file("x.csv", [sheet({ key: "x.csv::", status: "empty" })])))).toBe(false)
    expect(canAutoSave(null)).toBe(false)
  })
})

describe("corregir un rol", () => {
  it("cambia el rol de una columna sin tocar las demás", () => {
    const edit = setRole(clara, undefined, "total", "otro")
    expect(currentRoles(clara, edit)).toEqual({ fecha: "fecha", producto: "producto", cantidad: "cantidad", total: "otro" })
  })

  it("cada rol vive en una sola columna: el anterior pasa a «dato adicional»", () => {
    const edit = setRole(clara, undefined, "cantidad", "total")
    expect(currentRoles(clara, edit)).toMatchObject({ cantidad: "total", total: "otro" })
  })

  it("elegir «dato adicional» no desplaza a nadie", () => {
    const edit = setRole(clara, setRole(clara, undefined, "total", "otro"), "cantidad", "otro")
    expect(Object.values(currentRoles(clara, edit)).filter((r) => r === "otro")).toHaveLength(2)
  })

  it("isEdited detecta cambios reales y no cambios que dejan lo mismo", () => {
    expect(isEdited(clara, undefined)).toBe(false)
    expect(isEdited(clara, setRole(clara, undefined, "total", "total"))).toBe(false)
    expect(isEdited(clara, setRole(clara, undefined, "total", "otro"))).toBe(true)
  })
})

describe("corregir el tipo de hoja", () => {
  it("los roles que no valen para el tipo nuevo pasan a «dato adicional»", () => {
    const edit = setKind(clara, undefined, "compras", ONTOLOGY)
    // compras (en este vocabulario) acepta fecha y total; producto y cantidad quedan como dato adicional
    expect(currentRoles(clara, edit)).toEqual({ fecha: "fecha", producto: "otro", cantidad: "otro", total: "total" })
    expect(edit.kind).toBe("compras")
  })

  it("«otro» deja todo como dato adicional", () => {
    const edit = setKind(clara, undefined, "otro", ONTOLOGY)
    expect(new Set(Object.values(currentRoles(clara, edit)))).toEqual(new Set(["otro"]))
  })
})

describe("plan que se confirma", () => {
  it("sin cambios manda lo propuesto: hoja nueva con su nombre y los roles tal cual", () => {
    const plan = buildPlan(proposal(file("ventas.csv", [clara])), {}, {})
    expect(plan).toHaveLength(1)
    expect(plan[0]).toMatchObject({
      file_name: "ventas.csv", sheet_name: null, action: "create", table_id: null, into_sheet: null,
      display_name: "Ventas octubre", kind: "ventas", mapping_source: "heuristic",
    })
    expect(plan[0].columns).toEqual([
      { name: "fecha", role: "fecha", confidence: 0.98, edited: false },
      { name: "producto", role: "producto", confidence: 0.98, edited: false },
      { name: "cantidad", role: "cantidad", confidence: 0.98, edited: false },
      { name: "total", role: "total", confidence: 0.98, edited: false },
    ])
  })

  it("lo que la persona corrigió sale marcado como editado y con confianza total", () => {
    const edits: Record<string, SheetEdit> = { [clara.key]: setRole(clara, undefined, "total", "otro") }
    const cols = buildPlan(proposal(file("ventas.csv", [clara])), edits, {})[0].columns!
    expect(cols.find((c) => c.name === "total")).toEqual({ name: "total", role: "otro", confidence: 1, edited: true })
    expect(cols.find((c) => c.name === "fecha")!.edited).toBe(false)
  })

  it("renombrar la hoja nueva se respeta (y se recorta)", () => {
    const plan = buildPlan(proposal(file("ventas.csv", [clara])), { [clara.key]: { displayName: "  Mis ventas  " } }, {})
    expect(plan[0].display_name).toBe("Mis ventas")
  })

  it("una hoja que se suma a una existente manda su id y no un nombre", () => {
    const s = sheet({
      key: "v2.csv::",
      destination: { action: "append", table_id: "t1", into_sheet: null, display_name: "Ventas", similarity: 1, new_display_name: "Ventas nov", text: "" },
    })
    const plan = buildPlan(proposal(file("v2.csv", [s])), {}, {})
    expect(plan[0]).toMatchObject({ action: "append", table_id: "t1", into_sheet: null, display_name: null })
  })

  it("dentro de un mismo cargue se suma a la hoja del otro archivo por su clave", () => {
    const s = sheet({
      key: "feb.csv::",
      destination: { action: "append", table_id: null, into_sheet: "ene.csv::", display_name: "Ventas", similarity: 1, new_display_name: "Ventas feb", text: "" },
    })
    expect(buildPlan(proposal(file("feb.csv", [s])), {}, {})[0]).toMatchObject({ action: "append", into_sheet: "ene.csv::", table_id: null })
  })

  describe("duda de mezcla", () => {
    const ask = sheet({
      key: "n.csv::",
      destination: { action: "ask", table_id: "t9", into_sheet: null, display_name: "Ventas", similarity: 0.67, new_display_name: "Ventas norte", text: "" },
    })

    it("por omisión se guarda APARTE: nada se mezcla en silencio", () => {
      expect(buildPlan(proposal(file("n.csv", [ask])), {}, {})[0]).toMatchObject({ action: "create", table_id: null, display_name: "Ventas norte" })
    })

    it("si la persona decide sumarla, va a la hoja con la que se parecía", () => {
      const decisions: Record<string, Decision> = { [ask.key]: "append" }
      expect(buildPlan(proposal(file("n.csv", [ask])), {}, decisions)[0]).toMatchObject({ action: "append", table_id: "t9" })
    })
  })

  it("si se corrige el tipo, una hoja que iba a sumarse pasa a hoja nueva (ya no es de la misma clase)", () => {
    const s = sheet({
      key: "v2.csv::",
      destination: { action: "append", table_id: "t1", into_sheet: null, display_name: "Ventas", similarity: 1, new_display_name: "Ventas nov", text: "" },
    })
    const edits = { [s.key]: setKind(s, undefined, "compras", ONTOLOGY) }
    const item = buildPlan(proposal(file("v2.csv", [s])), edits, {})[0]
    expect(item).toMatchObject({ action: "create", table_id: null, kind: "compras", display_name: "Ventas nov" })
    expect(item.columns!.every((c) => c.edited)).toBe(true)
  })

  it("las hojas omitidas no cuentan y las que no están listas no entran al plan", () => {
    const vacia = sheet({ key: "x.csv::Vacia", status: "empty", destination: undefined, columns: undefined })
    const p = proposal(file("a.csv", [clara, dudosa]), file("x.csv", [vacia]))
    const plan = buildPlan(p, {}, { [dudosa.key]: "skip" })
    expect(plan.map((i) => i.action)).toEqual(["create", "skip"])
    expect(plannedCount(plan)).toBe(1)
  })
})

describe("textos", () => {
  it("frase de la hoja con lo destacado separado", () => {
    expect(sheetHeadline(clara)).toEqual({ lead: "Encontré", kindPhrase: "tus ventas", stats: "731 filas, de mayo a octubre de 2026" })
    const otro = sheet({ key: "o.csv::", kind: "otro", kind_phrase: "tus datos", stats: "45 filas y 6 columnas" })
    expect(sheetHeadline(otro)).toEqual({ lead: "Guardaré", kindPhrase: "tus datos tal cual", stats: "45 filas y 6 columnas" })
    expect(sheetHeadline(sheet({ key: "z::", kind_phrase: undefined }))).toBeNull()
  })

  it("lo que falta se dice como «Para decirte … necesito: …»", () => {
    expect(
      unlockSentence({ id: "cartera", title: "Cuánto te deben tus clientes", needs: "Una hoja con cliente, valor y fecha de vencimiento de cada cuenta por cobrar." })
    ).toBe("Para decirte cuánto te deben tus clientes necesito: una hoja con cliente, valor y fecha de vencimiento de cada cuenta por cobrar.")
  })
})
