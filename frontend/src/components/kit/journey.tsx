import { MessageCircleQuestion, Upload, Wand2 } from "lucide-react"
import { cn } from "@/lib/utils"

const STEPS = [
  {
    icon: Upload,
    title: "Sube un archivo",
    text: "Un Excel, un CSV o un JSON, tal como lo tienes. Sin plantillas obligatorias.",
  },
  {
    icon: Wand2,
    title: "Lo entendemos por ti",
    text: "Detectamos fechas, valores y categorías, y te mostramos lo que encontramos.",
  },
  {
    icon: MessageCircleQuestion,
    title: "Pregúntale lo que quieras",
    text: "«¿Cuánto vendí en marzo?» y te responde con cifras reales y gráficos.",
  },
]

/** El recorrido en tres pasos, para estados vacíos y bienvenida. */
export function Journey({ className }: { className?: string }) {
  return (
    <ol className={cn("auto-grid gap-3 [--auto-grid-min:14rem]", className)}>
      {STEPS.map((s, i) => (
        <li key={s.title} className="relative flex gap-3.5 rounded-2xl border bg-card/70 p-4">
          <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-primary-soft text-primary-strong">
            <s.icon className="h-5 w-5" aria-hidden="true" />
          </span>
          <div className="space-y-1">
            <p className="text-sm font-semibold">
              <span className="mr-1.5 font-display text-highlight-strong">{i + 1}.</span>
              {s.title}
            </p>
            <p className="text-[13px] leading-relaxed text-muted-foreground">{s.text}</p>
          </div>
        </li>
      ))}
    </ol>
  )
}
