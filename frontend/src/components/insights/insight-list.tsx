import { InsightCard } from "@/components/kit/insight-card"
import type { Insight } from "@/types/insights"

/**
 * Lista de hallazgos: el más importante va a todo el ancho como protagonista y
 * los demás en dos columnas (una sola en el celular).
 */
export function InsightList({ items, onAsk }: { items: Insight[]; onAsk?: (question: string) => void }) {
  return (
    <ul className="grid items-start gap-5 md:grid-cols-2 print:block print:space-y-4">
      {items.map((insight, i) => (
        <li key={insight.id} className={i === 0 ? "min-w-0 md:col-span-2" : "min-w-0"}>
          <InsightCard insight={insight} onAsk={onAsk} as="h3" featured={i === 0} />
        </li>
      ))}
    </ul>
  )
}
