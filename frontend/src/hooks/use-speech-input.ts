"use client"

import { useCallback, useEffect, useRef, useState } from "react"

/* Tipos mínimos de la Web Speech API (no vienen en lib.dom de TypeScript). */
interface SpeechRecognitionResultLike {
  isFinal: boolean
  0: { transcript: string }
}
interface SpeechRecognitionEventLike {
  resultIndex: number
  results: ArrayLike<SpeechRecognitionResultLike>
}
interface SpeechRecognitionLike {
  lang: string
  interimResults: boolean
  continuous: boolean
  onresult: ((e: SpeechRecognitionEventLike) => void) | null
  onerror: ((e: { error: string }) => void) | null
  onend: (() => void) | null
  start: () => void
  stop: () => void
  abort: () => void
}
type SpeechCtor = new () => SpeechRecognitionLike

function getCtor(): SpeechCtor | null {
  if (typeof window === "undefined") return null
  const w = window as unknown as { SpeechRecognition?: SpeechCtor; webkitSpeechRecognition?: SpeechCtor }
  return w.SpeechRecognition ?? w.webkitSpeechRecognition ?? null
}

const ERRORS: Record<string, string> = {
  "not-allowed": "Necesitamos permiso para usar el micrófono. Puedes darlo desde el candado de la barra de direcciones.",
  "service-not-allowed": "Tu navegador no permite dictar en este momento.",
  "no-speech": "No te escuchamos. Intenta de nuevo, un poco más cerca del micrófono.",
  "audio-capture": "No encontramos un micrófono en este equipo.",
  network: "El dictado necesita conexión a internet.",
}

/**
 * Dictado por voz con la Web Speech API del navegador (sin dependencias).
 * Si el navegador no la soporta, `supported` es false y no se muestra nada.
 */
export function useSpeechInput(onText: (text: string, final: boolean) => void) {
  const [supported, setSupported] = useState(false)
  const [listening, setListening] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const recRef = useRef<SpeechRecognitionLike | null>(null)
  const onTextRef = useRef(onText)
  onTextRef.current = onText

  useEffect(() => setSupported(getCtor() !== null), [])
  useEffect(() => () => recRef.current?.abort(), [])

  const stop = useCallback(() => {
    recRef.current?.stop()
  }, [])

  const start = useCallback(() => {
    const Ctor = getCtor()
    if (!Ctor) return
    setError(null)
    try {
      const rec = new Ctor()
      rec.lang = "es-CO"
      rec.interimResults = true
      rec.continuous = false
      rec.onresult = (e) => {
        let text = ""
        let final = false
        for (let i = e.resultIndex; i < e.results.length; i++) {
          text += e.results[i][0].transcript
          if (e.results[i].isFinal) final = true
        }
        onTextRef.current(text, final)
      }
      rec.onerror = (e) => {
        if (e.error !== "aborted") setError(ERRORS[e.error] ?? "No pudimos usar el dictado ahora. Escribe tu pregunta, por favor.")
      }
      rec.onend = () => setListening(false)
      recRef.current = rec
      rec.start()
      setListening(true)
    } catch {
      setListening(false)
      setError("No pudimos usar el dictado ahora. Escribe tu pregunta, por favor.")
    }
  }, [])

  return { supported, listening, error, start, stop, clearError: () => setError(null) }
}
