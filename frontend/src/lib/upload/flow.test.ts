import { describe, expect, test } from "vitest"

/** Los formateadores usan espacio duro entre cifra y unidad; aquí se comparan como espacios normales. */
const plain = (s: string | undefined) => (s ?? "").replace(/\u00a0/g, " ")
import { assessUpload, predictDestination } from "./assess"
import { computeInsights, parseDateCell, parseNumberCell } from "./insights"
import { initialUploadState, phaseMessage, stepIndex, stepsFor, uploadReducer, type UploadState } from "./flow"
import type { AnalysisColumn, FileAnalysis } from "./types"
import type { LocalRead } from "./read-local"

const col = (name: string, type: string, extra: Partial<AnalysisColumn> = {}): AnalysisColumn => ({
  original_name: name,
  clean_name: name.toLowerCase().replace(/ /g, "_"),
  inferred_type: type,
  non_null_count: 10,
  total_count: 10,
  null_count: 0,
  unique_count: 5,
  sample_values: [],
  is_required: true,
  ...extra,
})

const analysis = (columns: AnalysisColumn[], extra: Partial<FileAnalysis> = {}): FileAnalysis => ({
  row_count: 10,
  column_count: columns.length,
  columns,
  suggested_table_name: "ventas",
  suggested_display_name: "Ventas",
  matching_table: null,
  ...extra,
})

const tables = [{ id: "t1", table_name: "clientes", display_name: "Clientes", row_count: 40 }]
const oneSheet: LocalRead = { sheets: [{ name: null, header: ["a"], rows: [["x"]] }] }

describe("predictDestination", () => {
  test("hoja nueva cuando no se parece a nada", () => {
    expect(predictDestination(analysis([col("Total", "number")]), tables)).toEqual({ kind: "new", name: "Ventas", newColumns: [] })
  })

  test("existente si el servidor encuentra coincidencia suficiente", () => {
    const a = analysis([col("Ciudad", "text")], {
      matching_table: {
        table_id: "t1", table_name: "clientes", display_name: "Clientes", match_score: 0.8,
        matched_columns: ["ciudad"], missing_in_table: ["fecha_alta"], extra_in_table: [],
      },
    })
    expect(predictDestination(a, tables)).toEqual({
      kind: "existing", name: "Clientes", tableId: "t1", existingRows: 40, newColumns: ["Fecha alta"],
    })
  })

  test("coincidencia baja (< 0,5) NO cuenta, pero el mismo nombre sugerido sí", () => {
    const low = analysis([col("x", "text")], {
      matching_table: { table_id: "t1", table_name: "clientes", display_name: "Clientes", match_score: 0.4, matched_columns: [], missing_in_table: [], extra_in_table: [] },
    })
    expect(predictDestination(low, tables).kind).toBe("new")
    expect(predictDestination(analysis([col("x", "text")], { suggested_table_name: "clientes" }), tables)).toMatchObject({
      kind: "existing",
      name: "Clientes",
    })
  })
})

describe("assessUpload", () => {
  test("un archivo limpio para una hoja nueva se guarda sin pedir revisión", () => {
    const a = assessUpload({ analysis: analysis([col("Fecha", "date"), col("Total", "number")]), tables, local: oneSheet, kind: "csv" })
    expect(a.needsReview).toBe(false)
    expect(a.issues).toEqual([])
  })

  test("mezclar con datos existentes pide revisión y lo explica", () => {
    const a = assessUpload({
      analysis: analysis([col("x", "text")], { suggested_table_name: "clientes" }),
      tables,
      local: oneSheet,
      kind: "csv",
    })
    expect(a.needsReview).toBe(true)
    expect(a.reviewReasons.join(" ")).toContain("«Clientes», que ya tiene 40 filas")
  })

  test("títulos faltantes (Unnamed) y columnas vacías se avisan", () => {
    const a = assessUpload({
      analysis: analysis([
        col("Reporte de ventas 2026", "text"),
        col("Unnamed: 1", "text"),
        col("Unnamed: 2", "text"),
        col("Notas", "text", { non_null_count: 0, null_count: 10 }),
      ]),
      tables: [],
      local: oneSheet,
      kind: "xlsx",
    })
    expect(a.needsReview).toBe(true)
    expect(a.issues.map((i) => i.id)).toEqual(expect.arrayContaining(["header", "empty-cols"]))
    expect(a.issues.find((i) => i.id === "header")?.title).toBe("Parece que la primera fila no tiene los títulos de las columnas")
  })

  test("pocas celdas vacías: aviso informativo sin bloquear el guardado directo", () => {
    const a = assessUpload({
      analysis: analysis([col("Fecha", "date", { null_count: 2, non_null_count: 8 }), col("Total", "number")]),
      tables: [],
      local: oneSheet,
      kind: "csv",
    })
    expect(a.needsReview).toBe(false)
    expect(a.issues[0]).toMatchObject({ id: "blanks", tone: "info" })
    expect(a.issues[0].detail).toContain("Fecha: 2 celdas")
  })

  test("Excel con varias hojas, o sin poder leerlo localmente, pide revisión", () => {
    const multi: LocalRead = {
      sheets: [
        { name: "Ventas", header: ["a"], rows: [["1"]] },
        { name: "Vacía", header: [], rows: [] },
        { name: "Clientes", header: ["b"], rows: [["2"], ["3"]] },
      ],
    }
    const a = assessUpload({ analysis: analysis([col("a", "text")]), tables: [], local: multi, kind: "xlsx" })
    expect(a.sheets).toEqual([{ name: "Ventas", rows: 1 }, { name: "Clientes", rows: 2 }])
    expect(a.needsReview).toBe(true)
    const unknown = assessUpload({ analysis: analysis([col("a", "text")]), tables: [], local: null, kind: "xlsx" })
    expect(unknown.unknownSheets).toBe(true)
    expect(unknown.needsReview).toBe(true)
  })

  test("sin filas: bloqueado", () => {
    const a = assessUpload({ analysis: analysis([col("a", "text")], { row_count: 0 }), tables: [], local: oneSheet, kind: "csv" })
    expect(a.blocked).toBe(true)
  })
})

describe("lectura de celdas igual que el servidor", () => {
  test("números: solo formato simple con punto decimal", () => {
    expect(parseNumberCell(" 1234.5 ")).toBe(1234.5)
    expect(parseNumberCell("1e3")).toBe(1000)
    expect(parseNumberCell(42)).toBe(42)
    expect(parseNumberCell("1.234,56")).toBeNull()
    expect(parseNumberCell("$ 12.500")).toBeNull()
    expect(parseNumberCell(true)).toBeNull()
  })

  test("fechas: ISO, D/M/AAAA, D/M/AA, AAAA-MM y AAAAMMDD", () => {
    const now = new Date(2026, 9, 16)
    const ymd = (d: Date | null) => (d ? [d.getFullYear(), d.getMonth() + 1, d.getDate()] : null)
    expect(ymd(parseDateCell("2026-03-01 00:00:00", now))).toEqual([2026, 3, 1])
    expect(ymd(parseDateCell("15/03/2026", now))).toEqual([2026, 3, 15])
    expect(ymd(parseDateCell("15/03/26", now))).toEqual([2026, 3, 15])
    expect(ymd(parseDateCell("15/03/55", now))).toEqual([1955, 3, 15])
    expect(ymd(parseDateCell("2026-03", now))).toEqual([2026, 3, 1])
    expect(ymd(parseDateCell("20260315", now))).toEqual([2026, 3, 15])
    expect(parseDateCell("31/02/2026", now)).toBeNull()
    expect(parseDateCell("mañana", now)).toBeNull()
  })
})

describe("computeInsights", () => {
  const columns = [
    col("Fecha", "date", { unique_count: 6 }),
    col("Sede", "text", { unique_count: 3 }),
    col("Total", "number", { unique_count: 6 }),
  ]
  const sheet = {
    name: null,
    header: ["Fecha", "Sede", "Total"],
    rows: [
      ["2026-08-03", "Chapinero", "1000"],
      ["2026-08-20", "Usaquén", "1000"],
      ["2026-09-02", "Chapinero", "1500"],
      ["2026-09-10", "Chapinero", "800"],
      ["2026-09-28", "Usaquén", "200"],
      ["no es fecha", "Cedritos", "abc"],
    ],
  }
  const text = (parts: { text: string }[]) => parts.map((p) => p.text).join("")

  test("periodo, total, líder, cambio mes a mes y gráfico por mes", () => {
    const res = computeInsights(sheet, columns, new Date(2026, 9, 16))!
    const byId = Object.fromEntries(res.facts.map((f) => [f.id, plain(text(f.parts))]))
    expect(byId.period).toBe("Tus datos van del 3 de agosto al 28 de septiembre de 2026.")
    expect(byId.total).toBe("En total, «Total» suma $ 4.500 en 6 filas.")
    expect(byId.leader).toBe("Por sede, lidera Chapinero: $ 3.300, el 73 % del total.")
    expect(byId.change).toBe("Septiembre sumó $ 2.500, +25 % frente a agosto.")
    expect(res.chart).toEqual({
      title: "Total por mes",
      form: "bar",
      unit: "money",
      points: [
        { name: "agosto", value: 2000 },
        { name: "septiembre", value: 2500 },
      ],
    })
  })

  test("avisa cuando el último mes está incompleto", () => {
    const partial = { ...sheet, rows: sheet.rows.filter((r) => r[0] !== "2026-09-28") }
    const res = computeInsights(partial, columns, new Date(2026, 9, 16))!
    expect(plain(text(res.facts.find((f) => f.id === "change")!.parts))).toContain("(con datos hasta el 10 de septiembre)")
  })

  test("si las columnas no coinciden con el análisis, no adivina", () => {
    expect(computeInsights({ ...sheet, header: ["a", "b"] }, columns)).toBeNull()
  })

  test("sin medida cuenta filas y grafica por categoría", () => {
    const cols = [col("Ciudad", "text", { unique_count: 2 }), col("Nombre", "text", { unique_count: 4 })]
    const res = computeInsights(
      { name: null, header: ["Ciudad", "Nombre"], rows: [["Cali", "a"], ["Cali", "b"], ["Pasto", "c"], ["Cali", "d"]] },
      cols
    )!
    expect(plain(text(res.facts[0].parts))).toBe("Guardamos 4 filas con datos.")
    expect(plain(text(res.facts[1].parts))).toBe("Por ciudad, lidera Cali: 3 filas, el 75 % del total.")
    expect(res.chart?.title).toBe("Filas por ciudad")
  })
})

describe("máquina de estados del cargue", () => {
  const file = new File(["a"], "a.csv")
  const okAssessment = { destination: null, sheets: [], unknownSheets: false, issues: [], needsReview: false, reviewReasons: [], blocked: false }
  const a = analysis([col("x", "text")])

  function run(actions: Parameters<typeof uploadReducer>[1][]): UploadState {
    return actions.reduce(uploadReducer, initialUploadState)
  }

  test("camino feliz sin revisión: leer → entender → guardar → listo", () => {
    let s = run([{ type: "select", file, kind: "csv" }])
    expect(s.phase).toBe("reading")
    s = uploadReducer(s, { type: "local-read", run: s.run, local: null })
    expect(s.phase).toBe("understanding")
    s = uploadReducer(s, { type: "analyzed", run: s.run, analysis: a, assessment: okAssessment })
    expect(s.phase).toBe("saving")
    expect(s.autoSaved).toBe(true)
    expect(stepIndex(s)).toBe(2)
    s = uploadReducer(s, { type: "saved", run: s.run, result: { status: "created_new_table", rows_inserted: 10 } })
    expect(s.phase).toBe("done")
    expect(stepIndex(s)).toBe(4)
    expect(phaseMessage(s)).toContain("Listo")
  })

  test("con revisión espera la confirmación y cambia la etiqueta del paso", () => {
    let s = run([{ type: "select", file, kind: "csv" }])
    s = uploadReducer(s, { type: "local-read", run: s.run, local: null })
    s = uploadReducer(s, { type: "analyzed", run: s.run, analysis: a, assessment: { ...okAssessment, needsReview: true } })
    expect(s.phase).toBe("review")
    expect(stepsFor(s)[1].label).toBe("Revisar contigo")
    s = uploadReducer(s, { type: "confirm" })
    expect(s.phase).toBe("saving")
  })

  test("un archivo bloqueado no se puede confirmar", () => {
    let s = run([{ type: "select", file, kind: "csv" }])
    s = uploadReducer(s, { type: "local-read", run: s.run, local: null })
    s = uploadReducer(s, { type: "analyzed", run: s.run, analysis: a, assessment: { ...okAssessment, blocked: true } })
    expect(uploadReducer(s, { type: "confirm" }).phase).toBe("review")
  })

  test("los errores permiten reintentar la fase que falló, conservando el archivo", () => {
    let s = run([{ type: "select", file, kind: "csv" }])
    s = uploadReducer(s, { type: "local-read", run: s.run, local: null })
    s = uploadReducer(s, { type: "fail", run: s.run, at: "understanding", error: { title: "x", description: "y", retryable: true, action: "retry" } })
    expect(s.phase).toBe("failed")
    expect(s.file).toBe(file)
    expect(stepIndex(s)).toBe(1)
    s = uploadReducer(s, { type: "retry" })
    expect(s.phase).toBe("understanding")
  })

  test("las respuestas de un intento anterior se ignoran", () => {
    let s = run([{ type: "select", file, kind: "csv" }])
    const oldRun = s.run
    s = uploadReducer(s, { type: "select", file, kind: "csv" })
    expect(uploadReducer(s, { type: "local-read", run: oldRun, local: null }).phase).toBe("reading")
  })

  test("rechazo local y reinicio", () => {
    const s = uploadReducer(initialUploadState, { type: "reject", file, problem: { title: "t", description: "d" } })
    expect(s.phase).toBe("rejected")
    expect(phaseMessage(s)).toBe("t")
    expect(uploadReducer(s, { type: "reset" }).phase).toBe("idle")
  })
})
