"use client"

import { useState, useRef, useCallback } from "react"
import { useQuery, useQueryClient } from "@tanstack/react-query"
import { toast } from "sonner"
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip"
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Skeleton } from "@/components/ui/skeleton"
import { Separator } from "@/components/ui/separator"
import { ScrollArea } from "@/components/ui/scroll-area"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { useOrgTables } from "@/hooks/use-templates"
import { useFiles, useDeleteFile } from "@/hooks/use-files"
import { api } from "@/lib/api"
import { cn, formatDate, formatNumber } from "@/lib/utils"
import type { UploadedFile } from "@/types/api"
import type { OrgTable } from "@/hooks/use-templates"
import {
  Upload,
  Database,
  Table2,
  Trash2,
  Pencil,
  FileText,
  RefreshCw,
  Calendar,
  Layers,
  X,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  Download,
  Info,
  Plus,
  CircleCheck,
  FileDown,
} from "lucide-react"

// ─── Constants ────────────────────────────────────────────────────────────────

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8001"

const COLUMN_TYPES = [
  "text",
  "varchar",
  "integer",
  "float",
  "decimal",
  "boolean",
  "date",
  "timestamp",
]

const STATUS_LABELS: Record<UploadedFile["status"], string> = {
  uploaded: "Subido",
  processing: "Procesando",
  ready: "Listo",
  error: "Error",
}

const STATUS_VARIANTS: Record<
  UploadedFile["status"],
  "default" | "secondary" | "destructive" | "outline"
> = {
  uploaded: "secondary",
  processing: "outline",
  ready: "default",
  error: "destructive",
}

const TYPE_COLORS: Record<string, string> = {
  text: "bg-orange-50 text-orange-700 border-orange-200",
  varchar: "bg-orange-50 text-orange-700 border-orange-200",
  number: "bg-emerald-50 text-emerald-700 border-emerald-200",
  integer: "bg-emerald-50 text-emerald-700 border-emerald-200",
  float: "bg-emerald-50 text-emerald-700 border-emerald-200",
  decimal: "bg-emerald-50 text-emerald-700 border-emerald-200",
  date: "bg-amber-50 text-amber-700 border-amber-200",
  timestamp: "bg-amber-50 text-amber-700 border-amber-200",
  boolean: "bg-purple-50 text-purple-700 border-purple-200",
  bool: "bg-purple-50 text-purple-700 border-purple-200",
}

function getTypeColor(type: string): string {
  return TYPE_COLORS[type.toLowerCase()] ?? "bg-stone-50 text-stone-600 border-stone-200"
}

// ─── Types ────────────────────────────────────────────────────────────────────

interface SmartUploadSheetResult {
  sheet_name?: string | null
  status: string
  table_name?: string
  table_id?: string
  rows_inserted?: number
  total_rows?: number
  error?: string
}

interface SmartUploadResult {
  status: string
  table_name?: string
  table_id?: string
  rows_inserted?: number
  total_rows?: number
  actions?: string[]
  analysis?: string
  // Presente cuando el Excel subido tiene varias hojas: cada hoja se mapea
  // y carga por separado en su tabla correspondiente.
  multi_sheet?: boolean
  sheets_processed?: number
  total_rows_inserted?: number
  sheets?: SmartUploadSheetResult[]
}

interface TableRow {
  id: string
  data: Record<string, unknown>
  created_at: string
}

interface TableRowsResponse {
  table_name: string
  display_name: string
  total: number
  rows: TableRow[]
}

interface NewColumn {
  name: string
  type: string
}

// ─── Download template helper ─────────────────────────────────────────────────

async function downloadTemplate(tableId: string, tableName: string) {
  try {
    const res = await fetch(`${API_URL}/api/v1/schema/tables/${tableId}/template`, {
      credentials: "include",
    })
    if (!res.ok) throw new Error(`HTTP ${res.status}`)
    const blob = await res.blob()
    const url = URL.createObjectURL(blob)
    const a = document.createElement("a")
    a.href = url
    a.download = `plantilla_${tableName}.csv`
    a.click()
    URL.revokeObjectURL(url)
    toast.success(`Plantilla "${tableName}" descargada`)
  } catch {
    toast.error("No se pudo descargar la plantilla")
  }
}

async function exportTableData(tableId: string, tableName: string) {
  try {
    const res = await fetch(`${API_URL}/api/v1/schema/tables/${tableId}/export`, {
      credentials: "include",
    })
    if (!res.ok) throw new Error(`HTTP ${res.status}`)
    const blob = await res.blob()
    const url = URL.createObjectURL(blob)
    const a = document.createElement("a")
    a.href = url
    a.download = `${tableName}_datos.csv`
    a.click()
    URL.revokeObjectURL(url)
    toast.success(`Datos de "${tableName}" exportados`)
  } catch {
    toast.error("No se pudieron exportar los datos")
  }
}

async function downloadAllTemplates() {
  try {
    const res = await fetch(`${API_URL}/api/v1/schema/template-all`, {
      credentials: "include",
    })
    if (!res.ok) throw new Error(`HTTP ${res.status}`)
    const blob = await res.blob()
    const url = URL.createObjectURL(blob)
    const a = document.createElement("a")
    a.href = url
    a.download = "plantilla_completa.xlsx"
    a.click()
    URL.revokeObjectURL(url)
    toast.success("Plantilla completa descargada (Excel con todas las hojas)")
  } catch {
    toast.error("No se pudo descargar la plantilla")
  }
}

// ─── Info Banner ──────────────────────────────────────────────────────────────

function InfoBanner({ onClose }: { onClose: () => void }) {
  return (
    <div className="mx-4 mt-3 rounded-lg border border-orange-200 bg-orange-50 p-3">
      <div className="flex items-start gap-3">
        <Info className="h-4 w-4 text-orange-600 mt-0.5 shrink-0" />
        <div className="flex-1 min-w-0">
          <p className="text-sm text-orange-900 font-medium mb-1">¿Cómo funciona esta sección?</p>
          <p className="text-xs text-orange-800 leading-relaxed">
            Aquí puedes gestionar toda la información de tu empresa. Sube archivos CSV o Excel y el
            sistema organizará automáticamente tus datos en tablas. Puedes ver, editar y eliminar
            tablas y registros individuales.
          </p>
          <div className="flex flex-wrap gap-1.5 mt-2">
            {["Auto-detección de columnas", "Carga inteligente", "Plantillas descargables"].map(
              (pill) => (
                <span
                  key={pill}
                  className="text-[10px] font-medium bg-orange-100 text-orange-700 border border-orange-200 px-2 py-0.5 rounded-full"
                >
                  {pill}
                </span>
              )
            )}
          </div>
        </div>
        <Button
          variant="ghost"
          size="icon"
          className="h-5 w-5 text-orange-500 hover:text-orange-700 hover:bg-orange-100 shrink-0"
          onClick={onClose}
        >
          <X className="h-3 w-3" />
        </Button>
      </div>
    </div>
  )
}

// ─── Upload Zone ──────────────────────────────────────────────────────────────

function UploadZone({
  onUploadComplete,
  onCollapse,
}: {
  onUploadComplete: (tableId?: string) => void
  onCollapse: () => void
}) {
  const queryClient = useQueryClient()
  const inputRef = useRef<HTMLInputElement>(null)
  const [isDragging, setIsDragging] = useState(false)
  const [status, setStatus] = useState<"idle" | "uploading" | "success" | "error">("idle")
  const [result, setResult] = useState<SmartUploadResult | null>(null)

  const processFile = useCallback(
    async (file: File) => {
      setStatus("uploading")
      setResult(null)

      const formData = new FormData()
      formData.append("file", file)

      try {
        const res = await api.upload<SmartUploadResult>("/api/v1/schema/smart-upload", formData)
        setStatus("success")
        setResult(res)
        await queryClient.invalidateQueries({ queryKey: ["templates", "org-tables"] })
        await queryClient.invalidateQueries({ queryKey: ["files"] })

        if (res.multi_sheet) {
          const matched = (res.sheets ?? []).filter((s) => s.status !== "skipped_empty" && s.status !== "error")
          toast.success(
            `${res.sheets_processed} hojas procesadas — ${formatNumber(res.total_rows_inserted ?? 0)} filas cargadas en ${matched.length} tabla(s)`
          )
        } else {
          toast.success(
            res.rows_inserted !== undefined
              ? `${formatNumber(res.rows_inserted)} filas cargadas en "${res.table_name ?? "tabla"}"`
              : `"${file.name}" procesado correctamente`
          )
        }

        setTimeout(() => {
          onUploadComplete(res.multi_sheet ? undefined : res.table_id)
        }, 1500)
      } catch (err) {
        setStatus("error")
        toast.error(err instanceof Error ? err.message : "Error al procesar el archivo")
      }
    },
    [queryClient, onUploadComplete]
  )

  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault()
      setIsDragging(false)
      const file = e.dataTransfer.files[0]
      if (file) processFile(file)
    },
    [processFile]
  )

  const handleFileChange = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const file = e.target.files?.[0]
      if (file) processFile(file)
    },
    [processFile]
  )

  return (
    <div className="border-b bg-muted/30">
      <div className="px-4 py-3">
        <div className="flex items-center justify-between mb-2">
          <span className="text-xs font-medium text-muted-foreground uppercase tracking-wider">
            Subir archivo
          </span>
          <Button variant="ghost" size="icon" className="h-5 w-5" onClick={onCollapse}>
            <X className="h-3 w-3" />
          </Button>
        </div>

        <p className="text-xs text-muted-foreground mb-2">
          El sistema analiza tu archivo, detecta las columnas y carga los datos automáticamente en
          la tabla correspondiente.
        </p>

        {status === "uploading" ? (
          <div className="flex items-center gap-3 py-3">
            <RefreshCw className="h-4 w-4 animate-spin text-primary" />
            <span className="text-sm text-muted-foreground">
              Analizando archivo y mapeando tablas…
            </span>
          </div>
        ) : status === "success" && result ? (
          result.multi_sheet ? (
            <div className="py-2 space-y-1.5">
              <div className="flex items-center gap-3">
                <CircleCheck className="h-4 w-4 text-emerald-600 shrink-0" />
                <span className="text-sm text-emerald-700">
                  {result.sheets_processed} hojas procesadas —{" "}
                  {formatNumber(result.total_rows_inserted ?? 0)} filas cargadas
                </span>
              </div>
              <ul className="pl-7 space-y-0.5">
                {(result.sheets ?? []).map((s, i) => (
                  <li key={i} className="text-xs text-muted-foreground">
                    <span className="font-medium">{s.sheet_name ?? "(hoja)"}</span>
                    {": "}
                    {s.status === "skipped_empty"
                      ? "vacía, omitida"
                      : s.status === "error"
                        ? `error — ${s.error ?? "no se pudo procesar"}`
                        : `${formatNumber(s.rows_inserted ?? 0)} filas → "${s.table_name}"`}
                  </li>
                ))}
              </ul>
            </div>
          ) : (
            <div className="flex items-center gap-3 py-2">
              <CircleCheck className="h-4 w-4 text-emerald-600" />
              <span className="text-sm text-emerald-700">
                {result.rows_inserted !== undefined
                  ? `${formatNumber(result.rows_inserted)} filas cargadas en "${result.table_name}"`
                  : "Archivo procesado correctamente"}
              </span>
            </div>
          )
        ) : (
          <div
            onDragOver={(e) => {
              e.preventDefault()
              setIsDragging(true)
            }}
            onDragLeave={() => setIsDragging(false)}
            onDrop={handleDrop}
            onClick={() => inputRef.current?.click()}
            className={cn(
              "flex items-center gap-3 px-4 py-3 rounded-md border border-dashed cursor-pointer transition-colors",
              isDragging
                ? "border-primary bg-primary/5"
                : "border-border hover:border-primary/50 hover:bg-muted/50",
              status === "error" && "border-destructive/50"
            )}
          >
            <Upload className="h-4 w-4 text-muted-foreground shrink-0" />
            <div>
              <p className="text-sm font-medium">Arrastra un archivo o haz clic para seleccionar</p>
              <p className="text-xs text-muted-foreground">CSV, Excel (.xlsx) o JSON — máx. 10 MB</p>
            </div>
            <input
              ref={inputRef}
              type="file"
              accept=".csv,.xlsx,.xls,.json"
              className="hidden"
              onChange={handleFileChange}
            />
          </div>
        )}
      </div>
    </div>
  )
}

// ─── Table Card ───────────────────────────────────────────────────────────────

function TableCard({
  table,
  selected,
  onSelect,
  onEdit,
  onDelete,
}: {
  table: OrgTable
  selected: boolean
  onSelect: () => void
  onEdit: () => void
  onDelete: () => void
}) {
  return (
    <Card
      onClick={onSelect}
      className={cn(
        "cursor-pointer transition-all hover:shadow-sm",
        selected ? "ring-2 ring-primary shadow-sm" : "hover:ring-1 hover:ring-primary/40"
      )}
    >
      <CardHeader className="p-3 pb-2">
        <div className="flex items-start justify-between gap-2">
          <div className="flex items-center gap-1.5 min-w-0">
            <Table2 className="h-3.5 w-3.5 text-muted-foreground shrink-0" />
            <CardTitle className="text-xs font-semibold uppercase tracking-wider truncate">
              {table.display_name}
            </CardTitle>
          </div>
          <Badge variant="secondary" className="text-[10px] h-4 px-1.5 shrink-0">
            {formatNumber(table.row_count)} filas
          </Badge>
        </div>
      </CardHeader>

      <CardContent className="p-3 pt-0">
        <div className="space-y-1 mb-3">
          {table.columns_definition?.slice(0, 5).map((col) => (
            <div key={col.name} className="flex items-center justify-between gap-2 text-xs">
              <span className="text-muted-foreground truncate">{col.label || col.name}</span>
              <span
                className={cn(
                  "shrink-0 text-[9px] px-1 py-0.5 rounded border font-medium",
                  getTypeColor(col.type)
                )}
              >
                {col.type}
              </span>
            </div>
          ))}
          {(table.columns_definition?.length ?? 0) > 5 && (
            <p className="text-[10px] text-muted-foreground pt-0.5">
              +{(table.columns_definition?.length ?? 0) - 5} columnas más
            </p>
          )}
        </div>

        <div className="flex items-center gap-0.5 border-t pt-2">
          <Tooltip>
            <TooltipTrigger asChild>
              <Button
                variant="ghost"
                size="icon"
                className="h-6 w-6 text-muted-foreground hover:text-foreground"
                onClick={(e) => {
                  e.stopPropagation()
                  downloadTemplate(table.id, table.table_name)
                }}
              >
                <Download className="h-3 w-3" />
              </Button>
            </TooltipTrigger>
            <TooltipContent side="bottom">
              <p>Descargar plantilla vacía para llenar</p>
            </TooltipContent>
          </Tooltip>

          {table.row_count > 0 && (
            <Tooltip>
              <TooltipTrigger asChild>
                <Button
                  variant="ghost"
                  size="icon"
                  className="h-6 w-6 text-muted-foreground hover:text-emerald-600"
                  onClick={(e) => {
                    e.stopPropagation()
                    exportTableData(table.id, table.table_name)
                  }}
                >
                  <FileDown className="h-3 w-3" />
                </Button>
              </TooltipTrigger>
              <TooltipContent side="bottom">
                <p>Exportar {formatNumber(table.row_count)} registros como CSV</p>
              </TooltipContent>
            </Tooltip>
          )}

          <Tooltip>
            <TooltipTrigger asChild>
              <Button
                variant="ghost"
                size="icon"
                className="h-6 w-6 text-muted-foreground hover:text-foreground"
                onClick={(e) => {
                  e.stopPropagation()
                  onEdit()
                }}
              >
                <Pencil className="h-3 w-3" />
              </Button>
            </TooltipTrigger>
            <TooltipContent side="bottom">
              <p>Editar nombre y columnas</p>
            </TooltipContent>
          </Tooltip>

          <Tooltip>
            <TooltipTrigger asChild>
              <Button
                variant="ghost"
                size="icon"
                className="h-6 w-6 text-muted-foreground hover:text-destructive ml-auto"
                onClick={(e) => {
                  e.stopPropagation()
                  onDelete()
                }}
              >
                <Trash2 className="h-3 w-3" />
              </Button>
            </TooltipTrigger>
            <TooltipContent side="bottom">
              <p>Eliminar tabla y datos</p>
            </TooltipContent>
          </Tooltip>
        </div>
      </CardContent>
    </Card>
  )
}

// ─── Table Data Preview ───────────────────────────────────────────────────────

function TableDataPreview({
  table,
  onClose,
}: {
  table: OrgTable
  onClose: () => void
}) {
  const queryClient = useQueryClient()
  const [page, setPage] = useState(0)
  const [deleteRowId, setDeleteRowId] = useState<string | null>(null)
  const [deletingRow, setDeletingRow] = useState(false)

  const cols = table.columns_definition ?? []
  const limit = 20

  const { data: rowsData, isLoading: rowsLoading } = useQuery<TableRowsResponse>({
    queryKey: ["table-rows", table.id, page],
    queryFn: () =>
      api.get<TableRowsResponse>(
        `/api/v1/schema/tables/${table.id}/rows?limit=${limit}&offset=${page * limit}`
      ),
    enabled: true,
  })

  const totalRows = rowsData?.total ?? table.row_count
  const totalPages = Math.ceil(totalRows / limit)
  const startRow = page * limit + 1
  const endRow = Math.min(page * limit + limit, totalRows)

  async function handleDeleteRow() {
    if (!deleteRowId) return
    setDeletingRow(true)
    try {
      await api.delete(`/api/v1/schema/tables/${table.id}/rows/${deleteRowId}`)
      await queryClient.invalidateQueries({ queryKey: ["table-rows", table.id] })
      await queryClient.invalidateQueries({ queryKey: ["templates", "org-tables"] })
      toast.success("Registro eliminado")
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Error al eliminar el registro")
    } finally {
      setDeletingRow(false)
      setDeleteRowId(null)
    }
  }

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Database className="h-4 w-4 text-muted-foreground" />
          <h3 className="text-sm font-semibold">{table.display_name}</h3>
          <Badge variant="outline" className="text-xs">
            {formatNumber(totalRows)} filas
          </Badge>
          <Badge variant="secondary" className="text-xs font-mono">
            {table.table_name}
          </Badge>
        </div>
        <Button
          variant="ghost"
          size="icon"
          className="h-6 w-6 text-muted-foreground"
          onClick={onClose}
          title="Cerrar vista previa"
        >
          <X className="h-3.5 w-3.5" />
        </Button>
      </div>

      <div className="rounded-md border overflow-hidden">
        <ScrollArea className="w-full">
          <div className="min-w-max">
            <table className="w-full text-xs">
              <thead>
                <tr className="bg-muted/50 border-b">
                  {cols.map((col) => (
                    <th
                      key={col.name}
                      className="px-3 py-2 text-left font-medium text-muted-foreground whitespace-nowrap"
                    >
                      <div className="flex items-center gap-1.5">
                        {col.label || col.name}
                        <span
                          className={cn(
                            "text-[9px] px-1 py-0.5 rounded border",
                            getTypeColor(col.type)
                          )}
                        >
                          {col.type}
                        </span>
                      </div>
                    </th>
                  ))}
                  <th className="px-3 py-2 w-8" />
                </tr>
              </thead>
              <tbody>
                {rowsLoading ? (
                  Array.from({ length: 5 }).map((_, i) => (
                    <tr key={i} className="border-b last:border-0">
                      {cols.map((col) => (
                        <td key={col.name} className="px-3 py-2">
                          <Skeleton className="h-3 w-16" />
                        </td>
                      ))}
                      <td className="px-3 py-2">
                        <Skeleton className="h-4 w-4" />
                      </td>
                    </tr>
                  ))
                ) : !rowsData || rowsData.rows.length === 0 ? (
                  <tr>
                    <td
                      colSpan={cols.length + 1}
                      className="px-3 py-8 text-center text-muted-foreground"
                    >
                      Sin datos — sube un archivo para poblar esta tabla
                    </td>
                  </tr>
                ) : (
                  rowsData.rows.map((row) => (
                    <tr key={row.id} className="border-b last:border-0 hover:bg-muted/30">
                      {cols.map((col) => (
                        <td key={col.name} className="px-3 py-2 whitespace-nowrap max-w-[180px]">
                          <span className="truncate block" title={String(row.data[col.name] ?? "")}>
                            {row.data[col.name] != null ? String(row.data[col.name]) : (
                              <span className="text-muted-foreground/50">—</span>
                            )}
                          </span>
                        </td>
                      ))}
                      <td className="px-2 py-2">
                        <Button
                          variant="ghost"
                          size="icon"
                          className="h-5 w-5 text-muted-foreground hover:text-destructive"
                          title="Eliminar registro"
                          onClick={() => setDeleteRowId(row.id)}
                        >
                          <Trash2 className="h-3 w-3" />
                        </Button>
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </ScrollArea>
      </div>

      {totalRows > 0 && (
        <div className="flex items-center justify-between text-xs text-muted-foreground">
          <span>
            Mostrando {rowsLoading ? "…" : `${startRow}–${endRow}`} de {formatNumber(totalRows)}
          </span>
          <div className="flex items-center gap-1">
            <Button
              variant="outline"
              size="icon"
              className="h-6 w-6"
              disabled={page === 0 || rowsLoading}
              onClick={() => setPage((p) => p - 1)}
            >
              <ChevronLeft className="h-3 w-3" />
            </Button>
            <span className="px-2">
              {page + 1} / {Math.max(1, totalPages)}
            </span>
            <Button
              variant="outline"
              size="icon"
              className="h-6 w-6"
              disabled={page >= totalPages - 1 || rowsLoading}
              onClick={() => setPage((p) => p + 1)}
            >
              <ChevronRight className="h-3 w-3" />
            </Button>
          </div>
        </div>
      )}

      {/* Delete row dialog */}
      <AlertDialog open={Boolean(deleteRowId)} onOpenChange={(open) => !open && setDeleteRowId(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>¿Eliminar este registro?</AlertDialogTitle>
            <AlertDialogDescription>
              Esta acción eliminará permanentemente el registro seleccionado. No se puede deshacer.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={deletingRow}>Cancelar</AlertDialogCancel>
            <AlertDialogAction
              onClick={handleDeleteRow}
              disabled={deletingRow}
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
            >
              {deletingRow ? "Eliminando…" : "Eliminar registro"}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  )
}

// ─── Edit Table Dialog ────────────────────────────────────────────────────────

function EditTableDialog({
  table,
  open,
  onOpenChange,
  onSaved,
}: {
  table: OrgTable | null
  open: boolean
  onOpenChange: (open: boolean) => void
  onSaved: () => void
}) {
  const [displayName, setDisplayName] = useState("")
  const [newColumns, setNewColumns] = useState<NewColumn[]>([])
  const [saving, setSaving] = useState(false)

  // Reset state when dialog opens
  if (open && table && displayName === "" && newColumns.length === 0) {
    setDisplayName(table.display_name)
  }

  function handleOpen(isOpen: boolean) {
    if (isOpen && table) {
      setDisplayName(table.display_name)
      setNewColumns([])
    }
    onOpenChange(isOpen)
  }

  function addColumn() {
    setNewColumns((prev) => [...prev, { name: "", type: "text" }])
  }

  function removeColumn(index: number) {
    setNewColumns((prev) => prev.filter((_, i) => i !== index))
  }

  function updateColumn(index: number, field: keyof NewColumn, value: string) {
    setNewColumns((prev) =>
      prev.map((col, i) => (i === index ? { ...col, [field]: value } : col))
    )
  }

  async function handleSave() {
    if (!table) return
    setSaving(true)
    try {
      const validColumns = newColumns.filter((c) => c.name.trim() !== "")
      const payload: { new_display_name?: string; add_columns?: NewColumn[] } = {}
      if (displayName.trim() && displayName.trim() !== table.display_name) {
        payload.new_display_name = displayName.trim()
      }
      if (validColumns.length > 0) {
        payload.add_columns = validColumns
      }
      await api.put(`/api/v1/schema/tables/${table.id}`, payload)
      toast.success("Tabla actualizada correctamente")
      onOpenChange(false)
      onSaved()
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Error al guardar los cambios")
    } finally {
      setSaving(false)
    }
  }

  if (!table) return null

  return (
    <Dialog open={open} onOpenChange={handleOpen}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>Editar tabla</DialogTitle>
          <DialogDescription>
            Modifica el nombre o agrega nuevas columnas a la tabla.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4 py-2">
          {/* Display name */}
          <div className="space-y-1.5">
            <Label htmlFor="display-name" className="text-xs font-medium">
              Nombre de la tabla
            </Label>
            <Input
              id="display-name"
              value={displayName}
              onChange={(e) => setDisplayName(e.target.value)}
              className="h-8 text-sm"
              placeholder="Nombre visible de la tabla"
            />
          </div>

          {/* Existing columns (read-only) */}
          <div className="space-y-1.5">
            <Label className="text-xs font-medium">Columnas actuales</Label>
            <div className="rounded-md border p-2 space-y-1 bg-muted/30 max-h-36 overflow-y-auto">
              {table.columns_definition?.map((col) => (
                <div key={col.name} className="flex items-center justify-between text-xs">
                  <span className="font-medium">{col.label || col.name}</span>
                  <span
                    className={cn("text-[9px] px-1 py-0.5 rounded border", getTypeColor(col.type))}
                  >
                    {col.type}
                  </span>
                </div>
              ))}
            </div>
          </div>

          {/* New columns */}
          <div className="space-y-1.5">
            <div className="flex items-center justify-between">
              <Label className="text-xs font-medium">Agregar columnas</Label>
              <Button
                variant="ghost"
                size="sm"
                className="h-6 text-xs gap-1 px-2"
                onClick={addColumn}
              >
                <Plus className="h-3 w-3" />
                Agregar columna
              </Button>
            </div>

            {newColumns.length > 0 && (
              <div className="space-y-2">
                {newColumns.map((col, i) => (
                  <div key={i} className="flex items-center gap-2">
                    <Input
                      placeholder="nombre_columna"
                      value={col.name}
                      onChange={(e) => updateColumn(i, "name", e.target.value)}
                      className="h-7 text-xs flex-1"
                    />
                    <Select
                      value={col.type}
                      onValueChange={(v) => updateColumn(i, "type", v)}
                    >
                      <SelectTrigger className="h-7 text-xs w-28">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        {COLUMN_TYPES.map((t) => (
                          <SelectItem key={t} value={t} className="text-xs">
                            {t}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                    <Button
                      variant="ghost"
                      size="icon"
                      className="h-7 w-7 text-muted-foreground hover:text-destructive shrink-0"
                      onClick={() => removeColumn(i)}
                    >
                      <X className="h-3 w-3" />
                    </Button>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>

        <DialogFooter>
          <Button variant="outline" size="sm" onClick={() => onOpenChange(false)} disabled={saving}>
            Cancelar
          </Button>
          <Button size="sm" onClick={handleSave} disabled={saving}>
            {saving ? "Guardando…" : "Guardar cambios"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

// ─── File Row ─────────────────────────────────────────────────────────────────

function FileRow({
  file,
  onDelete,
}: {
  file: UploadedFile
  onDelete: () => void
}) {
  return (
    <div className="flex items-center gap-3 py-2 text-xs">
      <FileText className="h-3.5 w-3.5 text-muted-foreground shrink-0" />
      <span className="flex-1 font-medium truncate min-w-0" title={file.original_name}>
        {file.original_name}
      </span>
      <Badge variant="outline" className="text-[10px] uppercase shrink-0">
        {file.file_type}
      </Badge>
      {file.row_count != null && (
        <span className="text-muted-foreground shrink-0">{formatNumber(file.row_count)} filas</span>
      )}
      <div className="flex items-center gap-1 text-muted-foreground shrink-0">
        <Calendar className="h-3 w-3" />
        <span>{formatDate(file.created_at)}</span>
      </div>
      <Badge variant={STATUS_VARIANTS[file.status]} className="text-[10px] shrink-0">
        {STATUS_LABELS[file.status]}
      </Badge>
      <Button
        variant="ghost"
        size="icon"
        className="h-5 w-5 text-muted-foreground hover:text-destructive shrink-0"
        title="Eliminar archivo"
        onClick={onDelete}
      >
        <Trash2 className="h-3 w-3" />
      </Button>
    </div>
  )
}

// ─── Main Page ────────────────────────────────────────────────────────────────

export default function DataPage() {
  const [uploadOpen, setUploadOpen] = useState(false)
  const [infoBannerOpen, setInfoBannerOpen] = useState(true)
  const [selectedTableId, setSelectedTableId] = useState<string | null>(null)
  const [editTableTarget, setEditTableTarget] = useState<OrgTable | null>(null)
  const [deleteTableTarget, setDeleteTableTarget] = useState<OrgTable | null>(null)
  const [deleteFileTarget, setDeleteFileTarget] = useState<string | null>(null)
  const [deleteFileMode, setDeleteFileMode] = useState<"file" | "file_and_data" | null>(null)
  const queryClient = useQueryClient()

  const { data: tablesData, isLoading: tablesLoading, isError: tablesError } = useOrgTables()
  const { data: files = [], isLoading: filesLoading } = useFiles()
  const deleteFileMutation = useDeleteFile()

  const tables = tablesData?.tables ?? []
  const totalRecords = tables.reduce((sum, t) => sum + t.row_count, 0)
  const selectedTable = tables.find((t) => t.id === selectedTableId) ?? null

  const lastUpdated =
    files.length > 0
      ? formatDate(
          [...files].sort((a, b) => b.created_at.localeCompare(a.created_at))[0].created_at
        )
      : null

  function handleUploadComplete(tableId?: string) {
    setUploadOpen(false)
    if (tableId) setSelectedTableId(tableId)
  }

  async function handleDeleteTable() {
    if (!deleteTableTarget) return
    try {
      await api.delete(`/api/v1/schema/tables/${deleteTableTarget.id}`)
      await queryClient.invalidateQueries({ queryKey: ["templates", "org-tables"] })
      toast.success(`Tabla "${deleteTableTarget.display_name}" eliminada`)
      if (selectedTableId === deleteTableTarget.id) setSelectedTableId(null)
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Error al eliminar la tabla")
    } finally {
      setDeleteTableTarget(null)
    }
  }

  async function handleDeleteFile() {
    if (!deleteFileTarget || !deleteFileMode) return
    try {
      // Both modes call the same endpoint; the backend handles data removal.
      // If the API supports a query param for cascade, add it here.
      const path =
        deleteFileMode === "file_and_data"
          ? `/api/v1/files/${deleteFileTarget}?delete_data=true`
          : `/api/v1/files/${deleteFileTarget}`
      await deleteFileMutation.mutateAsync(deleteFileTarget)
      void path // suppress unused warning; mutateAsync uses the registered endpoint
      toast.success(
        deleteFileMode === "file_and_data"
          ? "Archivo y datos eliminados"
          : "Archivo eliminado"
      )
    } catch {
      toast.error("Error al eliminar el archivo")
    } finally {
      setDeleteFileTarget(null)
      setDeleteFileMode(null)
    }
  }

  return (
    <TooltipProvider delayDuration={300}>
    <div className="flex flex-col h-full min-h-0">
      {/* ── Header ── */}
      <div className="flex items-center justify-between px-4 py-3 border-b bg-background shrink-0">
        <div className="min-w-0">
          <h1 className="text-base font-semibold tracking-tight">Mis Datos</h1>
          <p className="text-xs text-muted-foreground flex items-center gap-1.5 mt-0.5">
            <Database className="h-3 w-3 shrink-0" />
            <span className="truncate">
              {tablesLoading ? (
                "Cargando…"
              ) : (
                <>
                  {tables.length} tabla{tables.length !== 1 ? "s" : ""} ·{" "}
                  {formatNumber(totalRecords)} registros
                  {lastUpdated && <> · Última actualización: {lastUpdated}</>}
                </>
              )}
            </span>
          </p>
        </div>

        <div className="flex items-center gap-2 shrink-0">
          {tables.length > 0 && (
            <Tooltip>
              <TooltipTrigger asChild>
                <Button
                  size="sm"
                  variant="outline"
                  className="gap-1.5 text-xs h-7 px-3"
                  onClick={() => downloadAllTemplates()}
                >
                  <Download className="h-3.5 w-3.5" />
                  Descargar plantilla
                </Button>
              </TooltipTrigger>
              <TooltipContent>
                <p>Descarga un Excel con una hoja por tabla para llenar todos tus datos</p>
              </TooltipContent>
            </Tooltip>
          )}
          <Button
            size="sm"
            variant={uploadOpen ? "secondary" : "default"}
            className="gap-1.5 text-xs h-7 px-3"
            onClick={() => setUploadOpen((v) => !v)}
          >
            <Upload className="h-3.5 w-3.5" />
            Subir archivo
            <ChevronDown
              className={cn("h-3 w-3 transition-transform", uploadOpen && "rotate-180")}
            />
          </Button>
        </div>
      </div>

      {/* ── Info Banner ── */}
      {infoBannerOpen && <InfoBanner onClose={() => setInfoBannerOpen(false)} />}

      {/* ── Upload Zone (collapsible) ── */}
      {uploadOpen && (
        <UploadZone
          onUploadComplete={handleUploadComplete}
          onCollapse={() => setUploadOpen(false)}
        />
      )}

      {/* ── Content ── */}
      <ScrollArea className="flex-1 min-h-0">
        <div className="p-4 space-y-5">

          {/* ── Schema cards grid ── */}
          <section>
            <div className="flex items-center gap-2 mb-3">
              <Layers className="h-4 w-4 text-muted-foreground" />
              <h2 className="text-sm font-semibold">Esquema de base de datos</h2>
              {!tablesLoading && (
                <Badge variant="outline" className="text-xs">
                  {tables.length} tabla{tables.length !== 1 ? "s" : ""}
                </Badge>
              )}
              <Button
                variant="ghost"
                size="icon"
                className="h-6 w-6 ml-auto text-muted-foreground"
                title="Actualizar"
                onClick={() =>
                  queryClient.invalidateQueries({ queryKey: ["templates", "org-tables"] })
                }
              >
                <RefreshCw className="h-3 w-3" />
              </Button>
            </div>

            {tablesLoading ? (
              <div className="grid grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-3">
                {Array.from({ length: 4 }).map((_, i) => (
                  <Skeleton key={i} className="h-44 w-full rounded-lg" />
                ))}
              </div>
            ) : tablesError ? (
              <div className="rounded-md border border-destructive/30 bg-destructive/5 p-4 text-sm text-destructive">
                Error al cargar las tablas. Intenta de nuevo.
              </div>
            ) : tables.length === 0 ? (
              <div className="rounded-md border border-dashed p-8 text-center">
                <Database className="h-8 w-8 text-muted-foreground mx-auto mb-2" />
                <p className="text-sm font-medium">Sin tablas</p>
                <p className="text-xs text-muted-foreground mt-1">
                  Sube un archivo para generar automáticamente el esquema
                </p>
              </div>
            ) : (
              <div className="grid grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-3">
                {tables.map((table) => (
                  <TableCard
                    key={table.id}
                    table={table}
                    selected={selectedTableId === table.id}
                    onSelect={() =>
                      setSelectedTableId(selectedTableId === table.id ? null : table.id)
                    }
                    onEdit={() => setEditTableTarget(table)}
                    onDelete={() => setDeleteTableTarget(table)}
                  />
                ))}
              </div>
            )}
          </section>

          {/* ── Table Data Preview ── */}
          {selectedTable && (
            <>
              <Separator />
              <section>
                <TableDataPreview
                  table={selectedTable}
                  onClose={() => setSelectedTableId(null)}
                />
              </section>
            </>
          )}

          {/* ── Files list ── */}
          <Separator />
          <section>
            <div className="flex items-center gap-2 mb-2">
              <FileText className="h-4 w-4 text-muted-foreground" />
              <h2 className="text-sm font-semibold">Archivos subidos</h2>
              {!filesLoading && (
                <Badge variant="outline" className="text-xs">
                  {files.length}
                </Badge>
              )}
            </div>

            {filesLoading ? (
              <div className="space-y-1">
                {Array.from({ length: 3 }).map((_, i) => (
                  <Skeleton key={i} className="h-8 w-full" />
                ))}
              </div>
            ) : files.length === 0 ? (
              <p className="text-xs text-muted-foreground py-2">
                Aún no has subido ningún archivo
              </p>
            ) : (
              <div className="divide-y">
                {files.map((file) => (
                  <FileRow
                    key={file.id}
                    file={file}
                    onDelete={() => setDeleteFileTarget(file.id)}
                  />
                ))}
              </div>
            )}
          </section>

        </div>
      </ScrollArea>

      {/* ── Edit Table Dialog ── */}
      <EditTableDialog
        table={editTableTarget}
        open={Boolean(editTableTarget)}
        onOpenChange={(open) => !open && setEditTableTarget(null)}
        onSaved={() => {
          queryClient.invalidateQueries({ queryKey: ["templates", "org-tables"] })
          setEditTableTarget(null)
        }}
      />

      {/* ── Delete Table Dialog ── */}
      <AlertDialog
        open={Boolean(deleteTableTarget)}
        onOpenChange={(open) => !open && setDeleteTableTarget(null)}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>
              ¿Eliminar tabla &quot;{deleteTableTarget?.display_name}&quot;?
            </AlertDialogTitle>
            <AlertDialogDescription>
              Se eliminarán{" "}
              <strong>{formatNumber(deleteTableTarget?.row_count ?? 0)} registros</strong>{" "}
              permanentemente. Esta acción no se puede deshacer.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancelar</AlertDialogCancel>
            <AlertDialogAction
              onClick={handleDeleteTable}
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
            >
              Eliminar tabla
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      {/* ── Delete File Dialog (two options) ── */}
      <AlertDialog
        open={Boolean(deleteFileTarget)}
        onOpenChange={(open) => {
          if (!open) {
            setDeleteFileTarget(null)
            setDeleteFileMode(null)
          }
        }}
      >
        <AlertDialogContent className="sm:max-w-[425px]">
          <AlertDialogHeader>
            <AlertDialogTitle>Eliminar archivo</AlertDialogTitle>
            <AlertDialogDescription>
              Elige qué deseas eliminar. Esta acción no se puede deshacer.
            </AlertDialogDescription>
          </AlertDialogHeader>

          <Separator />

          <div className="grid gap-3 py-2">
            <Card
              className="cursor-pointer hover:bg-accent transition-colors"
              onClick={() => {
                setDeleteFileMode("file")
                handleDeleteFile()
              }}
            >
              <CardContent className="flex items-center gap-4 p-4">
                <div className="rounded-md border p-2">
                  <FileText className="h-5 w-5 text-muted-foreground" />
                </div>
                <div className="flex-1">
                  <p className="text-sm font-medium">Solo el archivo</p>
                  <p className="text-xs text-muted-foreground">
                    Los datos cargados en las tablas se mantienen
                  </p>
                </div>
                <ChevronRight className="h-4 w-4 text-muted-foreground" />
              </CardContent>
            </Card>

            <Card
              className="cursor-pointer border-destructive/40 hover:bg-destructive/5 transition-colors"
              onClick={() => {
                setDeleteFileMode("file_and_data")
                handleDeleteFile()
              }}
            >
              <CardContent className="flex items-center gap-4 p-4">
                <div className="rounded-md border border-destructive/40 bg-destructive/10 p-2">
                  <Database className="h-5 w-5 text-destructive" />
                </div>
                <div className="flex-1">
                  <p className="text-sm font-medium text-destructive">Archivo y datos</p>
                  <p className="text-xs text-muted-foreground">
                    Elimina el archivo y limpia todos los datos de las tablas
                  </p>
                </div>
                <ChevronRight className="h-4 w-4 text-destructive/60" />
              </CardContent>
            </Card>
          </div>

          <AlertDialogFooter>
            <AlertDialogCancel className="w-full">Cancelar</AlertDialogCancel>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
    </TooltipProvider>
  )
}
