"use client"

import { ArrowUpRight, MessageCircleQuestion } from "lucide-react"
import { cn } from "@/lib/utils"

/** Preguntas sugeridas como chips grandes y tocables. */
export function SuggestionChips({
  questions,
  onPick,
  className,
  layout = "wrap",
  disabled = false,
}: {
  questions: string[]
  onPick: (question: string) => void
  className?: string
  /** "wrap": en línea; "stack": una debajo de otra (paneles angostos). */
  layout?: "wrap" | "stack"
  disabled?: boolean
}) {
  if (questions.length === 0) return null
  return (
    <ul className={cn(layout === "wrap" ? "flex flex-wrap gap-2" : "flex flex-col gap-2", className)}>
      {questions.map((q) => (
        <li key={q} className={layout === "stack" ? "w-full" : undefined}>
          <button
            type="button"
            disabled={disabled}
            onClick={() => onPick(q)}
            className={cn(
              "group inline-flex min-h-11 items-center gap-2.5 rounded-xl border bg-card px-3.5 py-2 text-left text-sm font-medium text-foreground shadow-card transition-[border-color,background-color,transform] duration-150 hover:-translate-y-px hover:border-primary/40 hover:bg-primary-soft/50 disabled:pointer-events-none disabled:opacity-60",
              layout === "stack" && "w-full"
            )}
          >
            <MessageCircleQuestion className="h-4 w-4 shrink-0 text-primary" aria-hidden="true" />
            <span className="flex-1">{q}</span>
            <ArrowUpRight
              className="h-4 w-4 shrink-0 text-muted-foreground transition-transform group-hover:-translate-y-0.5 group-hover:translate-x-0.5 group-hover:text-primary"
              aria-hidden="true"
            />
          </button>
        </li>
      ))}
    </ul>
  )
}
