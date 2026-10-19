/**
 * Lógica pura de la carga inteligente: qué hoja necesita ayuda, cómo corrige la persona un rol o el tipo de hoja,
 * y cómo se arma el plan que se confirma con `POST /intake/commit`. Sin React ni red: todo se prueba aparte.
 */
import type { MissingInsight } from "@/types/insights"
import type {
  AnalyzeResponse,
  IntakeColumn,
  IntakeFile,
  IntakeSheet,
  Ontology,
  PlanColumn,
  PlanSheet,
  SheetKind,
} from "@/types/intake"

export const OTHER_ROLE = "otro"

/** Nombre corto de cada tipo de hoja para etiquetas (espejo de KIND_LABEL del backend). */
export const KIND_NAME: Record<SheetKind, string> = {
  productos: "Productos",
  ventas: "Ventas",
  compras: "Compras",
  cuentas_por_cobrar: "Cuentas por cobrar",
  movimientos_inventario: "Movimientos de inventario",
  clientes: "Clientes",
  proveedores: "Proveedores",
  otro: "Otros datos",
}

/** Tipo de hoja que dejó la carga inteligente en una hoja guardada (null en las hojas anteriores o sin tipo). */
export function storedKind(columns: Array<{ sheet?: { kind: SheetKind } }> | undefined): SheetKind | null {
  const kind = columns?.[0]?.sheet?.kind
  return kind && kind !== "otro" ? kind : null
}

/** Lo que la persona cambió de una hoja (todo opcional: sin cambios = lo que propuso el sistema). */
export interface SheetEdit {
  kind?: SheetKind
  /** nombre de columna -> rol. Cuando existe, trae TODAS las columnas. */
  roles?: Record<string, string>
  displayName?: string
}

export type Decision = "create" | "append" | "skip"

export interface ReadySheet {
  file: IntakeFile
  sheet: IntakeSheet
}

export function readySheets(proposal: AnalyzeResponse | null): ReadySheet[] {
  if (!proposal) return []
  return proposal.files.flatMap((file) =>
    file.sheets.filter((s) => s.status === "ready" && s.columns && s.destination).map((sheet) => ({ file, sheet }))
  )
}

export function currentKind(sheet: IntakeSheet, edit?: SheetEdit): SheetKind {
  return edit?.kind ?? sheet.kind ?? "otro"
}

export function currentRoles(sheet: IntakeSheet, edit?: SheetEdit): Record<string, string> {
  if (edit?.roles) return edit.roles
  return Object.fromEntries((sheet.columns ?? []).map((c) => [c.name, c.role]))
}

// --- confianza en palabras -----------------------------------------------------

export type ConfidenceLevel = "high" | "medium" | "low"

export function confidenceLevel(confidence: number): ConfidenceLevel {
  if (confidence >= 0.85) return "high"
  if (confidence >= 0.6) return "medium"
  return "low"
}

export const CONFIDENCE_LABEL: Record<ConfidenceLevel, string> = {
  high: "Seguro",
  medium: "Casi seguro",
  low: "Revísalo",
}

// --- ¿necesita a la persona? ---------------------------------------------------

/** Solo se pide intervención con baja confianza o duda de mezcla. */
export function sheetNeedsAttention(sheet: IntakeSheet): boolean {
  return Boolean(sheet.needs_review) || sheet.destination?.action === "ask"
}

export function attentionReasons(sheet: IntakeSheet): string[] {
  const reasons = [...(sheet.review_reasons ?? [])]
  if (sheet.destination?.action === "ask" && !reasons.some((r) => /junto|suma|aparte/i.test(r))) {
    reasons.push("Se parece a una hoja que ya tienes y no estoy seguro de si van juntas.")
  }
  return reasons
}

/** Si todo es claro, se guarda directo (con «Deshacer»). */
export function canAutoSave(proposal: AnalyzeResponse | null): boolean {
  const ready = readySheets(proposal)
  return ready.length > 0 && ready.every(({ sheet }) => !sheetNeedsAttention(sheet))
}

// --- correcciones ----------------------------------------------------------------

function rolesOf(ontology: Ontology | undefined, kind: SheetKind): string[] {
  return (ontology?.roles?.[kind] ?? []).map((r) => r.role)
}

/** Asigna un rol a una columna. Cada rol vive en UNA sola columna: si estaba en otra, esa pasa a «dato adicional». */
export function setRole(sheet: IntakeSheet, edit: SheetEdit | undefined, columnName: string, role: string): SheetEdit {
  const roles = { ...currentRoles(sheet, edit) }
  if (role !== OTHER_ROLE) {
    for (const [name, r] of Object.entries(roles)) {
      if (name !== columnName && r === role) roles[name] = OTHER_ROLE
    }
  }
  roles[columnName] = role
  return { ...edit, roles }
}

/** Cambia el tipo de hoja: los roles que ya no valen para ese tipo pasan a «dato adicional». */
export function setKind(sheet: IntakeSheet, edit: SheetEdit | undefined, kind: SheetKind, ontology: Ontology | undefined): SheetEdit {
  const valid = new Set([...rolesOf(ontology, kind), OTHER_ROLE])
  const roles = Object.fromEntries(
    Object.entries(currentRoles(sheet, edit)).map(([name, r]) => [name, kind !== "otro" && valid.has(r) ? r : OTHER_ROLE])
  )
  return { ...edit, kind, roles }
}

export function isEdited(sheet: IntakeSheet, edit?: SheetEdit): boolean {
  if (!edit) return false
  if (edit.kind && edit.kind !== sheet.kind) return true
  if (edit.roles) {
    const original = Object.fromEntries((sheet.columns ?? []).map((c) => [c.name, c.role]))
    return Object.entries(edit.roles).some(([name, r]) => original[name] !== r)
  }
  return false
}

// --- plan ------------------------------------------------------------------------

export function defaultDecision(sheet: IntakeSheet): Decision {
  return sheet.destination?.action === "append" ? "append" : "create"
}

export function buildPlan(
  proposal: AnalyzeResponse | null,
  edits: Record<string, SheetEdit>,
  decisions: Record<string, Decision>
): PlanSheet[] {
  return readySheets(proposal).map(({ file, sheet }) => {
    const edit = edits[sheet.key]
    const kind = currentKind(sheet, edit)
    const kindChanged = Boolean(edit?.kind && edit.kind !== sheet.kind)
    const roles = currentRoles(sheet, edit)
    const original = Object.fromEntries((sheet.columns ?? []).map((c: IntakeColumn) => [c.name, c]))
    const columns: PlanColumn[] = (sheet.columns ?? []).map((c) => {
      const role = roles[c.name] ?? c.role
      const edited = kindChanged || role !== original[c.name]?.role
      return { name: c.name, role, confidence: edited ? 1 : c.confidence, edited }
    })
    let action: Decision = decisions[sheet.key] ?? defaultDecision(sheet)
    // un tipo corregido ya no coincide con la hoja con la que se emparejó: va aparte
    if (kindChanged && action === "append") action = "create"
    const dest = sheet.destination!
    return {
      file_name: file.file_name,
      sheet_name: sheet.sheet_name,
      action,
      table_id: action === "append" ? dest.table_id : null,
      into_sheet: action === "append" ? dest.into_sheet : null,
      display_name: action === "create" ? edit?.displayName?.trim() || dest.new_display_name : null,
      kind,
      mapping_source: sheet.mapping_source ?? "heuristic",
      columns,
    }
  })
}

/** Las hojas que se van a guardar de verdad (sin las que la persona omitió). */
export function plannedCount(plan: PlanSheet[]): number {
  return plan.filter((p) => p.action !== "skip").length
}

// --- «Con esto ya puedo decirte» ---------------------------------------------------

/** "Para decirte cuánto te deben tus clientes necesito: una hoja con cliente, valor y fecha de vencimiento..." */
export function unlockSentence(missing: MissingInsight): string {
  const title = missing.title.charAt(0).toLowerCase() + missing.title.slice(1)
  const needs = missing.needs.trim()
  const lowered = needs.charAt(0).toLowerCase() + needs.slice(1)
  return `Para decirte ${title.replace(/\.$/, "")} necesito: ${lowered}`
}

/** Frase del encabezado de una hoja: separa lo que va resaltado ("tus ventas") del resto. */
export function sheetHeadline(sheet: IntakeSheet): { lead: string; kindPhrase: string; stats: string } | null {
  if (!sheet.kind_phrase || !sheet.stats) return null
  if (sheet.kind === "otro") return { lead: "Guardaré", kindPhrase: "tus datos tal cual", stats: sheet.stats }
  return { lead: "Encontré", kindPhrase: sheet.kind_phrase, stats: sheet.stats }
}
