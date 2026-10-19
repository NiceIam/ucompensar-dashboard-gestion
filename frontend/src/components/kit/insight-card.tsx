"use client"

import { useId, useState, type ElementType } from "react"
import {
  ArrowRight,
  ChevronDown,
  CircleAlert,
  Eye,
  Lightbulb,
  Sparkles,
  TriangleAlert,
  type LucideIcon,
} from "lucide-react"
import { Button } from "@/components/ui/button"
import { TONE, type Tone } from "@/components/kit/tone"
import { SEVERITY_LABEL, formatMetric, joinNames, prettyTable } from "@/lib/insights"
import { formatNumber, pluralize } from "@/lib/format"
import { cn } from "@/lib/utils"
import type { Insight, InsightKind, InsightMetric, InsightSeverity } from "@/types/insights"

/**
 * Cada severidad = tono + icono + palabra. El color nunca va solo:
 * quien no distingue colores (o usa lector de pantalla) lee "Importante", "Ojo" o "Dato".
 */
const SEVERITY: Record<InsightSeverity, { tone: Tone; icon: LucideIcon; bar: string }> = {
  important: { tone: "danger", icon: CircleAlert, bar: "bg-destructive" },
  attention: { tone: "warning", icon: Eye, bar: "bg-warning" },
  info: { tone: "info", icon: Lightbulb, bar: "bg-info" },
}

const KIND_LABEL: Record<InsightKind, string | null> = {
  money: "Plata",
  risk: "Riesgo",
  opportunity: "Oportunidad",
  info: null,
}

const COLS: Record<number, string> = {
  1: "[@container(min-width:26rem)]:grid-cols-1",
  2: "[@container(min-width:26rem)]:grid-cols-2",
}

/**
 * Cifras del hallazgo: filas compactas cuando la tarjeta es angosta y baldosas en una
 * sola fila cuando cabe (se mide el ANCHO DE LA TARJETA, no el de la pantalla: con el
 * chat abierto la tarjeta es angosta aunque la pantalla sea grande).
 */
function MetricTiles({ metrics }: { metrics: InsightMetric[] }) {
  return (
    <dl className={cn("grid gap-2", COLS[metrics.length] ?? "[@container(min-width:26rem)]:grid-cols-3")}>
      {metrics.map((m) => (
        <div
          key={m.label}
          className="flex min-w-0 items-baseline justify-between gap-3 rounded-xl border bg-muted/60 px-3.5 py-2.5 [@container(min-width:26rem)]:block [@container(min-width:26rem)]:py-3"
        >
          <dt className="text-[13px] leading-snug text-muted-foreground">{m.label}</dt>
          <dd
            className={cn(
              "text-right font-display font-semibold [@container(min-width:26rem)]:mt-1 [@container(min-width:26rem)]:text-left",
              m.unit === "text"
                ? "text-base leading-snug [@container(min-width:26rem)]:text-[17px]"
                : "text-xl leading-none tabular [@container(min-width:26rem)]:text-[22px]"
            )}
          >
            {formatMetric(m)}
          </dd>
        </div>
      ))}
    </dl>
  )
}

/** Versión protagonista: la primera cifra en grande y las demás debajo. */
function FeaturedMetrics({ metrics }: { metrics: InsightMetric[] }) {
  const [first, ...rest] = metrics
  return (
    <dl className="space-y-3 rounded-2xl border bg-muted/60 p-4 sm:p-5">
      <div>
        <dt className="text-sm leading-snug text-muted-foreground">{first.label}</dt>
        <dd
          className={cn(
            "mt-1.5 font-display font-semibold",
            first.unit === "text" ? "text-2xl leading-tight" : "text-[44px] leading-none tabular sm:text-[52px]"
          )}
        >
          {formatMetric(first)}
        </dd>
      </div>
      {rest.length > 0 && (
        <div className="space-y-2 border-t pt-3">
          {rest.map((m) => (
            <div key={m.label} className="flex items-baseline justify-between gap-3">
              <dt className="text-[13px] leading-snug text-muted-foreground">{m.label}</dt>
              <dd className={cn("text-right font-display text-lg font-semibold leading-snug", m.unit !== "text" && "tabular")}>
                {formatMetric(m)}
              </dd>
            </div>
          ))}
        </div>
      )}
    </dl>
  )
}

/**
 * Tarjeta de hallazgo: la frase de plata calculada por el servidor, sus cifras,
 * qué hacer y, siempre, "Ver cómo lo calculé" (la transparencia del producto).
 */
export function InsightCard({
  insight,
  onAsk,
  as: Heading = "h3",
  featured = false,
  defaultOpen = false,
  className,
}: {
  insight: Insight
  /** Abre el chat con la pregunta del hallazgo. Sin esto (o sin `ask`) no se muestra el botón. */
  onAsk?: (question: string) => void
  /** Nivel del título según donde viva la tarjeta (h2 si la sección no tiene título propio). */
  as?: ElementType
  /** El hallazgo protagonista: ancho completo, título más grande y la primera cifra gigante. */
  featured?: boolean
  defaultOpen?: boolean
  className?: string
}) {
  const uid = useId()
  const titleId = `${uid}-title`
  const panelId = `${uid}-how`
  const buttonId = `${uid}-how-btn`
  const [open, setOpen] = useState(defaultOpen)

  const sev = SEVERITY[insight.severity] ?? SEVERITY.info
  const tone = TONE[sev.tone]
  const SevIcon = sev.icon
  const kind = KIND_LABEL[insight.kind]
  const how = insight.how
  const tables = how.tables.map(prettyTable)

  const badge = (
    <p className="flex flex-wrap items-center gap-x-3 gap-y-1.5 text-[13px]">
      <span className={cn("inline-flex min-h-7 items-center gap-1.5 rounded-full px-2.5 font-semibold", tone.badge)}>
        <SevIcon className="h-4 w-4" aria-hidden="true" />
        {SEVERITY_LABEL[insight.severity]}
      </span>
      {kind && <span className="font-semibold uppercase tracking-[0.08em] text-muted-foreground">{kind}</span>}
    </p>
  )

  const heading = (
    <Heading
      id={titleId}
      className={cn(
        "font-display font-semibold leading-[1.15] text-balance",
        featured ? "text-[26px] sm:text-[32px]" : "text-[22px] sm:text-[26px]"
      )}
    >
      {insight.title}
    </Heading>
  )

  const sentence = (
    <p className={cn("leading-relaxed text-foreground/90 text-pretty", featured ? "text-[18px]" : "text-[17px]")}>{insight.sentence}</p>
  )

  const action = insight.action ? (
    <div className="flex gap-3 rounded-xl border border-primary/20 bg-primary-soft px-4 py-3.5 text-primary-strong">
      <ArrowRight className="mt-1 h-4 w-4 shrink-0" aria-hidden="true" />
      <div className="min-w-0 space-y-0.5">
        <p className="text-[13px] font-semibold uppercase tracking-[0.08em]">Qué hacer</p>
        <p className="text-[15px] font-medium leading-relaxed text-foreground">{insight.action}</p>
      </div>
    </div>
  ) : null

  return (
    <article
      aria-labelledby={titleId}
      className={cn(
        "surface relative flex min-w-0 flex-col overflow-hidden [container-type:inline-size] print:break-inside-avoid print:shadow-none",
        className
      )}
    >
      <span className={cn("h-1 w-full shrink-0", sev.bar)} aria-hidden="true" />

      <div className="flex flex-1 flex-col gap-4 p-5 sm:p-6">
        {featured ? (
          <div className="grid gap-4 [@container(min-width:44rem)]:grid-cols-[minmax(0,1fr)_18rem] [@container(min-width:44rem)]:gap-x-8">
            {badge}
            {heading}
            {insight.metrics.length > 0 && (
              <div className="min-w-0 self-start [@container(min-width:44rem)]:col-start-2 [@container(min-width:44rem)]:row-span-4 [@container(min-width:44rem)]:row-start-1">
                <FeaturedMetrics metrics={insight.metrics} />
              </div>
            )}
            {sentence}
            {action}
          </div>
        ) : (
          <>
            {badge}
            {heading}
            {sentence}
            {insight.metrics.length > 0 && <MetricTiles metrics={insight.metrics} />}
            {action}
          </>
        )}

        {how.notes.length > 0 && (
          <ul className="space-y-1.5" aria-label="Avisos sobre esta cifra">
            {how.notes.map((note) => (
              <li key={note} className="flex items-start gap-2 text-[13px] leading-snug text-muted-foreground">
                <TriangleAlert className="mt-0.5 h-4 w-4 shrink-0 text-warning-strong" aria-hidden="true" />
                <span>{note}</span>
              </li>
            ))}
          </ul>
        )}

        <div className="mt-auto flex flex-wrap gap-2 pt-1 print:hidden">
          <Button
            id={buttonId}
            type="button"
            variant="outline"
            className="w-full sm:w-auto"
            aria-expanded={open}
            aria-controls={panelId}
            aria-label={`Ver cómo lo calculé: ${insight.title}`}
            onClick={() => setOpen((v) => !v)}
          >
            Ver cómo lo calculé
            <ChevronDown className={cn("transition-transform duration-200", open && "rotate-180")} aria-hidden="true" />
          </Button>
          {onAsk && insight.ask && (
            <Button
              type="button"
              variant="soft"
              className="w-full sm:w-auto"
              aria-label={`Preguntar al asistente: ${insight.ask}`}
              onClick={() => onAsk(insight.ask as string)}
            >
              <Sparkles aria-hidden="true" />
              Preguntar al asistente
            </Button>
          )}
        </div>

        {/* El cálculo siempre existe en el documento; en pantalla se abre y se cierra, al imprimir se muestra completo. */}
        <section
          id={panelId}
          role="region"
          aria-labelledby={buttonId}
          hidden={!open}
          data-print-open
          className="space-y-4 rounded-xl border bg-muted/50 p-4 sm:p-5"
        >
          <h4 className="font-display text-lg font-semibold">Así lo calculé</h4>

          {how.steps.length > 0 && (
            <ol className="space-y-3">
              {how.steps.map((step, i) => (
                <li key={step} className="flex items-start gap-3 text-[15px] leading-relaxed">
                  <span
                    className="mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-primary-soft text-xs font-semibold text-primary-strong tabular"
                    aria-hidden="true"
                  >
                    {i + 1}
                  </span>
                  <span className="min-w-0 text-pretty">
                    <span className="sr-only">Paso {i + 1}: </span>
                    {step}
                  </span>
                </li>
              ))}
            </ol>
          )}

          <p className="border-t pt-3 text-sm leading-relaxed text-muted-foreground">
            {tables.length > 0 ? (
              <>
                Usé tu información de <strong className="font-semibold text-foreground">{joinNames(tables)}</strong>
                {how.rows_used > 0 && <> ({pluralize(how.rows_used, "fila", "filas")} en total)</>}.
              </>
            ) : how.rows_used > 0 ? (
              <>Usé {formatNumber(how.rows_used, 0)} filas de tus datos.</>
            ) : (
              <>Todo sale de lo que subiste a tus hojas.</>
            )}{" "}
            Son cuentas exactas con tus propios datos, sin inteligencia artificial.
          </p>
        </section>
      </div>
    </article>
  )
}
