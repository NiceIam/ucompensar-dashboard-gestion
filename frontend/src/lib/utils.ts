import { clsx, type ClassValue } from "clsx"
import { twMerge } from "tailwind-merge"
import {
  formatDate as formatDateEs,
  formatFileSize as formatFileSizeEs,
  formatNumber as formatNumberEs,
} from "@/lib/format"

export function cn(...inputs: ClassValue[]): string {
  return twMerge(clsx(inputs))
}

/** Compatibilidad: los formateadores viven en `@/lib/format` (es-CO). */
export function formatDate(date: string | Date): string {
  return formatDateEs(date, "short")
}

export function formatFileSize(bytes: number): string {
  return formatFileSizeEs(bytes)
}

export function formatNumber(value: number): string {
  return formatNumberEs(value)
}

export function formatCurrency(value: number, currency = "COP"): string {
  return new Intl.NumberFormat("es-CO", {
    style: "currency",
    currency,
    maximumFractionDigits: 0,
  }).format(value)
}

export function formatPercent(value: number, decimals = 1): string {
  return `${value >= 0 ? "+" : ""}${value.toFixed(decimals)}%`
}
