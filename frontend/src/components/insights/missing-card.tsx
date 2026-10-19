import type { ElementType } from "react"
import Link from "next/link"
import { FilePlus2, Upload } from "lucide-react"
import { Button } from "@/components/ui/button"
import type { MissingInsight } from "@/types/insights"

/**
 * Algo que todavía no podemos contarte y lo que hace falta para lograrlo,
 * dicho en lenguaje simple, con el camino directo a subir esos datos.
 */
export function MissingCard({ item, as: Heading = "h3" }: { item: MissingInsight; as?: ElementType }) {
  return (
    <article className="flex min-w-0 flex-col gap-4 rounded-2xl border border-dashed bg-card/60 p-5">
      <div className="flex items-start gap-3">
        <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-highlight-soft text-highlight-strong">
          <FilePlus2 className="h-5 w-5" aria-hidden="true" />
        </span>
        <div className="min-w-0 space-y-1.5">
          <Heading className="font-display text-lg font-semibold leading-snug text-balance">{item.title}</Heading>
          <p className="text-[15px] leading-relaxed text-muted-foreground text-pretty">
            <span className="font-semibold text-foreground/85">Necesito: </span>
            {item.needs}
          </p>
        </div>
      </div>
      <Button asChild variant="outline" className="mt-auto w-full sm:w-fit">
        <Link href="/data" aria-label={`Subir mis datos para ver: ${item.title}`}>
          <Upload aria-hidden="true" />
          Subir mis datos
        </Link>
      </Button>
    </article>
  )
}
