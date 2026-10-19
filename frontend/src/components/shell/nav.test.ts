import { describe, expect, test } from "vitest"
import { NAV_ITEMS, breadcrumbsFor, isActive } from "./nav"

describe("navegación", () => {
  test("el resumen está en el menú lateral y en la barra del celular", () => {
    const mobile = NAV_ITEMS.filter((i) => i.mobile !== false).map((i) => i.href)
    expect(NAV_ITEMS.map((i) => i.href)).toContain("/resumen")
    expect(mobile).toEqual(["/", "/resumen", "/data", "/dashboards"])
  })

  test("Configuración sale de la barra del celular (queda en el menú de la cuenta) pero no del lateral", () => {
    expect(NAV_ITEMS.find((i) => i.href === "/settings")?.mobile).toBe(false)
  })

  test("la barra del celular tiene 4 lugares (más el botón del chat al centro)", () => {
    expect(NAV_ITEMS.filter((i) => i.mobile !== false)).toHaveLength(4)
  })

  test("ruta activa y migas del resumen", () => {
    expect(isActive("/resumen", "/resumen")).toBe(true)
    expect(isActive("/resumen", "/")).toBe(false)
    expect(breadcrumbsFor("/resumen")).toEqual([{ label: "Resumen de la semana", href: undefined }])
  })
})
