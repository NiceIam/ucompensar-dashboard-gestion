"use client"

import { useEffect, useState } from "react"
import { toast } from "sonner"
import { ArrowRight } from "lucide-react"
import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { NativeSelect } from "@/components/kit/native-select"
import { Notice } from "@/components/kit/notice"
import { useOntology, useUpdateRoles } from "@/hooks/use-intake"
import type { OrgTable } from "@/hooks/use-templates"
import { humanizeError } from "@/lib/errors"
import { OTHER_ROLE } from "@/lib/intake/plan"
import type { SheetKind } from "@/types/intake"

/**
 * Corregir lo que entendí de una hoja YA guardada: qué es (ventas, compras...) y para qué sirve cada columna.
 * Lo que la persona elige queda como verdad de esa estructura: la próxima hoja con los mismos encabezados
 * sale ya corregida, sin preguntar.
 */
export function RolesDialog({
  table,
  open,
  onOpenChange,
}: {
  table: OrgTable | null
  open: boolean
  onOpenChange: (open: boolean) => void
}) {
  const { data: ontology, isLoading } = useOntology()
  const update = useUpdateRoles()
  const [kind, setKind] = useState<SheetKind>("otro")
  const [roles, setRoles] = useState<Record<string, string>>({})
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!open || !table) return
    const cols = table.columns_definition ?? []
    setKind(cols[0]?.sheet?.kind ?? "otro")
    setRoles(Object.fromEntries(cols.map((c) => [c.name, c.role ?? OTHER_ROLE])))
    setError(null)
  }, [open, table])

  if (!table) return null
  const cols = table.columns_definition ?? []
  const roleOptions = ontology?.roles?.[kind] ?? []
  const known = Boolean(cols[0]?.sheet)

  function changeKind(next: SheetKind) {
    const valid = new Set((ontology?.roles?.[next] ?? []).map((r) => r.role))
    setKind(next)
    setRoles((cur) => Object.fromEntries(Object.entries(cur).map(([n, r]) => [n, next !== "otro" && valid.has(r) ? r : OTHER_ROLE])))
  }

  function changeRole(column: string, role: string) {
    setRoles((cur) => {
      const next = { ...cur }
      if (role !== OTHER_ROLE) for (const [n, r] of Object.entries(next)) if (n !== column && r === role) next[n] = OTHER_ROLE
      next[column] = role
      return next
    })
  }

  async function save() {
    if (!table) return
    setError(null)
    try {
      await update.mutateAsync({
        tableId: table.id,
        kind,
        roles: Object.fromEntries(Object.entries(roles).map(([n, r]) => [n, r === OTHER_ROLE ? null : r])),
      })
      toast.success("Listo, ya lo entiendo así", { description: "Los hallazgos se recalculan con esto." })
      onOpenChange(false)
    } catch (err) {
      const h = humanizeError(err, "save")
      setError(`${h.title}. ${h.description}`)
    }
  }

  return (
    <Dialog open={open} onOpenChange={(o) => !update.isPending && onOpenChange(o)}>
      <DialogContent className="max-h-[90vh] max-w-2xl overflow-y-auto">
        <DialogHeader>
          <DialogTitle>Lo que entendí de «{table.display_name}»</DialogTitle>
          <DialogDescription>
            {known
              ? "Si algo no es como lo entendí, cámbialo aquí. Tus filas no se tocan."
              : "Esta hoja es de antes y todavía no sé qué es cada columna. Dímelo y calculo mejor tus hallazgos."}
          </DialogDescription>
        </DialogHeader>

        {isLoading || !ontology ? (
          <p className="py-6 text-center text-sm text-muted-foreground" role="status">
            Cargando opciones…
          </p>
        ) : (
          <form
            className="space-y-5"
            onSubmit={(e) => {
              e.preventDefault()
              void save()
            }}
          >
            <div className="space-y-1.5">
              <label htmlFor="roles-kind" className="text-sm font-semibold">
                ¿Qué es esta hoja?
              </label>
              <NativeSelect
                id="roles-kind"
                label="Qué es esta hoja"
                value={kind}
                onChange={(v) => changeKind(v as SheetKind)}
                options={ontology.kinds.map((k) => ({ value: k.kind, label: k.choice_label }))}
              />
            </div>

            <ul className="divide-y rounded-xl border bg-card px-4" aria-label="Columnas">
              {cols.map((c) => {
                const role = roles[c.name] ?? OTHER_ROLE
                const explain = roleOptions.find((r) => r.role === role)?.explain ?? "un dato extra que guardo tal cual"
                return (
                  <li key={c.name} className="grid gap-2 py-3 sm:grid-cols-[minmax(0,1fr)_minmax(0,15rem)] sm:items-center sm:gap-4">
                    <p className="min-w-0 text-[15px] leading-snug">
                      <span className="font-semibold">«{c.label || c.name}»</span>
                      <ArrowRight className="mx-1.5 inline h-3.5 w-3.5 text-muted-foreground" aria-hidden="true" />
                      <span className="text-foreground/85">{explain}</span>
                    </p>
                    <NativeSelect
                      label={`Qué es la columna «${c.label || c.name}»`}
                      value={role}
                      onChange={(v) => changeRole(c.name, v)}
                      options={[
                        ...roleOptions.filter((r) => r.role !== OTHER_ROLE).map((r) => ({ value: r.role, label: r.label })),
                        { value: OTHER_ROLE, label: "Dato adicional (lo guardo tal cual)" },
                      ]}
                    />
                  </li>
                )
              })}
            </ul>

            {error && (
              <Notice tone="danger" title="No se pudo guardar">
                {error}
              </Notice>
            )}

            <DialogFooter className="gap-2 sm:gap-2">
              <Button type="button" variant="ghost" onClick={() => onOpenChange(false)} disabled={update.isPending}>
                Cancelar
              </Button>
              <Button type="submit" loading={update.isPending}>
                Guardar
              </Button>
            </DialogFooter>
          </form>
        )}
      </DialogContent>
    </Dialog>
  )
}
