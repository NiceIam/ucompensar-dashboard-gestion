/** Datos de ejemplo para las pruebas de la carga inteligente (la forma exacta de /intake/analyze). */
import type {
  AnalyzeResponse,
  CommitResponse,
  IntakeColumn,
  IntakeFile,
  IntakeSheet,
  Ontology,
  SheetKind,
} from "@/types/intake"

export const ONTOLOGY: Ontology = {
  kinds: [
    { kind: "productos", label: "productos", choice_label: "Lista de productos (costos, precios, existencias)" },
    { kind: "ventas", label: "ventas", choice_label: "Ventas (lo que vendiste)" },
    { kind: "compras", label: "compras", choice_label: "Compras (lo que le compraste a proveedores)" },
    { kind: "cuentas_por_cobrar", label: "cuentas por cobrar", choice_label: "Cuentas por cobrar (lo que te deben)" },
    { kind: "movimientos_inventario", label: "movimientos de inventario", choice_label: "Movimientos de inventario (entradas y salidas)" },
    { kind: "clientes", label: "clientes", choice_label: "Lista de clientes" },
    { kind: "proveedores", label: "proveedores", choice_label: "Lista de proveedores" },
    { kind: "otro", label: "datos", choice_label: "Otra cosa (la guardo tal cual)" },
  ],
  roles: {
    productos: [
      { role: "producto_nombre", label: "Nombre del producto", explain: "el nombre de cada producto" },
      { role: "costo_unitario", label: "Costo", explain: "lo que pagaste por cada producto" },
      { role: "stock", label: "Existencias", explain: "cuántas unidades tienes disponibles" },
      { role: "otro", label: "Dato adicional", explain: "un dato extra que guardo tal cual" },
    ],
    ventas: [
      { role: "fecha", label: "Fecha de la venta", explain: "el día en que se hizo la venta" },
      { role: "producto", label: "Producto vendido", explain: "qué producto se vendió" },
      { role: "cantidad", label: "Cantidad", explain: "cuántas unidades se vendieron" },
      { role: "precio_unitario", label: "Precio por unidad", explain: "lo que cobraste por cada unidad" },
      { role: "total", label: "Total de la venta", explain: "lo que sumó toda la venta" },
      { role: "cliente", label: "Cliente", explain: "quién compró" },
      { role: "otro", label: "Dato adicional", explain: "un dato extra que guardo tal cual" },
    ],
    compras: [
      { role: "fecha", label: "Fecha de la compra", explain: "el día en que hiciste la compra" },
      { role: "costo_unitario", label: "Costo por unidad", explain: "lo que pagaste por cada unidad" },
      { role: "total", label: "Total de la compra", explain: "lo que sumó toda la compra" },
      { role: "otro", label: "Dato adicional", explain: "un dato extra que guardo tal cual" },
    ],
    cuentas_por_cobrar: [{ role: "otro", label: "Dato adicional", explain: "un dato extra que guardo tal cual" }],
    movimientos_inventario: [{ role: "otro", label: "Dato adicional", explain: "un dato extra que guardo tal cual" }],
    clientes: [{ role: "otro", label: "Dato adicional", explain: "un dato extra que guardo tal cual" }],
    proveedores: [{ role: "otro", label: "Dato adicional", explain: "un dato extra que guardo tal cual" }],
    otro: [{ role: "otro", label: "Dato adicional", explain: "un dato extra que guardo tal cual" }],
  },
}

export function column(index: number, original: string, role: string, confidence = 0.98, explain = ""): IntakeColumn {
  return {
    index,
    name: original.toLowerCase().replace(/\s+/g, "_"),
    original_name: original,
    role,
    role_label: role,
    explain,
    confidence,
    type: "text",
    sample: ["a", "b"],
    source: "heuristic",
  }
}

export function sheet(over: Partial<IntakeSheet> & { key: string }): IntakeSheet {
  const kind: SheetKind = over.kind ?? "ventas"
  return {
    sheet_name: null,
    status: "ready",
    rows: 731,
    columns_count: 4,
    kind,
    kind_label: kind,
    kind_confidence: 0.98,
    mapping_source: "heuristic",
    from_cache: false,
    needs_review: false,
    review_reasons: [],
    period: { from: "2026-05-02", to: "2026-10-17" },
    kind_phrase: "tus ventas",
    stats: "731 filas, de mayo a octubre de 2026",
    summary: "Encontré tus ventas: 731 filas, de mayo a octubre de 2026.",
    columns: [
      column(0, "Fecha", "fecha", 0.98, "el día en que se hizo la venta"),
      column(1, "Producto", "producto", 0.98, "qué producto se vendió"),
      column(2, "Cantidad", "cantidad", 0.98, "cuántas unidades se vendieron"),
      column(3, "Total", "total", 0.98, "lo que sumó toda la venta"),
    ],
    tokens: { model_calls: 0, prompt: 0, output: 0, thoughts: 0, total: 0, from_cache: false },
    signature: "abc",
    destination: {
      action: "create",
      table_id: null,
      into_sheet: null,
      display_name: null,
      similarity: null,
      new_display_name: "Ventas octubre",
      text: "Se guardará como una hoja nueva: «Ventas octubre».",
    },
    ...over,
  }
}

export function file(name: string, sheets: IntakeSheet[]): IntakeFile {
  return { file_name: name, status: "ok", error: null, sheets }
}

export function proposal(...files: IntakeFile[]): AnalyzeResponse {
  return {
    files,
    ai: { model_calls: 0, prompt_tokens: 0, output_tokens: 0, thoughts_tokens: 0, cache_hits: 0 },
    limits: { max_files: 10, max_rows: 10000 },
  }
}

export function commitResponse(over: Partial<CommitResponse> = {}): CommitResponse {
  return {
    results: [
      {
        key: "ventas.csv::",
        file_name: "ventas.csv",
        sheet_name: null,
        status: "created",
        table_id: "t1",
        table_name: "ventas",
        display_name: "Ventas octubre",
        kind: "ventas",
        kind_label: "ventas",
        rows_inserted: 731,
        total_rows: 731,
        message: "Guardé 731 filas en «Ventas octubre».",
        error: null,
        undo: { action: "delete_table", table_id: "t1" },
      },
    ],
    totals: { created: 1, appended: 0, duplicates: 0, errors: 0, rows_inserted: 731 },
    ...over,
  }
}
