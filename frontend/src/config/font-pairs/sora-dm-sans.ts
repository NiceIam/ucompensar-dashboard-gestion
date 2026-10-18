import { DM_Sans, Sora } from "next/font/google"
import { tuning, type FontPair } from "./types"

/*
 * B · Sora (titulares y cifras) + DM Sans (texto).
 * Sora es ancha y tecnológica; DM Sans, geométrica de bajo contraste.
 * Variables: un archivo por familia (subconjunto latin) para todos los pesos.
 */
const display = Sora({
  subsets: ["latin"],
  variable: "--font-display",
  display: "swap",
  fallback: ["ui-sans-serif", "system-ui", "Segoe UI", "Roboto", "Arial", "sans-serif"],
})

const sans = DM_Sans({
  subsets: ["latin"],
  variable: "--font-sans",
  display: "swap",
  fallback: ["ui-sans-serif", "system-ui", "Segoe UI", "Roboto", "Arial", "sans-serif"],
})

export const fontPair: FontPair = {
  name: "Sora + DM Sans",
  className: `${display.variable} ${sans.variable}`,
  style: tuning({
    // DM Sans es un poco cerrada en tamaños pequeños: se abre apenas.
    "--tracking-body": "0.006em",
    "--font-features": '"calt"',
  }),
}
