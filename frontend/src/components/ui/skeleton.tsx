import * as React from "react"
import { cn } from "@/lib/utils"

/** Bloque de carga con un brillo suave que recorre el contenido (se apaga con movimiento reducido). */
function Skeleton({
  className,
  ...props
}: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      aria-hidden="true"
      className={cn(
        "relative overflow-hidden rounded-lg bg-muted before:absolute before:inset-0 before:w-1/2 before:animate-sweep before:bg-gradient-to-r before:from-transparent before:via-card/60 before:to-transparent",
        className
      )}
      {...props}
    />
  )
}

export { Skeleton }
