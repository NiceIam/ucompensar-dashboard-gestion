"use client"

import { useMemo, useRef, useState } from "react"
import { toast } from "sonner"
import { Download, RefreshCw } from "lucide-react"
import { Button } from "@/components/ui/button"
import { PageHeader, SectionHeader } from "@/components/kit/page-header"
import { ConfirmDialog } from "@/components/kit/confirm-dialog"
import { ErrorState } from "@/components/kit/empty-state"
import { Journey } from "@/components/kit/journey"
import { CardGridSkeleton } from "@/components/kit/skeletons"
import { AdvancedSettings } from "@/components/data/advanced-settings"
import { DataCard } from "@/components/data/data-card"
import { DataViewer } from "@/components/data/data-viewer"
import { EditTableDialog } from "@/components/data/edit-table-dialog"
import { UploadFlow } from "@/components/data/upload-flow"
import { downloads, useDeleteTable } from "@/hooks/use-data"
import { useOrgTables, type OrgTable } from "@/hooks/use-templates"
import { useChat } from "@/providers/chat-provider"
import { usePageTitle } from "@/hooks/use-page-title"
import { humanizeError } from "@/lib/errors"
import { formatNumber, pluralize } from "@/lib/format"
import { questionsForTable } from "@/lib/suggestions"

async function runDownload(task: () => Promise<void>, success: string) {
  try {
    await task()
    toast.success(success)
  } catch (err) {
    const h = humanizeError(err, "download")
    toast.error(h.title, { description: h.description })
  }
}

export default function DataPage() {
  const { data, isLoading, isError, error, refetch, isFetching } = useOrgTables()
  const tables = useMemo(() => data?.tables ?? [], [data])
  const withRows = useMemo(() => tables.filter((t) => t.row_count > 0).sort((a, b) => b.row_count - a.row_count), [tables])
  const empties = useMemo(() => tables.filter((t) => t.row_count === 0), [tables])
  const totalRows = withRows.reduce((s, t) => s + t.row_count, 0)
  const hasData = withRows.length > 0

  const { ask } = useChat()
  const deleteTable = useDeleteTable()
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [editing, setEditing] = useState<OrgTable | null>(null)
  const [deleting, setDeleting] = useState<OrgTable | null>(null)
  const viewerRef = useRef<HTMLDivElement>(null)
  const selected = tables.find((t) => t.id === selectedId) ?? null

  usePageTitle("Mis datos")

  function view(tableId: string) {
    setSelectedId(tableId)
    requestAnimationFrame(() => viewerRef.current?.scrollIntoView({ behavior: "smooth", block: "start" }))
  }

  async function confirmDelete() {
    if (!deleting) return
    try {
      await deleteTable.mutateAsync(deleting.id)
      toast.success(`Eliminamos «${deleting.display_name}»`)
      if (selectedId === deleting.id) setSelectedId(null)
      setDeleting(null)
    } catch (err) {
      const h = humanizeError(err, "delete")
      toast.error(h.title, { description: h.description })
    }
  }

  const cardProps = (t: OrgTable) => ({
    table: t,
    selected: t.id === selectedId,
    onView: () => (t.id === selectedId ? setSelectedId(null) : view(t.id)),
    onAsk: () =>
      ask(
        questionsForTable({ name: t.display_name, rowCount: t.row_count, columns: t.columns_definition ?? [] })[0] ??
          `Hazme un resumen de ${t.display_name}`
      ),
    onRename: () => setEditing(t),
    onDelete: () => setDeleting(t),
    onDownloadTemplate: () => runDownload(() => downloads.tableTemplate(t.id, t.table_name), `Plantilla de «${t.display_name}» descargada`),
    onExport: () => runDownload(() => downloads.tableExport(t.id, t.table_name), `Datos de «${t.display_name}» descargados`),
  })

  return (
    <div className="space-y-10">
      <PageHeader
        eyebrow="Mis datos"
        title={isLoading ? "Tu información" : hasData ? "Tu información" : "Empecemos por tus datos"}
        description={
          hasData
            ? "Aquí vive todo lo que has subido. Agrega más archivos cuando quieras: los organizamos solos."
            : "Sube un Excel, CSV o JSON y lo organizamos por ti. Luego puedes preguntarle lo que quieras."
        }
      />

      <UploadFlow tables={tables} hero={!isLoading && !hasData} onViewTable={view} onAsk={(q) => ask(q)} />

      {!isLoading && !hasData && !isError && <Journey />}

      {/* Tus datos */}
      {(isLoading || hasData || isError) && (
        <section aria-labelledby="your-data" className="space-y-5">
          <SectionHeader
            id="your-data"
            title="Tus datos"
            description={
              isLoading
                ? "Cargando…"
                : hasData
                  ? `${pluralize(withRows.length, "hoja", "hojas")} · ${formatNumber(totalRows)} filas en total`
                  : undefined
            }
            action={
              hasData ? (
                <Button variant="ghost" size="sm" onClick={() => void refetch()} disabled={isFetching} aria-label="Actualizar la lista">
                  <RefreshCw className={isFetching ? "animate-spin" : ""} aria-hidden="true" />
                  Actualizar
                </Button>
              ) : undefined
            }
          />
          {isLoading ? (
            <CardGridSkeleton count={3} />
          ) : isError ? (
            <div className="surface">
              <ErrorState error={humanizeError(error, "load")} onRetry={() => void refetch()} retrying={isFetching} />
            </div>
          ) : (
            <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
              {withRows.map((t) => (
                <DataCard key={t.id} {...cardProps(t)} />
              ))}
            </div>
          )}
        </section>
      )}

      {selected && (
        <div ref={viewerRef} className="scroll-mt-24">
          <DataViewer key={selected.id} table={selected} onClose={() => setSelectedId(null)} />
        </div>
      )}

      {/* Hojas preparadas sin filas (por ejemplo, las del tipo de negocio) */}
      {!isLoading && empties.length > 0 && (
        <section aria-labelledby="ready-to-fill" className="space-y-5">
          <SectionHeader
            id="ready-to-fill"
            title="Listas para llenar"
            description="Las preparamos según tu tipo de negocio. Descarga la plantilla, llénala en Excel y súbela arriba."
            action={
              <Button
                variant="outline"
                size="sm"
                onClick={() => runDownload(() => downloads.allTemplates(), "Plantilla completa descargada")}
              >
                <Download aria-hidden="true" />
                Plantilla con todas
              </Button>
            }
          />
          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
            {empties.map((t) => (
              <DataCard key={t.id} {...cardProps(t)} />
            ))}
          </div>
        </section>
      )}

      {!isLoading && <AdvancedSettings tables={tables} />}

      <EditTableDialog table={editing} open={Boolean(editing)} onOpenChange={(o) => !o && setEditing(null)} />

      <ConfirmDialog
        open={Boolean(deleting)}
        onOpenChange={(o) => !o && setDeleting(null)}
        title={`¿Eliminar «${deleting?.display_name ?? ""}»?`}
        description={
          deleting && deleting.row_count > 0
            ? `Se borrarán para siempre sus ${formatNumber(deleting.row_count)} filas. El asistente ya no podrá consultarlas.`
            : "Se borrará esta hoja vacía. Podrás volver a crearla subiendo un archivo."
        }
        confirmLabel="Sí, eliminar"
        loading={deleteTable.isPending}
        onConfirm={confirmDelete}
      />
    </div>
  )
}
