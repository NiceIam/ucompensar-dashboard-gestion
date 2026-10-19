import { Inter, Urbanist } from "next/font/google"
import { tuning, type FontPair } from "./types"

/*
 * C · Urbanist (titulares y cifras) + Inter (texto).
 * Urbanist es geométrica de trazo limpio, con aire a Futura; Inter para leer.
 * Variables: un archivo por familia (subconjunto latin) para todos los pesos.
 */
const display = Urbanist({
  subsets: ["latin"],
  variable: "--font-display",
  display: "swap",
  fallback: ["ui-sans-serif", "system-ui", "Segoe UI", "Roboto", "Arial", "sans-serif"],
})

const sans = Inter({
  subsets: ["latin"],
  variable: "--font-sans",
  display: "swap",
  fallback: ["ui-sans-serif", "system-ui", "Segoe UI", "Roboto", "Arial", "sans-serif"],
})

export const fontPair: FontPair = {
  name: "Urbanist + Inter",
  className: `${display.variable} ${sans.variable}`,
  style: tuning({
    "--tracking-body": "0em",
    "--font-features": '"calt"',
  }),
}
