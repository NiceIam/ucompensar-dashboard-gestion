"use client"

import type { ReactNode } from "react"
import { SimpleChart, type ChartForm } from "@/components/charts/simple-chart"
import { DashboardCard } from "@/components/chat/dashboard-card"
import { DashboardEditCard } from "@/components/chat/dashboard-edit-card"
import { MESSAGE_BLOCK, MESSAGE_BLOCK_GLOBAL, parseDashboardBlock } from "@/lib/dashboard-block"
import { parseDashboardEditBlock } from "@/lib/dashboard-edit-block"
import { monthName } from "@/lib/format"
import { cn } from "@/lib/utils"

/** Bloque ```chart que manda el backend (contrato existente, no cambia). */
export interface ChatChartConfig {
  type: string
  title: string
  data: { name: string; value: number }[]
  x?: string
  y?: string
  color?: string
  /** Unidad de la medida (money en pesos); el servidor la decide por la columna medida. */
  unit?: "money" | "count" | "number"
}

/** Etiquetas de fecha del servidor ("2026-07", "2026-07-15") en español corto. */
export function prettyLabel(name: string): string {
  let m = name.match(/^(\d{4})-(\d{2})$/)
  if (m) return `${monthName(Number(m[2]) - 1).slice(0, 3)} ${m[1]}`
  m = name.match(/^(\d{4})-(\d{2})-(\d{2})$/)
  if (m) return `${Number(m[3])} ${monthName(Number(m[2]) - 1).slice(0, 3)} ${m[1]}`
  return name
}

function InlineChart({ config }: { config: ChatChartConfig }) {
  if (!Array.isArray(config.data) || config.data.length === 0) return null
  const form: ChartForm = config.type === "pie" ? "pie" : config.type === "line" ? "line" : config.type === "area" ? "area" : "bar"
  const points = config.data
    .filter((d) => d && typeof d.value === "number")
    .map((d) => ({ name: prettyLabel(String(d.name ?? "")), value: d.value }))
  return (
    <figure className="my-2 rounded-xl border bg-background/60 p-3">
      <figcaption className="pr-24 text-[13px] font-semibold">{config.title || "Gráfico"}</figcaption>
      <SimpleChart form={form} points={points} unit={config.unit === "money" ? "money" : "number"} label={config.title || "Gráfico"} height={190} />
    </figure>
  )
}

/** **negrita** dentro de una línea. */
function renderInline(text: string, key: string): ReactNode[] {
  return text.split(/(\*\*[^*]+\*\*)/).map((part, j) =>
    part.startsWith("**") && part.endsWith("**") && part.length > 4 ? (
      <strong key={`${key}-b${j}`} className="font-semibold text-foreground">
        {part.slice(2, -2)}
      </strong>
    ) : (
      <span key={`${key}-t${j}`}>{part}</span>
    )
  )
}

function parseTableRow(line: string): string[] {
  return line
    .trim()
    .replace(/^\|/, "")
    .replace(/\|$/, "")
    .split("|")
    .map((c) => c.trim())
}

function isTableSeparatorRow(line: string): boolean {
  if (!line.trim().startsWith("|")) return false
  const cells = parseTableRow(line)
  return cells.length > 0 && cells.every((c) => /^:?-{2,}:?$/.test(c))
}

/** Markdown básico: títulos, listas, tablas, citas y separadores. */
function renderTextBlock(text: string, keyPrefix: string): ReactNode {
  const lines = text.split("\n")
  const blocks: ReactNode[] = []
  let list: { type: "ul" | "ol"; items: string[] } | null = null

  const flushList = () => {
    if (!list) return
    const { items, type } = list
    const Tag = type
    blocks.push(
      <Tag
        key={`${keyPrefix}-list${blocks.length}`}
        className={cn("my-1.5 space-y-1 pl-5", type === "ul" ? "list-disc marker:text-primary" : "list-decimal marker:font-semibold marker:text-primary")}
      >
        {items.map((item, i) => (
          <li key={i} className="pl-0.5">
            {renderInline(item, `${keyPrefix}-li${blocks.length}-${i}`)}
          </li>
        ))}
      </Tag>
    )
    list = null
  }

  let i = 0
  while (i < lines.length) {
    const line = lines[i]
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
        <div key={`${keyPrefix}-tbl${i}`} className="relative my-2 overflow-x-auto rounded-xl border">
          <table className="w-full text-[13px]">
            <thead className="bg-muted/60">
              <tr>
                {header.map((h, hi) => (
                  <th key={hi} scope="col" className="whitespace-nowrap px-3 py-2 text-left font-semibold">
                    {renderInline(h, `${keyPrefix}-th${i}-${hi}`)}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((row, ri) => (
                <tr key={ri} className="border-t">
                  {row.map((cell, ci) => (
                    <td key={ci} className="whitespace-nowrap px-3 py-2 tabular">
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
    if (/^(---|\*\*\*|___)$/.test(line.trim())) {
      flushList()
      blocks.push(<hr key={`${keyPrefix}-hr${i}`} className="my-2 border-border" />)
      i++
      continue
    }
    const heading = line.match(/^#{1,3}\s+(.*)/)
    const quote = line.match(/^>\s?(.*)/)
    const bullet = line.match(/^\s*[-*•]\s+(.*)/)
    const numbered = line.match(/^\s*\d+[.)]\s+(.*)/)
    if (quote) {
      flushList()
      blocks.push(
        <p key={`${keyPrefix}-q${i}`} className="my-1 border-l-2 border-highlight pl-3 text-muted-foreground">
          {renderInline(quote[1], `${keyPrefix}-q${i}`)}
        </p>
      )
    } else if (heading) {
      flushList()
      blocks.push(
        <p key={`${keyPrefix}-h${i}`} className="mt-2 font-display text-base font-semibold first:mt-0">
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
    } else if (line.trim() === "") {
      flushList()
    } else {
      flushList()
      blocks.push(
        <p key={`${keyPrefix}-p${i}`} className="my-1 first:mt-0 last:mb-0">
          {renderInline(line, `${keyPrefix}-p${i}`)}
        </p>
      )
    }
    i++
  }
  flushList()
  return <>{blocks}</>
}

/** Contenido del asistente: texto con formato + gráficos y tarjetas de tablero en línea. */
export function MessageContent({ text }: { text: string }) {
  const parts = text.split(MESSAGE_BLOCK)
  return (
    <>
      {parts.map((part, i) => {
        // ```dashboard_edit va ANTES que ```dashboard: el segundo es prefijo del primero.
        if (part.startsWith("```dashboard_edit") && MESSAGE_BLOCK.test(part)) {
          const edit = parseDashboardEditBlock(part.replace(/^```dashboard_edit\s*\n/, "").replace(/\n```$/, ""))
          return edit ? <DashboardEditCard key={i} edit={edit} /> : null
        }
        if (part.startsWith("```dashboard") && MESSAGE_BLOCK.test(part)) {
          const board = parseDashboardBlock(part.replace(/^```dashboard\s*\n/, "").replace(/\n```$/, ""))
          return board ? <DashboardCard key={i} dashboard={board} /> : null
        }
        if (part.startsWith("```chart") && MESSAGE_BLOCK.test(part)) {
          const json = part.replace(/^```chart\s*\n/, "").replace(/\n```$/, "")
          try {
            return <InlineChart key={i} config={JSON.parse(json) as ChatChartConfig} />
          } catch {
            return null
          }
        }
        if (!part.trim()) return null
        return <div key={i}>{renderTextBlock(part.trim(), `b${i}`)}</div>
      })}
    </>
  )
}

/** Texto plano del mensaje, sin bloques de gráfico ni de tablero (para copiar). */
export function plainText(text: string): string {
  return text
    .replace(MESSAGE_BLOCK_GLOBAL, "")
    .replace(/\*\*([^*]+)\*\*/g, "$1")
    .trim()
}
