/**
 * Máquina de estados de la zona de carga única (varios archivos a la vez):
 *
 *   idle ──soltar──▶ analyzing ──▶ (review ──confirmar──▶) saving ──▶ done
 *     ▲                  │                                   │
 *     └──── rejected ◀───┘ (ningún archivo sirve)            └──▶ failed ──reintentar──▶ (fase que falló)
 *
 * Si todo es claro, de "analyzing" se pasa directo a "saving" (guardar directo con «Deshacer»); solo se queda en
 * "review" cuando hay baja confianza o duda de mezcla. Cada archivo muestra su propio estado en lenguaje simple:
 * leyendo → entendiendo → listo.
 */
import type { HumanError } from "@/lib/errors"
import { canAutoSave, defaultDecision, readySheets, setKind, setRole, type Decision, type SheetEdit } from "@/lib/intake/plan"
import type { LocalFileKind, LocalProblem } from "@/lib/upload/local-file"
import type { AnalyzeResponse, CommitResponse, Ontology, SheetKind } from "@/types/intake"

export const MAX_FILES = 10

export type IntakePhase = "idle" | "rejected" | "analyzing" | "review" | "saving" | "done" | "failed"
export type EntryStatus = "reading" | "understanding" | "ready" | "attention" | "problem"

export interface FileEntry {
  id: string
  file: File
  kind: LocalFileKind | null
  status: EntryStatus
  problem?: LocalProblem
}

export interface IntakeState {
  phase: IntakePhase
  /** Aumenta con cada tanda nueva: las respuestas de un intento viejo se ignoran. */
  run: number
  entries: FileEntry[]
  proposal: AnalyzeResponse | null
  edits: Record<string, SheetEdit>
  decisions: Record<string, Decision>
  result: CommitResponse | null
  error: HumanError | null
  failedAt: "analyzing" | "saving" | null
  /** Se guardó sin pasar por la revisión. */
  autoSaved: boolean
  undone: boolean
}

export interface NewEntry {
  file: File
  kind: LocalFileKind | null
  problem?: LocalProblem
}

export type IntakeAction =
  | { type: "add"; entries: NewEntry[] }
  | { type: "problems"; run: number; problems: Record<string, LocalProblem> }
  | { type: "understanding"; run: number }
  | { type: "analyzed"; run: number; proposal: AnalyzeResponse }
  | { type: "edit-role"; key: string; column: string; role: string }
  | { type: "edit-kind"; key: string; kind: SheetKind; ontology?: Ontology }
  | { type: "rename"; key: string; name: string }
  | { type: "decide"; key: string; decision: Decision }
  | { type: "confirm" }
  | { type: "saved"; run: number; result: CommitResponse }
  | { type: "fail"; run: number; error: HumanError; at: "analyzing" | "saving" }
  | { type: "retry" }
  | { type: "remove"; id: string }
  | { type: "undone" }
  | { type: "reset" }

export const initialIntakeState: IntakeState = {
  phase: "idle",
  run: 0,
  entries: [],
  proposal: null,
  edits: {},
  decisions: {},
  result: null,
  error: null,
  failedAt: null,
  autoSaved: false,
  undone: false,
}

let seq = 0
function entryId(file: File): string {
  seq += 1
  return `${seq}-${file.name}-${file.size}`
}

function toEntry(n: NewEntry): FileEntry {
  return {
    id: entryId(n.file),
    file: n.file,
    kind: n.kind,
    status: n.problem ? "problem" : "reading",
    problem: n.problem,
  }
}

/** Archivos que sí se mandan al servidor. */
export function validEntries(entries: FileEntry[]): FileEntry[] {
  return entries.filter((e) => e.status !== "problem" && e.kind)
}

/** Pasa por cada hoja de la propuesta y marca el estado de cada archivo. */
function entriesAfterAnalysis(entries: FileEntry[], proposal: AnalyzeResponse): FileEntry[] {
  const byName = new Map(proposal.files.map((f) => [f.file_name, f]))
  return entries.map((e) => {
    if (e.status === "problem") return e
    const f = byName.get(e.file.name)
    if (!f) return { ...e, status: "ready" }
    if (f.status === "error" && f.error) return { ...e, status: "problem", problem: { title: f.error.message, description: "" } }
    const ready = f.sheets.filter((s) => s.status === "ready")
    if (ready.length === 0) {
      const err = f.sheets.find((s) => s.status === "error")?.error
      return {
        ...e,
        status: "problem",
        problem: { title: err?.message ?? "Este archivo no tiene datos que pueda usar", description: "" },
      }
    }
    const needs = ready.some((s) => s.needs_review || s.destination?.action === "ask")
    return { ...e, status: needs ? "attention" : "ready" }
  })
}

export function intakeReducer(state: IntakeState, action: IntakeAction): IntakeState {
  switch (action.type) {
    case "add": {
      const fresh = action.entries.map(toEntry)
      // Una tanda terminada o rechazada empieza de cero; una en revisión suma los archivos nuevos y se vuelve a entender todo.
      const base = state.phase === "review" || state.phase === "analyzing" ? state.entries : []
      const keep = state.phase === "review" || state.phase === "analyzing"
      const merged = [...base, ...fresh]
      const room = Math.max(0, MAX_FILES - base.length)
      const entries = merged.map((e, i) =>
        i >= base.length + room && e.status !== "problem"
          ? { ...e, status: "problem" as const, problem: { title: `Puedes subir hasta ${MAX_FILES} archivos a la vez`, description: "Sube el resto en otra tanda." } }
          : e
      )
      const hasValid = validEntries(entries).length > 0
      return {
        ...initialIntakeState,
        run: state.run + 1,
        phase: hasValid ? "analyzing" : "rejected",
        entries: entries.map((e) => (e.status === "problem" ? e : { ...e, status: "reading" as const })),
        edits: keep ? state.edits : {},
        decisions: keep ? state.decisions : {},
      }
    }
    case "problems": {
      if (action.run !== state.run || state.phase !== "analyzing") return state
      const entries = state.entries.map((e) =>
        action.problems[e.id] ? { ...e, status: "problem" as const, problem: action.problems[e.id] } : e
      )
      return { ...state, entries, phase: validEntries(entries).length > 0 ? "analyzing" : "rejected" }
    }
    case "understanding": {
      if (action.run !== state.run || state.phase !== "analyzing") return state
      return { ...state, entries: state.entries.map((e) => (e.status === "reading" ? { ...e, status: "understanding" as const } : e)) }
    }
    case "analyzed": {
      if (action.run !== state.run || state.phase !== "analyzing") return state
      const auto = canAutoSave(action.proposal)
      const decisions = { ...state.decisions }
      for (const { sheet } of readySheets(action.proposal)) {
        if (!(sheet.key in decisions)) decisions[sheet.key] = defaultDecision(sheet)
      }
      const hasReady = readySheets(action.proposal).length > 0
      return {
        ...state,
        phase: !hasReady ? "rejected" : auto ? "saving" : "review",
        proposal: action.proposal,
        entries: entriesAfterAnalysis(state.entries, action.proposal),
        decisions,
        autoSaved: auto,
      }
    }
    case "edit-role": {
      if (state.phase !== "review" || !state.proposal) return state
      const sheet = readySheets(state.proposal).find((r) => r.sheet.key === action.key)?.sheet
      if (!sheet) return state
      return { ...state, edits: { ...state.edits, [action.key]: setRole(sheet, state.edits[action.key], action.column, action.role) } }
    }
    case "edit-kind": {
      if (state.phase !== "review" || !state.proposal) return state
      const sheet = readySheets(state.proposal).find((r) => r.sheet.key === action.key)?.sheet
      if (!sheet) return state
      const decisions = { ...state.decisions }
      if (action.kind !== sheet.kind && decisions[action.key] === "append") decisions[action.key] = "create"
      return {
        ...state,
        decisions,
        edits: { ...state.edits, [action.key]: setKind(sheet, state.edits[action.key], action.kind, action.ontology) },
      }
    }
    case "rename":
      if (state.phase !== "review") return state
      return { ...state, edits: { ...state.edits, [action.key]: { ...state.edits[action.key], displayName: action.name } } }
    case "decide":
      if (state.phase !== "review") return state
      return { ...state, decisions: { ...state.decisions, [action.key]: action.decision } }
    case "confirm":
      if (state.phase !== "review") return state
      return { ...state, phase: "saving" }
    case "saved":
      if (action.run !== state.run || state.phase !== "saving") return state
      return { ...state, phase: "done", result: action.result, error: null, failedAt: null }
    case "fail":
      if (action.run !== state.run) return state
      return { ...state, phase: "failed", error: action.error, failedAt: action.at }
    case "retry":
      if (state.phase !== "failed" || !state.failedAt) return state
      return { ...state, run: state.run + 1, phase: state.failedAt === "analyzing" ? "analyzing" : "saving", error: null, failedAt: null,
        entries: state.entries.map((e) => (e.status === "problem" ? e : { ...e, status: "reading" as const })) }
    case "remove": {
      if (state.phase !== "review" && state.phase !== "rejected" && state.phase !== "analyzing") return state
      const entries = state.entries.filter((e) => e.id !== action.id)
      if (entries.length === 0) return { ...initialIntakeState, run: state.run + 1 }
      if (state.phase === "rejected") return { ...state, entries, phase: validEntries(entries).length > 0 ? "analyzing" : "rejected", run: state.run + 1 }
      // Se vuelve a entender sin ese archivo (la propuesta depende de todos los archivos juntos).
      return { ...state, entries: entries.map((e) => (e.status === "problem" ? e : { ...e, status: "reading" as const })), run: state.run + 1,
        phase: validEntries(entries).length > 0 ? "analyzing" : "rejected", proposal: null }
    }
    case "undone":
      return state.phase === "done" ? { ...state, undone: true } : state
    case "reset":
      return { ...initialIntakeState, run: state.run + 1 }
    default:
      return state
  }
}

/** Frase corta de lo que está pasando, para la región en vivo. */
export function intakeMessage(state: IntakeState): string {
  const n = validEntries(state.entries).length
  switch (state.phase) {
    case "analyzing":
      return n > 1 ? `Leyendo y entendiendo tus ${n} archivos…` : "Leyendo y entendiendo tu archivo…"
    case "saving":
      return "Guardando tus datos…"
    case "review":
      return "Revisa lo que entendí antes de guardar."
    case "done":
      return "¡Listo! Tus datos quedaron guardados."
    case "failed":
      return state.error?.title ?? "Algo salió mal."
    case "rejected":
      return "No pude usar ese archivo."
    default:
      return ""
  }
}
