"use client"

import { useCallback, useState } from "react"
import { useDropzone, type FileRejection } from "react-dropzone"
import { Upload, FileText, X, AlertCircle } from "lucide-react"
import { Progress } from "@/components/ui/progress"
import { Button } from "@/components/ui/button"
import { cn, formatFileSize } from "@/lib/utils"

const ACCEPTED_TYPES: Record<string, string[]> = {
  "text/csv": [".csv"],
  "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": [
    ".xlsx",
  ],
  "application/json": [".json"],
}

const MAX_SIZE = 10 * 1024 * 1024 // 10MB

interface FileUploadZoneProps {
  onUpload: (file: File) => Promise<void>
  uploading?: boolean
  progress?: number
  className?: string
}

export function FileUploadZone({
  onUpload,
  uploading = false,
  progress = 0,
  className,
}: FileUploadZoneProps) {
  const [selectedFile, setSelectedFile] = useState<File | null>(null)
  const [error, setError] = useState<string | null>(null)

  const onDrop = useCallback(
    async (acceptedFiles: File[], rejectedFiles: FileRejection[]) => {
      setError(null)

      if (rejectedFiles.length > 0) {
        const firstError = rejectedFiles[0].errors[0]
        if (firstError.message.includes("file-too-large")) {
          setError(`El archivo supera el límite de ${formatFileSize(MAX_SIZE)}`)
        } else {
          setError("Formato no válido. Sube archivos CSV, Excel (.xlsx) o JSON.")
        }
        return
      }

      const file = acceptedFiles[0]
      if (!file) return

      setSelectedFile(file)
      try {
        await onUpload(file)
      } catch (err) {
        setError(
          err instanceof Error ? err.message : "Error al subir el archivo"
        )
        setSelectedFile(null)
      }
    },
    [onUpload]
  )

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: ACCEPTED_TYPES,
    maxSize: MAX_SIZE,
    maxFiles: 1,
    disabled: uploading,
  })

  const clearFile = () => {
    setSelectedFile(null)
    setError(null)
  }

  return (
    <div className={cn("space-y-3", className)}>
      <div
        {...getRootProps()}
        className={cn(
          "relative flex flex-col items-center justify-center rounded-xl border-2 border-dashed p-8 text-center cursor-pointer transition-colors",
          isDragActive
            ? "border-primary bg-primary/5"
            : "border-muted-foreground/25 hover:border-primary/50 hover:bg-accent/50",
          uploading && "pointer-events-none opacity-60"
        )}
      >
        <input {...getInputProps()} />

        <div className="flex h-12 w-12 items-center justify-center rounded-full bg-primary/10 mb-3">
          <Upload className="h-6 w-6 text-primary" />
        </div>

        <p className="text-sm font-medium">
          {isDragActive
            ? "Suelta el archivo aquí..."
            : "Arrastra tu archivo aquí"}
        </p>
        <p className="text-xs text-muted-foreground mt-1">
          o{" "}
          <span className="text-primary font-medium">
            haz clic para seleccionar
          </span>
        </p>
        <p className="text-xs text-muted-foreground mt-2">
          CSV, Excel (.xlsx), JSON — máximo {formatFileSize(MAX_SIZE)}
        </p>
      </div>

      {/* Error */}
      {error && (
        <div className="flex items-center gap-2 rounded-lg border border-destructive/50 bg-destructive/10 px-3 py-2 text-sm text-destructive">
          <AlertCircle className="h-4 w-4 shrink-0" />
          {error}
        </div>
      )}

      {/* Selected file */}
      {selectedFile && !error && (
        <div className="rounded-lg border bg-card p-3 space-y-2">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2 min-w-0">
              <FileText className="h-4 w-4 text-muted-foreground shrink-0" />
              <span className="text-sm font-medium truncate">
                {selectedFile.name}
              </span>
              <span className="text-xs text-muted-foreground shrink-0">
                {formatFileSize(selectedFile.size)}
              </span>
            </div>
            {!uploading && (
              <Button
                variant="ghost"
                size="icon"
                className="h-6 w-6 shrink-0"
                onClick={(e) => {
                  e.stopPropagation()
                  clearFile()
                }}
              >
                <X className="h-3.5 w-3.5" />
              </Button>
            )}
          </div>

          {uploading && (
            <div className="space-y-1">
              <Progress value={progress} className="h-1.5" />
              <p className="text-xs text-muted-foreground">
                Subiendo... {progress}%
              </p>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
