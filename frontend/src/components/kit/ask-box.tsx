"use client"

import { useState } from "react"
import { ArrowUp, Sparkles } from "lucide-react"
import { DotField } from "@/components/kit/dots"
import { SuggestionChips } from "@/components/kit/suggestion-chips"
import { cn } from "@/lib/utils"

/**
 * "Pregúntale a tus datos": la entrada grande de la página de inicio. Al
 * enviar, abre el chat con la pregunta ya enviada.
 */
export function AskBox({
  onAsk,
  suggestions,
  compact = false,
  className,
}: {
  onAsk: (question: string) => void
  suggestions: string[]
  /** Versión más baja (el inicio ya tiene los hallazgos como protagonistas). */
  compact?: boolean
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
        "relative overflow-hidden rounded-3xl bg-brand px-5 py-7 text-brand-foreground shadow-card ring-1 ring-inset ring-highlight/15 sm:px-8 sm:py-9",
        compact && "py-5 sm:px-7 sm:py-6",
        className
      )}
    >
      <DotField fade="top-right" className="[--dots-alpha:0.35] [--dots-gap:20px] [--dots-size:1.8px]" />

      <div className={cn("relative", compact ? "space-y-4" : "space-y-5")}>
        <div className="space-y-1.5">
          <p className="inline-flex items-center gap-2 text-[13px] font-semibold uppercase tracking-[0.08em] text-primary-strong">
            <Sparkles className="h-4 w-4 text-highlight" aria-hidden="true" />
            Asistente
          </p>
          <h2
            id="ask-title"
            className={cn("font-display font-semibold leading-tight", compact ? "text-[24px] sm:text-[26px]" : "text-[28px] sm:text-[34px]")}
          >
            Pregúntale a tus datos
          </h2>
          <p className="max-w-xl text-[15px] text-brand-foreground/80">
            {compact
              ? "¿Quieres saber algo más? Escríbelo como se lo dirías a un colega."
              : "Escribe como le hablarías a un colega. Te respondemos con cifras de tus propias hojas."}
          </p>
        </div>

        <form
          onSubmit={(e) => {
            e.preventDefault()
            submit()
          }}
          className="flex items-center gap-2 rounded-2xl bg-card p-1.5 pl-4 text-foreground shadow-float ring-1 ring-border focus-within:ring-4 focus-within:ring-highlight/35"
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
            className="inline-flex h-12 shrink-0 items-center gap-2 rounded-xl bg-primary px-4 font-semibold text-primary-foreground transition hover:bg-primary-hover disabled:opacity-50"
          >
            <span className="hidden sm:inline">Preguntar</span>
            <ArrowUp className="h-5 w-5" aria-hidden="true" />
            <span className="sr-only sm:hidden">Preguntar</span>
          </button>
        </form>

        {suggestions.length > 0 && (
          <div className="space-y-2">
            <p className="text-sm font-medium text-brand-foreground/75">O prueba con una de estas:</p>
            <SuggestionChips questions={suggestions} onPick={onAsk} />
          </div>
        )}
      </div>
    </section>
  )
}
