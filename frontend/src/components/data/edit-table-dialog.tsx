"use client"

import { useEffect, useState } from "react"
import { toast } from "sonner"
import { ChevronDown, Plus, X } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { Field } from "@/components/kit/field"
import { ColumnPill } from "@/components/data/column-kind"
import { useUpdateTable } from "@/hooks/use-data"
import type { OrgTable } from "@/hooks/use-templates"
import { humanizeError } from "@/lib/errors"
import { cn } from "@/lib/utils"

/** Tipos que se pueden elegir al agregar una columna (nombre amable -> tipo del servidor). */
const COLUMN_TYPES = [
  { value: "text", label: "Texto (nombres, categorías)" },
  { value: "integer", label: "Número entero (cantidades)" },
  { value: "float", label: "Número con decimales (precios, valores)" },
  { value: "date", label: "Fecha" },
  { value: "boolean", label: "Sí / No" },
]

/** Igual que el servidor al leer archivos: minúsculas y "_" en vez de espacios. */
export function columnKey(label: string): string {
  return label.trim().toLowerCase().replace(/\s+/g, "_")
}

interface NewColumn {
  label: string
  type: string
}

/** Cambiar el nombre de una hoja y, en ajustes avanzados, agregarle columnas. */
export function EditTableDialog({
  table,
  open,
  onOpenChange,
}: {
  table: OrgTable | null
  open: boolean
  onOpenChange: (open: boolean) => void
}) {
  const update = useUpdateTable()
  const [name, setName] = useState("")
  const [advanced, setAdvanced] = useState(false)
  const [columns, setColumns] = useState<NewColumn[]>([])
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (open && table) {
      setName(table.display_name)
      setColumns([])
      setAdvanced(false)
      setError(null)
    }
  }, [open, table])

  if (!table) return null
  const existing = new Set((table.columns_definition ?? []).map((c) => c.name))

  async function save() {
    if (!table) return
    const trimmed = name.trim()
    if (trimmed.length < 2) {
      setError("Escribe un nombre de al menos 2 letras.")
      return
    }
    const valid = columns.filter((c) => c.label.trim())
    const repeated = valid.find((c) => existing.has(columnKey(c.label)))
    if (repeated) {
      setError(`Ya hay una columna llamada «${repeated.label.trim()}».`)
      return
    }
    setError(null)
    try {
      await update.mutateAsync({
        tableId: table.id,
        newDisplayName: trimmed !== table.display_name ? trimmed : undefined,
        addColumns: valid.map((c) => ({ name: columnKey(c.label), type: c.type, label: c.label.trim() })),
      })
      toast.success("Cambios guardados")
      onOpenChange(false)
    } catch (err) {
      const h = humanizeError(err, "save")
      setError(`${h.title}. ${h.description}`)
    }
  }

  return (
    <Dialog open={open} onOpenChange={(o) => !update.isPending && onOpenChange(o)}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>Editar «{table.display_name}»</DialogTitle>
          <DialogDescription>Cambia cómo se llama. Tus filas no se modifican.</DialogDescription>
        </DialogHeader>

        <form
          className="space-y-5"
          onSubmit={(e) => {
            e.preventDefault()
            void save()
          }}
        >
          <Field label="Nombre" error={error ?? undefined}>
            {({ id, describedBy, invalid }) => (
              <Input id={id} value={name} onChange={(e) => setName(e.target.value)} aria-describedby={describedBy} aria-invalid={invalid} maxLength={150} autoFocus />
            )}
          </Field>

          <div className="space-y-2">
            <p className="text-sm font-semibold">Columnas actuales</p>
            <div className="flex max-h-32 flex-wrap gap-1.5 overflow-y-auto">
              {(table.columns_definition ?? []).map((c) => (
                <ColumnPill key={c.name} column={c} />
              ))}
            </div>
          </div>

          <div className="rounded-xl border">
            <button
              type="button"
              onClick={() => setAdvanced((v) => !v)}
              className="flex min-h-11 w-full items-center justify-between px-4 py-2 text-left text-sm font-semibold"
              aria-expanded={advanced}
            >
              Ajustes avanzados: agregar columnas
              <ChevronDown className={cn("h-4 w-4 transition-transform", advanced && "rotate-180")} aria-hidden="true" />
            </button>
            {advanced && (
              <div className="space-y-3 border-t px-4 py-4">
                <p className="text-[13px] text-muted-foreground">
                  Útil si vas a subir archivos con columnas nuevas. Normalmente no hace falta: al subir un archivo las agregamos solos.
                </p>
                {columns.map((col, i) => (
                  <div key={i} className="flex flex-col gap-2 rounded-lg bg-muted/50 p-2 sm:flex-row sm:items-center">
                    <Input
                      placeholder="Ej.: Fecha de entrega"
                      value={col.label}
                      onChange={(e) => setColumns((cs) => cs.map((c, j) => (j === i ? { ...c, label: e.target.value } : c)))}
                      aria-label={`Nombre de la columna ${i + 1}`}
                      className="sm:flex-1"
                    />
                    <div className="flex items-center gap-2">
                      <Select value={col.type} onValueChange={(v) => setColumns((cs) => cs.map((c, j) => (j === i ? { ...c, type: v } : c)))}>
                        <SelectTrigger className="w-full sm:w-52" aria-label={`Tipo de la columna ${i + 1}`}>
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          {COLUMN_TYPES.map((t) => (
                            <SelectItem key={t.value} value={t.value}>
                              {t.label}
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                      <Button
                        type="button"
                        variant="ghost"
                        size="icon-sm"
                        onClick={() => setColumns((cs) => cs.filter((_, j) => j !== i))}
                        aria-label={`Quitar la columna ${i + 1}`}
                      >
                        <X aria-hidden="true" />
                      </Button>
                    </div>
                  </div>
                ))}
                <Button type="button" variant="outline" size="sm" onClick={() => setColumns((cs) => [...cs, { label: "", type: "text" }])}>
                  <Plus aria-hidden="true" />
                  Agregar una columna
                </Button>
              </div>
            )}
          </div>

          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)} disabled={update.isPending}>
              Cancelar
            </Button>
            <Button type="submit" loading={update.isPending} loadingText="Guardando…">
              Guardar cambios
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
