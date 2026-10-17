"use client"

import Link from "next/link"
import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState, type KeyboardEvent } from "react"
import { toast } from "sonner"
import { ArrowUp, Check, Copy, Mic, Paperclip, RotateCcw, Square, Upload, X } from "lucide-react"
import { Button } from "@/components/ui/button"
import { BrandMark } from "@/components/kit/logo"
import { Notice } from "@/components/kit/notice"
import { SuggestionChips } from "@/components/kit/suggestion-chips"
import { MessageContent, plainText } from "@/components/chat/message-content"
import { firstName } from "@/components/shell/user-menu"
import { useOrgTables } from "@/hooks/use-templates"
import { useSpeechInput } from "@/hooks/use-speech-input"
import { useAuthContext } from "@/providers/auth-provider"
import { useChat } from "@/providers/chat-provider"
import { suggestQuestions } from "@/lib/suggestions"
import { validateLocalFile, withExplicitType } from "@/lib/upload/local-file"
import { cn } from "@/lib/utils"
import type { ChatMessage } from "@/types/api"

/** Mensajes de espera que cambian con el tiempo para que la espera no se sienta muerta. */
const THINKING = [
  { after: 0, text: "Revisando tus datos…" },
  { after: 4000, text: "Haciendo las cuentas…" },
  { after: 10000, text: "Armando la respuesta…" },
  { after: 20000, text: "Esta está difícil; ya casi…" },
]

function Thinking() {
  const [index, setIndex] = useState(0)
  useEffect(() => {
    const timers = THINKING.slice(1).map((t, i) => window.setTimeout(() => setIndex(i + 1), t.after))
    return () => timers.forEach((t) => window.clearTimeout(t))
  }, [])
  return (
    <div className="flex items-start gap-2.5" role="status" aria-live="polite">
      <BrandMark className="h-7 w-7 rounded-lg" animated />
      <div className="flex items-center gap-2.5 rounded-2xl rounded-tl-md border bg-card px-3.5 py-2.5 text-sm text-muted-foreground shadow-card">
        <span className="flex gap-1" aria-hidden="true">
          {[0, 150, 300].map((d) => (
            <span key={d} className="h-1.5 w-1.5 animate-soft-pulse rounded-full bg-primary" style={{ animationDelay: `${d}ms` }} />
          ))}
        </span>
        {THINKING[index].text}
      </div>
    </div>
  )
}

function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false)
  return (
    <button
      type="button"
      onClick={async () => {
        try {
          await navigator.clipboard.writeText(plainText(text))
          setCopied(true)
          window.setTimeout(() => setCopied(false), 1600)
        } catch {
          toast.error("No pudimos copiar el texto")
        }
      }}
      className="inline-flex h-8 items-center gap-1.5 rounded-lg px-2 text-xs font-medium text-muted-foreground transition hover:bg-accent hover:text-foreground"
      aria-label={copied ? "Respuesta copiada" : "Copiar respuesta"}
    >
      {copied ? <Check className="h-3.5 w-3.5" aria-hidden="true" /> : <Copy className="h-3.5 w-3.5" aria-hidden="true" />}
      {copied ? "Copiado" : "Copiar"}
    </button>
  )
}

function Bubble({ message }: { message: ChatMessage }) {
  if (message.role === "user") {
    return (
      <div className="flex justify-end">
        <div className="max-w-[86%] whitespace-pre-wrap rounded-2xl rounded-br-md bg-primary px-3.5 py-2.5 text-[15px] leading-relaxed text-primary-foreground shadow-card">
          {message.content}
        </div>
      </div>
    )
  }
  return (
    <div className="group flex items-start gap-2.5">
      <BrandMark className="mt-0.5 h-7 w-7 rounded-lg" />
      <div className="min-w-0 max-w-[calc(100%-2.5rem)] flex-1">
        <div className="rounded-2xl rounded-tl-md border bg-card px-3.5 py-2.5 text-[15px] leading-relaxed text-foreground/90 shadow-card">
          <MessageContent text={message.content} />
        </div>
        <div className="mt-0.5 opacity-100 transition sm:opacity-0 sm:group-focus-within:opacity-100 sm:group-hover:opacity-100">
          <CopyButton text={message.content} />
        </div>
      </div>
    </div>
  )
}

/**
 * Panel del asistente. Escritorio (≥lg): acoplado a la derecha del contenido.
 * Celular y tableta: pantalla completa (o panel lateral) por encima.
 */
export function FloatingChat() {
  const { isOpen, close, pending, consumePending, chat } = useChat()
  const { messages, isLoading, isSending, errorInfo, lastFailed, selectedFile, sendMessage, retryLast, sendFile, setSelectedFile, clearError, currentPage } = chat
  const { user } = useAuthContext()
  const tablesQuery = useOrgTables()
  const tables = useMemo(() => tablesQuery.data?.tables ?? [], [tablesQuery.data])
  const withRows = tables.filter((t) => t.row_count > 0)
  const suggestions = useMemo(
    () =>
      suggestQuestions(
        tables.map((t) => ({ name: t.display_name, rowCount: t.row_count, columns: t.columns_definition ?? [] })),
        4
      ),
    [tables]
  )

  const [input, setInput] = useState("")
  const panelRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLTextAreaElement>(null)
  const fileRef = useRef<HTMLInputElement>(null)
  const endRef = useRef<HTMLDivElement>(null)
  const baseInput = useRef("")

  const speech = useSpeechInput((text, final) => {
    const joined = `${baseInput.current}${baseInput.current && !baseInput.current.endsWith(" ") ? " " : ""}${text}`
    setInput(joined)
    if (final) baseInput.current = joined
  })

  // React 18 no maneja `inert` como booleano: se pone directo en el DOM.
  useEffect(() => {
    const el = panelRef.current
    if (!el) return
    if (isOpen) el.removeAttribute("inert")
    else el.setAttribute("inert", "")
  }, [isOpen])

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth", block: "end" })
  }, [messages.length, isSending, errorInfo])

  useEffect(() => {
    if (isOpen) window.setTimeout(() => inputRef.current?.focus(), 250)
  }, [isOpen])

  // Altura automática del cuadro de texto (1 a 6 líneas)
  useLayoutEffect(() => {
    const el = inputRef.current
    if (!el) return
    el.style.height = "auto"
    el.style.height = `${Math.min(el.scrollHeight, 160)}px`
  }, [input])

  const send = useCallback(
    async (text: string) => {
      const value = text.trim()
      if (!value && !selectedFile) return
      if (isSending) return
      setInput("")
      baseInput.current = ""
      if (selectedFile) {
        await sendFile(selectedFile, value || undefined)
        return
      }
      const result = await sendMessage(value)
      // Un 429 (límite/cuota) no envía el mensaje: se devuelve el texto al cuadro para no perderlo.
      if (result?.rateLimited) setInput((current) => current || value)
    },
    [isSending, selectedFile, sendFile, sendMessage]
  )

  // Preguntas que llegan desde otras pantallas (inicio, cierre del cargue, tarjetas)
  useEffect(() => {
    if (!pending || !isOpen) return
    consumePending()
    if (pending.send && !isSending) void send(pending.text)
    else {
      setInput(pending.text)
      window.setTimeout(() => inputRef.current?.focus(), 50)
    }
  }, [pending, isOpen, consumePending, isSending, send])

  function onKeyDown(e: KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
      e.preventDefault()
      void send(input)
    }
  }

  function onPanelKeyDown(e: KeyboardEvent<HTMLDivElement>) {
    if (e.key === "Escape") {
      e.stopPropagation()
      close()
    }
  }

  const empty = !isLoading && messages.length === 0
  const name = firstName(user?.full_name)

  return (
    <>
      <input
        ref={fileRef}
        type="file"
        accept=".csv,.xlsx,.json"
        className="hidden"
        onChange={(e) => {
          const f = e.target.files?.[0]
          e.target.value = ""
          if (!f) return
          const check = validateLocalFile(f)
          if (!check.ok) {
            toast.error(check.title, { description: check.description })
            return
          }
          // Con el tipo correcto según la extensión (Windows marca los .csv como Excel).
          setSelectedFile(withExplicitType(f, check.kind))
        }}
        aria-hidden="true"
        tabIndex={-1}
      />

      {/* Fondo oscuro en tableta (en celular el panel ocupa todo) */}
      {isOpen && (
        <div className="fixed inset-0 z-40 hidden bg-[hsl(var(--shadow)/0.4)] backdrop-blur-[2px] md:block lg:hidden" onClick={close} aria-hidden="true" />
      )}

      <div
        ref={panelRef}
        role="complementary"
        aria-label="Asistente IA"
        onKeyDown={onPanelKeyDown}
        className={cn(
          "flex flex-col overflow-hidden bg-background",
          // Celular y tableta: por encima del contenido
          "fixed inset-0 z-50 transition-transform duration-300 ease-out md:inset-y-0 md:left-auto md:right-0 md:w-[440px] md:border-l md:shadow-float",
          isOpen ? "translate-x-0" : "translate-x-full",
          // Escritorio: acoplado
          "lg:static lg:z-auto lg:shrink-0 lg:translate-x-0 lg:border-l lg:shadow-none lg:transition-[width] lg:duration-300",
          isOpen ? "lg:w-[400px] xl:w-[440px]" : "lg:w-0 lg:border-l-0"
        )}
      >
        <div className={cn("flex h-full w-full flex-col lg:min-w-[400px] xl:min-w-[440px]", !isOpen && "lg:invisible")}>
          {/* Encabezado */}
          <header className="flex h-16 shrink-0 items-center gap-3 border-b bg-card/70 px-4 backdrop-blur lg:h-[72px]">
            <BrandMark className="h-9 w-9" />
            <div className="min-w-0 flex-1">
              <p className="font-display text-lg font-semibold leading-tight">Pregúntale a tus datos</p>
              <p className="truncate text-xs text-muted-foreground">Asistente con IA · responde con tus cifras</p>
            </div>
            <Button variant="ghost" size="icon-sm" onClick={close} aria-label="Cerrar el asistente">
              <X aria-hidden="true" />
            </Button>
          </header>

          {/* Conversación */}
          <div className="min-h-0 flex-1 overflow-y-auto overscroll-contain" role="log" aria-live="polite" aria-relevant="additions">
            <div className="space-y-5 px-4 py-5">
              {isLoading ? (
                <div className="space-y-4" aria-label="Cargando la conversación">
                  {[70, 50, 85].map((w, i) => (
                    <div key={i} className={cn("h-12 animate-pulse rounded-2xl bg-muted", i % 2 ? "ml-auto" : "")} style={{ width: `${w}%` }} />
                  ))}
                </div>
              ) : empty ? (
                <div className="space-y-5 pt-2">
                  <div className="space-y-2">
                    <h2 className="font-display text-2xl font-semibold leading-tight">
                      Hola{name ? `, ${name}` : ""}. ¿Qué quieres saber?
                    </h2>
                    <p className="text-[15px] leading-relaxed text-muted-foreground">
                      Consulto las hojas que subiste y te respondo con cifras y gráficos. Si algo no te cuadra, pídeme el detalle: a veces me
                      equivoco.
                    </p>
                  </div>
                  {withRows.length > 0 ? (
                    <div className="space-y-2.5">
                      <p className="text-sm font-semibold">Puedes empezar por aquí</p>
                      <SuggestionChips questions={suggestions} onPick={(q) => void send(q)} layout="stack" disabled={isSending} />
                    </div>
                  ) : !tablesQuery.isLoading ? (
                    <Notice
                      tone="highlight"
                      title="Todavía no tienes datos para consultar"
                      action={
                        <Button asChild size="sm" variant="outline" onClick={close}>
                          <Link href="/data">
                            <Upload aria-hidden="true" />
                            Subir un archivo
                          </Link>
                        </Button>
                      }
                    >
                      Sube un Excel o CSV y vuelve: podré responderte con tus cifras.
                    </Notice>
                  ) : null}
                </div>
              ) : (
                messages.map((m) => <Bubble key={m.id} message={m} />)
              )}

              {isSending && <Thinking />}

              {errorInfo && !isSending && (
                <Notice
                  tone={errorInfo.rateLimited ? "warning" : "danger"}
                  title={errorInfo.title}
                  onDismiss={clearError}
                  action={
                    errorInfo.retryable && lastFailed ? (
                      <Button size="sm" variant="outline" onClick={() => void retryLast()}>
                        <RotateCcw aria-hidden="true" />
                        Reintentar
                      </Button>
                    ) : undefined
                  }
                >
                  {errorInfo.description}
                  {lastFailed && !errorInfo.rateLimited && (
                    <span className="mt-1 block text-[13px] text-muted-foreground">Tu pregunta: «{lastFailed}»</span>
                  )}
                </Notice>
              )}
              <div ref={endRef} />
            </div>
          </div>

          {/* Redactar */}
          <div className="shrink-0 border-t bg-card/80 px-3 pb-3 pt-3 backdrop-blur pb-safe">
            {selectedFile && (
              <div className="mb-2 flex items-center gap-2 rounded-xl border bg-muted/60 px-3 py-2">
                <Paperclip className="h-4 w-4 shrink-0 text-muted-foreground" aria-hidden="true" />
                <span className="min-w-0 flex-1 truncate text-sm">{selectedFile.name}</span>
                <button
                  type="button"
                  onClick={() => setSelectedFile(null)}
                  className="inline-flex h-8 w-8 items-center justify-center rounded-lg text-muted-foreground hover:bg-accent hover:text-foreground"
                  aria-label="Quitar el archivo adjunto"
                >
                  <X className="h-4 w-4" aria-hidden="true" />
                </button>
              </div>
            )}
            {speech.error && (
              <p className="mb-2 rounded-lg bg-warning-soft px-3 py-2 text-[13px] text-warning-strong" role="status">
                {speech.error}
              </p>
            )}
            <form
              onSubmit={(e) => {
                e.preventDefault()
                void send(input)
              }}
              className="flex items-end gap-1.5 rounded-2xl border bg-background p-1.5 transition focus-within:border-ring focus-within:ring-4 focus-within:ring-ring/15"
            >
              <Button
                type="button"
                variant="ghost"
                size="icon-sm"
                onClick={() => fileRef.current?.click()}
                disabled={isSending}
                aria-label="Adjuntar archivo"
                title="Adjuntar un archivo (Excel, CSV o JSON)"
                className="text-muted-foreground"
              >
                <Paperclip aria-hidden="true" />
              </Button>
              <label htmlFor="chat-input" className="sr-only">
                Mensaje para el asistente
              </label>
              <textarea
                id="chat-input"
                ref={inputRef}
                rows={1}
                value={input}
                onChange={(e) => {
                  setInput(e.target.value)
                  baseInput.current = e.target.value
                }}
                onKeyDown={onKeyDown}
                placeholder={speech.listening ? "Te escucho…" : currentPage.placeholder}
                className="max-h-40 min-h-[44px] min-w-0 flex-1 resize-none bg-transparent px-1 py-2.5 text-[15px] leading-6 outline-none placeholder:text-muted-foreground/80 sm:min-h-[36px] sm:py-1.5"
                disabled={isSending}
              />
              {speech.supported && (
                <Button
                  type="button"
                  variant="ghost"
                  size="icon-sm"
                  onClick={() => (speech.listening ? speech.stop() : speech.start())}
                  aria-pressed={speech.listening}
                  aria-label={speech.listening ? "Dejar de dictar" : "Dictar con la voz"}
                  title={speech.listening ? "Dejar de dictar" : "Dictar con la voz"}
                  className={cn(speech.listening ? "bg-danger-soft text-danger-strong hover:bg-danger-soft" : "text-muted-foreground")}
                  disabled={isSending}
                >
                  {speech.listening ? <Square className="h-3.5 w-3.5 fill-current" aria-hidden="true" /> : <Mic aria-hidden="true" />}
                </Button>
              )}
              <Button
                type="submit"
                size="icon-sm"
                disabled={(!input.trim() && !selectedFile) || isSending}
                aria-label="Enviar mensaje"
                className="rounded-xl"
              >
                <ArrowUp aria-hidden="true" />
              </Button>
            </form>
            <p className="mt-2 hidden text-center text-[11px] text-muted-foreground sm:block">
              <kbd className="font-sans font-semibold">Enter</kbd> envía · <kbd className="font-sans font-semibold">Shift + Enter</kbd> nueva línea ·{" "}
              <kbd className="font-sans font-semibold">Ctrl K</kbd> abre o cierra
            </p>
          </div>
        </div>
      </div>
    </>
  )
}
