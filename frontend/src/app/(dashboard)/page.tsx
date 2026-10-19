"use client"

import Link from "next/link"
import { useMemo } from "react"
import { ArrowRight, BarChart3, ChartColumnBig, FolderOpen, Layers, Rows3, Upload } from "lucide-react"
import { Button } from "@/components/ui/button"
import { AskBox } from "@/components/kit/ask-box"
import { DataSentence, Figure } from "@/components/kit/data-sentence"
import { EmptyState, ErrorState } from "@/components/kit/empty-state"
import { Journey } from "@/components/kit/journey"
import { SectionHeader } from "@/components/kit/page-header"
import { CardGridSkeleton, ListSkeleton } from "@/components/kit/skeletons"
import { ColumnPill } from "@/components/data/column-kind"
import { TableIcon } from "@/components/data/table-icon"
import { firstName } from "@/components/shell/user-menu"
import { useDashboards } from "@/hooks/use-dashboards"
import { usePageTitle } from "@/hooks/use-page-title"
import { useOrgTables } from "@/hooks/use-templates"
import { useAuthContext } from "@/providers/auth-provider"
import { useChat } from "@/providers/chat-provider"
import { humanizeError } from "@/lib/errors"
import { formatNumber, formatRelative, formatShare, greeting, monthName, pluralize } from "@/lib/format"
import { suggestQuestions } from "@/lib/suggestions"

const WEEKDAYS = ["domingo", "lunes", "martes", "miércoles", "jueves", "viernes", "sábado"]

function todayLabel(d = new Date()) {
  return `${WEEKDAYS[d.getDay()]} ${d.getDate()} de ${monthName(d.getMonth())}`
}

export default function HomePage() {
  usePageTitle("Inicio")
  const { user } = useAuthContext()
  const { ask } = useChat()
  const tablesQuery = useOrgTables()
  const dashboardsQuery = useDashboards()

  const tables = useMemo(() => tablesQuery.data?.tables ?? [], [tablesQuery.data])
  const withRows = useMemo(() => tables.filter((t) => t.row_count > 0).sort((a, b) => b.row_count - a.row_count), [tables])
  const ready = tables.filter((t) => t.row_count === 0)
  const totalRows = withRows.reduce((s, t) => s + t.row_count, 0)
  const dashboards = useMemo(
    () => [...(dashboardsQuery.data ?? [])].sort((a, b) => b.created_at.localeCompare(a.created_at)),
    [dashboardsQuery.data]
  )
  const suggestions = useMemo(
    () =>
      suggestQuestions(
        withRows.map((t) => ({ name: t.display_name, rowCount: t.row_count, columns: t.columns_definition ?? [] })),
        3
      ),
    [withRows]
  )

  const name = firstName(user?.full_name)
  const loading = tablesQuery.isLoading

  return (
    <div className="space-y-10">
      <header className="space-y-2">
        <p className="text-[13px] font-semibold uppercase tracking-[0.08em] text-primary first-letter:uppercase">
          {todayLabel()}
        </p>
        <h1 className="font-display text-[32px] font-semibold leading-[1.1] sm:text-[40px]">
          {greeting()}
          {name ? `, ${name}` : ""}.
        </h1>
        <p className="max-w-2xl text-[15px] text-muted-foreground">
          {loading
            ? "Estamos trayendo tu información…"
            : withRows.length > 0
              ? "Esto es lo que tienes hoy. Pregunta lo que quieras: las respuestas salen de tus propios datos."
              : "Todo está listo. Solo falta tu información para empezar a orientarte."}
        </p>
      </header>

      {loading ? (
        <div className="space-y-6">
          <div className="h-56 animate-pulse rounded-3xl bg-muted" />
          <CardGridSkeleton count={3} />
        </div>
      ) : tablesQuery.isError ? (
        <div className="surface">
          <ErrorState
            error={humanizeError(tablesQuery.error, "load")}
            onRetry={() => void tablesQuery.refetch()}
            retrying={tablesQuery.isFetching}
          />
        </div>
      ) : withRows.length === 0 ? (
        /* ── Sin datos: bienvenida que guía ── */
        <section className="surface overflow-hidden rounded-3xl">
          <div className="flex flex-wrap">
            <EmptyState
              illustration="compass"
              title="Empecemos por tus datos"
              description="Sube un Excel, CSV o JSON con la información de tu negocio. Nosotros la organizamos y tú le preguntas lo que quieras."
              actions={
                <Button asChild size="lg">
                  <Link href="/data">
                    <Upload aria-hidden="true" />
                    Subir mi primer archivo
                  </Link>
                </Button>
              }
              className="min-w-0 flex-[1.1_1_22rem] lg:px-10"
            >
              {ready.length > 0 && (
                <p className="max-w-md text-sm text-muted-foreground">
                  Ya preparamos {pluralize(ready.length, "hoja", "hojas")} para tu tipo de negocio (
                  {ready
                    .slice(0, 3)
                    .map((t) => t.display_name)
                    .join(", ")}
                  {ready.length > 3 ? "…" : ""}). Si quieres, descarga la plantilla en Mis datos.
                </p>
              )}
            </EmptyState>
            <div className="min-w-0 flex-[1_1_20rem] bg-muted/40 p-6 lg:p-10">
              <p className="mb-4 text-sm font-semibold">Así funciona</p>
              <Journey className="[--auto-grid-min:100%]" />
            </div>
          </div>
        </section>
      ) : (
        /* ── Con datos ── */
        <>
          <AskBox onAsk={(q) => ask(q)} suggestions={suggestions} />

          <div className="flex flex-wrap gap-8">
            <section aria-labelledby="home-data" className="min-w-0 flex-[1.6_1_26rem] space-y-5">
              <SectionHeader
                id="home-data"
                title="Tus datos"
                description={`${pluralize(withRows.length, "hoja", "hojas")} con ${formatNumber(totalRows)} filas`}
                action={
                  <Button asChild variant="ghost" size="sm">
                    <Link href="/data">
                      Ver todo
                      <ArrowRight aria-hidden="true" />
                    </Link>
                  </Button>
                }
              />
              <ul className="auto-grid gap-3 [--auto-grid-min:15rem]">
                {withRows.slice(0, 4).map((t) => (
                  <li key={t.id}>
                    <Link
                      href="/data"
                      className="surface group flex h-full flex-col gap-3 p-4 transition hover:-translate-y-0.5 hover:shadow-raised focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                    >
                      <div className="flex items-center gap-3">
                        <TableIcon name={`${t.table_name} ${t.display_name}`} className="h-10 w-10" />
                        <div className="min-w-0 flex-1">
                          <p className="truncate font-display text-lg font-semibold leading-tight">{t.display_name}</p>
                          <p className="text-sm text-muted-foreground">{pluralize(t.row_count, "fila", "filas")}</p>
                        </div>
                        <ArrowRight className="h-4 w-4 shrink-0 text-muted-foreground transition group-hover:translate-x-0.5 group-hover:text-primary" aria-hidden="true" />
                      </div>
                      <div className="flex flex-wrap gap-1.5">
                        {(t.columns_definition ?? []).slice(0, 3).map((c) => (
                          <ColumnPill key={c.name} column={c} />
                        ))}
                      </div>
                    </Link>
                  </li>
                ))}
              </ul>
              <div className="auto-grid gap-3 pt-2 [--auto-grid-min:15rem]">
                <Link
                  href="/data"
                  className="group flex min-h-16 items-center gap-3 rounded-2xl border border-dashed px-4 py-3 transition hover:border-primary/50 hover:bg-primary-soft/30"
                >
                  <Upload className="h-5 w-5 shrink-0 text-primary" aria-hidden="true" />
                  <span className="min-w-0 flex-1">
                    <span className="block font-semibold">Agregar más datos</span>
                    <span className="block text-sm text-muted-foreground">Excel, CSV o JSON</span>
                  </span>
                  <ArrowRight className="h-4 w-4 shrink-0 text-muted-foreground transition group-hover:translate-x-0.5" aria-hidden="true" />
                </Link>
                <Link
                  href="/dashboards"
                  className="group flex min-h-16 items-center gap-3 rounded-2xl border border-dashed px-4 py-3 transition hover:border-primary/50 hover:bg-primary-soft/30"
                >
                  <ChartColumnBig className="h-5 w-5 shrink-0 text-primary" aria-hidden="true" />
                  <span className="min-w-0 flex-1">
                    <span className="block font-semibold">Ver tus tableros</span>
                    <span className="block text-sm text-muted-foreground">Gráficos listos para revisar</span>
                  </span>
                  <ArrowRight className="h-4 w-4 shrink-0 text-muted-foreground transition group-hover:translate-x-0.5" aria-hidden="true" />
                </Link>
              </div>
              {withRows.length > 4 && (
                <p className="text-sm text-muted-foreground">Y {pluralize(withRows.length - 4, "hoja más", "hojas más")} en Mis datos.</p>
              )}
            </section>

            <aside className="min-w-0 flex-[1_1_18rem] space-y-8">
              <section aria-labelledby="home-summary" className="surface space-y-4 p-5 sm:p-6">
                <h2 id="home-summary" className="font-display text-xl font-semibold">
                  En pocas palabras
                </h2>
                <DataSentence icon={Rows3}>
                  Tienes <Figure>{formatNumber(totalRows)}</Figure> filas guardadas en {pluralize(withRows.length, "hoja", "hojas")}.
                </DataSentence>
                {withRows[0] && withRows.length > 1 && (
                  <DataSentence icon={Layers}>
                    La más grande es «{withRows[0].display_name}», con <Figure>{formatShare(withRows[0].row_count / totalRows)}</Figure> de
                    tus filas.
                  </DataSentence>
                )}
                {dashboards[0] && (
                  <DataSentence icon={ChartColumnBig}>
                    Tu tablero más reciente es «{dashboards[0].name}», creado {formatRelative(dashboards[0].created_at)}.
                  </DataSentence>
                )}
                {ready.length > 0 && (
                  <DataSentence icon={FolderOpen} tone="highlight">
                    {ready.length === 1 ? `«${ready[0].display_name}» está lista` : `${ready.length} hojas están listas`} para llenar
                    cuando quieras.
                  </DataSentence>
                )}
              </section>

              <section aria-labelledby="home-dashboards" className="space-y-4">
                <SectionHeader
                  id="home-dashboards"
                  title="Tableros"
                  action={
                    <Button asChild variant="ghost" size="sm">
                      <Link href="/dashboards">
                        Ver todos
                        <ArrowRight aria-hidden="true" />
                      </Link>
                    </Button>
                  }
                />
                {dashboardsQuery.isLoading ? (
                  <ListSkeleton rows={3} />
                ) : dashboards.length === 0 ? (
                  <div className="rounded-2xl border border-dashed p-5 text-sm text-muted-foreground">
                    Aún no tienes tableros. Crea uno en{" "}
                    <Link href="/dashboards" className="font-semibold text-primary underline-offset-4 hover:underline">
                      Tableros
                    </Link>{" "}
                    para tener tus gráficos a mano.
                  </div>
                ) : (
                  <ul className="space-y-2">
                    {dashboards.slice(0, 3).map((d) => (
                      <li key={d.dashboard_id}>
                        <Link
                          href={`/dashboards/${d.dashboard_id}`}
                          className="group flex min-h-14 items-center gap-3 rounded-xl border bg-card px-4 py-3 transition hover:border-primary/40 hover:shadow-card"
                        >
                          <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-highlight-soft text-highlight-strong">
                            <BarChart3 className="h-[18px] w-[18px]" aria-hidden="true" />
                          </span>
                          <span className="min-w-0 flex-1">
                            <span className="block truncate font-semibold">{d.name}</span>
                            <span className="block text-xs text-muted-foreground first-letter:uppercase">Creado {formatRelative(d.created_at)}</span>
                          </span>
                          <ArrowRight className="h-4 w-4 shrink-0 text-muted-foreground transition group-hover:translate-x-0.5" aria-hidden="true" />
                        </Link>
                      </li>
                    ))}
                  </ul>
                )}
              </section>
            </aside>
          </div>
        </>
      )}
    </div>
  )
}
