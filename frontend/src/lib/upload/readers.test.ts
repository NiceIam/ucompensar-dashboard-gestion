import { describe, expect, test } from "vitest"
import { decodeText, detectSeparator, parseCsv } from "./csv"
import { columnIndex, excelSerialToDate, isDateFormatCode, readXlsx, readZipIndex } from "./xlsx"
import { readLocalFile, sheetsWithData } from "./read-local"
import { friendlyFileName, validateLocalFile, withExplicitType } from "./local-file"

// ─── ZIP mínimo para pruebas (método 0 = sin comprimir, o 8 = deflate) ─────────

async function deflateRaw(data: Uint8Array): Promise<Uint8Array | null> {
  if (typeof CompressionStream === "undefined") return null
  try {
    const stream = new Response(data as unknown as BodyInit).body!.pipeThrough(new CompressionStream("deflate-raw"))
    return new Uint8Array(await new Response(stream).arrayBuffer())
  } catch {
    return null
  }
}

async function makeZip(files: Record<string, string>, deflate = false): Promise<ArrayBuffer> {
  const enc = new TextEncoder()
  const parts: Uint8Array[] = []
  const central: Uint8Array[] = []
  let offset = 0
  for (const [name, content] of Object.entries(files)) {
    const nameBytes = enc.encode(name)
    const raw = enc.encode(content)
    const packed = deflate ? (await deflateRaw(raw)) ?? raw : raw
    const method = deflate && packed !== raw ? 8 : 0
    const local = new DataView(new ArrayBuffer(30))
    local.setUint32(0, 0x04034b50, true)
    local.setUint16(8, method, true)
    local.setUint32(18, packed.length, true)
    local.setUint32(22, raw.length, true)
    local.setUint16(26, nameBytes.length, true)
    parts.push(new Uint8Array(local.buffer), nameBytes, packed)
    const cd = new DataView(new ArrayBuffer(46))
    cd.setUint32(0, 0x02014b50, true)
    cd.setUint16(10, method, true)
    cd.setUint32(20, packed.length, true)
    cd.setUint32(24, raw.length, true)
    cd.setUint16(28, nameBytes.length, true)
    cd.setUint32(42, offset, true)
    central.push(new Uint8Array(cd.buffer), nameBytes)
    offset += 30 + nameBytes.length + packed.length
  }
  const cdSize = central.reduce((s, p) => s + p.length, 0)
  const eocd = new DataView(new ArrayBuffer(22))
  eocd.setUint32(0, 0x06054b50, true)
  eocd.setUint16(8, Object.keys(files).length, true)
  eocd.setUint16(10, Object.keys(files).length, true)
  eocd.setUint32(12, cdSize, true)
  eocd.setUint32(16, offset, true)
  const all = [...parts, ...central, new Uint8Array(eocd.buffer)]
  const out = new Uint8Array(all.reduce((s, p) => s + p.length, 0))
  let at = 0
  for (const p of all) {
    out.set(p, at)
    at += p.length
  }
  return out.buffer
}

const WORKBOOK = `<?xml version="1.0" encoding="UTF-8"?>
<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
<sheets><sheet name="Ventas" sheetId="1" r:id="rId1"/><sheet name="Vacía" sheetId="2" r:id="rId2"/><sheet name="Clientes" sheetId="3" r:id="rId3"/></sheets></workbook>`
const RELS = `<?xml version="1.0"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Target="worksheets/sheet1.xml"/><Relationship Id="rId2" Target="worksheets/sheet2.xml"/><Relationship Id="rId3" Target="/xl/worksheets/sheet3.xml"/></Relationships>`
const SHARED = `<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><si><t>fecha</t></si><si><t>producto</t></si><si><t>total</t></si><si><r><t>Café </t></r><r><t>de origen</t></r></si><si><t>ciudad</t></si><si><t>Bogotá</t></si></sst>`
const STYLES = `<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><numFmts count="1"><numFmt numFmtId="164" formatCode="dd/mm/yyyy;@"/></numFmts><cellXfs count="3"><xf numFmtId="0"/><xf numFmtId="164"/><xf numFmtId="4"/></cellXfs></styleSheet>`
const SHEET1 = `<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>
<row r="1"><c r="A1" t="s"><v>0</v></c><c r="B1" t="s"><v>1</v></c><c r="C1" t="s"><v>2</v></c></row>
<row r="2"><c r="A2" s="1"><v>46082</v></c><c r="B2" t="s"><v>3</v></c><c r="C2" s="2"><v>9500.5</v></c></row>
<row r="4"><c r="A4" s="1"><v>46083</v></c><c r="C4"><v>12000</v></c></row>
</sheetData></worksheet>`
const SHEET2 = `<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData/></worksheet>`
const SHEET3 = `<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>
<row r="1"><c r="A1" t="s"><v>4</v></c><c r="B1" t="inlineStr"><is><t>activo</t></is></c></row>
<row r="2"><c r="A2" t="s"><v>5</v></c><c r="B2" t="b"><v>1</v></c></row>
</sheetData></worksheet>`

const XLSX_FILES = {
  "xl/workbook.xml": WORKBOOK,
  "xl/_rels/workbook.xml.rels": RELS,
  "xl/sharedStrings.xml": SHARED,
  "xl/styles.xml": STYLES,
  "xl/worksheets/sheet1.xml": SHEET1,
  "xl/worksheets/sheet2.xml": SHEET2,
  "xl/worksheets/sheet3.xml": SHEET3,
}

describe("CSV", () => {
  test("decodifica UTF-8 con BOM y cae a Windows-1252 si hace falta", () => {
    expect(decodeText(new Uint8Array([0xef, 0xbb, 0xbf, 0x61, 0xc3, 0xb1]))).toBe("añ")
    expect(decodeText(new Uint8Array([0x61, 0xf1]))).toBe("añ") // ñ en cp1252
  })

  test("detecta el separador como el servidor", () => {
    expect(detectSeparator("a;b;c\n1;2;3")).toBe(";")
    expect(detectSeparator("a,b\n1,2")).toBe(",")
    expect(detectSeparator('"x;y",b,c\n')).toBe(",")
    expect(detectSeparator("a\tb\tc")).toBe("\t")
  })

  test("respeta comillas, comillas escapadas y saltos de línea dentro de celdas", () => {
    const rows = parseCsv('nombre,nota\r\n"Pérez, Ana","dijo ""hola""\nadiós"\nLuis,ok\n')
    expect(rows).toEqual([
      ["nombre", "nota"],
      ["Pérez, Ana", 'dijo "hola"\nadiós'],
      ["Luis", "ok"],
    ])
  })
})

describe("Excel (.xlsx) sin dependencias", () => {
  test("utilidades", () => {
    expect(columnIndex("A1")).toBe(0)
    expect(columnIndex("AB12")).toBe(27)
    expect(isDateFormatCode("dd/mm/yyyy;@")).toBe(true)
    expect(isDateFormatCode("#,##0.00")).toBe(false)
    expect(isDateFormatCode('"Total: "0')).toBe(false)
    const d = excelSerialToDate(46082)
    expect([d.getFullYear(), d.getMonth() + 1, d.getDate()]).toEqual([2026, 3, 1])
  })

  test("lee hojas, textos compartidos, fechas, números, booleanos y filas saltadas", async () => {
    const buffer = await makeZip(XLSX_FILES)
    expect(readZipIndex(buffer)).toHaveLength(7)
    const sheets = await readXlsx(buffer)
    expect(sheets.map((s) => s.name)).toEqual(["Ventas", "Vacía", "Clientes"])
    const [ventas, vacia, clientes] = sheets
    expect(ventas.rows[0]).toEqual(["fecha", "producto", "total"])
    expect((ventas.rows[1][0] as Date).getDate()).toBe(1)
    expect(ventas.rows[1][1]).toBe("Café de origen")
    expect(ventas.rows[1][2]).toBe(9500.5)
    expect(ventas.rows[2]).toEqual([]) // fila 3 no existe en el XML
    expect(ventas.rows[3][1]).toBeNull()
    expect(ventas.rows[3][2]).toBe(12000)
    expect(vacia.rows).toEqual([])
    expect(clientes.rows[1]).toEqual(["Bogotá", true])
  })

  test("también funciona con partes comprimidas (deflate), si el entorno lo permite", async () => {
    if (typeof CompressionStream === "undefined" || typeof DecompressionStream === "undefined") return
    const buffer = await makeZip(XLSX_FILES, true)
    const sheets = await readXlsx(buffer)
    expect(sheets[0].rows[1][1]).toBe("Café de origen")
  })

  test("readLocalFile arma encabezados y omite hojas sin datos", async () => {
    const buffer = await makeZip(XLSX_FILES)
    const read = await readLocalFile(new Blob([buffer]), "xlsx")
    expect(read).not.toBeNull()
    const withData = sheetsWithData(read)
    expect(withData.map((s) => [s.name, s.rows.length])).toEqual([
      ["Ventas", 2],
      ["Clientes", 1],
    ])
    expect(withData[0].header).toEqual(["fecha", "producto", "total"])
  })

  test("un archivo que no es ZIP devuelve null en vez de fallar", async () => {
    expect(await readLocalFile(new Blob(["hola"]), "xlsx")).toBeNull()
  })
})

describe("readLocalFile con CSV y JSON", () => {
  test("CSV con punto y coma y filas vacías", async () => {
    const read = await readLocalFile(new Blob(["fecha;total\n\n01/03/2026;9500\n02/03/2026;12000\n"]), "csv")
    expect(read?.sheets[0].header).toEqual(["fecha", "total"])
    expect(read?.sheets[0].rows).toEqual([
      ["01/03/2026", "9500"],
      ["02/03/2026", "12000"],
    ])
  })

  test("JSON de objetos (une todas las claves en orden)", async () => {
    const read = await readLocalFile(new Blob([JSON.stringify([{ a: 1 }, { a: 2, b: true }, { b: { x: 1 } }])]), "json")
    expect(read?.sheets[0].header).toEqual(["a", "b"])
    expect(read?.sheets[0].rows).toEqual([
      [1, null],
      [2, true],
      [null, '{"x":1}'],
    ])
  })
})

describe("validación local", () => {
  test("acepta Excel, CSV y JSON y explica lo demás", () => {
    expect(validateLocalFile({ name: "ventas.xlsx", size: 100 })).toEqual({ ok: true, kind: "xlsx" })
    expect(validateLocalFile({ name: "ventas.CSV", size: 100 })).toEqual({ ok: true, kind: "csv" })
    const xls = validateLocalFile({ name: "viejo.xls", size: 100 })
    expect(xls.ok).toBe(false)
    if (!xls.ok) expect(xls.description).toContain(".xlsx")
    const pdf = validateLocalFile({ name: "reporte.pdf", size: 100 })
    expect(pdf.ok).toBe(false)
    const empty = validateLocalFile({ name: "a.csv", size: 0 })
    expect(empty.ok).toBe(false)
    const big = validateLocalFile({ name: "a.csv", size: 12 * 1024 * 1024 })
    expect(big.ok).toBe(false)
    if (!big.ok) expect(big.title).toContain("12 MB")
  })

  test("los CSV salen con su tipo MIME correcto (Windows los marca como Excel)", () => {
    const original = new File(["a,b"], "datos.csv", { type: "application/vnd.ms-excel" })
    const fixed = withExplicitType(original, "csv")
    expect(fixed.type).toBe("text/csv")
    expect(fixed.name).toBe("datos.csv")
  })

  test("nombre amable a partir del archivo", () => {
    expect(friendlyFileName("ventas_marzo-2026.xlsx")).toBe("Ventas marzo 2026")
    expect(friendlyFileName(".csv")).toBe("Mis datos")
  })
})
