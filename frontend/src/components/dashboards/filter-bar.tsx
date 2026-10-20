"use client"

import { useEffect, useMemo, useState } from "react"
import { CalendarDays, Check, ChevronDown, Search, SlidersHorizontal, X } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover"
import { useFilterValueSearch } from "@/hooks/use-dashboards"
import {
  MAX_CATEGORIES,
  PRESETS,
  describeFilters,
  hasActiveFilters,
  periodLabel,
  removeFilter,
  setCategory,
  setPeriod,
  validateRange,
} from "@/lib/dashboard-filters"
import { formatNumber } from "@/lib/format"
import { cn } from "@/lib/utils"
import type { DashboardFilters, FilterDimension, FilterOptions } from "@/types/dashboard-filters"

const triggerClass =
  "inline-flex min-h-11 max-w-full items-center gap-2 rounded-xl border border-input bg-card px-3.5 text-sm font-semibold transition hover:border-foreground/25 hover:bg-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring sm:min-h-10"

// ─── Periodo ────────────────────────────────────────────────────────────────

function PeriodPicker({ filters, options, onChange }: { filters: DashboardFilters; options?: FilterOptions; onChange: (next: DashboardFilters) => void }) {
  const [open, setOpen] = useState(false)
  const [from, setFrom] = useState(filters.period?.from ?? "")
  const [to, setTo] = useState(filters.period?.to ?? "")
  const [error, setError] = useState<string | null>(null)
  const current = filters.period?.preset ?? (filters.period ? "custom" : "all")

  useEffect(() => {
    if (open) {
      setFrom(filters.period?.from ?? "")
      setTo(filters.period?.to ?? "")
      setError(null)
    }
  }, [open, filters.period])

  function choose(id: (typeof PRESETS)[number]["id"]) {
    onChange(setPeriod(filters, id === "all" ? null : { preset: id }))
    setOpen(false)
  }

  function applyRange() {
    const problem = validateRange(from || undefined, to || undefined)
    if (problem) {
      setError(problem)
      return
    }
    onChange(setPeriod(filters, { ...(from ? { from } : {}), ...(to ? { to } : {}) }))
    setOpen(false)
  }

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <button type="button" className={triggerClass} aria-label={`Período: ${periodLabel(filters.period)}. Cambiar`}>
          <CalendarDays className="h-4 w-4 shrink-0 text-primary" aria-hidden="true" />
          <span className="truncate">
            <span className="font-medium text-muted-foreground">Período: </span>
            {periodLabel(filters.period)}
          </span>
          <ChevronDown className="h-4 w-4 shrink-0 opacity-60" aria-hidden="true" />
        </button>
      </PopoverTrigger>
      <PopoverContent
        align="start"
        collisionPadding={12}
        className="max-h-[var(--radix-popover-content-available-height)] w-[min(22rem,calc(100vw-2rem))] space-y-4 overflow-y-auto p-4"
      >
        <div role="group" aria-label="Atajos de período" className="grid grid-cols-2 gap-2">
          {PRESETS.map((p) => (
            <button
              key={p.id}
              type="button"
              aria-pressed={current === p.id}
              onClick={() => choose(p.id)}
              className={cn(
                "flex min-h-11 items-center justify-between gap-2 rounded-lg border px-3 text-left text-sm font-medium transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
                current === p.id ? "border-primary bg-primary-soft text-primary-strong" : "border-input hover:bg-accent"
              )}
            >
              {p.label}
              {current === p.id && <Check className="h-4 w-4 shrink-0" aria-hidden="true" />}
            </button>
          ))}
        </div>
        <fieldset className="space-y-3 border-t pt-4">
          <legend className="sr-only">Rango de fechas</legend>
          <p className="text-sm font-semibold">Elige un rango</p>
          <div className="grid grid-cols-2 gap-3">
            <label className="space-y-1 text-[13px] font-medium text-muted-foreground">
              Desde
              <Input type="date" value={from} min={options?.date?.min} max={options?.date?.max ?? undefined} onChange={(e) => setFrom(e.target.value)} className="text-foreground" />
            </label>
            <label className="space-y-1 text-[13px] font-medium text-muted-foreground">
              Hasta
              <Input type="date" value={to} min={options?.date?.min} max={options?.date?.max ?? undefined} onChange={(e) => setTo(e.target.value)} className="text-foreground" />
            </label>
          </div>
          {options?.date && (
            <p className="text-xs text-muted-foreground">
              Tus datos van del {options.date.min.split("-").reverse().join("/")} al {options.date.max.split("-").reverse().join("/")}.
            </p>
          )}
          {error && (
            <p role="alert" className="text-sm font-medium text-danger-strong">
              {error}
            </p>
          )}
          <Button type="button" className="w-full" onClick={applyRange}>
            Aplicar rango
          </Button>
        </fieldset>
      </PopoverContent>
    </Popover>
  )
}

// ─── Categorías ─────────────────────────────────────────────────────────────

function ValuePicker({
  dashboardId,
  dim,
  filters,
  onChange,
}: {
  dashboardId: string
  dim: FilterDimension
  filters: DashboardFilters
  onChange: (next: DashboardFilters) => void
}) {
  const [open, setOpen] = useState(false)
  const [q, setQ] = useState("")
  const [debounced, setDebounced] = useState("")
  const selected = useMemo(() => filters.where.find((w) => w.key === dim.key)?.values ?? [], [filters.where, dim.key])
  const active = selected.length > 0
  const blocked = !active && filters.where.length >= MAX_CATEGORIES

  useEffect(() => {
    const t = window.setTimeout(() => setDebounced(q), 250)
    return () => window.clearTimeout(t)
  }, [q])
  useEffect(() => {
    if (!open) setQ("")
  }, [open])

  // Con más valores que los listados, se busca en el servidor (sobre TODOS); si no, se filtra la lista local.
  const remote = dim.more > 0 && debounced.trim().length > 0
  const search = useFilterValueSearch(dashboardId, remote ? dim.key : null, debounced)
  const found = search.data?.dimensions.find((d) => d.key === dim.key)?.values
  const base = remote ? (found ?? []) : dim.values.filter((v) => v.value.toLowerCase().includes(q.trim().toLowerCase()))
  // Lo ya elegido siempre se ve (aunque no esté entre los más frecuentes).
  const listed = new Set(base.map((v) => v.value.toLowerCase()))
  const pinned = q.trim() ? [] : selected.filter((v) => !listed.has(v.toLowerCase())).map((v) => ({ value: v, count: 0 }))
  const rows = [...pinned, ...base]

  function toggle(value: string) {
    const has = selected.some((v) => v.toLowerCase() === value.toLowerCase())
    const next = has ? selected.filter((v) => v.toLowerCase() !== value.toLowerCase()) : [...selected, value]
    onChange(setCategory(filters, dim.key, next))
  }

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <button
          type="button"
          disabled={blocked}
          title={blocked ? `Puedes filtrar por ${MAX_CATEGORIES} cosas a la vez; quita un filtro para usar este.` : undefined}
          aria-label={active ? `${dim.label}: ${selected.length} elegidos. Cambiar` : `Filtrar por ${dim.label.toLowerCase()}`}
          className={cn(triggerClass, active && "border-primary bg-primary-soft text-primary-strong", "disabled:cursor-not-allowed disabled:opacity-50")}
        >
          <span className="truncate">{dim.label}</span>
          {active && <span className="rounded-full bg-primary px-1.5 text-xs font-semibold text-primary-foreground">{selected.length}</span>}
          <ChevronDown className="h-4 w-4 shrink-0 opacity-60" aria-hidden="true" />
        </button>
      </PopoverTrigger>
      <PopoverContent
        align="start"
        collisionPadding={12}
        className="flex max-h-[var(--radix-popover-content-available-height)] w-[min(22rem,calc(100vw-2rem))] flex-col gap-3 p-3"
      >
        <div className="relative shrink-0">
          <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" aria-hidden="true" />
          <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder={`Buscar ${dim.label.toLowerCase()}`} aria-label={`Buscar ${dim.label.toLowerCase()}`} className="pl-9" />
        </div>
        <ul className="min-h-24 flex-1 space-y-0.5 overflow-y-auto" aria-label={dim.label}>
          {rows.map((v) => {
            const checked = selected.some((s) => s.toLowerCase() === v.value.toLowerCase())
            return (
              <li key={v.value}>
                <label className="flex min-h-11 cursor-pointer items-center gap-3 rounded-lg px-2 text-sm hover:bg-accent has-[:focus-visible]:ring-2 has-[:focus-visible]:ring-ring">
                  <input type="checkbox" checked={checked} onChange={() => toggle(v.value)} className="h-4 w-4 shrink-0 accent-[hsl(var(--primary))]" />
                  <span className="min-w-0 flex-1 truncate">{v.value}</span>
                  {v.count > 0 && <span className="tabular text-xs text-muted-foreground">{formatNumber(v.count, 0)}</span>}
                </label>
              </li>
            )
          })}
          {rows.length === 0 && (
            <li className="px-2 py-3 text-sm text-muted-foreground" role="status">
              {remote && search.isFetching ? "Buscando…" : "No encontré ese valor."}
            </li>
          )}
        </ul>
        {dim.more > 0 && !q.trim() && <p className="shrink-0 px-1 text-xs text-muted-foreground">Y {formatNumber(dim.more, 0)} más: escribe arriba para buscarlos.</p>}
        <div className="flex shrink-0 items-center justify-between gap-2 border-t pt-3">
          <Button type="button" variant="ghost" size="sm" disabled={!active} onClick={() => onChange(setCategory(filters, dim.key, []))}>
            Quitar filtro
          </Button>
          <Button type="button" size="sm" onClick={() => setOpen(false)}>
            Listo
          </Button>
        </div>
      </PopoverContent>
    </Popover>
  )
}

// ─── Barra ──────────────────────────────────────────────────────────────────

/**
 * Filtros del tablero: periodo con atajos y categorías (producto, cliente...) con búsqueda. Los filtros activos
 * se ven como fichas con «Quitar». El estado lo guarda la página en la URL (compartible).
 */
export function FilterBar({
  dashboardId,
  options,
  loading,
  filters,
  onChange,
  busy,
}: {
  dashboardId: string
  options?: FilterOptions
  loading?: boolean
  filters: DashboardFilters
  onChange: (next: DashboardFilters) => void
  busy?: boolean
}) {
  const chips = describeFilters(filters, options?.dimensions)
  const hasDims = (options?.dimensions.length ?? 0) > 0
  return (
    <section aria-label="Filtros del tablero" className="surface space-y-3 p-3 sm:p-4" aria-busy={busy}>
      <div className="flex flex-wrap items-center gap-2">
        <span className="mr-1 inline-flex items-center gap-1.5 text-sm font-semibold text-muted-foreground">
          <SlidersHorizontal className="h-4 w-4" aria-hidden="true" />
          Filtrar
        </span>
        <PeriodPicker filters={filters} options={options} onChange={onChange} />
        {options?.dimensions.map((dim) => (
          <ValuePicker key={dim.key} dashboardId={dashboardId} dim={dim} filters={filters} onChange={onChange} />
        ))}
        {loading && !hasDims && <span className="text-sm text-muted-foreground">Cargando opciones…</span>}
      </div>
      {chips.length > 0 && (
        <div className="flex flex-wrap items-center gap-2 border-t pt-3" role="group" aria-label="Filtros activos">
          <span className="text-[13px] font-medium text-muted-foreground">Filtros activos:</span>
          {chips.map((chip) => (
            <span key={chip.id} className="inline-flex min-h-9 max-w-full items-center gap-1 rounded-full bg-primary-soft pl-3 pr-1 text-[13px] text-primary-strong">
              <span className="truncate">
                <span className="font-medium">{chip.name}: </span>
                <span className="font-semibold">{chip.text}</span>
              </span>
              <button
                type="button"
                onClick={() => onChange(removeFilter(filters, chip.id))}
                aria-label={`Quitar filtro ${chip.name}`}
                className="inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-full transition hover:bg-primary/15 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              >
                <X className="h-3.5 w-3.5" aria-hidden="true" />
              </button>
            </span>
          ))}
          {hasActiveFilters(filters) && chips.length > 1 && (
            <Button type="button" variant="ghost" size="sm" onClick={() => onChange({ period: null, where: [] })}>
              Quitar todos
            </Button>
          )}
        </div>
      )}
    </section>
  )
}
