/**
 * Copia texto al portapapeles. Usa la API moderna si existe; si no (navegadores
 * viejos, páginas sin https), intenta el método antiguo con un campo oculto.
 * Devuelve `false` si ninguno funcionó, para que la pantalla lo diga con claridad.
 */
export async function copyText(text: string): Promise<boolean> {
  try {
    if (typeof navigator !== "undefined" && navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(text)
      return true
    }
  } catch {
    // permiso denegado o contexto no seguro: se prueba el método antiguo
  }
  try {
    if (typeof document === "undefined" || typeof document.execCommand !== "function") return false
    const area = document.createElement("textarea")
    area.value = text
    area.setAttribute("readonly", "")
    area.setAttribute("aria-hidden", "true")
    area.style.position = "fixed"
    area.style.top = "0"
    area.style.left = "-9999px"
    document.body.appendChild(area)
    area.select()
    const ok = document.execCommand("copy")
    area.remove()
    return ok
  } catch {
    return false
  }
}
