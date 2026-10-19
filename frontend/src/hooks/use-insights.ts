"use client"

import { useQuery } from "@tanstack/react-query"
import { api } from "@/lib/api"
import { normalizeInsights } from "@/lib/insights"
import type { InsightsResponse } from "@/types/insights"

/** Clave de caché: se invalida cuando la persona sube, edita o borra datos (ver `DATA_KEYS.insights`). */
export const INSIGHTS_KEY = ["insights"] as const

/**
 * Hallazgos de plata calculados por el servidor (sin IA). Inicio y /resumen
 * comparten esta consulta: se pide una sola vez y se reutiliza.
 */
export function useInsights() {
  return useQuery<InsightsResponse>({
    queryKey: INSIGHTS_KEY,
    queryFn: async () => normalizeInsights(await api.get<Partial<InsightsResponse>>("/api/v1/insights")),
    staleTime: 60_000,
    refetchOnWindowFocus: false,
    retry: 1,
  })
}
