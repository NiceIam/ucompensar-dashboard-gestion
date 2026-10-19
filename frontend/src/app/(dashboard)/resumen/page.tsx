"use client"

import Link from "next/link"
import { useMemo } from "react"
import { Share2, Upload } from "lucide-react"
import { Button } from "@/components/ui/button"
import { BrandName } from "@/components/kit/logo"
import { EmptyState, ErrorState } from "@/components/kit/empty-state"
import { PageHeader, SectionHeader } from "@/components/kit/page-header"
import { InsightCardSkeleton } from "@/components/kit/skeletons"
import { InsightList } from "@/components/insights/insight-list"
import { MissingCard } from "@/components/insights/missing-card"
import { ShareActions } from "@/components/insights/share-actions"
import { useInsights } from "@/hooks/use-insights"
import { usePageTitle } from "@/hooks/use-page-title"
import { useChat } from "@/providers/chat-provider"
import { humanizeError } from "@/lib/errors"
import { buildSummaryText, dayLabel, periodLabel, sortInsights } from "@/lib/insights"

export default function ResumenPage() {
  usePageTitle("Resumen de la semana")
  const { ask } = useChat()
  const query = useInsights()
  const data = query.data

  const items = useMemo(() => sortInsights(data?.items ?? []), [data])
  const missing = data?.missing ?? []
  const summary = useMemo(() => (data ? buildSummaryText(data) : ""), [data])

  const period = periodLabel(data?.period)
  const generated = data ? new Date(data.generated_at) : null
  const generatedLabel = generated && !Number.isNaN(generated.getTime()) ? `Calculado el ${dayLabel(generated)}` : null

  return (
    <div className="space-y-10">
      <PageHeader
        eyebrow="Esta semana en tu negocio"
        title="Tu resumen de la semana"
        description={
          query.isLoading
            ? "Estamos haciendo las cuentas con tus datos…"
            : "Lo que conviene revisar en tu negocio, con las cuentas a la vista. Todo sale de tus propios datos."
        }
      >
        {(period || generatedLabel) && (
          <p className="text-sm font-medium text-foreground/80">
            {period}
            {period && generatedLabel ? " · " : ""}
            <span className="text-muted-foreground">{generatedLabel}</span>
          </p>
        )}
      </PageHeader>

      {query.isLoading ? (
        <InsightCardSkeleton count={4} />
      ) : query.isError ? (
        <div className="surface">
          <ErrorState error={humanizeError(query.error, "load")} onRetry={() => void query.refetch()} retrying={query.isFetching} />
        </div>
      ) : items.length === 0 && missing.length === 0 ? (
        <section className="surface">
          <EmptyState
            illustration="empty"
            title="Todavía no tengo hallazgos para ti"
            description="Sube la información de tu negocio (productos y ventas, por ejemplo) y aquí te cuento qué conviene revisar esta semana."
            actions={
              <Button asChild size="lg">
                <Link href="/data">
                  <Upload aria-hidden="true" />
                  Subir mis datos
                </Link>
              </Button>
            }
          />
        </section>
      ) : (
        <>
          {items.length > 0 && (
            <section aria-label="Compartir el resumen" className="surface flex flex-wrap items-center gap-x-6 gap-y-4 p-4 sm:p-5 print:hidden">
              <div className="flex min-w-0 flex-[1_1_15rem] items-center gap-3 lg:flex-[0_1_16rem]">
                <span className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-primary-soft text-primary-strong">
                  <Share2 className="h-5 w-5" aria-hidden="true" />
                </span>
                <div className="min-w-0">
                  <p className="font-display text-lg font-semibold leading-tight">Compártelo con tu socio</p>
                  <p className="text-sm text-muted-foreground">Un mensaje corto con lo más importante.</p>
                </div>
              </div>
              <ShareActions text={summary} className="min-w-0 flex-[1_1_22rem] lg:flex-[1_1_0]" />
            </section>
          )}

          {items.length > 0 && (
            <section aria-labelledby="resumen-hallazgos" className="space-y-5">
              <SectionHeader
                id="resumen-hallazgos"
                title={items.length === 1 ? "1 hallazgo" : `${items.length} hallazgos`}
                description="Ordenados del más importante al menos importante."
              />
              <InsightList items={items} onAsk={(q) => ask(q)} />
            </section>
          )}

          {missing.length > 0 && (
            <section id="te-falta" aria-labelledby="resumen-falta" className="scroll-mt-24 space-y-5 print:hidden">
              <SectionHeader
                id="resumen-falta"
                title="Lo que te falta para ver más"
                description={
                  items.length === 0
                    ? "Todavía no puedo calcular nada con lo que hay. Esto es lo que necesito de ti:"
                    : "Con estos datos te puedo contar más cosas de tu negocio."
                }
              />
              <ul className="auto-grid gap-4 [--auto-grid-min:20rem]">
                {missing.map((m) => (
                  <li key={m.id} className="min-w-0">
                    <MissingCard item={m} as="h3" />
                  </li>
                ))}
              </ul>
            </section>
          )}

          {items.length > 0 && summary && (
            <section aria-labelledby="resumen-mensaje" className="space-y-3 print:hidden">
              <SectionHeader
                id="resumen-mensaje"
                title="Así se verá el mensaje"
                description="Esto es exactamente lo que se envía o se copia."
              />
              <pre className="surface whitespace-pre-wrap break-words p-4 font-sans text-[15px] leading-relaxed text-foreground/90 sm:p-5">
                {summary}
              </pre>
            </section>
          )}

          <footer className="hidden items-center justify-between gap-4 border-t pt-4 text-xs text-muted-foreground print:flex">
            <span>Cuentas exactas con los datos del negocio, sin inteligencia artificial.</span>
            <BrandName size="sm" className="items-end text-right" />
          </footer>
        </>
      )}
    </div>
  )
}
