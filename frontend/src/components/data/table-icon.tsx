import {
  Boxes,
  ClipboardList,
  FileSpreadsheet,
  HandCoins,
  Package,
  Receipt,
  ShoppingBag,
  Truck,
  Users,
  UtensilsCrossed,
  Wrench,
  type LucideIcon,
} from "lucide-react"
import { nameTokens } from "@/lib/data-vocabulary"
import { cn } from "@/lib/utils"

// Se compara por inicio de palabra: "inventario" no debe confundirse con "venta".
const RULES: [RegExp, LucideIcon][] = [
  [/(^| )(venta|pedido|orden)/, ShoppingBag],
  [/(^| )(cliente|usuario|contacto|empleado|paciente)/, Users],
  [/(^| )(inventario|stock|bodega|existencia)/, Boxes],
  [/(^| )(producto|articulo|item)/, Package],
  [/(^| )(proveedor|compra)/, Truck],
  [/(^| )(factura|recibo|pago)/, Receipt],
  [/(^| )(cotizacion|presupuesto)/, HandCoins],
  [/(^| )(menu|plato|receta)/, UtensilsCrossed],
  [/(^| )(servicio|tarea)/, Wrench],
  [/(^| )(movimiento|registro|bitacora)/, ClipboardList],
]

/** Icono según el nombre de la hoja (ventas, clientes, inventario…). */
export function tableIconFor(name: string): LucideIcon {
  const text = nameTokens(name).join(" ")
  return RULES.find(([re]) => re.test(text))?.[1] ?? FileSpreadsheet
}

export function TableIcon({ name, className }: { name: string; className?: string }) {
  const Icon = tableIconFor(name)
  return (
    <span className={cn("flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-primary-soft text-primary-strong", className)}>
      <Icon className="h-5 w-5" aria-hidden="true" />
    </span>
  )
}
