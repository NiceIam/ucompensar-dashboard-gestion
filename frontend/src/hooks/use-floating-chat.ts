"use client"

import { useCallback, useEffect, useRef, useState } from "react"
import { usePathname } from "next/navigation"
import { api } from "@/lib/api"
import { describeChatError, getChatErrorMessage, isChatLimitError, type ChatErrorInfo } from "@/lib/chat-errors"
import { humanizeError } from "@/lib/errors"
import type { ChatMessage } from "@/types/api"

// El backend devuelve `message_id` en el historial; se normaliza a `id`.
type HistoryMessage = Omit<ChatMessage, "id"> & { id?: string; message_id?: string }

interface ChatHistory {
  messages: HistoryMessage[]
  total: number
}

interface SendMessageResponse {
  message_id: string
  role: "user" | "assistant"
  content: string
  created_at: string
}

interface PageContext {
  label: string
  placeholder: string
}

const PAGE_CONTEXT_MAP: Record<string, PageContext> = {
  "/": {
    label: "Inicio",
    placeholder: "Escribe tu pregunta…",
  },
  "/data": {
    label: "Mis datos",
    placeholder: "Pregunta sobre tus datos…",
  },
  "/dashboards": {
    label: "Tableros",
    placeholder: "Pide un dato o un gráfico…",
  },
  "/settings": {
    label: "Configuración",
    placeholder: "Escribe tu pregunta…",
  },
}

function getPageContext(pathname: string): PageContext {
  // Exact match first
  if (PAGE_CONTEXT_MAP[pathname]) {
    return PAGE_CONTEXT_MAP[pathname]!
  }
  // Prefix match for nested routes
  for (const [key, ctx] of Object.entries(PAGE_CONTEXT_MAP)) {
    if (key !== "/" && pathname.startsWith(key)) {
      return ctx
    }
  }
  return {
    label: "Asistente",
    placeholder: "Escribe tu pregunta…",
  }
}

export interface SendMessageResult {
  /** El backend rechazó el mensaje por límite/cuota (429): no se envió y el texto conviene restaurarlo. */
  rateLimited: boolean
}

export interface FloatingChatState {
  messages: ChatMessage[]
  isLoading: boolean
  isSending: boolean
  /** Mensaje de error ya traducido a lenguaje humano (o null). */
  error: string | null
  /** El mismo error con título, descripción y si se puede reintentar. */
  errorInfo: ChatErrorInfo | null
  /** Texto del último mensaje que falló por red/servidor (para "Reintentar"). */
  lastFailed: string | null
  currentPage: PageContext
  selectedFile: File | null
  sendMessage: (content: string) => Promise<SendMessageResult>
  retryLast: () => Promise<SendMessageResult>
  sendFile: (file: File, message?: string) => Promise<void>
  setSelectedFile: (file: File | null) => void
  clearError: () => void
}

export function useFloatingChat(): FloatingChatState {
  const pathname = usePathname()
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [isLoading, setIsLoading] = useState(false)
  const [isSending, setIsSending] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [errorInfo, setErrorInfo] = useState<ChatErrorInfo | null>(null)
  const [lastFailed, setLastFailed] = useState<string | null>(null)
  const [selectedFile, setSelectedFile] = useState<File | null>(null)
  const hasFetched = useRef(false)

  const currentPage = getPageContext(pathname)

  const loadHistory = useCallback(async () => {
    if (hasFetched.current) return
    hasFetched.current = true
    setIsLoading(true)
    try {
      const data = await api.get<ChatHistory>("/api/v1/chat/history?limit=50")
      setMessages(
        data.messages.map((m, i) => ({
          id: m.id ?? m.message_id ?? `history-${i}`,
          role: m.role,
          content: m.content,
          created_at: m.created_at,
        }))
      )
    } catch {
      // History load failure is non-critical; start with empty state
    } finally {
      setIsLoading(false)
    }
  }, [])

  useEffect(() => {
    void loadHistory()
  }, [loadHistory])

  const sendMessage = useCallback(
    async (content: string) => {
      if (!content.trim() || isSending) return { rateLimited: false }
      setIsSending(true)
      setError(null)
      setErrorInfo(null)
      setLastFailed(null)
      let rateLimited = false

      // Optimistic user message
      const optimisticUser: ChatMessage = {
        id: `optimistic-${Date.now()}`,
        role: "user",
        content: content.trim(),
        created_at: new Date().toISOString(),
      }
      setMessages((prev) => [...prev, optimisticUser])

      try {
        const response = await api.post<SendMessageResponse>(
          "/api/v1/chat/message",
          { content: content.trim() }
        )
        const assistantMsg: ChatMessage = {
          id: response.message_id,
          role: response.role,
          content: response.content,
          created_at: response.created_at,
        }
        setMessages((prev) => [...prev, assistantMsg])
      } catch (err) {
        rateLimited = isChatLimitError(err)
        setError(getChatErrorMessage(err, "No pudimos enviar tu mensaje. Inténtalo de nuevo."))
        const info = describeChatError(err)
        setErrorInfo(info)
        if (info.retryable) setLastFailed(content.trim())
        // Remove optimistic message on failure
        setMessages((prev) =>
          prev.filter((m) => m.id !== optimisticUser.id)
        )
      } finally {
        setIsSending(false)
      }
      return { rateLimited }
    },
    [isSending]
  )

  const sendFile = useCallback(
    async (file: File, message?: string) => {
      if (isSending) return
      setIsSending(true)
      setError(null)
      setErrorInfo(null)
      setLastFailed(null)

      const optimisticUser: ChatMessage = {
        id: `optimistic-file-${Date.now()}`,
        role: "user",
        content: message ?? `Archivo adjunto: ${file.name}`,
        created_at: new Date().toISOString(),
      }
      setMessages((prev) => [...prev, optimisticUser])

      try {
        const formData = new FormData()
        formData.append("file", file)
        if (message) formData.append("message", message)

        const response = await api.upload<SendMessageResponse>(
          "/api/v1/chat/upload",
          formData
        )
        const assistantMsg: ChatMessage = {
          id: response.message_id,
          role: response.role,
          content: response.content,
          created_at: response.created_at,
        }
        setMessages((prev) => [...prev, assistantMsg])
        setSelectedFile(null)
      } catch (err) {
        const h = humanizeError(err, "upload")
        setError(`${h.title}. ${h.description}`)
        setErrorInfo({ title: h.title, description: h.description, retryable: false, rateLimited: false })
        setMessages((prev) =>
          prev.filter((m) => m.id !== optimisticUser.id)
        )
      } finally {
        setIsSending(false)
      }
    },
    [isSending]
  )

  const clearError = useCallback(() => {
    setError(null)
    setErrorInfo(null)
  }, [])

  const retryLast = useCallback(async () => {
    if (!lastFailed) return { rateLimited: false }
    return sendMessage(lastFailed)
  }, [lastFailed, sendMessage])

  return {
    messages,
    isLoading,
    isSending,
    error,
    errorInfo,
    lastFailed,
    currentPage,
    selectedFile,
    sendMessage,
    retryLast,
    sendFile,
    setSelectedFile,
    clearError,
  }
}
