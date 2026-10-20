import { describe, expect, test } from "vitest"
import { ApiError } from "./errors"
import { hasDashboardBlock, MESSAGE_BLOCK } from "./dashboard-block"
import {
  dashboardEditBlocks,
  editedDashboardIds,
  editHeadline,
  editSummary,
  newerEditsInfo,
  newerEditsMessage,
  parseDashboardEditBlock,
  type ChatDashboardEdit,
} from "./dashboard-edit-block"

const ID = "3f2c1f7e-1111-4222-8333-444455556666"
const VERSION = "9a1b2c3d-5555-4666-8777-888899990000"
const wire = {
  id: ID,
  name: "Ventas por día",
  widgets: 4,
  version: VERSION,
  noop: false,
  renamed: { from: "Ventas", to: "Ventas por día" },
  added: ["Suma de total por método de pago"],
  replaced: [{ from: "Cantidad por producto", to: "Suma de total por mes" }],
  removed: ["Promedio de precio"],
  unchanged: ["Cantidad por producto"],
}
const parse = (obj: unknown) => parseDashboardEditBlock(JSON.stringify(obj))
const block = (obj: unknown) => `\`\`\`dashboard_edit\n${JSON.stringify(obj)}\n\`\`\``

describe("bloque dashboard_edit del servidor", () => {
  test("un bloque válido se lee completo", () => {
    expect(parse(wire)).toEqual(wire)
  })

  test.each([
    ["id que no es UUID", { ...wire, id: "../../admin" }],
    ["id con javascript", { ...wire, id: "javascript:alert(1)" }],
    ["id con ruta", { ...wire, id: `${ID}/../..` }],
    ["id numérico", { ...wire, id: 7 }],
    ["sin id", { ...wire, id: undefined }],
    ["sin nombre", { ...wire, name: "   " }],
    ["nombre que no es texto", { ...wire, name: { a: 1 } }],
    ["no es objeto", "texto"],
    ["lista", [wire]],
    ["null", null],
  ])("se rechaza: %s", (_label, value) => {
    expect(parse(value)).toBeNull()
  })

  test("JSON roto no lanza", () => {
    expect(parseDashboardEditBlock("{no es json")).toBeNull()
    expect(parseDashboardEditBlock("")).toBeNull()
  })

  test("tipos incorrectos en el resto de campos se descartan sin tumbar el bloque", () => {
    const edit = parse({
      id: ID,
      name: "X",
      widgets: "4",
      version: 12,
      noop: "yes",
      renamed: "nuevo",
      added: "no es lista",
      replaced: [{ from: "a" }, "b", null, { from: 1, to: 2 }],
      removed: [1, null, {}, "Válido"],
      unchanged: { a: 1 },
    })
    expect(edit).toEqual({
      id: ID,
      name: "X",
      widgets: null,
      version: null,
      noop: false,
      renamed: null,
      added: [],
      replaced: [],
      removed: ["Válido"],
      unchanged: [],
    })
  })

  test("las listas se acotan a 6 y cada texto a 80 caracteres", () => {
    const many = Array.from({ length: 5000 }, (_, i) => `Gráfico ${i}`)
    const edit = parse({ ...wire, added: many, removed: many, unchanged: many, replaced: many.map((t) => ({ from: t, to: t })) })
    expect(edit?.added).toHaveLength(6)
    expect(edit?.removed).toHaveLength(6)
    expect(edit?.unchanged).toHaveLength(6)
    expect(edit?.replaced).toHaveLength(6)
    const long = parse({ ...wire, added: ["a".repeat(500)], renamed: { from: "b".repeat(500), to: "c".repeat(500) } })
    expect(long?.added[0]).toHaveLength(80)
    expect(long?.renamed?.from).toHaveLength(80)
    expect(parse({ ...wire, name: "n".repeat(500) })?.name).toHaveLength(120)
  })

  test("textos con HTML o Markdown se conservan como texto (React los pinta escapados)", () => {
    const edit = parse({ ...wire, added: ["<img src=x onerror=alert(1)>", "[click](http://evil) **negrita**"] })
    expect(edit?.added).toEqual(["<img src=x onerror=alert(1)>", "[click](http://evil) **negrita**"])
  })

  test("widgets fuera de rango no se confían", () => {
    expect(parse({ ...wire, widgets: 9999 })?.widgets).toBeNull()
    expect(parse({ ...wire, widgets: -1 })?.widgets).toBeNull()
    expect(parse({ ...wire, widgets: 2.5 })?.widgets).toBeNull()
    expect(parse({ ...wire, widgets: 0 })?.widgets).toBe(0)
  })

  test("sin cambio (noop) no hay versión que deshacer, aunque el servidor la mande", () => {
    expect(parse({ ...wire, noop: true })?.version).toBeNull()
    expect(parse({ ...wire, noop: true, version: null })?.noop).toBe(true)
  })

  test("una versión que no es UUID no se acepta", () => {
    expect(parse({ ...wire, version: "../x" })?.version).toBeNull()
  })
})

describe("resumen de lo que cambió", () => {
  const base: ChatDashboardEdit = { ...(wire as ChatDashboardEdit) }
  const only = (over: Partial<ChatDashboardEdit>): ChatDashboardEdit => ({
    ...base,
    renamed: null,
    added: [],
    replaced: [],
    removed: [],
    unchanged: [],
    ...over,
  })

  test("agregó, quitó, reemplazó y renombró", () => {
    expect(editSummary(only({ added: ["a", "b"], removed: ["c", "d"], replaced: [{ from: "x", to: "y" }], renamed: { from: "a", to: "b" } }))).toBe(
      "agregué 2 gráficos, quité 2, reemplacé 1, cambié el nombre"
    )
  })

  test("el sustantivo va en el primer tramo y concuerda en singular", () => {
    expect(editSummary(only({ added: ["a"] }))).toBe("agregué 1 gráfico")
    expect(editSummary(only({ removed: ["a"] }))).toBe("quité 1 gráfico")
    expect(editSummary(only({ added: ["a"], removed: ["c"] }))).toBe("agregué 1 gráfico, quité 1")
    expect(editSummary(only({ replaced: [{ from: "x", to: "y" }, { from: "z", to: "w" }] }))).toBe("reemplacé 2 gráficos")
  })

  test("solo renombrar, o nada", () => {
    expect(editSummary(only({ renamed: { from: "a", to: "b" } }))).toBe("cambié el nombre")
    expect(editSummary(only({}))).toBe("")
  })

  test("frase principal de la tarjeta", () => {
    expect(editHeadline(only({ name: "Ventas por día", added: ["a"], removed: ["b"] }))).toBe("Edité «Ventas por día»: agregué 1 gráfico, quité 1.")
    expect(editHeadline(only({ name: "Ventas" }))).toBe("Edité «Ventas».")
    expect(editHeadline(only({ noop: true, unchanged: ["a"] }))).toBe("No cambié nada: eso ya estaba en el tablero.")
  })
})

describe("mensaje con bloque de edición", () => {
  test("MESSAGE_BLOCK reconoce los tres tipos de bloque y los parte bien", () => {
    const text = `Antes\n${block(wire)}\nMedio\n\`\`\`dashboard\n{"id":"${ID}"}\n\`\`\`\n\`\`\`chart\n{}\n\`\`\`\nFin`
    const parts = text.split(MESSAGE_BLOCK)
    expect(parts.filter((p) => p.startsWith("```dashboard_edit"))).toHaveLength(1)
    expect(parts.filter((p) => p.startsWith("```dashboard\n"))).toHaveLength(1)
    expect(parts.filter((p) => p.startsWith("```chart"))).toHaveLength(1)
  })

  test("hasDashboardBlock también es true para un bloque de edición válido", () => {
    expect(hasDashboardBlock(`Listo.\n${block(wire)}`)).toBe(true)
    expect(hasDashboardBlock(`Listo.\n${block({ ...wire, noop: true })}`)).toBe(true)
    expect(hasDashboardBlock(block({ ...wire, id: "no" }))).toBe(false)
    expect(hasDashboardBlock("```dashboard_edit\nroto\n```")).toBe(false)
  })

  test("los ids editados no incluyen sin-cambios ni repetidos ni bloques inválidos", () => {
    const other = "11111111-2222-4333-8444-555566667777"
    const text = [block(wire), block({ ...wire, noop: true, id: other }), block({ ...wire, id: "no" }), block(wire)].join("\n")
    expect(dashboardEditBlocks(text)).toHaveLength(3)
    expect(editedDashboardIds(text)).toEqual([ID])
    expect(editedDashboardIds("sin bloques")).toEqual([])
  })
})

describe("aviso de ediciones más recientes (409)", () => {
  const conflict = (detail: unknown, status = 409) => new ApiError(status, JSON.stringify({ detail }))

  test("lo reconoce con su cantidad", () => {
    expect(newerEditsInfo(conflict({ code: "newer_edits", count: 3, message: "x" }))).toEqual({ count: 3 })
  })

  test("sin cantidad creíble igual se reconoce", () => {
    expect(newerEditsInfo(conflict({ code: "newer_edits" }))).toEqual({ count: null })
    expect(newerEditsInfo(conflict({ code: "newer_edits", count: "3" }))).toEqual({ count: null })
    expect(newerEditsInfo(conflict({ code: "newer_edits", count: -2 }))).toEqual({ count: null })
  })

  test("otros errores no son este aviso", () => {
    expect(newerEditsInfo(conflict({ code: "otra" }))).toBeNull()
    expect(newerEditsInfo(conflict("texto", 409))).toBeNull()
    expect(newerEditsInfo(conflict({ code: "newer_edits", count: 2 }, 404))).toBeNull()
    expect(newerEditsInfo(new Error("x"))).toBeNull()
    expect(newerEditsInfo(new ApiError(409, "no es json"))).toBeNull()
    expect(newerEditsInfo(null)).toBeNull()
  })

  test("el mensaje concuerda en singular y plural", () => {
    expect(newerEditsMessage(2)).toBe("Este tablero tiene 2 cambios más recientes. Si deshaces este, también se pierden esos.")
    expect(newerEditsMessage(1)).toBe("Este tablero tiene 1 cambio más reciente. Si deshaces este, también se pierde ese.")
    expect(newerEditsMessage(null)).toMatch(/cambios más recientes/)
  })
})
