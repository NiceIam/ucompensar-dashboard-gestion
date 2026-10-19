"use client"

import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from "react"
import { useQueryClient } from "@tanstack/react-query"
import { useFloatingChat, type FloatingChatState } from "@/hooks/use-floating-chat"

/** Pregunta que otra parte de la app le pasa al chat (inicio, cierre del cargue...). */
export interface PendingQuestion {
  id: number
  text: string
  /** true: se envía apenas se abre el chat; false: queda escrita para que la persona la ajuste. */
  send: boolean
}

interface ChatContextValue {
  isOpen: boolean
  open: () => void
  close: () => void
  toggle: () => void
  /** Abre el chat con una pregunta (enviada o solo escrita). */
  ask: (question: string, options?: { send?: boolean }) => void
  pending: PendingQuestion | null
  consumePending: () => void
  chat: FloatingChatState
}

const ChatContext = createContext<ChatContextValue | null>(null)

const STORAGE_KEY = "brujula.chat.open"

function readPreference(): boolean | null {
  try {
    const v = window.localStorage.getItem(STORAGE_KEY)
    return v === null ? null : v === "1"
  } catch {
    return null
  }
}

function savePreference(open: boolean) {
  try {
    window.localStorage.setItem(STORAGE_KEY, open ? "1" : "0")
  } catch {
    // almacenamiento bloqueado (modo privado): no pasa nada
  }
}

function isDesktop(): boolean {
  return typeof window !== "undefined" && window.matchMedia("(min-width: 1024px)").matches
}

/**
 * Estado del chat compartido por toda la app: una sola conversación, el panel
 * abierto/cerrado y la posibilidad de "preguntar" desde cualquier pantalla.
 * Atajo global: Ctrl/⌘ + K abre o cierra el chat.
 */
export function ChatProvider({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient()
  // Si el chat crea un tablero, la lista de tableros se refresca sin esperar a que caduque su caché.
  const chat = useFloatingChat({ onDashboardCreated: () => void queryClient.invalidateQueries({ queryKey: ["dashboards"] }) })
  const [isOpen, setIsOpen] = useState(false)
  const [pending, setPending] = useState<PendingQuestion | null>(null)
  const counter = useRef(0)

  // En escritorio se respeta la última preferencia; en el celular siempre arranca cerrado.
  useEffect(() => {
    if (isDesktop() && readPreference() === true) setIsOpen(true)
    const mq = window.matchMedia("(min-width: 1024px)")
    const onChange = (e: MediaQueryListEvent) => {
      if (!e.matches) setIsOpen(false)
    }
    mq.addEventListener("change", onChange)
    return () => mq.removeEventListener("change", onChange)
  }, [])

  const setOpen = useCallback((next: boolean) => {
    setIsOpen(next)
    if (isDesktop()) savePreference(next)
  }, [])

  const open = useCallback(() => setOpen(true), [setOpen])
  const close = useCallback(() => setOpen(false), [setOpen])
  const toggle = useCallback(() => setIsOpen((prev) => {
    const next = !prev
    if (isDesktop()) savePreference(next)
    return next
  }), [])

  const ask = useCallback(
    (question: string, options?: { send?: boolean }) => {
      const text = question.trim()
      if (!text) return
      counter.current += 1
      setPending({ id: counter.current, text, send: options?.send ?? true })
      setOpen(true)
    },
    [setOpen]
  )

  const consumePending = useCallback(() => setPending(null), [])

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if ((e.ctrlKey || e.metaKey) && !e.altKey && e.key.toLowerCase() === "k") {
        e.preventDefault()
        toggle()
      }
    }
    window.addEventListener("keydown", onKey)
    return () => window.removeEventListener("keydown", onKey)
  }, [toggle])

  const value = useMemo<ChatContextValue>(
    () => ({ isOpen, open, close, toggle, ask, pending, consumePending, chat }),
    [isOpen, open, close, toggle, ask, pending, consumePending, chat]
  )

  return <ChatContext.Provider value={value}>{children}</ChatContext.Provider>
}

export function useChat(): ChatContextValue {
  const ctx = useContext(ChatContext)
  if (!ctx) throw new Error("useChat debe usarse dentro de <ChatProvider>")
  return ctx
}

/** Versión tolerante para componentes que también viven fuera del área con chat. */
export function useOptionalChat(): ChatContextValue | null {
  return useContext(ChatContext)
}
