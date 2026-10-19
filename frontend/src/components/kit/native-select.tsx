import { ChevronDown } from "lucide-react"
import { cn } from "@/lib/utils"

export interface NativeSelectOption {
  value: string
  label: string
}

/**
 * Desplegable nativo con el aspecto del sistema de diseño. Se usa donde hay muchos (una fila por columna):
 * en el celular abre el selector del sistema, que es lo más cómodo, y se maneja bien con teclado y lector de pantalla.
 */
export function NativeSelect({
  value,
  onChange,
  options,
  label,
  id,
  disabled,
  className,
}: {
  value: string
  onChange: (value: string) => void
  options: NativeSelectOption[]
  /** Nombre accesible (lo que lee el lector de pantalla). */
  label: string
  id?: string
  disabled?: boolean
  className?: string
}) {
  return (
    <div className={cn("relative", className)}>
      <select
        id={id}
        aria-label={label}
        value={value}
        disabled={disabled}
        onChange={(e) => onChange(e.target.value)}
        className="h-11 w-full appearance-none rounded-xl border border-input bg-card py-2 pl-3.5 pr-10 text-[15px] text-foreground ring-offset-background hover:border-foreground/25 focus:border-ring focus:outline-none focus:ring-4 focus:ring-ring/15 disabled:cursor-not-allowed disabled:opacity-50 sm:h-10 sm:text-sm"
      >
        {options.map((o) => (
          <option key={o.value} value={o.value}>
            {o.label}
          </option>
        ))}
      </select>
      <ChevronDown className="pointer-events-none absolute right-3 top-1/2 h-4 w-4 -translate-y-1/2 opacity-60" aria-hidden="true" />
    </div>
  )
}
