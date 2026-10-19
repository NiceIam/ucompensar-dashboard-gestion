"use client"

import { useEffect, useState } from "react"
import { Skeleton } from "@/components/ui/skeleton"
import { cn } from "@/lib/utils"
import {
  Wrench,
  Briefcase,
  UtensilsCrossed,
  Building2,
  ShoppingCart,
  HelpCircle,
} from "lucide-react"

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000"

interface BusinessType {
  id: string
  name: string
  display_name: string
  description: string
  icon: string
}

interface BusinessTypesResponse {
  types: BusinessType[]
  total: number
}

function getIcon(name: string) {
  const lower = name.toLowerCase()
  if (lower.includes("ferret") || lower.includes("retail") || lower.includes("hardware")) {
    return Wrench
  }
  if (lower.includes("servic")) {
    return Briefcase
  }
  if (lower.includes("restaur") || lower.includes("food") || lower.includes("comida") || lower.includes("caf")) {
    return UtensilsCrossed
  }
  if (lower.includes("comercio") || lower.includes("tienda")) {
    return ShoppingCart
  }
  if (lower.includes("empresa") || lower.includes("company")) {
    return Building2
  }
  return HelpCircle
}

interface BusinessTypeSelectorProps {
  value: string
  onChange: (id: string) => void
  error?: string
}

export function BusinessTypeSelector({
  value,
  onChange,
  error,
}: BusinessTypeSelectorProps) {
  const [types, setTypes] = useState<BusinessType[]>([])
  const [loading, setLoading] = useState(true)
  const [fetchError, setFetchError] = useState<string | null>(null)
  const [attempt, setAttempt] = useState(0)

  useEffect(() => {
    let cancelled = false

    async function load() {
      setLoading(true)
      setFetchError(null)
      try {
        const res = await fetch(`${API_URL}/api/v1/templates/business-types`)
        if (!res.ok) throw new Error(`HTTP ${res.status}`)
        const data = (await res.json()) as BusinessTypesResponse
        if (!cancelled) {
          setTypes(data.types)
        }
      } catch {
        if (!cancelled) {
          setFetchError("No pudimos cargar los tipos de negocio. Revisa tu conexión e inténtalo de nuevo.")
        }
      } finally {
        if (!cancelled) {
          setLoading(false)
        }
      }
    }

    void load()
    return () => {
      cancelled = true
    }
  }, [attempt])

  if (loading) {
    return (
      <div className="auto-grid gap-3 [--auto-grid-min:10.5rem]">
        {[1, 2, 3].map((i) => (
          <Skeleton key={i} className="h-32 w-full rounded-xl" />
        ))}
      </div>
    )
  }

  if (fetchError) {
    return (
      <div className="flex flex-col items-start gap-3 rounded-xl border border-destructive/30 bg-danger-soft p-4 text-sm text-danger-strong" role="alert">
        <p>{fetchError}</p>
        <button
          type="button"
          onClick={() => setAttempt((a) => a + 1)}
          className="inline-flex min-h-10 items-center rounded-lg border border-current/30 px-3 font-semibold hover:bg-card/50"
        >
          Intentar de nuevo
        </button>
      </div>
    )
  }

  return (
    <div className="space-y-2" role="radiogroup" aria-label="Tipo de negocio">
      <div className="auto-grid gap-3 [--auto-grid-min:10.5rem]">
        {types.map((type) => {
          const Icon = getIcon(type.name)
          const isSelected = value === type.id

          return (
            <button
              key={type.id}
              type="button"
              onClick={() => onChange(type.id)}
              role="radio"
              aria-checked={isSelected}
              className={cn(
                "group relative flex flex-col items-start gap-2 rounded-xl border-2 p-4 text-left transition-all",
                "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2",
                isSelected
                  ? "border-primary bg-primary-soft/60 shadow-card"
                  : "border-border bg-card hover:border-primary/50 hover:bg-muted/50",
              )}
            >
              {/* Selection indicator */}
              <span
                className={cn(
                  "absolute right-3 top-3 flex h-4 w-4 items-center justify-center rounded-full border-2 transition-all",
                  isSelected
                    ? "border-primary bg-primary"
                    : "border-muted-foreground/40 bg-transparent",
                )}
              >
                {isSelected && (
                  <span className="h-1.5 w-1.5 rounded-full bg-primary-foreground" />
                )}
              </span>

              {/* Icon */}
              <span
                className={cn(
                  "flex h-10 w-10 items-center justify-center rounded-lg transition-colors",
                  isSelected
                    ? "bg-primary text-primary-foreground"
                    : "bg-muted text-muted-foreground group-hover:bg-primary/10 group-hover:text-primary",
                )}
              >
                <Icon className="h-5 w-5" />
              </span>

              {/* Text */}
              <div className="min-w-0 flex-1 pr-4">
                <p
                  className={cn(
                    "text-sm font-semibold leading-tight",
                    isSelected ? "text-primary-strong" : "text-foreground",
                  )}
                >
                  {type.display_name}
                </p>
                <p className="mt-1 text-xs leading-snug text-muted-foreground line-clamp-2">
                  {type.description}
                </p>
              </div>
            </button>
          )
        })}
      </div>

      {error && (
        <p className="text-sm font-medium text-destructive">{error}</p>
      )}
    </div>
  )
}
