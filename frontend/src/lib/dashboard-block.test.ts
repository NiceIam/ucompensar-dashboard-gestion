import { describe, expect, test } from "vitest"
import { dashboardHref, hasDashboardBlock, isUuid, parseDashboardBlock } from "./dashboard-block"

const ID = "3f2c1f7e-1111-4222-8333-444455556666"
const block = (obj: unknown) => `\`\`\`dashboard\n${JSON.stringify(obj)}\n\`\`\``

describe("bloque dashboard del servidor", () => {
  test("un bloque válido se lee completo", () => {
    expect(parseDashboardBlock(JSON.stringify({ id: ID, name: " Ventas por mes ", widgets: 4, existing: false }))).toEqual({
      id: ID,
      name: "Ventas por mes",
      widgets: 4,
      existing: false,
    })
    expect(parseDashboardBlock(JSON.stringify({ id: ID, name: "X", widgets: null, existing: true }))).toEqual({
      id: ID,
      name: "X",
      widgets: null,
      existing: true,
    })
  })

  test.each([
    ["id que no es UUID", { id: "../../admin", name: "x", widgets: 1 }],
    ["id con javascript", { id: "javascript:alert(1)", name: "x", widgets: 1 }],
    ["id numérico", { id: 12, name: "x", widgets: 1 }],
    ["id con ruta", { id: `${ID}/../..`, name: "x", widgets: 1 }],
    ["sin nombre", { id: ID, name: "  ", widgets: 1 }],
    ["nombre que no es texto", { id: ID, name: { a: 1 }, widgets: 1 }],
    ["no es objeto", "texto"],
    ["null", null],
  ])("se rechaza: %s", (_label, value) => {
    expect(parseDashboardBlock(JSON.stringify(value))).toBeNull()
  })

  test("JSON roto no lanza", () => {
    expect(parseDashboardBlock("{no es json")).toBeNull()
    expect(parseDashboardBlock("")).toBeNull()
  })

  test("widgets fuera de rango no se confían", () => {
    expect(parseDashboardBlock(JSON.stringify({ id: ID, name: "x", widgets: 9999 }))?.widgets).toBeNull()
    expect(parseDashboardBlock(JSON.stringify({ id: ID, name: "x", widgets: -1 }))?.widgets).toBeNull()
    expect(parseDashboardBlock(JSON.stringify({ id: ID, name: "x", widgets: "4" }))?.widgets).toBeNull()
  })

  test("el nombre se acota", () => {
    expect(parseDashboardBlock(JSON.stringify({ id: ID, name: "a".repeat(500) }))?.name).toHaveLength(120)
  })

  test("el enlace solo existe con un UUID válido", () => {
    expect(dashboardHref(ID)).toBe(`/dashboards/${ID}`)
    expect(dashboardHref("123")).toBeNull()
    expect(dashboardHref(undefined)).toBeNull()
    expect(dashboardHref("https://evil.example/x")).toBeNull()
    expect(isUuid(ID.toUpperCase())).toBe(true)
  })

  test("hasDashboardBlock solo cuenta bloques válidos", () => {
    expect(hasDashboardBlock(`Listo.\n${block({ id: ID, name: "Ventas", widgets: 3 })}`)).toBe(true)
    expect(hasDashboardBlock(block({ id: "no", name: "Ventas" }))).toBe(false)
    expect(hasDashboardBlock("```dashboard\nroto\n```")).toBe(false)
    expect(hasDashboardBlock("sin bloques")).toBe(false)
  })
})
