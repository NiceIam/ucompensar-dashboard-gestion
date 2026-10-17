"use client"

import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type KeyboardEvent,
} from "react"
import {
  X,
  Paperclip,
  Send,
  Plus,
  Trash2,
  Sparkles,
  Loader2,
  Bot,
  User,
  PanelRightClose,
  PanelRightOpen,
} from "lucide-react"
import {
  BarChart, Bar, LineChart, Line, PieChart, Pie, Cell,
  XAxis, YAxis, CartesianGrid, Tooltip as RechartsTooltip,
  ResponsiveContainer,
} from "recharts"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Badge } from "@/components/ui/badge"
import { ScrollArea } from "@/components/ui/scroll-area"
import { cn } from "@/lib/utils"
import { useChat } from "@/providers/chat-provider"

interface ChatMessage {
  id: string
  role: "user" | "assistant"
  content: string
  created_at: string
}

// ─── Inline chart colors ───────────────────────────────────────────────────

const PIE_COLORS = ["#F37021", "#8B6AAD", "#2ABFBF", "#4A2D6B", "#E8A838", "#D4572A", "#6B4E8B", "#1A9E9E"]

interface ChartConfig {
  type: string
  title: string
  data: { name: string; value: number }[]
  x: string
  y: string
  color: string
}

function InlineChart({ config }: { config: ChartConfig }) {
  if (!config.data || config.data.length === 0) return null

  return (
    <div className="my-2 rounded-lg border bg-background p-2">
      <p className="text-[10px] font-medium text-muted-foreground mb-1">{config.title}</p>
      <ResponsiveContainer width="100%" height={150}>
        {config.type === "pie" ? (
          <PieChart>
            <Pie data={config.data} dataKey="value" nameKey="name" cx="50%" cy="50%" outerRadius={55} label={false}>
              {config.data.map((_, i) => (
                <Cell key={i} fill={PIE_COLORS[i % PIE_COLORS.length]} />
              ))}
            </Pie>
            <RechartsTooltip />
          </PieChart>
        ) : config.type === "line" ? (
          <LineChart data={config.data}>
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis dataKey="name" tick={{ fontSize: 9 }} />
            <YAxis tick={{ fontSize: 9 }} />
            <RechartsTooltip />
            <Line type="monotone" dataKey="value" stroke={config.color} strokeWidth={2} dot={{ r: 2 }} />
          </LineChart>
        ) : (
          <BarChart data={config.data}>
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis dataKey="name" tick={{ fontSize: 9 }} />
            <YAxis tick={{ fontSize: 9 }} />
            <RechartsTooltip />
            <Bar dataKey="value" fill={config.color} radius={[3, 3, 0, 0]} />
          </BarChart>
        )}
      </ResponsiveContainer>
    </div>
  )
}

// ─── Content renderer (bold, listas, titulos + charts) ─────────────────────

// Aplica **negrita** dentro de una linea de texto plana.
function renderInline(text: string, keyPrefix: string): React.ReactNode[] {
  const boldParts = text.split(/(\*\*[^*]+\*\*)/)
  return boldParts.map((bp, j) =>
    bp.startsWith("**") && bp.endsWith("**") ? (
      <strong key={`${keyPrefix}-b${j}`}>{bp.slice(2, -2)}</strong>
    ) : (
      <span key={`${keyPrefix}-t${j}`}>{bp}</span>
    )
  )
}

// Filas de una tabla markdown ("| a | b |") -> celdas sin las barras externas.
function parseTableRow(line: string): string[] {
  const trimmed = line.trim().replace(/^\|/, "").replace(/\|$/, "")
  return trimmed.split("|").map((c) => c.trim())
}

// Fila separadora de tabla markdown: "| --- | :--- |" (solo guiones/dos puntos).
function isTableSeparatorRow(line: string): boolean {
  if (!line.trim().startsWith("|")) return false
  const cells = parseTableRow(line)
  return cells.length > 0 && cells.every((c) => /^:?-{2,}:?$/.test(c))
}

// Convierte un bloque de texto (sin chart) linea por linea: reconoce
// "## titulo", "- item" / "* item", "1. item", tablas "| a | b |" y
// separadores "---" como markdown basico, en vez de mostrar los simbolos
// literales. Cualquier otra linea es un parrafo.
function renderTextBlock(text: string, keyPrefix: string): React.ReactNode {
  const lines = text.split("\n")
  const blocks: React.ReactNode[] = []
  let list: { type: "ul" | "ol"; items: string[] } | null = null

  const flushList = () => {
    if (!list) return
    const items = list.items
    const ListTag = list.type
    blocks.push(
      <ListTag
        key={`${keyPrefix}-list${blocks.length}`}
        className={cn("my-1 space-y-0.5", ListTag === "ul" ? "list-disc pl-4" : "list-decimal pl-4")}
      >
        {items.map((item, i) => (
          <li key={i}>{renderInline(item, `${keyPrefix}-li${blocks.length}-${i}`)}</li>
        ))}
      </ListTag>
    )
    list = null
  }

  let i = 0
  while (i < lines.length) {
    const line = lines[i]

    // Tabla markdown: fila de encabezado seguida de una fila separadora.
    if (line.trim().startsWith("|") && i + 1 < lines.length && isTableSeparatorRow(lines[i + 1])) {
      flushList()
      const header = parseTableRow(line)
      const rows: string[][] = []
      let j = i + 2
      while (j < lines.length && lines[j].trim().startsWith("|")) {
        rows.push(parseTableRow(lines[j]))
        j++
      }
      blocks.push(
        <div key={`${keyPrefix}-tbl${i}`} className="my-1.5 overflow-x-auto rounded-md border">
          <table className="w-full text-xs">
            <thead className="bg-background/60">
              <tr>
                {header.map((h, hi) => (
                  <th key={hi} className="border-b px-2 py-1 text-left font-medium">
                    {renderInline(h, `${keyPrefix}-th${i}-${hi}`)}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((row, ri) => (
                <tr key={ri} className="border-b last:border-0">
                  {row.map((cell, ci) => (
                    <td key={ci} className="px-2 py-1">
                      {renderInline(cell, `${keyPrefix}-td${i}-${ri}-${ci}`)}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )
      i = j
      continue
    }

    // Linea divisoria sola ("---", "***", "___").
    if (/^(---|\*\*\*|___)$/.test(line.trim())) {
      flushList()
      blocks.push(<hr key={`${keyPrefix}-hr${i}`} className="my-1.5 border-border" />)
      i++
      continue
    }

    const heading = line.match(/^#{1,3}\s+(.*)/)
    const quote = line.match(/^>\s?(.*)/)
    const bullet = line.match(/^[-*]\s+(.*)/)
    const numbered = line.match(/^\d+\.\s+(.*)/)

    if (quote) {
      flushList()
      blocks.push(
        <p
          key={`${keyPrefix}-q${i}`}
          className="border-l-2 border-muted-foreground/30 pl-2 text-muted-foreground"
        >
          {renderInline(quote[1], `${keyPrefix}-q${i}`)}
        </p>
      )
    } else if (heading) {
      flushList()
      blocks.push(
        <p key={`${keyPrefix}-h${i}`} className="font-semibold mt-1 first:mt-0">
          {renderInline(heading[1], `${keyPrefix}-h${i}`)}
        </p>
      )
    } else if (bullet) {
      if (!list || list.type !== "ul") {
        flushList()
        list = { type: "ul", items: [] }
      }
      list.items.push(bullet[1])
    } else if (numbered) {
      if (!list || list.type !== "ol") {
        flushList()
        list = { type: "ol", items: [] }
      }
      list.items.push(numbered[1])
    } else {
      flushList()
      blocks.push(
        <p key={`${keyPrefix}-p${i}`} className="min-h-[1em]">
          {renderInline(line, `${keyPrefix}-p${i}`)}
        </p>
      )
    }
    i++
  }
  flushList()

  return <>{blocks}</>
}

function renderContent(text: string): React.ReactNode[] {
  // Split by ```chart blocks
  const parts = text.split(/(```chart\n[\s\S]*?\n```)/)
  return parts.map((part, i) => {
    if (part.startsWith("```chart\n")) {
      const jsonStr = part.replace("```chart\n", "").replace("\n```", "")
      try {
        const config = JSON.parse(jsonStr) as ChartConfig
        return <InlineChart key={i} config={config} />
      } catch {
        return null
      }
    }
    return <div key={i}>{renderTextBlock(part, `b${i}`)}</div>
  })
}

// ─── Single message bubble ──────────────────────────────────────────────────

function MessageBubble({ message }: { message: ChatMessage }) {
  const isUser = message.role === "user"

  return (
    <div className={cn("flex gap-2 items-end", isUser && "flex-row-reverse")}>
      <div
        className={cn(
          "flex h-6 w-6 shrink-0 items-center justify-center rounded-full text-[10px]",
          isUser
            ? "bg-primary text-primary-foreground"
            : "bg-muted text-muted-foreground"
        )}
      >
        {isUser ? <User className="h-3 w-3" /> : <Bot className="h-3 w-3" />}
      </div>

      <div
        className={cn(
          "max-w-[85%] rounded-2xl px-3 py-2 text-sm leading-relaxed",
          isUser
            ? "bg-primary text-primary-foreground rounded-br-sm"
            : "bg-muted text-foreground rounded-bl-sm"
        )}
      >
        {isUser ? (
          <span className="whitespace-pre-wrap">{message.content}</span>
        ) : (
          <div>{renderContent(message.content)}</div>
        )}
      </div>
    </div>
  )
}

// ─── Tool button row ────────────────────────────────────────────────────────

const TOOL_BUTTONS = [
  { label: "Crear tabla", icon: Plus, message: "Crea una nueva tabla para mis datos" },
  { label: "Limpiar datos", icon: Trash2, message: "Limpia y normaliza mis datos" },
] as const

// ─── Main FloatingChat component ────────────────────────────────────────────

export function FloatingChat() {
  const { isOpen, toggle: onToggle, chat } = useChat()
  const {
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
  } = chat

  const [inputValue, setInputValue] = useState("")
  const messagesEndRef = useRef<HTMLDivElement>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)
  const inputRef = useRef<HTMLInputElement>(null)
  const fabRef = useRef<HTMLButtonElement>(null)

  // Auto-scroll to bottom
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" })
  }, [messages.length, isSending])

  // Focus input when panel opens
  useEffect(() => {
    if (isOpen) {
      setTimeout(() => inputRef.current?.focus(), 300)
    }
  }, [isOpen])

  // Cerrar con Escape — solo en móvil (desktop mantiene su comportamiento previo)
  useEffect(() => {
    if (!isOpen) return
    function handleEscape(e: globalThis.KeyboardEvent) {
      if (e.key !== "Escape") return
      if (window.matchMedia("(min-width: 1024px)").matches) return
      onToggle()
      // Restablece el foco al FAB tras cerrar en móvil
      requestAnimationFrame(() => fabRef.current?.focus())
    }
    document.addEventListener("keydown", handleEscape)
    return () => document.removeEventListener("keydown", handleEscape)
  }, [isOpen, onToggle])

  const handleSend = useCallback(async () => {
    const text = inputValue.trim()
    if ((!text && !selectedFile) || isSending) return

    setInputValue("")

    if (selectedFile) {
      await sendFile(selectedFile, text || undefined)
    } else {
      const result = await sendMessage(text)
      // Un 429 (límite/cuota) rechaza el mensaje sin enviarlo: se devuelve el texto al input para no perderlo.
      if (result?.rateLimited) setInputValue((current) => current || text)
    }
  }, [inputValue, selectedFile, isSending, sendMessage, sendFile])

  const handleKeyDown = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault()
      void handleSend()
    }
  }

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (file) setSelectedFile(file)
    e.target.value = ""
  }

  const handleToolButton = (message: string) => {
    setInputValue(message)
    inputRef.current?.focus()
  }

  return (
    <>
      {/* Hidden file input */}
      <input
        ref={fileInputRef}
        type="file"
        accept=".pdf,.csv,.xlsx,.xls"
        className="hidden"
        onChange={handleFileChange}
        aria-hidden="true"
      />

      {/* Overlay — solo móvil cuando el chat está abierto */}
      {isOpen && (
        <div
          className="fixed inset-0 z-40 bg-black/40 lg:hidden"
          onClick={onToggle}
          aria-hidden="true"
        />
      )}

      {/* Chat panel —
          Desktop (≥lg): integrado al flex del layout (pegado, requisito universidad).
          Móvil (<lg):   sheet lateral fixed desde la derecha con overlay. */}
      <div
        inert={!isOpen}
        className={cn(
          "flex flex-col border-l bg-background shrink-0 overflow-hidden",
          // Móvil: fixed sheet lateral
          "fixed inset-y-0 right-0 z-50 w-full max-w-[420px] h-dvh",
          "transition-transform duration-300 ease-in-out",
          isOpen ? "translate-x-0" : "translate-x-full",
          // Desktop: reset al flow del layout
          "lg:static lg:z-auto lg:h-auto lg:max-w-none lg:translate-x-0",
          "lg:transition-[width] lg:duration-300",
          isOpen ? "lg:w-[380px] xl:w-[420px]" : "lg:w-0"
        )}
        role="complementary"
        aria-label="Asistente IA"
        aria-hidden={!isOpen}
      >
        <div className={cn("flex flex-col h-full w-full lg:min-w-[380px] xl:min-w-[420px]", !isOpen && "lg:invisible")}>
          {/* Header */}
          <div className="flex h-14 shrink-0 items-center gap-3 border-b px-4">
            <div className="flex h-8 w-8 items-center justify-center rounded-full bg-primary/10">
              <Sparkles className="h-4 w-4 text-primary" />
            </div>
            <div className="flex-1 min-w-0">
              <p className="text-sm font-semibold leading-tight">Asistente IA</p>
            </div>
            <Badge variant="secondary" className="text-xs shrink-0">
              {currentPage.label}
            </Badge>
            <Button
              variant="ghost"
              size="icon"
              className="h-8 w-8 shrink-0"
              onClick={onToggle}
              aria-label="Cerrar asistente"
            >
              <PanelRightClose className="h-4 w-4" />
            </Button>
          </div>

          {/* Messages */}
          <ScrollArea className="flex-1 min-h-0">
            <div className="px-4 py-4 space-y-3">
              {isLoading ? (
                <div className="flex items-center justify-center py-12">
                  <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
                </div>
              ) : messages.length === 0 ? (
                <div className="flex flex-col items-center justify-center py-10 text-center gap-3">
                  <div className="flex h-12 w-12 items-center justify-center rounded-full bg-primary/10">
                    <Bot className="h-6 w-6 text-primary" />
                  </div>
                  <div className="space-y-1">
                    <p className="text-sm font-medium">Hola, soy tu Asistente IA</p>
                    <p className="text-xs text-muted-foreground max-w-[260px]">
                      Conozco todos los datos de tu empresa. Preguntame lo que necesites
                      o sube un archivo para cargar datos.
                    </p>
                  </div>
                </div>
              ) : (
                messages.map((msg) => (
                  <MessageBubble key={msg.id} message={msg} />
                ))
              )}

              {/* Typing indicator */}
              {isSending && (
                <div className="flex gap-2 items-end">
                  <div className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-muted">
                    <Bot className="h-3 w-3 text-muted-foreground" />
                  </div>
                  <div className="bg-muted rounded-2xl rounded-bl-sm px-3 py-2">
                    <div className="flex gap-1 items-center h-4">
                      <span className="w-1.5 h-1.5 rounded-full bg-muted-foreground/60 animate-bounce [animation-delay:0ms]" />
                      <span className="w-1.5 h-1.5 rounded-full bg-muted-foreground/60 animate-bounce [animation-delay:150ms]" />
                      <span className="w-1.5 h-1.5 rounded-full bg-muted-foreground/60 animate-bounce [animation-delay:300ms]" />
                    </div>
                  </div>
                </div>
              )}

              {/* Error */}
              {error && (
                <div className="flex items-center justify-between gap-2 rounded-lg bg-destructive/10 px-3 py-2 text-xs text-destructive">
                  <span>{error}</span>
                  <button onClick={clearError} className="shrink-0 hover:opacity-70" aria-label="Cerrar error">
                    <X className="h-3 w-3" />
                  </button>
                </div>
              )}

              <div ref={messagesEndRef} />
            </div>
          </ScrollArea>

          {/* Tool buttons */}
          <div className="flex gap-1.5 px-4 pt-2 shrink-0 overflow-x-auto pb-1 scrollbar-none">
            {TOOL_BUTTONS.map((btn) => (
              <button
                key={btn.label}
                onClick={() => handleToolButton(btn.message)}
                className={cn(
                  "flex items-center gap-1.5 whitespace-nowrap rounded-full border",
                  "px-2.5 py-1 text-xs font-medium transition-colors shrink-0",
                  "hover:bg-accent hover:text-accent-foreground",
                  "text-muted-foreground bg-background"
                )}
              >
                <btn.icon className="h-3 w-3" />
                {btn.label}
              </button>
            ))}
          </div>

          {/* File chip */}
          {selectedFile && (
            <div className="mx-4 mt-2 flex items-center gap-2 rounded-lg border bg-muted/50 px-3 py-1.5 shrink-0">
              <Paperclip className="h-3.5 w-3.5 text-muted-foreground shrink-0" />
              <span className="flex-1 truncate text-xs text-foreground">{selectedFile.name}</span>
              <button
                onClick={() => setSelectedFile(null)}
                className="shrink-0 text-muted-foreground hover:text-foreground"
                aria-label="Quitar archivo"
              >
                <X className="h-3 w-3" />
              </button>
            </div>
          )}

          {/* Input bar */}
          <div className="border-t p-3 shrink-0">
            <div className="flex items-center gap-2">
              <Button
                variant="ghost"
                size="icon"
                className="h-8 w-8 shrink-0 text-muted-foreground hover:text-foreground"
                type="button"
                title="Adjuntar archivo"
                onClick={() => fileInputRef.current?.click()}
                disabled={isSending}
                aria-label="Adjuntar archivo"
              >
                <Paperclip className="h-4 w-4" />
              </Button>

              <Input
                ref={inputRef}
                value={inputValue}
                onChange={(e) => setInputValue(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder={currentPage.placeholder}
                className="h-9 flex-1 text-sm"
                disabled={isSending}
                aria-label="Mensaje para el asistente"
              />

              <Button
                size="icon"
                className="h-8 w-8 shrink-0"
                type="button"
                onClick={() => void handleSend()}
                disabled={(!inputValue.trim() && !selectedFile) || isSending}
                aria-label="Enviar mensaje"
              >
                {isSending ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <Send className="h-4 w-4" />
                )}
              </Button>
            </div>
            <p className="mt-1.5 text-[10px] text-muted-foreground text-center">
              IA con memoria de tu empresa
            </p>
          </div>
        </div>
      </div>

    </>
  )
}
