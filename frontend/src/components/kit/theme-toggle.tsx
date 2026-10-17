"use client"

import { useEffect, useState } from "react"
import { Monitor, Moon, Sun } from "lucide-react"
import { useTheme } from "next-themes"
import { cn } from "@/lib/utils"

const OPTIONS = [
  { value: "light", label: "Claro", icon: Sun },
  { value: "dark", label: "Oscuro", icon: Moon },
  { value: "system", label: "Como mi dispositivo", icon: Monitor },
] as const

/** Selector de tema de tres opciones (control segmentado accesible). */
export function ThemeSwitcher({ className, showLabels = false }: { className?: string; showLabels?: boolean }) {
  const { theme, setTheme } = useTheme()
  const [mounted, setMounted] = useState(false)
  useEffect(() => setMounted(true), [])
  const current = mounted ? theme ?? "system" : undefined

  return (
    <div role="radiogroup" aria-label="Apariencia" className={cn("inline-flex rounded-xl border bg-muted/60 p-1", className)}>
      {OPTIONS.map(({ value, label, icon: Icon }) => {
        const active = current === value
        return (
          <button
            key={value}
            type="button"
            role="radio"
            aria-checked={active}
            aria-label={label}
            title={label}
            onClick={() => setTheme(value)}
            className={cn(
              "inline-flex h-11 min-w-11 items-center justify-center gap-2 rounded-lg px-2.5 text-sm font-medium transition-colors sm:h-8 sm:min-w-8",
              active ? "bg-card text-foreground shadow-card" : "text-muted-foreground hover:text-foreground"
            )}
          >
            <Icon className="h-4 w-4" aria-hidden="true" />
            {showLabels && <span>{label}</span>}
          </button>
        )
      })}
    </div>
  )
}
