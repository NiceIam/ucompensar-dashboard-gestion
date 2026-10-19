"use client"

import { useRouter } from "next/navigation"
import { useEffect } from "react"
import { AppShell } from "@/components/shell/app-shell"
import { FloatingChat } from "@/components/chat/floating-chat"
import { DotsLoader } from "@/components/kit/dots"
import { ChatProvider } from "@/providers/chat-provider"
import { useAuthContext } from "@/providers/auth-provider"

function FullPageLoader() {
  return (
    <div className="flex h-dvh flex-col items-center justify-center gap-4 bg-background" role="status" aria-live="polite">
      <DotsLoader size="lg" />
      <p className="text-sm font-medium text-muted-foreground">Preparando tu espacio…</p>
    </div>
  )
}

export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  const { user, loading: authLoading } = useAuthContext()
  const router = useRouter()

  // Respaldo del lado del cliente a la protección de rutas: el middleware
  // (basado en la cookie access_token) no puede detectar la sesión cuando
  // frontend y backend viven en dominios/sitios distintos (ej. dos proyectos
  // de Vercel) -- ahí la cookie nunca es visible en el dominio del frontend.
  // Este efecto usa /api/v1/auth/me (que sí viaja cross-site con
  // credentials:"include") como fuente de verdad real.
  useEffect(() => {
    if (!authLoading && !user) {
      router.replace("/login")
    }
  }, [authLoading, user, router])

  if (authLoading || !user) return <FullPageLoader />

  return (
    <ChatProvider>
      <AppShell chat={<FloatingChat />}>{children}</AppShell>
    </ChatProvider>
  )
}
