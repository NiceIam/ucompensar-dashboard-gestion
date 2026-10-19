"use client"

import { useEffect, useRef, useState } from "react"
import { Check, Copy, Printer, Send } from "lucide-react"
import { Button } from "@/components/ui/button"
import { copyText } from "@/lib/clipboard"
import { whatsappUrl } from "@/lib/insights"
import { cn } from "@/lib/utils"

type CopyState = "idle" | "copied" | "failed"

/**
 * Compartir el resumen: WhatsApp (mensaje ya escrito, la persona elige el
 * contacto), copiar el texto, o imprimir / guardar como PDF.
 */
export function ShareActions({ text, className }: { text: string; className?: string }) {
  const [copy, setCopy] = useState<CopyState>("idle")
  const timer = useRef<number | null>(null)

  useEffect(() => () => {
    if (timer.current) window.clearTimeout(timer.current)
  }, [])

  const onCopy = async () => {
    const ok = await copyText(text)
    setCopy(ok ? "copied" : "failed")
    if (timer.current) window.clearTimeout(timer.current)
    timer.current = window.setTimeout(() => setCopy("idle"), ok ? 2600 : 6000)
  }

  const disabled = !text.trim()

  return (
    <div className={cn("space-y-2", className)}>
      <div className="grid gap-2 sm:flex sm:flex-wrap">
        {disabled ? (
          <Button type="button" disabled className="w-full sm:w-auto">
            <Send aria-hidden="true" />
            Compartir por WhatsApp
          </Button>
        ) : (
          <Button asChild className="w-full sm:w-auto">
            <a href={whatsappUrl(text)} target="_blank" rel="noopener noreferrer">
              <Send aria-hidden="true" />
              Compartir por WhatsApp
              <span className="sr-only"> (se abre en una pestaña nueva)</span>
            </a>
          </Button>
        )}

        <Button type="button" variant="outline" disabled={disabled} onClick={() => void onCopy()} className="w-full sm:w-auto">
          {copy === "copied" ? <Check className="text-success-strong" aria-hidden="true" /> : <Copy aria-hidden="true" />}
          {copy === "copied" ? "Resumen copiado" : "Copiar resumen"}
        </Button>

        <Button type="button" variant="outline" onClick={() => window.print()} className="w-full sm:w-auto">
          <Printer aria-hidden="true" />
          Imprimir / guardar PDF
        </Button>
      </div>

      {/* Confirmación para lector de pantalla y para quien mira: siempre presente en el documento. */}
      <p role="status" aria-live="polite" className={cn("min-h-5 text-sm", copy === "failed" ? "text-danger-strong" : "text-success-strong", copy === "idle" && "sr-only")}>
        {copy === "copied" && "Listo: el resumen quedó copiado, pégalo donde quieras."}
        {copy === "failed" && "No pudimos copiarlo automáticamente. Selecciona el mensaje de más abajo y cópialo."}
      </p>
    </div>
  )
}
