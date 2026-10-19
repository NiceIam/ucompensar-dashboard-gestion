import { describe, expect, test } from "vitest"

/** Los formateadores usan espacio duro entre cifra y unidad; aquí se comparan como espacios normales. */
const plain = (s: string | undefined) => (s ?? "").replace(/\u00a0/g, " ")
import {
  formatChange,
  formatCompact,
  formatDate,
  formatDateRange,
  formatFileSize,
  formatMoney,
  formatNumber,
  formatRelative,
  formatShare,
  greeting,
  pluralize,
} from "./format"

describe("formatNumber (es-CO)", () => {
  test("miles con punto y decimales con coma", () => {
    expect(formatNumber(1234567.891)).toBe("1.234.567,89")
    expect(formatNumber(1234.5, 0)).toBe("1.235")
    expect(formatNumber(0)).toBe("0")
  })

  test("valores no finitos se muestran como guion largo", () => {
    expect(formatNumber(Number.NaN)).toBe("—")
    expect(formatNumber(Number.POSITIVE_INFINITY)).toBe("—")
  })
})

describe("formatCompact", () => {
  test("cifras cortas para titulares", () => {
    expect(plain(formatCompact(850))).toBe("850")
    expect(plain(formatCompact(9_999))).toBe("9.999")
    expect(plain(formatCompact(12_400))).toBe("12,4 mil")
    expect(plain(formatCompact(250_000))).toBe("250 mil")
    expect(plain(formatCompact(12_400_000))).toBe("12,4 M")
    expect(plain(formatCompact(3_200_000_000))).toBe("3.200 M")
    expect(plain(formatCompact(-1_500_000))).toBe("-1,5 M")
  })
})

describe("formatMoney", () => {
  test("pesos completos y compactos", () => {
    expect(plain(formatMoney(12_400_000))).toBe("$ 12.400.000")
    expect(plain(formatMoney(12_400_000, { compact: true }))).toBe("$ 12,4 M")
    expect(plain(formatMoney(-2500))).toBe("-$ 2.500")
    expect(plain(formatMoney(19.5))).toBe("$ 19,5")
  })
})

describe("porcentajes", () => {
  test("formatShare usa coma decimal y espacio antes de %", () => {
    expect(plain(formatShare(0.183))).toBe("18 %")
    expect(plain(formatShare(0.0042))).toBe("0,4 %")
    expect(plain(formatShare(1))).toBe("100 %")
  })

  test("formatChange agrega el signo", () => {
    expect(plain(formatChange(0.18))).toBe("+18 %")
    expect(plain(formatChange(-0.05))).toBe("-5 %")
    expect(plain(formatChange(0))).toBe("0 %")
  })
})

describe("fechas", () => {
  const d = new Date(2026, 9, 16, 15, 30)

  test("formatDate en tres estilos", () => {
    expect(formatDate(d)).toBe("16 oct 2026")
    expect(formatDate(d, "long")).toBe("16 de octubre de 2026")
    expect(formatDate(d, "month")).toBe("octubre de 2026")
    expect(formatDate("no es fecha")).toBe("—")
  })

  test("formatDateRange omite el año repetido", () => {
    expect(formatDateRange(new Date(2026, 0, 3), new Date(2026, 2, 28))).toBe(
      "del 3 de enero al 28 de marzo de 2026"
    )
    expect(formatDateRange(new Date(2025, 11, 30), new Date(2026, 0, 2))).toBe(
      "del 30 de diciembre de 2025 al 2 de enero de 2026"
    )
    expect(formatDateRange(d, new Date(2026, 9, 16, 18))).toBe("el 16 de octubre de 2026")
  })

  test("formatRelative en lenguaje cotidiano", () => {
    const now = new Date(2026, 9, 16, 9)
    expect(formatRelative(new Date(2026, 9, 16, 1), now)).toBe("hoy")
    expect(formatRelative(new Date(2026, 9, 15, 23), now)).toBe("ayer")
    expect(formatRelative(new Date(2026, 9, 12), now)).toBe("hace 4 días")
    expect(formatRelative(new Date(2026, 9, 2), now)).toBe("hace 2 semanas")
    expect(formatRelative(new Date(2026, 7, 1), now)).toBe("hace 2 meses")
    expect(formatRelative(new Date(2025, 9, 1), now)).toBe("hace 1 año")
  })

  test("greeting según la hora", () => {
    expect(greeting(new Date(2026, 0, 1, 8))).toBe("Buenos días")
    expect(greeting(new Date(2026, 0, 1, 14))).toBe("Buenas tardes")
    expect(greeting(new Date(2026, 0, 1, 21))).toBe("Buenas noches")
  })
})

describe("otros", () => {
  test("pluralize", () => {
    expect(pluralize(1, "fila", "filas")).toBe("1 fila")
    expect(pluralize(1300, "fila", "filas")).toBe("1.300 filas")
  })

  test("formatFileSize", () => {
    expect(formatFileSize(0)).toBe("0 B")
    expect(formatFileSize(512)).toBe("512 B")
    expect(formatFileSize(1536)).toBe("1,5 KB")
    expect(formatFileSize(10 * 1024 * 1024)).toBe("10 MB")
  })
})
