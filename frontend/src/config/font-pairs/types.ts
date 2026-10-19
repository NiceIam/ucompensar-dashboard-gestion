import type { CSSProperties } from "react"

/** Un emparejamiento tipográfico: letra de titulares y cifras + letra de texto. */
export interface FontPair {
  /** Nombre legible, para documentación y capturas. */
  name: string
  /** Clases que definen --font-display y --font-sans (van en <html>). */
  className: string
  /**
   * Ajustes finos por familia (van en <body>): espaciado del texto y rasgos
   * OpenType. Las cifras siempre son de caja alta (lining), nunca de estilo antiguo.
   */
  style: CSSProperties
}

/** Atajo para declarar variables CSS en `style` sin pelear con los tipos de React. */
export const tuning = (vars: Record<`--${string}`, string>) => vars as CSSProperties
