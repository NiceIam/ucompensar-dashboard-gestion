"use client"

import { useState } from "react"
import { ArrowUp, Sparkles } from "lucide-react"
import { SuggestionChips } from "@/components/kit/suggestion-chips"
import { cn } from "@/lib/utils"

/**
 * "Pregúntale a tus datos": la entrada grande de la página de inicio. Al
 * enviar, abre el chat con la pregunta ya enviada.
 */
export function AskBox({
  onAsk,
  suggestions,
  className,
}: {
  onAsk: (question: string) => void
  suggestions: string[]
  className?: string
}) {
  const [value, setValue] = useState("")
  const submit = () => {
    const q = value.trim()
    if (!q) return
    onAsk(q)
    setValue("")
  }
  return (
    <section
      aria-labelledby="ask-title"
      className={cn(
        "relative overflow-hidden rounded-3xl bg-primary px-5 py-7 text-primary-foreground shadow-raised sm:px-8 sm:py-9",
        className
      )}
    >
      {/* Rosa de los vientos decorativa */}
      <svg
        viewBox="0 0 200 200"
        aria-hidden="true"
        className="pointer-events-none absolute -right-10 -top-12 h-64 w-64 text-primary-foreground/[0.07] sm:-right-6 sm:h-72 sm:w-72"
      >
        <circle cx="100" cy="100" r="92" fill="none" stroke="currentColor" strokeWidth="2" />
        <circle cx="100" cy="100" r="64" fill="none" stroke="currentColor" strokeWidth="1.5" strokeDasharray="3 7" />
        <path d="M100 4 L114 100 L100 196 L86 100 Z" fill="currentColor" />
        <path d="M4 100 L100 86 L196 100 L100 114 Z" fill="currentColor" />
      </svg>

      <div className="relative space-y-5">
        <div className="space-y-1.5">
          <p className="inline-flex items-center gap-2 text-[13px] font-semibold uppercase tracking-[0.08em] text-highlight">
            <Sparkles className="h-4 w-4" aria-hidden="true" />
            Asistente
          </p>
          <h2 id="ask-title" className="font-display text-[28px] font-semibold leading-tight sm:text-[34px]">
            Pregúntale a tus datos
          </h2>
          <p className="max-w-xl text-[15px] text-primary-foreground/80">
            Escribe como le hablarías a un colega. Te respondemos con cifras de tus propias hojas.
          </p>
        </div>

        <form
          onSubmit={(e) => {
            e.preventDefault()
            submit()
          }}
          className="flex items-center gap-2 rounded-2xl bg-card p-1.5 pl-4 text-foreground shadow-float focus-within:ring-4 focus-within:ring-highlight/40"
        >
          <label htmlFor="home-ask" className="sr-only">
            Tu pregunta
          </label>
          <input
            id="home-ask"
            value={value}
            onChange={(e) => setValue(e.target.value)}
            placeholder="Ej.: ¿cuál fue mi mejor mes?"
            className="h-12 min-w-0 flex-1 bg-transparent text-base outline-none placeholder:text-muted-foreground/80"
            autoComplete="off"
          />
          <button
            type="submit"
            disabled={!value.trim()}
            className="inline-flex h-12 shrink-0 items-center gap-2 rounded-xl bg-highlight px-4 font-semibold text-highlight-foreground transition hover:bg-highlight/90 disabled:opacity-50"
          >
            <span className="hidden sm:inline">Preguntar</span>
            <ArrowUp className="h-5 w-5" aria-hidden="true" />
            <span className="sr-only sm:hidden">Preguntar</span>
          </button>
        </form>

        {suggestions.length > 0 && (
          <div className="space-y-2">
            <p className="text-sm font-medium text-primary-foreground/75">O prueba con una de estas:</p>
            <SuggestionChips questions={suggestions} onPick={onAsk} className="[&_button]:border-transparent" />
          </div>
        )}
      </div>
    </section>
  )
}
