import { describe, expect, test } from "vitest"
import { ApiError, humanizeError, humanizeErrorText } from "./errors"

const api = (status: number, body: unknown) =>
  new ApiError(status, typeof body === "string" ? body : JSON.stringify(body))

/** Nada de lo que se muestra a la persona puede contener JSON, llaves o "HTTP". */
function expectHuman(text: string) {
  expect(text).not.toMatch(/[{}[\]]/)
  expect(text).not.toMatch(/HTTP \d/)
  expect(text).not.toMatch(/detail/)
}

describe("humanizeError", () => {
  test("sin conexión: dice qué pasó y en cargas recuerda que el archivo sigue ahí", () => {
    const h = humanizeError(new TypeError("Failed to fetch"), "upload")
    expect(h.title).toBe("No pudimos conectarnos")
    expect(h.description).toContain("Tu archivo sigue aquí")
    expect(h.retryable).toBe(true)
    expect(h.action).toBe("retry")
  })

  test("tipos de archivo no soportados piden otro archivo", () => {
    const h = humanizeError(api(422, { detail: "Tipo de archivo no soportado. Use CSV, Excel o JSON." }), "analyze")
    expect(h.title).toBe("Ese tipo de archivo no lo podemos leer")
    expect(h.action).toBe("choose-file")
    expect(h.retryable).toBe(false)
  })

  test("archivo sin encabezados", () => {
    const h = humanizeError(
      api(422, { detail: "El archivo no tiene columnas (encabezados). Verifique que no este vacio." }),
      "upload"
    )
    expect(h.title).toBe("Tu archivo parece vacío")
  })

  test("archivo ilegible", () => {
    const h = humanizeError(api(422, { detail: "Error al procesar el archivo. Verifique el formato." }), "analyze")
    expect(h.title).toBe("No pudimos leer tu archivo")
    expect(h.description).toMatch(/guárdalo de nuevo/)
  })

  test("errores 5xx son reintentables y nunca muestran el cuerpo crudo", () => {
    const h = humanizeError(api(500, '{"detail":"asyncpg.exceptions.UndefinedTableError: relation"}'), "save")
    expect(h.title).toBe("No pudimos guardar los cambios")
    expect(h.retryable).toBe(true)
    expectHuman(h.title)
    expectHuman(h.description)
    expect(h.technical).toContain("HTTP 500")
  })

  test("401 fuera del login es sesión vencida; en login es credenciales", () => {
    expect(humanizeError(api(401, { detail: "Not authenticated" }), "load").action).toBe("login")
    expect(humanizeError(api(401, { detail: "Credenciales invalidas" }), "login").title).toBe(
      "El correo o la contraseña no coinciden"
    )
  })

  test("registro con correo repetido", () => {
    const h = humanizeError(api(409, { detail: "El email ya esta registrado" }), "register")
    expect(h.title).toBe("Ya existe una cuenta con ese correo")
    expect(h.action).toBe("login")
  })

  test("validaciones de pydantic (lista) no se muestran en inglés", () => {
    const h = humanizeError(
      api(422, { detail: [{ loc: ["body", "name"], msg: "String should have at least 1 character", type: "x" }] }),
      "save"
    )
    expectHuman(h.description)
    expect(h.description).not.toMatch(/String should/)
  })

  test("404 de tabla", () => {
    expect(humanizeError(api(404, { detail: "Tabla no encontrada" }), "load").title).toBe(
      "Ya no encontramos esa información"
    )
  })

  test("frases claras del servidor se aprovechan como descripción", () => {
    const h = humanizeError(api(400, { detail: "El nombre debe tener al menos 2 letras" }), "save")
    expect(h.description).toBe("El nombre debe tener al menos 2 letras.")
  })

  test("HTML o JSON sin detalle nunca llegan a la persona", () => {
    for (const raw of ["<html><body>Bad gateway</body></html>", '{"foo": 1}', "[1,2]"]) {
      const h = humanizeError(new Error(raw), "general")
      expectHuman(h.title)
      expectHuman(h.description)
    }
  })

  test("valores que no son Error tienen un mensaje genérico amable", () => {
    const h = humanizeError("boom", "delete")
    expect(h.title).toBe("No pudimos borrarlo")
    expect(h.retryable).toBe(true)
  })

  test("humanizeErrorText junta título y descripción", () => {
    expect(humanizeErrorText(new TypeError("Failed to fetch"))).toBe(
      "No pudimos conectarnos. Revisa tu conexión a internet e inténtalo de nuevo en un momento."
    )
  })

  test("ApiError conserva el texto crudo en message (para el parser de límites del chat)", () => {
    const err = api(429, { detail: { code: "rate_limit_user", retry_after_seconds: 3 } })
    expect(JSON.parse(err.message)).toEqual({ detail: { code: "rate_limit_user", retry_after_seconds: 3 } })
    expect(err.status).toBe(429)
  })
})
