"use client"

import { PenLine } from "lucide-react"
import { Button } from "@/components/ui/button"
import { useChat } from "@/providers/chat-provider"

const NAME_MAX = 80

/**
 * El nombre del tablero es un dato no confiable: una sola línea, sin comillas angulares (cerrarían la cita
 * antes de tiempo ni caracteres de control) y acotado.
 */
export function safeBoardName(name: string): string {
  // eslint-disable-next-line no-control-regex
  const oneLine = name.replace(/[\x00-\x1f\x7f«»]/g, " ").replace(/\s+/g, " ").trim()
  return oneLine.length > NAME_MAX ? `${oneLine.slice(0, NAME_MAX - 1).trimEnd()}…` : oneLine
}

/** Frase guía que queda escrita en el chat (con el espacio final: la persona completa «agrégale un gráfico de…»). */
export function editPrompt(name: string): string {
  return `Quiero editar el tablero «${safeBoardName(name)}»: `
}

/**
 * «Pídele al asistente que lo edite»: abre el chat con una frase guía SIN enviarla (el mismo mecanismo de
 * «Pídele un tablero al asistente»), para que la persona escriba qué quiere cambiar.
 */
export function EditWithAssistantButton({ name }: { name: string }) {
  const { ask } = useChat()
  const ready = safeBoardName(name).length > 0
  return (
    <div className="pt-1">
      {/* El texto puede partirse en dos líneas: en un encabezado angosto (chat abierto) no debe salirse de su columna. */}
      <Button
        variant="soft"
        disabled={!ready}
        onClick={() => ask(editPrompt(name), { send: false })}
        className="h-auto min-h-11 max-w-full whitespace-normal py-2 text-left sm:h-auto sm:min-h-10"
      >
        <PenLine aria-hidden="true" />
        Pídele al asistente que lo edite
      </Button>
    </div>
  )
}
