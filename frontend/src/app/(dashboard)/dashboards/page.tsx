"use client"

import { useMemo, useState } from "react"
import Link from "next/link"
import { toast } from "sonner"
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Skeleton } from "@/components/ui/skeleton"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Badge } from "@/components/ui/badge"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog"
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from "@/components/ui/alert-dialog"
import {
  useDashboards,
  useCreateDashboard,
  useDeleteDashboard,
  useDownloadDashboardScript,
} from "@/hooks/use-dashboards"
import { formatDate } from "@/lib/utils"
import {
  BarChart3,
  Plus,
  LayoutDashboard,
  Download,
  Trash2,
  Eye,
  Sparkles,
  Clock,
  TrendingUp,
} from "lucide-react"

// Devuelve "Hoy", "Ayer" o "Hace N días/meses" según el delta a partir de la
// fecha de creación. Mejora la jerarquía visual frente al `formatDate` plano.
function formatRelativeDate(iso: string): string {
  const created = new Date(iso)
  const now = new Date()
  const diffMs = now.getTime() - created.getTime()
  const day = 1000 * 60 * 60 * 24
  const days = Math.floor(diffMs / day)
  if (days < 1) return "Hoy"
  if (days === 1) return "Ayer"
  if (days < 7) return `Hace ${days} días`
  if (days < 30) return `Hace ${Math.floor(days / 7)} semanas`
  if (days < 365) return `Hace ${Math.floor(days / 30)} meses`
  return `Hace ${Math.floor(days / 365)} años`
}

export default function DashboardsPage() {
  const [open, setOpen] = useState(false)
  const [name, setName] = useState("")
  const [description, setDescription] = useState("")

  const { data: dashboards = [], isLoading, isError } = useDashboards()
  const createMutation = useCreateDashboard()
  const deleteMutation = useDeleteDashboard()
  const downloadMutation = useDownloadDashboardScript()

  // Pequeño resumen para el header — derivado de la lista existente.
  const stats = useMemo(() => {
    const total = dashboards.length
    const recent = dashboards.filter((d) => {
      const days = (Date.now() - new Date(d.created_at).getTime()) / (1000 * 60 * 60 * 24)
      return days <= 7
    }).length
    return { total, recent }
  }, [dashboards])

  async function handleCreate() {
    if (!name.trim()) return
    try {
      await createMutation.mutateAsync({ name: name.trim(), description })
      toast.success(`Tablero "${name}" creado`)
      setOpen(false)
      setName("")
      setDescription("")
    } catch {
      toast.error("Error al crear el tablero")
    }
  }

  async function handleDelete(id: string, dashboardName: string) {
    try {
      await deleteMutation.mutateAsync(id)
      toast.success(`Tablero "${dashboardName}" eliminado`)
    } catch {
      toast.error("Error al eliminar el tablero")
    }
  }

  async function handleDownload(id: string) {
    try {
      await downloadMutation.mutateAsync({ id })
    } catch {
      toast.error("Error al descargar el script")
    }
  }

  return (
    <div className="space-y-6">
      {/* Header con resumen */}
      <div className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
        <div className="space-y-1">
          <div className="flex items-center gap-2">
            <h1 className="text-2xl font-bold tracking-tight">Tableros</h1>
            {stats.total > 0 && (
              <Badge variant="secondary" className="font-mono">
                {stats.total}
              </Badge>
            )}
          </div>
          <p className="text-sm text-muted-foreground">
            Visualizaciones interactivas de tus datos empresariales
            {stats.recent > 0 && (
              <>
                {" "}
                ·{" "}
                <span className="inline-flex items-center gap-1 text-foreground">
                  <TrendingUp className="h-3 w-3" />
                  {stats.recent} {stats.recent === 1 ? "nuevo esta semana" : "nuevos esta semana"}
                </span>
              </>
            )}
          </p>
        </div>

        <Dialog open={open} onOpenChange={setOpen}>
          <DialogTrigger asChild>
            <Button className="shadow-sm">
              <Plus className="mr-2 h-4 w-4" />
              Nuevo tablero
            </Button>
          </DialogTrigger>
          <DialogContent>
            <DialogHeader>
              <DialogTitle className="flex items-center gap-2">
                <Sparkles className="h-4 w-4 text-primary" />
                Crear tablero
              </DialogTitle>
              <DialogDescription>
                Dale un nombre descriptivo a tu nuevo tablero de datos.
              </DialogDescription>
            </DialogHeader>
            <div className="space-y-4 py-2">
              <div className="space-y-2">
                <Label htmlFor="dashboard-name">Nombre del tablero</Label>
                <Input
                  id="dashboard-name"
                  placeholder="ej. Ventas Q1 2025"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && handleCreate()}
                  autoFocus
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="dashboard-desc">
                  Descripcion{" "}
                  <span className="text-muted-foreground">(opcional)</span>
                </Label>
                <Input
                  id="dashboard-desc"
                  placeholder="Breve descripcion del tablero"
                  value={description}
                  onChange={(e) => setDescription(e.target.value)}
                />
              </div>
            </div>
            <DialogFooter>
              <Button variant="outline" onClick={() => setOpen(false)}>
                Cancelar
              </Button>
              <Button
                onClick={handleCreate}
                disabled={!name.trim() || createMutation.isPending}
              >
                {createMutation.isPending ? "Creando..." : "Crear tablero"}
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      </div>

      {isLoading ? (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {Array.from({ length: 6 }).map((_, i) => (
            <Skeleton key={i} className="h-48 rounded-xl" />
          ))}
        </div>
      ) : isError ? (
        <Card className="border-destructive/40 bg-destructive/5">
          <CardContent className="py-8 text-center">
            <p className="text-sm text-destructive font-medium">
              Error al cargar los tableros
            </p>
            <p className="text-xs text-muted-foreground mt-1">
              Verifica tu conexión e intenta de nuevo
            </p>
          </CardContent>
        </Card>
      ) : dashboards.length === 0 ? (
        <Card className="border-dashed bg-muted/20">
          <CardContent className="flex flex-col items-center justify-center py-20 text-center">
            <div className="relative">
              <div className="absolute inset-0 bg-primary/10 blur-2xl rounded-full" />
              <div className="relative flex h-16 w-16 items-center justify-center rounded-2xl bg-gradient-to-br from-primary/20 to-primary/5 border border-primary/20">
                <LayoutDashboard className="h-7 w-7 text-primary" />
              </div>
            </div>
            <p className="text-lg font-semibold mt-5">No tienes tableros aún</p>
            <p className="text-sm text-muted-foreground mt-1 max-w-xs">
              Crea tu primer tablero o pídele al Asistente IA que lo genere a
              partir de tus datos
            </p>
            <Button className="mt-5" onClick={() => setOpen(true)}>
              <Plus className="mr-2 h-4 w-4" />
              Crear primer tablero
            </Button>
          </CardContent>
        </Card>
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {dashboards.map((dashboard) => (
            <Card
              key={dashboard.dashboard_id}
              className="group flex flex-col overflow-hidden border bg-card transition-all hover:border-primary/40 hover:shadow-md"
            >
              {/* Banner decorativo */}
              <div className="relative h-20 overflow-hidden bg-gradient-to-br from-primary/10 via-primary/5 to-transparent">
                <div className="absolute inset-0 opacity-30 transition-opacity group-hover:opacity-60">
                  <BarChart3
                    className="absolute -bottom-3 -right-3 h-24 w-24 text-primary/40"
                    strokeWidth={1.2}
                  />
                </div>
                <div className="relative flex items-start justify-between p-4">
                  <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-background shadow-sm ring-1 ring-border">
                    <BarChart3 className="h-4 w-4 text-primary" />
                  </div>
                  <Badge
                    variant="outline"
                    className="bg-background/80 backdrop-blur-sm font-mono text-[10px]"
                  >
                    .py
                  </Badge>
                </div>
              </div>

              <CardHeader className="pb-2 pt-3">
                <CardTitle className="text-base font-semibold leading-tight line-clamp-1">
                  {dashboard.name}
                </CardTitle>
                <CardDescription
                  className="line-clamp-2 min-h-[2.5rem] text-xs"
                  title={dashboard.description ?? undefined}
                >
                  {dashboard.description?.trim() || (
                    <span className="italic text-muted-foreground/60">
                      Sin descripción
                    </span>
                  )}
                </CardDescription>
              </CardHeader>

              <CardContent className="mt-auto flex flex-col gap-3 pt-0">
                <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
                  <Clock className="h-3 w-3" />
                  <span title={formatDate(dashboard.created_at)}>
                    {formatRelativeDate(dashboard.created_at)}
                  </span>
                  <span className="text-muted-foreground/40">·</span>
                  <span className="text-muted-foreground/80">
                    {formatDate(dashboard.created_at)}
                  </span>
                </div>

                <div className="flex items-center gap-1.5">
                  <Button asChild size="sm" className="flex-1">
                    <Link href={`/dashboards/${dashboard.dashboard_id}`}>
                      <Eye className="mr-1.5 h-3.5 w-3.5" />
                      Ver tablero
                    </Link>
                  </Button>
                  <Button
                    size="sm"
                    variant="ghost"
                    onClick={() => handleDownload(dashboard.dashboard_id)}
                    disabled={
                      downloadMutation.isPending &&
                      downloadMutation.variables?.id === dashboard.dashboard_id
                    }
                    title="Descargar script .py"
                    aria-label={`Descargar script Python del tablero ${dashboard.name}`}
                    className="h-9 w-9 p-0"
                  >
                    <Download className="h-3.5 w-3.5" />
                  </Button>
                  <AlertDialog>
                    <AlertDialogTrigger asChild>
                      <Button
                        size="sm"
                        variant="ghost"
                        className="h-9 w-9 p-0 text-muted-foreground hover:bg-destructive/10 hover:text-destructive"
                        title="Eliminar tablero"
                        aria-label={`Eliminar tablero ${dashboard.name}`}
                      >
                        <Trash2 className="h-3.5 w-3.5" />
                      </Button>
                    </AlertDialogTrigger>
                    <AlertDialogContent>
                      <AlertDialogHeader>
                        <AlertDialogTitle>Eliminar tablero</AlertDialogTitle>
                        <AlertDialogDescription>
                          Esta acción no se puede deshacer. El tablero{" "}
                          <strong>{dashboard.name}</strong> será eliminado
                          permanentemente, junto con su script y configuración.
                        </AlertDialogDescription>
                      </AlertDialogHeader>
                      <AlertDialogFooter>
                        <AlertDialogCancel>Cancelar</AlertDialogCancel>
                        <AlertDialogAction
                          className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
                          onClick={() =>
                            handleDelete(dashboard.dashboard_id, dashboard.name)
                          }
                        >
                          Eliminar
                        </AlertDialogAction>
                      </AlertDialogFooter>
                    </AlertDialogContent>
                  </AlertDialog>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}
    </div>
  )
}
