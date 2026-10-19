"use client"

import Link from "next/link"
import { useEffect, useMemo, useRef, useState } from "react"
import { toast } from "sonner"
import { ArrowRight, MessageSquarePlus, MoreHorizontal, Search, Sparkles, Trash2, Wand2 } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import { DashboardPreview } from "@/components/dashboards/dashboard-preview"
import { ConfirmDialog } from "@/components/kit/confirm-dialog"
import { EmptyState, ErrorState } from "@/components/kit/empty-state"
import { Notice } from "@/components/kit/notice"
import { PageHeader } from "@/components/kit/page-header"
import { CardGridSkeleton } from "@/components/kit/skeletons"
import { DotsLoader } from "@/components/kit/dots"
import { useDashboards, useDeleteDashboard, useSuggestDashboards } from "@/hooks/use-dashboards"
import { usePageTitle } from "@/hooks/use-page-title"
import { useOrgTables } from "@/hooks/use-templates"
import { useChat } from "@/providers/chat-provider"
import { dashboardRequests, GENERIC_DASHBOARD_REQUEST } from "@/lib/dashboard-examples"
import { humanizeError } from "@/lib/errors"
import { formatDate, formatRelative, pluralize } from "@/lib/format"
import type { Dashboard } from "@/types/api"

/** Variación decorativa estable por tablero (no representa datos). */
function hueFor(id: string): number {
  let h = 0
  for (const ch of id) h = (h * 31 + ch.charCodeAt(0)) % 360
  return h
}

function Cover({ dashboard }: { dashboard: Dashboard }) {
  const rotate = hueFor(dashboard.dashboard_id) % 60
  const initial = dashboard.name.trim().charAt(0).toUpperCase() || "T"
  return (
    <div className="relative h-28 overflow-hidden rounded-t-2xl bg-primary-soft" aria-hidden="true">
      {dashboard.preview ? (
        <div className="absolute inset-x-4 bottom-3 top-3 pl-14">
          <DashboardPreview preview={dashboard.preview} />
        </div>
      ) : (
        <svg viewBox="0 0 200 100" preserveAspectRatio="xMidYMid slice" className="absolute inset-0 h-full w-full text-primary/15">
          <g transform={`rotate(${rotate - 30} 160 50)`}>
            <circle cx="160" cy="50" r="70" fill="none" stroke="currentColor" strokeWidth="1.5" />
            <circle cx="160" cy="50" r="46" fill="none" stroke="currentColor" strokeWidth="1" strokeDasharray="3 6" />
            <path d="M160 -24 L170 50 L160 124 L150 50 Z" fill="currentColor" />
            <path d="M86 50 L160 40 L234 50 L160 60 Z" fill="currentColor" />
          </g>
        </svg>
      )}
      <span className="absolute bottom-3 left-4 flex h-12 w-12 items-center justify-center rounded-xl bg-card font-display text-2xl font-semibold text-primary-strong shadow-card">
        {initial}
      </span>
    </div>
  )
}

const SOURCE_LABEL: Record<NonNullable<Dashboard["source"]>, string> = {
  assistant: "Lo creó el asistente",
  ai: "Sugerido para ti",
  rules: "Sugerido para ti",
}

export default function DashboardsPage() {
  usePageTitle("Tableros")
  const { ask } = useChat()
  const { data: dashboards = [], isLoading, isError, error, refetch, isFetching } = useDashboards()
  const tablesQuery = useOrgTables()
  const tables = useMemo(() => tablesQuery.data?.tables ?? [], [tablesQuery.data])
  const withRows = useMemo(() => tables.filter((t) => t.row_count > 0), [tables])
  const hasData = withRows.length > 0
  const deleteMutation = useDeleteDashboard()
  const suggest = useSuggestDashboards()

  const [toDelete, setToDelete] = useState<Dashboard | null>(null)
  const [query, setQuery] = useState("")
  const autoTried = useRef(false)

  const examples = useMemo(
    () =>
      dashboardRequests(
        withRows.map((t) => ({ name: t.display_name, rowCount: t.row_count, columns: t.columns_definition ?? [] })),
        3
      ),
    [withRows]
  )

  const sorted = useMemo(() => [...dashboards].sort((a, b) => b.created_at.localeCompare(a.created_at)), [dashboards])
  const visible = useMemo(() => {
    const q = query.trim().toLowerCase()
    return q ? sorted.filter((d) => `${d.name} ${d.description ?? ""}`.toLowerCase().includes(q)) : sorted
  }, [sorted, query])

  // «Tableros» nunca debe quedar vacío cuando ya hay datos: la primera vez que se abre vacío se piden
  // sugerencias al servidor (una sola vez por visita; el servidor no repite lo que ya sugirió ni lo que borraste).
  useEffect(() => {
    if (autoTried.current || isLoading || isError || tablesQuery.isLoading) return
    if (dashboards.length > 0 || !hasData) return
    autoTried.current = true
    suggest.mutate({ auto: true })
  }, [isLoading, isError, tablesQuery.isLoading, dashboards.length, hasData, suggest])

  function askForDashboard(request?: string, send = false) {
    ask(request ?? examples[0] ?? GENERIC_DASHBOARD_REQUEST, { send })
  }

  async function suggestNow() {
    try {
      const result = await suggest.mutateAsync({ auto: false })
      if (result.status === "created") {
        toast.success(
          result.dashboards.length === 1 ? "Armamos un tablero con tus datos" : `Armamos ${result.dashboards.length} tableros con tus datos`
        )
      } else if (result.status === "exists") {
        toast.info("Ya tienes los tableros sugeridos para estos datos", {
          description: "Si subes una hoja nueva o cambian las columnas, te proponemos otros.",
        })
      } else {
        toast.info("Por ahora no hay con qué armar un tablero", { description: "Sube una hoja con datos y vuelve a intentarlo." })
      }
    } catch (err) {
      const h = humanizeError(err, "save")
      toast.error(h.title, { description: h.description })
    }
  }

  async function confirmDelete() {
    if (!toDelete) return
    try {
      await deleteMutation.mutateAsync(toDelete.dashboard_id)
      toast.success(`Eliminamos «${toDelete.name}»`)
      setToDelete(null)
    } catch (err) {
      const h = humanizeError(err, "delete")
      toast.error(h.title, { description: h.description })
    }
  }

  const actions = hasData ? (
    <>
      <Button onClick={() => askForDashboard()}>
        <MessageSquarePlus aria-hidden="true" />
        Pídele un tablero al asistente
      </Button>
      <Button variant="outline" onClick={() => void suggestNow()} loading={suggest.isPending} loadingText="Buscando ideas…">
        <Wand2 aria-hidden="true" />
        Sugerir tableros
      </Button>
    </>
  ) : undefined

  const preparing = suggest.isPending && dashboards.length === 0

  return (
    <div className="space-y-8">
      <PageHeader
        eyebrow="Tableros"
        title="Tus tableros"
        description="Los arma el asistente con tus datos: pídele uno con tus palabras o deja que te sugiera. Cada vez que abres un tablero se calcula con tus datos de ese momento."
        actions={actions}
      />

      {dashboards.length > 6 && (
        <div className="relative max-w-sm">
          <Search className="pointer-events-none absolute left-3.5 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" aria-hidden="true" />
          <Input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Buscar un tablero"
            aria-label="Buscar un tablero"
            className="pl-10"
          />
        </div>
      )}

      {isLoading ? (
        <CardGridSkeleton count={3} className="[--auto-grid-min:18rem]" />
      ) : isError ? (
        <div className="surface">
          <ErrorState error={humanizeError(error, "load")} onRetry={() => void refetch()} retrying={isFetching} />
        </div>
      ) : dashboards.length === 0 ? (
        <div className="surface">
          {preparing ? (
            <div className="flex flex-col items-center gap-4 px-6 py-14 text-center" role="status" aria-live="polite">
              <DotsLoader size="lg" />
              <div className="space-y-1">
                <p className="font-display text-xl font-semibold">Estamos armando tableros con tus datos…</p>
                <p className="text-[15px] text-muted-foreground">Solo toma unos segundos.</p>
              </div>
            </div>
          ) : (
            <EmptyState
              illustration="chart"
              title={hasData ? "Pídele a tu asistente el primer tablero" : "Primero sube tus datos"}
              description={
                hasData
                  ? "Cuéntale qué quieres ver, con tus palabras, y lo arma con tus datos. Estos son pedidos de ejemplo con las columnas que ya subiste:"
                  : "Con tus datos cargados, el asistente arma los tableros por ti: tú solo dices qué quieres ver."
              }
              actions={
                hasData ? undefined : (
                  <Button asChild size="lg">
                    <Link href="/data">Subir mis datos</Link>
                  </Button>
                )
              }
            >
              {hasData && (
                <div className="flex w-full max-w-xl flex-col items-stretch gap-4">
                  {suggest.isError && (
                    <Notice tone="warning" title="No pudimos sugerir tableros ahora">
                      {humanizeError(suggest.error, "save").description}
                    </Notice>
                  )}
                  <ul className="flex flex-col gap-2" aria-label="Pedidos de ejemplo">
                    {(examples.length > 0 ? examples : [GENERIC_DASHBOARD_REQUEST]).map((example) => (
                      <li key={example}>
                        <button
                          type="button"
                          onClick={() => askForDashboard(example, true)}
                          className="group flex min-h-11 w-full items-center gap-3 rounded-xl border bg-card px-4 py-3 text-left text-[15px] font-medium transition hover:border-primary/50 hover:bg-primary-soft focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                        >
                          <Sparkles className="h-4 w-4 shrink-0 text-primary" aria-hidden="true" />
                          <span className="min-w-0 flex-1">{example}</span>
                          <ArrowRight className="h-4 w-4 shrink-0 text-muted-foreground transition group-hover:translate-x-0.5" aria-hidden="true" />
                        </button>
                      </li>
                    ))}
                  </ul>
                  <div className="flex flex-wrap justify-center gap-2">
                    <Button variant="outline" onClick={() => void suggestNow()} loading={suggest.isPending} loadingText="Buscando ideas…">
                      <Wand2 aria-hidden="true" />
                      Sugerir tableros
                    </Button>
                  </div>
                </div>
              )}
            </EmptyState>
          )}
        </div>
      ) : visible.length === 0 ? (
        <p className="rounded-2xl border border-dashed p-6 text-center text-muted-foreground">
          Ningún tablero coincide con «{query}».
        </p>
      ) : (
        <ul className="auto-grid gap-5 [--auto-grid-min:18rem]">
          {visible.map((d) => (
            <li key={d.dashboard_id}>
              <article className="surface group relative flex h-full flex-col transition duration-200 hover:-translate-y-0.5 hover:shadow-raised">
                <Cover dashboard={d} />
                <div className="flex flex-1 flex-col gap-2 p-5">
                  <div className="flex items-start gap-2">
                    <h2 className="min-w-0 flex-1 font-display text-xl font-semibold leading-tight">
                      <Link href={`/dashboards/${d.dashboard_id}`} className="after:absolute after:inset-0 focus-visible:outline-none group-focus-within:underline">
                        {d.name}
                      </Link>
                    </h2>
                    <DropdownMenu>
                      <DropdownMenuTrigger asChild>
                        <Button variant="ghost" size="icon-sm" className="relative z-10 -mr-2 -mt-1" aria-label={`Más opciones de ${d.name}`}>
                          <MoreHorizontal aria-hidden="true" />
                        </Button>
                      </DropdownMenuTrigger>
                      <DropdownMenuContent align="end" className="w-56">
                        <DropdownMenuItem onClick={() => setToDelete(d)} className="cursor-pointer text-danger-strong focus:bg-danger-soft focus:text-danger-strong">
                          <Trash2 className="h-4 w-4" aria-hidden="true" />
                          Eliminar tablero
                        </DropdownMenuItem>
                      </DropdownMenuContent>
                    </DropdownMenu>
                  </div>
                  {d.highlights && d.highlights.length > 0 ? (
                    <ul className="space-y-0.5 text-sm text-muted-foreground" aria-label="Qué muestra">
                      {d.highlights.map((h) => (
                        <li key={h} className="truncate">
                          {h}
                        </li>
                      ))}
                    </ul>
                  ) : (
                    <p className="line-clamp-2 text-sm text-muted-foreground">{d.description?.trim() || "Ábrelo para ver sus gráficos."}</p>
                  )}
                  <div className="mt-auto flex items-center justify-between gap-2 pt-3 text-xs text-muted-foreground">
                    <span title={formatDate(d.created_at, "long")} className="min-w-0 truncate first-letter:uppercase">
                      {d.source ? `${SOURCE_LABEL[d.source]} · ` : ""}
                      {formatRelative(d.created_at)}
                    </span>
                    <span className="inline-flex shrink-0 items-center gap-1 font-semibold text-primary">
                      Abrir
                      <ArrowRight className="h-3.5 w-3.5 transition group-hover:translate-x-0.5" aria-hidden="true" />
                    </span>
                  </div>
                </div>
              </article>
            </li>
          ))}
        </ul>
      )}

      {dashboards.length > 0 && (
        <p className="text-sm text-muted-foreground">{pluralize(dashboards.length, "tablero", "tableros")} en total.</p>
      )}

      <ConfirmDialog
        open={Boolean(toDelete)}
        onOpenChange={(o) => !o && setToDelete(null)}
        title={`¿Eliminar «${toDelete?.name ?? ""}»?`}
        description="Se borra el tablero. Tus datos no se tocan, y el asistente puede armarte otro cuando quieras."
        confirmLabel="Sí, eliminar"
        loading={deleteMutation.isPending}
        onConfirm={confirmDelete}
      />
    </div>
  )
}
