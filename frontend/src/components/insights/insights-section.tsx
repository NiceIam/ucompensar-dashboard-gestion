"use client"

import Link from "next/link"
import { ArrowRight, RotateCcw, Upload, Wallet } from "lucide-react"
import { Button } from "@/components/ui/button"
import { DotField } from "@/components/kit/dots"
import { InsightList } from "@/components/insights/insight-list"
import { Notice } from "@/components/kit/notice"
import { SectionHeader } from "@/components/kit/page-header"
import { InsightCardSkeleton } from "@/components/kit/skeletons"
import { humanizeError } from "@/lib/errors"
import { periodLabel, topInsights } from "@/lib/insights"
import type { InsightsResponse } from "@/types/insights"

/** Lo mínimo que se necesita de la consulta: así la sección se prueba sin proveedores. */
export interface InsightsQueryLike {
  data?: InsightsResponse
  isLoading: boolean
  isError: boolean
  error: unknown
  isFetching: boolean
  refetch: () => unknown
}

/**
 * "Esta semana en tu negocio" en el Inicio: los 3 hallazgos más importantes.
 * Maneja sus propios estados (cargando, error, sin hallazgos pero con faltantes,
 * vacío) sin tumbar el resto de la pantalla.
 */
export function InsightsSection({ query, onAsk }: { query: InsightsQueryLike; onAsk: (question: string) => void }) {
  const { data } = query
  const items = data?.items ?? []
  const missing = data?.missing ?? []
  const top = topInsights(items, 3)
  const period = periodLabel(data?.period)

  return (
    <section aria-labelledby="home-insights" className="space-y-5">
      <SectionHeader
        id="home-insights"
        title="Esta semana en tu negocio"
        description={
          query.isLoading
            ? "Buscando dónde se te va la plata…"
            : items.length > 0
              ? (period ?? "Lo que encontramos en tus datos, sin que tengas que preguntar.")
              : undefined
        }
        action={
          items.length > 0 ? (
            <Button asChild variant="ghost" size="sm" className="max-sm:-ml-3">
              <Link href="/resumen">
                {items.length > top.length ? `Ver todos (${items.length})` : "Ver resumen completo"}
                <ArrowRight aria-hidden="true" />
              </Link>
            </Button>
          ) : undefined
        }
      />

      {query.isLoading ? (
        <InsightCardSkeleton count={3} />
      ) : query.isError ? (
        <InsightsError error={query.error} retrying={query.isFetching} onRetry={() => void query.refetch()} />
      ) : items.length > 0 ? (
        <>
          <InsightList items={top} onAsk={onAsk} />
          {missing.length > 0 && (
            <p className="text-sm text-muted-foreground">
              Con más datos te puedo contar {missing.length === 1 ? "algo más" : `${missing.length} cosas más`}.{" "}
              <Link href="/resumen#te-falta" className="font-semibold text-primary underline-offset-4 hover:underline">
                Ver qué me falta
              </Link>
            </p>
          )}
        </>
      ) : missing.length > 0 ? (
        <NeedMoreData missing={missing} />
      ) : (
        <Notice tone="neutral" title="Todavía no hay hallazgos para mostrarte">
          Cuando tus datos tengan más movimiento, aquí aparecerán las cosas que conviene revisar esta semana.
        </Notice>
      )}
    </section>
  )
}

function InsightsError({ error, retrying, onRetry }: { error: unknown; retrying: boolean; onRetry: () => void }) {
  const human = humanizeError(error, "load")
  return (
    <Notice
      tone="warning"
      title="No pudimos armar tus hallazgos"
      action={
        human.action === "login" ? (
          <Button asChild size="sm">
            <a href="/login">Iniciar sesión</a>
          </Button>
        ) : (
          <Button variant="outline" size="sm" onClick={onRetry} loading={retrying} loadingText="Intentando…">
            <RotateCcw aria-hidden="true" />
            Intentar de nuevo
          </Button>
        )
      }
    >
      {human.description} El resto de tu inicio sigue funcionando.
    </Notice>
  )
}

/** Sin hallazgos todavía, pero sabemos qué falta: invitación amable a subir esos datos. */
function NeedMoreData({ missing }: { missing: InsightsResponse["missing"] }) {
  return (
    <div className="surface relative overflow-hidden p-5 sm:p-7">
      <DotField fade="top-right" className="[--dots-alpha:0.3] [--dots-gap:20px]" />
      <div className="relative flex flex-wrap items-start gap-5">
        <span className="flex h-12 w-12 shrink-0 items-center justify-center rounded-2xl bg-highlight-soft text-highlight-strong">
          <Wallet className="h-6 w-6" aria-hidden="true" />
        </span>
        <div className="min-w-0 flex-[1_1_20rem] space-y-4">
          <div className="space-y-1.5">
            <h3 className="font-display text-2xl font-semibold leading-tight text-balance">
              Para decirte cuánta plata tienes parada necesito tus productos y tus ventas
            </h3>
            <p className="max-w-2xl text-[15px] leading-relaxed text-muted-foreground">
              Con eso te cuento cuánta mercancía tienes quieta, qué productos te dejan más y cuáles se te están acabando. Esto es lo que me falta:
            </p>
          </div>
          <ul className="space-y-2">
            {missing.slice(0, 3).map((m) => (
              <li key={m.id} className="text-[15px] leading-relaxed">
                <span className="font-semibold">{m.title}.</span> <span className="text-muted-foreground">{m.needs}</span>
              </li>
            ))}
          </ul>
          <Button asChild size="lg">
            <Link href="/data">
              <Upload aria-hidden="true" />
              Subir mis datos
            </Link>
          </Button>
        </div>
      </div>
    </div>
  )
}
