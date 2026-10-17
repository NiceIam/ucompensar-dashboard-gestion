/**
 * Máquina de estados del cargue de un archivo:
 *
 *   idle ──elegir──▶ reading ──▶ understanding ──▶ (review ──confirmar──▶) saving ──▶ done
 *     ▲                │                │                                  │
 *     └──── rejected ◀─┘ (validación     └──────────── failed ◀────────────┘
 *                         local)                         └─reintentar─▶ (fase que falló)
 *
 * Si la evaluación no pide revisión, de "understanding" se pasa directo a "saving".
 */
import type { HumanError } from "@/lib/errors"
import type { Assessment } from "@/lib/upload/assess"
import type { LocalFileKind, LocalProblem } from "@/lib/upload/local-file"
import type { LocalRead } from "@/lib/upload/read-local"
import type { FileAnalysis, SmartUploadResult } from "@/lib/upload/types"

export type UploadPhase = "idle" | "rejected" | "reading" | "understanding" | "review" | "saving" | "done" | "failed"

export interface UploadState {
  phase: UploadPhase
  /** Aumenta con cada archivo nuevo: las respuestas de un intento viejo se ignoran. */
  run: number
  file: File | null
  kind: LocalFileKind | null
  problem: LocalProblem | null
  local: LocalRead | null
  analysis: FileAnalysis | null
  assessment: Assessment | null
  result: SmartUploadResult | null
  error: HumanError | null
  failedAt: "understanding" | "saving" | null
  /** Se guardó sin pasar por la revisión. */
  autoSaved: boolean
  undone: boolean
}

export type UploadAction =
  | { type: "select"; file: File; kind: LocalFileKind }
  | { type: "reject"; file: File; problem: LocalProblem }
  | { type: "local-read"; run: number; local: LocalRead | null }
  | { type: "analyzed"; run: number; analysis: FileAnalysis; assessment: Assessment }
  | { type: "confirm" }
  | { type: "saved"; run: number; result: SmartUploadResult }
  | { type: "fail"; run: number; error: HumanError; at: "understanding" | "saving" }
  | { type: "retry" }
  | { type: "undone" }
  | { type: "reset" }

export const initialUploadState: UploadState = {
  phase: "idle",
  run: 0,
  file: null,
  kind: null,
  problem: null,
  local: null,
  analysis: null,
  assessment: null,
  result: null,
  error: null,
  failedAt: null,
  autoSaved: false,
  undone: false,
}

export function uploadReducer(state: UploadState, action: UploadAction): UploadState {
  switch (action.type) {
    case "select":
      return { ...initialUploadState, phase: "reading", run: state.run + 1, file: action.file, kind: action.kind }
    case "reject":
      return { ...initialUploadState, phase: "rejected", run: state.run + 1, file: action.file, problem: action.problem }
    case "local-read":
      if (action.run !== state.run || state.phase !== "reading") return state
      return { ...state, phase: "understanding", local: action.local }
    case "analyzed": {
      if (action.run !== state.run || state.phase !== "understanding") return state
      const review = action.assessment.needsReview || action.assessment.blocked
      return {
        ...state,
        phase: review ? "review" : "saving",
        analysis: action.analysis,
        assessment: action.assessment,
        autoSaved: !review,
      }
    }
    case "confirm":
      if (state.phase !== "review" || state.assessment?.blocked) return state
      return { ...state, phase: "saving" }
    case "saved":
      if (action.run !== state.run || state.phase !== "saving") return state
      return { ...state, phase: "done", result: action.result, error: null, failedAt: null }
    case "fail":
      if (action.run !== state.run) return state
      return { ...state, phase: "failed", error: action.error, failedAt: action.at }
    case "retry":
      if (state.phase !== "failed" || !state.failedAt) return state
      return { ...state, phase: state.failedAt, error: null, failedAt: null }
    case "undone":
      return state.phase === "done" ? { ...state, undone: true } : state
    case "reset":
      return { ...initialUploadState, run: state.run + 1 }
    default:
      return state
  }
}

export const UPLOAD_STEPS = [
  { id: "read", label: "Leer tu archivo" },
  { id: "understand", label: "Entender tus datos" },
  { id: "save", label: "Guardar" },
  { id: "done", label: "¡Listo!" },
]

/** Paso visible para el indicador (0..3; 4 = todo completo). */
export function stepIndex(state: UploadState): number {
  switch (state.phase) {
    case "reading":
      return 0
    case "understanding":
    case "review":
      return 1
    case "saving":
      return 2
    case "done":
      return 4
    case "failed":
      return state.failedAt === "saving" ? 2 : 1
    default:
      return 0
  }
}

/** Pasos con la etiqueta del paso 2 ajustada cuando hay revisión. */
export function stepsFor(state: UploadState) {
  return UPLOAD_STEPS.map((s) =>
    s.id === "understand" && (state.phase === "review" || (state.assessment?.needsReview && state.phase !== "understanding"))
      ? { ...s, label: "Revisar contigo" }
      : s
  )
}

/** Frase corta de lo que está pasando ahora, para la región en vivo. */
export function phaseMessage(state: UploadState): string {
  switch (state.phase) {
    case "reading":
      return "Leyendo tu archivo…"
    case "understanding":
      return "Entendiendo tus columnas…"
    case "saving":
      return "Guardando tus datos…"
    case "review":
      return "Revisa lo que encontramos antes de guardar."
    case "done":
      return "¡Listo! Tus datos quedaron guardados."
    case "failed":
      return state.error?.title ?? "Algo salió mal."
    case "rejected":
      return state.problem?.title ?? "No pudimos usar ese archivo."
    default:
      return ""
  }
}
