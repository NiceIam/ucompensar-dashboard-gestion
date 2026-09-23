import type { Metadata, Viewport } from "next"
import localFont from "next/font/local"
import "./globals.css"
import { QueryProvider } from "@/providers/query-provider"
import { AuthProvider } from "@/providers/auth-provider"
import { Toaster } from "@/components/ui/sonner"
import { TooltipProvider } from "@/components/ui/tooltip"

const geist = localFont({
  src: "./fonts/GeistVF.woff",
  variable: "--font-sans",
  weight: "100 900",
})

export const metadata: Metadata = {
  title: "Dashboard de Gestión Estratégica | Ucompensar",
  description:
    "Plataforma SaaS para PYMES — análisis de datos con inteligencia artificial",
}

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  maximumScale: 5,
}

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode
}>) {
  return (
    <html lang="es" className={geist.variable}>
      <body className="antialiased">
        <QueryProvider>
          <AuthProvider>
            <TooltipProvider>
              {children}
              <Toaster richColors closeButton />
            </TooltipProvider>
          </AuthProvider>
        </QueryProvider>
      </body>
    </html>
  )
}
