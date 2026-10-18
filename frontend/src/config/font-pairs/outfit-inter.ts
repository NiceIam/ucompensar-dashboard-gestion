import { Inter, Outfit } from "next/font/google"
import { tuning, type FontPair } from "./types"

/*
 * A · Outfit (titulares y cifras) + Inter (texto).
 * Outfit es geométrica y redonda, pariente directa de la letra del logo de la
 * universidad; Inter es la referencia de legibilidad en pantalla a tamaño pequeño.
 * Ambas son variables: un solo archivo por familia (subconjunto latin, con tildes,
 * ñ, ¿ y ¡) cubre todos los pesos que usamos (400–700).
 */
const display = Outfit({
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
  name: "Outfit + Inter",
  className: `${display.variable} ${sans.variable}`,
  style: tuning({
    // Inter ya viene con espaciado abierto: no se aprieta. cv11 = «a» de un solo piso, como en «compensar».
    "--tracking-body": "0em",
    "--font-features": '"cv11", "calt"',
  }),
}
