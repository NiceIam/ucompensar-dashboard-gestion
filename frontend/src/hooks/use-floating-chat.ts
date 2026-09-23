"use client"

import { useCallback, useEffect, useRef, useState } from "react"
import { usePathname } from "next/navigation"
import { api } from "@/lib/api"
import type { ChatMessage } from "@/types/api"

interface ChatHistory {
  messages: ChatMessage[]
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
    label: "Dashboard",
    placeholder: "Pregunta sobre tu dashboard...",
  },
  "/data": {
    label: "Datos",
    placeholder: "Pregunta sobre tus datos...",
  },
  "/dashboards": {
    label: "Tableros",
    placeholder: "Pregunta sobre tus tableros...",
  },
  "/settings": {
    label: "Configuración",
    placeholder: "Pregunta sobre configuración...",
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
    placeholder: "Escribe un mensaje...",
  }
}

export interface FloatingChatState {
  messages: ChatMessage[]
  isLoading: boolean
  isSending: boolean
  error: string | null
  currentPage: PageContext
  selectedFile: File | null
  sendMessage: (content: string) => Promise<void>
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
  const [selectedFile, setSelectedFile] = useState<File | null>(null)
  const hasFetched = useRef(false)

  const currentPage = getPageContext(pathname)

  const loadHistory = useCallback(async () => {
    if (hasFetched.current) return
    hasFetched.current = true
    setIsLoading(true)
    try {
      const data = await api.get<ChatHistory>("/api/v1/chat/history?limit=50")
      setMessages(data.messages)
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
      if (!content.trim() || isSending) return
      setIsSending(true)
      setError(null)

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
        setError(
          err instanceof Error ? err.message : "Error al enviar el mensaje"
        )
        // Remove optimistic message on failure
        setMessages((prev) =>
          prev.filter((m) => m.id !== optimisticUser.id)
        )
      } finally {
        setIsSending(false)
      }
    },
    [isSending]
  )

  const sendFile = useCallback(
    async (file: File, message?: string) => {
      if (isSending) return
      setIsSending(true)
      setError(null)

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
        setError(
          err instanceof Error ? err.message : "Error al subir el archivo"
        )
        setMessages((prev) =>
          prev.filter((m) => m.id !== optimisticUser.id)
        )
      } finally {
        setIsSending(false)
      }
    },
    [isSending]
  )

  const clearError = useCallback(() => setError(null), [])

  return {
    messages,
    isLoading,
    isSending,
    error,
    currentPage,
    selectedFile,
    sendMessage,
    sendFile,
    setSelectedFile,
    clearError,
  }
}
