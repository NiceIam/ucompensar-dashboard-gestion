import { useMemo } from "react"
import { TriangleAlert } from "lucide-react"
import { InsightCard } from "@/components/kit/insight-card"
import { splitCommonNotes } from "@/lib/insights"
import type { Insight } from "@/types/insights"

/**
 * Lista de hallazgos: el primero (el que el servidor puso de primero) va a todo el
 * ancho como protagonista y los demás en dos columnas (una sola en el celular).
 * Los avisos que se repiten en varios hallazgos salen UNA vez, arriba; cada tarjeta
 * conserva solo los suyos.
 */
export function InsightList({ items, onAsk }: { items: Insight[]; onAsk?: (question: string) => void }) {
  const { common, items: cards } = useMemo(() => splitCommonNotes(items), [items])
  return (
    <div className="space-y-4">
      {common.length > 0 && <CommonNotes notes={common} />}
      <ul className="grid items-start gap-5 md:grid-cols-2 print:block print:space-y-4">
        {cards.map((insight, i) => (
          <li key={insight.id} className={i === 0 ? "min-w-0 md:col-span-2" : "min-w-0"}>
            <InsightCard insight={insight} onAsk={onAsk} as="h3" featured={i === 0} />
          </li>
        ))}
      </ul>
    </div>
  )
}

/** Franja discreta con los avisos que valen para todos los hallazgos de abajo (icono + texto). */
function CommonNotes({ notes }: { notes: string[] }) {
  return (
    <div
      role="note"
      aria-label="Avisos que aplican a todos los hallazgos"
      className="flex gap-3 rounded-xl border bg-muted/50 px-4 py-3 print:break-inside-avoid"
    >
      <TriangleAlert className="mt-0.5 h-4 w-4 shrink-0 text-warning-strong" aria-hidden="true" />
      <div className="min-w-0 space-y-1">
        <p className="text-[13px] font-semibold uppercase tracking-[0.08em] text-muted-foreground">Ten en cuenta</p>
        {notes.length === 1 ? (
          <p className="text-sm leading-relaxed text-foreground/85">{notes[0]}</p>
        ) : (
          <ul className="list-disc space-y-1 pl-4 text-sm leading-relaxed text-foreground/85">
            {notes.map((n) => (
              <li key={n}>{n}</li>
            ))}
          </ul>
        )}
      </div>
    </div>
  )
}
