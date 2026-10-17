"use client"

import Link from "next/link"
import { useRouter } from "next/navigation"
import { useMemo, useState } from "react"
import { toast } from "sonner"
import { ArrowRight, Code2, MoreHorizontal, Plus, Search, Sparkles, Trash2 } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import { ConfirmDialog } from "@/components/kit/confirm-dialog"
import { EmptyState, ErrorState } from "@/components/kit/empty-state"
import { Field } from "@/components/kit/field"
import { PageHeader } from "@/components/kit/page-header"
import { CardGridSkeleton } from "@/components/kit/skeletons"
import { useCreateDashboard, useDashboards, useDeleteDashboard, useDownloadDashboardScript } from "@/hooks/use-dashboards"
import { usePageTitle } from "@/hooks/use-page-title"
import { useOrgTables } from "@/hooks/use-templates"
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
      <svg viewBox="0 0 200 100" preserveAspectRatio="xMidYMid slice" className="absolute inset-0 h-full w-full text-primary/15">
        <g transform={`rotate(${rotate - 30} 160 50)`}>
          <circle cx="160" cy="50" r="70" fill="none" stroke="currentColor" strokeWidth="1.5" />
          <circle cx="160" cy="50" r="46" fill="none" stroke="currentColor" strokeWidth="1" strokeDasharray="3 6" />
          <path d="M160 -24 L170 50 L160 124 L150 50 Z" fill="currentColor" />
          <path d="M86 50 L160 40 L234 50 L160 60 Z" fill="currentColor" />
        </g>
      </svg>
      <span className="absolute bottom-3 left-4 flex h-12 w-12 items-center justify-center rounded-xl bg-card font-display text-2xl font-semibold text-primary-strong shadow-card">
        {initial}
      </span>
    </div>
  )
}

export default function DashboardsPage() {
  usePageTitle("Tableros")
  const router = useRouter()
  const { data: dashboards = [], isLoading, isError, error, refetch, isFetching } = useDashboards()
  const tablesQuery = useOrgTables()
  const hasData = (tablesQuery.data?.tables ?? []).some((t) => t.row_count > 0)
  const createMutation = useCreateDashboard()
  const deleteMutation = useDeleteDashboard()
  const downloadMutation = useDownloadDashboardScript()

  const [open, setOpen] = useState(false)
  const [name, setName] = useState("")
  const [description, setDescription] = useState("")
  const [nameError, setNameError] = useState<string | null>(null)
  const [toDelete, setToDelete] = useState<Dashboard | null>(null)
  const [query, setQuery] = useState("")

  const sorted = useMemo(() => [...dashboards].sort((a, b) => b.created_at.localeCompare(a.created_at)), [dashboards])
  const visible = useMemo(() => {
    const q = query.trim().toLowerCase()
    return q ? sorted.filter((d) => `${d.name} ${d.description ?? ""}`.toLowerCase().includes(q)) : sorted
  }, [sorted, query])

  async function create() {
    const trimmed = name.trim()
    if (trimmed.length < 2) {
      setNameError("Escribe un nombre de al menos 2 letras, por ejemplo «Ventas del mes».")
      return
    }
    setNameError(null)
    try {
      const created = await createMutation.mutateAsync({ name: trimmed, description: description.trim() || undefined })
      toast.success(`Creamos «${trimmed}»`, { description: "Le pusimos gráficos a partir de tus datos." })
      setOpen(false)
      setName("")
      setDescription("")
      const id = created?.dashboard_id ?? created?.id
      if (id) router.push(`/dashboards/${id}`)
    } catch (err) {
      const h = humanizeError(err, "save")
      setNameError(`${h.title}. ${h.description}`)
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

  async function download(d: Dashboard) {
    try {
      await downloadMutation.mutateAsync({ id: d.dashboard_id })
    } catch (err) {
      const h = humanizeError(err, "download")
      toast.error(h.title, { description: h.description })
    }
  }

  const newButton = (
    <Button onClick={() => setOpen(true)}>
      <Plus aria-hidden="true" />
      Nuevo tablero
    </Button>
  )

  return (
    <div className="space-y-8">
      <PageHeader
        eyebrow="Tableros"
        title="Tus tableros"
        description="Un tablero reúne varios gráficos de tus datos en una sola página. Cada vez que lo abres se calcula con tus datos de ese momento."
        actions={dashboards.length > 0 ? newButton : undefined}
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
          <EmptyState
            illustration="chart"
            title="Todavía no tienes tableros"
            description={
              hasData
                ? "Crea uno y lo llenamos con gráficos de tus datos automáticamente. Luego lo abres cuando quieras."
                : "Primero sube tus datos; después crea un tablero y lo llenamos con gráficos automáticamente."
            }
            actions={
              hasData ? (
                <Button size="lg" onClick={() => setOpen(true)}>
                  <Sparkles aria-hidden="true" />
                  Crear mi primer tablero
                </Button>
              ) : (
                <Button asChild size="lg">
                  <Link href="/data">Subir mis datos</Link>
                </Button>
              )
            }
          />
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
                      <DropdownMenuContent align="end" className="w-64">
                        <DropdownMenuItem onClick={() => void download(d)} className="cursor-pointer">
                          <Code2 className="h-4 w-4" aria-hidden="true" />
                          Descargar su código (avanzado)
                        </DropdownMenuItem>
                        <DropdownMenuSeparator />
                        <DropdownMenuItem onClick={() => setToDelete(d)} className="cursor-pointer text-danger-strong focus:bg-danger-soft focus:text-danger-strong">
                          <Trash2 className="h-4 w-4" aria-hidden="true" />
                          Eliminar tablero
                        </DropdownMenuItem>
                      </DropdownMenuContent>
                    </DropdownMenu>
                  </div>
                  <p className="line-clamp-2 text-sm text-muted-foreground">
                    {d.description?.trim() || "Ábrelo para ver sus gráficos."}
                  </p>
                  <div className="mt-auto flex items-center justify-between pt-3 text-xs text-muted-foreground">
                    <span title={formatDate(d.created_at, "long")} className="first-letter:uppercase">
                      Creado {formatRelative(d.created_at)}
                    </span>
                    <span className="inline-flex items-center gap-1 font-semibold text-primary">
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

      <Dialog open={open} onOpenChange={(o) => !createMutation.isPending && setOpen(o)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Nuevo tablero</DialogTitle>
            <DialogDescription>
              Ponle un nombre y lo llenamos con gráficos a partir de tus datos. Puedes eliminarlo cuando quieras.
            </DialogDescription>
          </DialogHeader>
          <form
            className="space-y-4"
            onSubmit={(e) => {
              e.preventDefault()
              void create()
            }}
          >
            <Field label="Nombre" error={nameError ?? undefined}>
              {({ id, describedBy, invalid }) => (
                <Input
                  id={id}
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  placeholder="Ej.: Ventas del mes"
                  aria-describedby={describedBy}
                  aria-invalid={invalid}
                  maxLength={120}
                  autoFocus
                />
              )}
            </Field>
            <Field label="Para qué es" optional hint="Una frase que te ayude a recordarlo.">
              {({ id, describedBy }) => (
                <Input
                  id={id}
                  value={description}
                  onChange={(e) => setDescription(e.target.value)}
                  placeholder="Ej.: Cómo van las ventas por sede"
                  aria-describedby={describedBy}
                  maxLength={240}
                />
              )}
            </Field>
            <DialogFooter>
              <Button type="button" variant="outline" onClick={() => setOpen(false)} disabled={createMutation.isPending}>
                Cancelar
              </Button>
              <Button type="submit" loading={createMutation.isPending} loadingText="Creando…">
                Crear tablero
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>

      <ConfirmDialog
        open={Boolean(toDelete)}
        onOpenChange={(o) => !o && setToDelete(null)}
        title={`¿Eliminar «${toDelete?.name ?? ""}»?`}
        description="Se borra el tablero y su configuración. Tus datos no se tocan."
        confirmLabel="Sí, eliminar"
        loading={deleteMutation.isPending}
        onConfirm={confirmDelete}
      />
    </div>
  )
}
