"use client"

import Link from "next/link"
import { ArrowRight, CheckCircle2, CircleDashed, MessageCircleQuestion } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Skeleton } from "@/components/ui/skeleton"
import { useInsights } from "@/hooks/use-insights"
import { unlockSentence } from "@/lib/intake/plan"

/**
 * «Con esto ya puedo decirte…»: qué hallazgos se habilitaron con lo que acaba de subir y cuáles faltan
 * ("Para decirte cuánto te deben necesito una lista de cuentas por cobrar"). Sale del mismo cálculo exacto del
 * resumen de la semana (GET /api/v1/insights), no de una suposición.
 */
export function UnlocksPanel({ onAsk }: { onAsk: (question: string) => void }) {
  const { data, isLoading, isError, refetch } = useInsights()

  return (
    <section aria-labelledby="unlocks-title" className="space-y-4 rounded-2xl border bg-card p-4 sm:p-5">
      <h4 id="unlocks-title" className="font-display text-xl font-semibold">
        Con esto ya puedo decirte
      </h4>

      {isLoading && (
        <div className="space-y-2" role="status" aria-label="Calculando lo que ya puedo decirte">
          <Skeleton className="h-6 w-3/4" />
          <Skeleton className="h-6 w-2/3" />
          <Skeleton className="h-6 w-4/5" />
        </div>
      )}

      {isError && (
        <p className="text-sm text-muted-foreground">
          No pude calcularlo ahora mismo.{" "}
          <button type="button" className="font-semibold text-primary underline-offset-4 hover:underline" onClick={() => void refetch()}>
            Intentar de nuevo
          </button>
        </p>
      )}

      {data && (
        <>
          {data.items.length > 0 ? (
            <ul className="space-y-2.5">
              {data.items.map((it) => (
                <li key={it.id} className="flex flex-wrap items-start gap-x-2.5 gap-y-1">
                  <CheckCircle2 className="mt-0.5 h-5 w-5 shrink-0 text-success" aria-hidden="true" />
                  <div className="min-w-[12rem] flex-1">
                    <p className="text-[15px] font-semibold leading-snug">{it.title}</p>
                  </div>
                  {it.ask && (
                    <Button variant="ghost" size="sm" className="ml-7 sm:ml-0" onClick={() => onAsk(it.ask!)}>
                      <MessageCircleQuestion aria-hidden="true" />
                      Preguntar
                    </Button>
                  )}
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-sm text-muted-foreground">
              Todavía no tengo con qué calcular tus hallazgos de plata. Mira abajo qué me falta.
            </p>
          )}

          {data.missing.length > 0 && (
            <div className="space-y-2 border-t pt-3">
              <p className="text-sm font-semibold text-muted-foreground">Lo que todavía no puedo decirte</p>
              <ul className="space-y-2">
                {data.missing.map((m) => (
                  <li key={m.id} className="flex items-start gap-2.5 text-sm leading-relaxed text-foreground/85">
                    <CircleDashed className="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground" aria-hidden="true" />
                    <span>{unlockSentence(m)}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {data.items.length > 0 && (
            <Button asChild variant="soft" size="sm">
              <Link href="/resumen">
                Ver mi resumen de la semana
                <ArrowRight aria-hidden="true" />
              </Link>
            </Button>
          )}
        </>
      )}
    </section>
  )
}
