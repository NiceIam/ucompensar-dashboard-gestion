"use client"

import type { ReactNode } from "react"
import { AlertTriangle, HelpCircle, type LucideIcon } from "lucide-react"
import {
  AlertDialog,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog"
import { Button } from "@/components/ui/button"
import { cn } from "@/lib/utils"

/**
 * Diálogo de confirmación: pregunta clara, qué pasa si confirmas, botón con la
 * acción exacta y bloqueo mientras se ejecuta (no se cierra a medias).
 */
export function ConfirmDialog({
  open,
  onOpenChange,
  title,
  description,
  confirmLabel,
  cancelLabel = "Cancelar",
  tone = "danger",
  loading = false,
  onConfirm,
  icon,
  children,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  title: ReactNode
  description?: ReactNode
  confirmLabel: ReactNode
  cancelLabel?: ReactNode
  tone?: "danger" | "primary"
  loading?: boolean
  onConfirm: () => void | Promise<void>
  icon?: LucideIcon
  children?: ReactNode
}) {
  const Icon = icon ?? (tone === "danger" ? AlertTriangle : HelpCircle)
  return (
    <AlertDialog open={open} onOpenChange={(next) => !loading && onOpenChange(next)}>
      <AlertDialogContent>
        <AlertDialogHeader className="sm:flex-row sm:items-start sm:gap-4 sm:space-y-0">
          <span
            className={cn(
              "mx-auto mb-1 flex h-12 w-12 shrink-0 items-center justify-center rounded-2xl sm:mx-0 sm:mb-0",
              tone === "danger" ? "bg-danger-soft text-danger-strong" : "bg-primary-soft text-primary-strong"
            )}
          >
            <Icon className="h-6 w-6" aria-hidden="true" />
          </span>
          <div className="space-y-2">
            <AlertDialogTitle>{title}</AlertDialogTitle>
            {description && (
              <AlertDialogDescription className="text-[15px] leading-relaxed">{description}</AlertDialogDescription>
            )}
          </div>
        </AlertDialogHeader>
        {children}
        <AlertDialogFooter>
          <AlertDialogCancel disabled={loading}>{cancelLabel}</AlertDialogCancel>
          <Button
            variant={tone === "danger" ? "destructive" : "default"}
            loading={loading}
            onClick={() => void onConfirm()}
          >
            {confirmLabel}
          </Button>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  )
}
