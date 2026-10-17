"use client"

import { useCallback } from "react"
import { useDropzone } from "react-dropzone"
import { FileJson, FileSpreadsheet, FileText, UploadCloud } from "lucide-react"
import { Illustration } from "@/components/kit/illustrations"
import { ACCEPT_ATTR } from "@/lib/upload/local-file"
import { cn } from "@/lib/utils"

const FORMATS = [
  { label: "Excel", hint: ".xlsx", icon: FileSpreadsheet },
  { label: "CSV", hint: ".csv", icon: FileText },
  { label: "JSON", hint: ".json", icon: FileJson },
]

/**
 * Zona para arrastrar o elegir un archivo. No filtra por tipo: la validación
 * la hace quien la usa (con mensajes humanos), así nunca hay rechazos mudos.
 * Accesible con teclado (Enter/Espacio abren el selector).
 */
export function FileDrop({
  onFile,
  disabled = false,
  compact = false,
  className,
  title,
}: {
  onFile: (file: File) => void
  disabled?: boolean
  compact?: boolean
  className?: string
  title?: string
}) {
  const onDrop = useCallback(
    (accepted: File[]) => {
      const file = accepted[0]
      if (file) onFile(file)
    },
    [onFile]
  )

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    multiple: false,
    disabled,
    noKeyboard: false,
  })

  const chips = (
    <ul className="flex flex-wrap items-center justify-center gap-2" aria-label="Formatos aceptados">
      {FORMATS.map(({ label, hint, icon: Icon }) => (
        <li
          key={label}
          className="inline-flex items-center gap-1.5 rounded-full border bg-card/80 px-3 py-1 text-xs font-medium text-foreground/80"
        >
          <Icon className="h-3.5 w-3.5 text-primary" aria-hidden="true" />
          {label}
          <span className="text-muted-foreground">{hint}</span>
        </li>
      ))}
      <li className="text-xs text-muted-foreground">hasta 10 MB</li>
    </ul>
  )

  return (
    <div
      {...getRootProps({
        role: "button",
        "aria-label": title ?? "Elegir un archivo para subir",
        "aria-disabled": disabled || undefined,
      })}
      className={cn(
        "group relative flex cursor-pointer flex-col items-center justify-center border-2 border-dashed text-center outline-none transition-[background-color,border-color,box-shadow] duration-150",
        "focus-visible:border-primary focus-visible:ring-4 focus-visible:ring-ring/20",
        compact ? "gap-3 rounded-2xl px-5 py-5 sm:flex-row sm:justify-between sm:text-left" : "gap-5 rounded-3xl px-6 py-10 sm:py-14",
        isDragActive
          ? "border-primary bg-primary-soft/70"
          : "border-input bg-card/60 hover:border-primary/50 hover:bg-primary-soft/30",
        disabled && "pointer-events-none opacity-60",
        className
      )}
    >
      <input {...getInputProps({ accept: ACCEPT_ATTR })} />
      {compact ? (
        <>
          <div className="flex items-center gap-3">
            <span
              className={cn(
                "flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-primary text-primary-foreground transition-transform duration-200",
                isDragActive && "scale-110"
              )}
            >
              <UploadCloud className="h-5 w-5" aria-hidden="true" />
            </span>
            <div className="text-left">
              <p className="font-semibold">
                {isDragActive ? "Suéltalo aquí" : title ?? "Agrega más datos"}
              </p>
              <p className="text-sm text-muted-foreground">
                <span className="[@media(pointer:coarse)]:hidden">Arrastra un archivo o </span>
                <span className="font-semibold text-primary underline-offset-4 group-hover:underline">
                  <span className="[@media(pointer:coarse)]:hidden">elígelo</span>
                  <span className="hidden [@media(pointer:coarse)]:inline">Toca para elegir un archivo</span>
                </span>
              </p>
            </div>
          </div>
          {chips}
        </>
      ) : (
        <>
          <Illustration
            name="upload"
            className={cn("h-28 transition-transform duration-300 sm:h-32", isDragActive && "scale-105 -rotate-2")}
          />
          <div className="space-y-1.5">
            <p className="font-display text-2xl font-semibold leading-tight">
              {isDragActive ? "Suéltalo aquí" : title ?? "Arrastra tu archivo aquí"}
            </p>
            <p className="text-[15px] text-muted-foreground">
              <span className="[@media(pointer:coarse)]:hidden">o </span>
              <span className="font-semibold text-primary underline-offset-4 group-hover:underline">
                <span className="[@media(pointer:coarse)]:hidden">elige uno de tu computador</span>
                <span className="hidden [@media(pointer:coarse)]:inline">Toca para elegir un archivo</span>
              </span>
            </p>
          </div>
          {chips}
        </>
      )}
    </div>
  )
}
