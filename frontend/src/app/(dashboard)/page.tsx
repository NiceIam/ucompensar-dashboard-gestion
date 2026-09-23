"use client"

import { useOrgTables } from "@/hooks/use-templates"
import { useETLJobs } from "@/hooks/use-etl"
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Progress } from "@/components/ui/progress"
import { Skeleton } from "@/components/ui/skeleton"
import {
  Database,
  FileText,
  BarChart3,
  Package,
  Users,
  Receipt,
  TrendingUp,
  Layers,
  Activity,
  CheckCircle2,
  XCircle,
  Clock,
  Loader2,
  FileSpreadsheet,
  Upload,
} from "lucide-react"
import type { ElementType } from "react"
import type { ETLStatus } from "@/hooks/use-etl"

const STATUS_CONFIG: Record<
  ETLStatus,
  { icon: ElementType; color: string; bg: string; label: string }
> = {
  pending: { icon: Clock, color: "text-amber-600", bg: "bg-amber-50", label: "Pendiente" },
  extracting: { icon: Loader2, color: "text-orange-600", bg: "bg-orange-50", label: "Extrayendo" },
  transforming: { icon: Loader2, color: "text-orange-600", bg: "bg-orange-50", label: "Transformando" },
  loading: { icon: Loader2, color: "text-orange-600", bg: "bg-orange-50", label: "Cargando" },
  completed: { icon: CheckCircle2, color: "text-emerald-600", bg: "bg-emerald-50", label: "Completado" },
  failed: { icon: XCircle, color: "text-red-600", bg: "bg-red-50", label: "Error" },
}

const TABLE_ICONS: Record<string, ElementType> = {
  productos: Package,
  ventas: BarChart3,
  proveedores: Users,
  clientes: Users,
  servicios: FileText,
  facturas: Receipt,
  cotizaciones: FileSpreadsheet,
  menu_items: FileText,
  pedidos: Receipt,
  inventario: Package,
  inventario_movimientos: Activity,
}

const TABLE_DESCRIPTIONS: Record<string, string> = {
  productos: "Inventario de productos, precios y stock disponible",
  ventas: "Registro de transacciones y ventas realizadas",
  proveedores: "Directorio de proveedores y contactos",
  clientes: "Base de datos de clientes y empresas",
  servicios: "Catalogo de servicios ofrecidos con tarifas",
  facturas: "Facturacion con IVA, totales y estado de pago",
  cotizaciones: "Propuestas comerciales y su estado",
  menu_items: "Platos del menu con precios y disponibilidad",
  pedidos: "Ordenes de clientes y mesas",
  inventario: "Control de ingredientes y existencias",
  inventario_movimientos: "Entradas y salidas de inventario",
}

export default function DashboardPage() {
  const { data: tablesData, isLoading: tablesLoading } = useOrgTables()
  const { data: jobsData, isLoading: jobsLoading } = useETLJobs()

  const tables = tablesData?.tables ?? []
  const jobs = jobsData?.jobs ?? []
  const totalRecords = tables.reduce((sum, t) => sum + (t.row_count ?? 0), 0)
  const tablesWithData = tables.filter((t) => (t.row_count ?? 0) > 0)
  const maxRows = Math.max(...tables.map((t) => t.row_count ?? 0), 1)

  return (
    <div className="space-y-6">
      {/* Header compacto */}
      <div>
        <h1 className="text-xl font-semibold tracking-tight">Resumen del negocio</h1>
        <p className="text-sm text-muted-foreground">
          Vista general de tus datos y estado de la plataforma
        </p>
      </div>

      {/* KPIs en fila compacta */}
      {tablesLoading ? (
        <div className="grid gap-3 grid-cols-2 lg:grid-cols-4">
          {[1, 2, 3, 4].map((i) => (
            <Skeleton key={i} className="h-20" />
          ))}
        </div>
      ) : (
        <div className="grid gap-3 grid-cols-2 lg:grid-cols-4">
          <Card className="shadow-none">
            <CardContent className="p-4">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-xs font-medium text-muted-foreground uppercase tracking-wider">
                    Registros
                  </p>
                  <p className="text-2xl font-bold mt-1">
                    {totalRecords.toLocaleString("es-CO")}
                  </p>
                </div>
                <div className="rounded-lg bg-orange-50 dark:bg-orange-950 p-2.5">
                  <Database className="h-4 w-4 text-orange-600 dark:text-orange-400" />
                </div>
              </div>
              <p className="text-xs text-muted-foreground mt-2">
                {totalRecords > 0 ? "Datos cargados en el sistema" : "Suba archivos para comenzar"}
              </p>
            </CardContent>
          </Card>

          <Card className="shadow-none">
            <CardContent className="p-4">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-xs font-medium text-muted-foreground uppercase tracking-wider">
                    Tablas
                  </p>
                  <p className="text-2xl font-bold mt-1">{tables.length}</p>
                </div>
                <div className="rounded-lg bg-purple-50 dark:bg-purple-950 p-2.5">
                  <Layers className="h-4 w-4 text-purple-600 dark:text-purple-400" />
                </div>
              </div>
              <p className="text-xs text-muted-foreground mt-2">
                {tablesWithData.length} con datos de {tables.length} configuradas
              </p>
            </CardContent>
          </Card>

          <Card className="shadow-none">
            <CardContent className="p-4">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-xs font-medium text-muted-foreground uppercase tracking-wider">
                    Archivos
                  </p>
                  <p className="text-2xl font-bold mt-1">{jobs.length}</p>
                </div>
                <div className="rounded-lg bg-teal-50 dark:bg-teal-950 p-2.5">
                  <Upload className="h-4 w-4 text-teal-600 dark:text-teal-400" />
                </div>
              </div>
              <p className="text-xs text-muted-foreground mt-2">
                {jobs.filter((j) => j.status === "completed").length} procesados correctamente
              </p>
            </CardContent>
          </Card>

          <Card className="shadow-none">
            <CardContent className="p-4">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-xs font-medium text-muted-foreground uppercase tracking-wider">
                    Cobertura
                  </p>
                  <p className="text-2xl font-bold mt-1">
                    {tables.length > 0
                      ? Math.round((tablesWithData.length / tables.length) * 100)
                      : 0}%
                  </p>
                </div>
                <div className="rounded-lg bg-amber-50 dark:bg-amber-950 p-2.5">
                  <TrendingUp className="h-4 w-4 text-amber-600 dark:text-amber-400" />

                </div>
              </div>
              <Progress
                value={tables.length > 0 ? (tablesWithData.length / tables.length) * 100 : 0}
                className="h-1.5 mt-2"
              />
            </CardContent>
          </Card>
        </div>
      )}

      {/* Tablas de datos — layout compacto tipo tabla */}
      <Card className="shadow-none">
        <CardHeader className="pb-3">
          <div className="flex items-center justify-between">
            <div>
              <CardTitle className="text-base">Estructura de datos</CardTitle>
              <CardDescription>
                Tablas configuradas para tu negocio y volumen de registros
              </CardDescription>
            </div>
            <Badge variant="secondary" className="font-mono">
              {tables.length} tablas
            </Badge>
          </div>
        </CardHeader>
        <CardContent className="p-0">
          {tablesLoading ? (
            <div className="p-6 space-y-3">
              {[1, 2, 3].map((i) => (
                <Skeleton key={i} className="h-14" />
              ))}
            </div>
          ) : tables.length === 0 ? (
            <div className="p-8 text-center">
              <Database className="h-10 w-10 mx-auto text-muted-foreground/40 mb-3" />
              <p className="text-sm text-muted-foreground">
                No hay tablas configuradas. El asistente IA las creara al subir datos.
              </p>
            </div>
          ) : (
            <div className="divide-y">
              {tables.map((table) => {
                const Icon = TABLE_ICONS[table.table_name] ?? Database
                const desc = TABLE_DESCRIPTIONS[table.table_name] ?? `Tabla de ${table.display_name.toLowerCase()}`
                const rowCount = table.row_count ?? 0
                const fillPercent = maxRows > 0 ? (rowCount / maxRows) * 100 : 0

                return (
                  <div
                    key={table.id}
                    className="flex items-center gap-4 px-6 py-3 hover:bg-muted/30 transition-colors"
                  >
                    <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-muted">
                      <Icon className="h-4 w-4 text-muted-foreground" />
                    </div>

                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2">
                        <p className="text-sm font-medium truncate">
                          {table.display_name}
                        </p>
                        <Badge
                          variant={rowCount > 0 ? "default" : "outline"}
                          className="text-[10px] px-1.5 py-0 h-4 shrink-0"
                        >
                          {rowCount > 0 ? `${rowCount.toLocaleString("es-CO")} filas` : "Vacía"}
                        </Badge>
                      </div>
                      <p className="text-xs text-muted-foreground truncate mt-0.5">
                        {desc} · {table.columns_definition?.length ?? 0} columnas
                      </p>
                    </div>

                    {/* Mini bar chart */}
                    <div className="w-24 shrink-0 hidden sm:block">
                      <div className="h-2 rounded-full bg-muted overflow-hidden">
                        <div
                          className="h-full rounded-full bg-primary/60 transition-all"
                          style={{ width: `${Math.max(fillPercent, rowCount > 0 ? 8 : 0)}%` }}
                        />
                      </div>
                    </div>

                    <p className="text-sm font-mono text-right w-16 shrink-0 tabular-nums">
                      {rowCount.toLocaleString("es-CO")}
                    </p>
                  </div>
                )
              })}
            </div>
          )}
        </CardContent>
      </Card>

      {/* Actividad reciente — solo si hay jobs */}
      {!jobsLoading && jobs.length > 0 && (
        <Card className="shadow-none">
          <CardHeader className="pb-3">
            <CardTitle className="text-base">Actividad reciente</CardTitle>
            <CardDescription>
              Archivos procesados por el sistema de carga de datos
            </CardDescription>
          </CardHeader>
          <CardContent className="p-0">
            <div className="divide-y">
              {jobs.slice(0, 5).map((job) => {
                const statusCfg = STATUS_CONFIG[job.status] ?? STATUS_CONFIG.pending
                const StatusIcon = statusCfg.icon
                const isAnimated = ["extracting", "transforming", "loading"].includes(job.status)
                return (
                  <div
                    key={job.job_id}
                    className="flex items-center gap-4 px-6 py-3"
                  >
                    <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-muted">
                      <FileText className="h-4 w-4 text-muted-foreground" />
                    </div>
                    <div className="flex-1 min-w-0">
                      <p className="text-sm font-medium truncate">
                        {job.filename || "Archivo sin nombre"}
                      </p>
                      <p className="text-xs text-muted-foreground">
                        {job.rows_loaded > 0 && `${job.rows_loaded.toLocaleString("es-CO")} filas cargadas`}
                        {job.error_message && job.error_message}
                        {!job.rows_loaded && !job.error_message && "En espera de procesamiento"}
                      </p>
                    </div>
                    <Badge
                      variant="outline"
                      className={`text-xs shrink-0 ${statusCfg.color} ${statusCfg.bg} border-transparent`}
                    >
                      <StatusIcon
                        className={`h-3 w-3 mr-1 ${isAnimated ? "animate-spin" : ""}`}
                      />
                      {statusCfg.label}
                    </Badge>
                  </div>
                )
              })}
            </div>
          </CardContent>
        </Card>
      )}

      {/* Guia rapida — solo sin datos */}
      {totalRecords === 0 && !tablesLoading && (
        <Card className="shadow-none border-dashed bg-muted/20">
          <CardContent className="p-6">
            <div className="flex items-start gap-4">
              <div className="rounded-lg bg-primary/10 p-3 shrink-0">
                <Upload className="h-5 w-5 text-primary" />
              </div>
              <div>
                <h3 className="text-sm font-semibold">Como empezar</h3>
                <p className="text-sm text-muted-foreground mt-1 leading-relaxed">
                  Usa el <strong>Asistente IA</strong> a la derecha para subir archivos CSV o Excel
                  con los datos de tu negocio. El agente analizara las columnas, creara o
                  ajustara las tablas automaticamente, y cargara los datos listos para consultar.
                </p>
                <div className="flex gap-6 mt-3 text-xs text-muted-foreground">
                  <span className="flex items-center gap-1.5">
                    <CheckCircle2 className="h-3.5 w-3.5 text-emerald-500" />
                    CSV, Excel, PDF
                  </span>
                  <span className="flex items-center gap-1.5">
                    <CheckCircle2 className="h-3.5 w-3.5 text-emerald-500" />
                    Max 10.000 filas
                  </span>
                  <span className="flex items-center gap-1.5">
                    <CheckCircle2 className="h-3.5 w-3.5 text-emerald-500" />
                    Auto-deteccion de columnas
                  </span>
                </div>
              </div>
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  )
}
