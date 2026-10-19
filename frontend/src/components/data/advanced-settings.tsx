"use client"

import { useState } from "react"
import { toast } from "sonner"
import { ChevronDown, Download, FileSpreadsheet, FileText, History, SlidersHorizontal, Trash2 } from "lucide-react"
import { Button } from "@/components/ui/button"
import { ConfirmDialog } from "@/components/kit/confirm-dialog"
import { StatusBadge } from "@/components/kit/status-badge"
import { ListSkeleton } from "@/components/kit/skeletons"
import { downloads } from "@/hooks/use-data"
import { useDeleteFile, useFiles } from "@/hooks/use-files"
import type { OrgTable } from "@/hooks/use-templates"
import { KIND_INFO, columnKind, columnLabel } from "@/lib/data-vocabulary"
import { humanizeError } from "@/lib/errors"
import { formatDate, formatFileSize, pluralize } from "@/lib/format"
import { cn } from "@/lib/utils"
import type { UploadedFile } from "@/types/api"

const FILE_STATUS: Record<UploadedFile["status"], { label: string; tone: "success" | "info" | "danger" | "neutral" }> = {
  ready: { label: "Listo", tone: "success" },
  processing: { label: "Procesando", tone: "info" },
  uploaded: { label: "Recibido", tone: "neutral" },
  error: { label: "Con error", tone: "danger" },
}

function FileHistory() {
  const { data: files = [], isLoading, isError } = useFiles()
  const remove = useDeleteFile()
  const [target, setTarget] = useState<UploadedFile | null>(null)

  async function confirm() {
    if (!target) return
    try {
      await remove.mutateAsync(target.id)
      toast.success("Archivo quitado del historial", { description: "Tus datos guardados siguen intactos." })
      setTarget(null)
    } catch (err) {
      const h = humanizeError(err, "delete")
      toast.error(h.title, { description: h.description })
    }
  }

  if (isLoading) return <ListSkeleton rows={2} />
  if (isError) return <p className="text-sm text-muted-foreground">No pudimos cargar el historial ahora mismo.</p>
  if (files.length === 0)
    return (
      <p className="text-sm text-muted-foreground">
        Todavía no hay archivos en el historial. (Los archivos subidos desde esta página se guardan directo en tus hojas.)
      </p>
    )

  return (
    <>
      <ul className="divide-y rounded-xl border bg-card">
        {files.map((f) => {
          const status = FILE_STATUS[f.status] ?? FILE_STATUS.uploaded
          const Icon = f.file_type === "xlsx" ? FileSpreadsheet : FileText
          return (
            <li key={f.id} className="flex items-center gap-3 px-4 py-3">
              <Icon className="h-5 w-5 shrink-0 text-muted-foreground" aria-hidden="true" />
              <div className="min-w-0 flex-1">
                <p className="truncate text-sm font-semibold" title={f.original_name}>
                  {f.original_name}
                </p>
                <p className="text-xs text-muted-foreground">
                  {formatDate(f.created_at)}
                  {f.row_count ? ` · ${pluralize(f.row_count, "fila", "filas")}` : ""}
                  {f.size_bytes ? ` · ${formatFileSize(f.size_bytes)}` : ""}
                </p>
              </div>
              <StatusBadge tone={status.tone} className="hidden sm:inline-flex">
                {status.label}
              </StatusBadge>
              <Button variant="ghost" size="icon-sm" onClick={() => setTarget(f)} aria-label={`Quitar ${f.original_name} del historial`}>
                <Trash2 aria-hidden="true" />
              </Button>
            </li>
          )
        })}
      </ul>
      <ConfirmDialog
        open={Boolean(target)}
        onOpenChange={(o) => !o && setTarget(null)}
        title="¿Quitar este archivo del historial?"
        description="Solo desaparece de esta lista. Los datos que ya se guardaron en tus hojas NO se borran; para eso, elimina la hoja desde su menú."
        confirmLabel="Quitar del historial"
        loading={remove.isPending}
        onConfirm={confirm}
      />
    </>
  )
}

/** Detalles técnicos y archivos anteriores, escondidos por defecto y explicados en lenguaje claro. */
export function AdvancedSettings({ tables }: { tables: OrgTable[] }) {
  const [open, setOpen] = useState(false)
  const [downloading, setDownloading] = useState(false)

  async function downloadAll() {
    setDownloading(true)
    try {
      await downloads.allTemplates()
      toast.success("Plantilla descargada", { description: "Es un Excel con una hoja por cada uno de tus datos." })
    } catch (err) {
      const h = humanizeError(err, "download")
      toast.error(h.title, { description: h.description })
    } finally {
      setDownloading(false)
    }
  }

  return (
    <section aria-labelledby="advanced-title" className="rounded-2xl border border-dashed">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        aria-controls="advanced-panel"
        className="flex min-h-14 w-full items-center gap-3 px-5 py-3 text-left"
      >
        <SlidersHorizontal className="h-5 w-5 text-muted-foreground" aria-hidden="true" />
        <span className="flex-1">
          <span id="advanced-title" className="block font-semibold">
            Ajustes avanzados
          </span>
          <span className="block text-sm text-muted-foreground">Plantillas, archivos anteriores y detalles técnicos. No los necesitas para el día a día.</span>
        </span>
        <ChevronDown className={cn("h-5 w-5 shrink-0 text-muted-foreground transition-transform", open && "rotate-180")} aria-hidden="true" />
      </button>

      {open && (
        <div id="advanced-panel" className="space-y-8 border-t border-dashed px-5 pb-6 pt-5">
          <div className="space-y-2">
            <h3 className="font-semibold">Plantilla de Excel</h3>
            <p className="text-sm text-muted-foreground">
              Un Excel con una hoja por cada uno de tus datos y sus columnas, listo para llenar y volver a subir.
            </p>
            <Button variant="outline" onClick={downloadAll} loading={downloading} disabled={tables.length === 0}>
              <Download aria-hidden="true" />
              Descargar plantilla completa
            </Button>
          </div>

          <div className="space-y-3">
            <h3 className="flex items-center gap-2 font-semibold">
              <History className="h-4 w-4 text-muted-foreground" aria-hidden="true" />
              Historial de archivos
            </h3>
            <FileHistory />
          </div>

          {tables.length > 0 && (
            <div className="space-y-3">
              <h3 className="font-semibold">Detalle técnico de las columnas</h3>
              <p className="text-sm text-muted-foreground">
                Cómo se guarda cada columna por dentro. Útil si alguien de soporte te lo pide.
              </p>
              <div className="space-y-4">
                {tables.map((t) => (
                  <details key={t.id} className="rounded-xl border bg-card">
                    <summary className="flex min-h-11 cursor-pointer items-center justify-between px-4 py-2 text-sm font-semibold">
                      {t.display_name}
                      <span className="font-mono text-xs font-normal text-muted-foreground">{t.table_name}</span>
                    </summary>
                    <div className="relative overflow-x-auto border-t">
                      <table className="w-full text-sm">
                        <thead className="bg-muted/50 text-left">
                          <tr>
                            <th scope="col" className="px-4 py-2 font-semibold">Columna</th>
                            <th scope="col" className="px-4 py-2 font-semibold">Nombre interno</th>
                            <th scope="col" className="px-4 py-2 font-semibold">Se entiende como</th>
                            <th scope="col" className="px-4 py-2 font-semibold">Tipo técnico</th>
                          </tr>
                        </thead>
                        <tbody>
                          {(t.columns_definition ?? []).map((c) => (
                            <tr key={c.name} className="border-t">
                              <td className="px-4 py-2">{columnLabel(c)}</td>
                              <td className="px-4 py-2 font-mono text-xs">{c.name}</td>
                              <td className="px-4 py-2">{KIND_INFO[columnKind(c)].label}</td>
                              <td className="px-4 py-2 font-mono text-xs">{c.type}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </details>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </section>
  )
}
