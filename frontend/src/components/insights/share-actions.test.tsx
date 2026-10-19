import { afterEach, describe, expect, test, vi } from "vitest"
import { render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { ShareActions } from "./share-actions"
import { copyText } from "@/lib/clipboard"

const TEXT = "Resumen de tu negocio (lunes 19 de octubre)\n• Tienes $47,6 M en mercancía & más"

afterEach(() => {
  vi.restoreAllMocks()
  Object.defineProperty(navigator, "clipboard", { value: undefined, configurable: true })
  Reflect.deleteProperty(document, "execCommand")
})

describe("compartir el resumen", () => {
  test("WhatsApp: enlace wa.me con el texto codificado, pestaña nueva y rel seguro", () => {
    render(<ShareActions text={TEXT} />)
    const link = screen.getByRole("link", { name: /Compartir por WhatsApp/ })
    expect(link).toHaveAttribute("href", `https://wa.me/?text=${encodeURIComponent(TEXT)}`)
    expect(link).toHaveAttribute("target", "_blank")
    expect(link).toHaveAttribute("rel", "noopener noreferrer")
    expect(link).toHaveAccessibleName(/se abre en una pestaña nueva/)
  })

  test("copiar: usa el portapapeles y lo confirma con un mensaje accesible", async () => {
    const user = userEvent.setup() // user-event instala su propio portapapeles: se reemplaza DESPUÉS
    const writeText = vi.fn().mockResolvedValue(undefined)
    Object.defineProperty(navigator, "clipboard", { value: { writeText }, configurable: true })
    render(<ShareActions text={TEXT} />)
    await user.click(screen.getByRole("button", { name: "Copiar resumen" }))
    expect(writeText).toHaveBeenCalledWith(TEXT)
    expect(await screen.findByRole("button", { name: "Resumen copiado" })).toBeInTheDocument()
    expect(screen.getByRole("status")).toHaveTextContent("el resumen quedó copiado")
  })

  test("sin portapapeles moderno degrada al método antiguo", async () => {
    Object.defineProperty(navigator, "clipboard", { value: undefined, configurable: true })
    const exec = vi.fn().mockReturnValue(true)
    Object.defineProperty(document, "execCommand", { value: exec, configurable: true })
    expect(await copyText(TEXT)).toBe(true)
    expect(exec).toHaveBeenCalledWith("copy")
    expect(document.querySelector("textarea")).toBeNull() // no deja basura en la página
  })

  test("si nada funciona lo dice y manda a copiar a mano", async () => {
    const user = userEvent.setup()
    Object.defineProperty(navigator, "clipboard", { value: undefined, configurable: true })
    render(<ShareActions text={TEXT} />)
    await user.click(screen.getByRole("button", { name: "Copiar resumen" }))
    await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent("No pudimos copiarlo automáticamente"))
    expect(screen.getByRole("button", { name: "Copiar resumen" })).toBeInTheDocument()
  })

  test("imprimir llama a window.print", async () => {
    const print = vi.spyOn(window, "print").mockImplementation(() => {})
    render(<ShareActions text={TEXT} />)
    await userEvent.setup().click(screen.getByRole("button", { name: /Imprimir \/ guardar PDF/ }))
    expect(print).toHaveBeenCalledTimes(1)
  })

  test("sin texto, compartir y copiar quedan desactivados (imprimir sigue)", () => {
    render(<ShareActions text="  " />)
    expect(screen.queryByRole("link", { name: /WhatsApp/ })).toBeNull()
    expect(screen.getByRole("button", { name: /WhatsApp/ })).toBeDisabled()
    expect(screen.getByRole("button", { name: "Copiar resumen" })).toBeDisabled()
    expect(screen.getByRole("button", { name: /Imprimir/ })).toBeEnabled()
  })
})
