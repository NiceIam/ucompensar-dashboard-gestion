"use client"

import Link from "next/link"
import Image from "next/image"
import { usePathname } from "next/navigation"
import { useEffect, useState } from "react"
import {
  LayoutDashboard,
  Database,
  BarChart3,
  Settings,
  LogOut,
  Menu,
  X,
  ChevronDown,
} from "lucide-react"
import { Button } from "@/components/ui/button"
import { Avatar, AvatarFallback } from "@/components/ui/avatar"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import { cn } from "@/lib/utils"
import { useAuth } from "@/hooks/use-auth"
import { useAuthContext } from "@/providers/auth-provider"
import { FloatingChat } from "@/components/chat/floating-chat"

const navItems = [
  { href: "/", label: "Resumen", icon: LayoutDashboard },
  { href: "/data", label: "Mis Datos", icon: Database },
  { href: "/dashboards", label: "Tableros", icon: BarChart3 },
  { href: "/settings", label: "Configuración", icon: Settings },
]

function Sidebar({
  open,
  onClose,
}: {
  open: boolean
  onClose: () => void
}) {
  const pathname = usePathname()

  return (
    <>
      {open && (
        <div
          className="fixed inset-0 z-20 bg-black/40 lg:hidden"
          onClick={onClose}
        />
      )}

      <aside
        className={cn(
          "fixed inset-y-0 left-0 z-30 flex w-64 flex-col bg-card border-r transition-transform duration-300 shrink-0 overflow-hidden",
          open ? "translate-x-0" : "-translate-x-full",
          "lg:static lg:translate-x-0"
        )}
      >
        {/* Background watermark */}
        <div className="pointer-events-none absolute bottom-4 left-1/2 -translate-x-1/2 opacity-[0.03]">
          <Image
            src="/logo-ucompensar-small.png"
            alt=""
            width={180}
            height={180}
            className="select-none"
          />
        </div>

        <div className="relative flex h-16 items-center gap-3 border-b px-5">
          <Image
            src="/logo-ucompensar.png"
            alt="Compensar"
            width={130}
            height={32}
            className="h-7 w-auto"
          />
          <Button
            variant="ghost"
            size="icon"
            className="ml-auto lg:hidden"
            onClick={onClose}
          >
            <X className="h-4 w-4" />
          </Button>
        </div>

        <nav className="relative flex-1 space-y-1 p-3 overflow-y-auto">
          {navItems.map((item) => {
            const isActive =
              item.href === "/"
                ? pathname === "/"
                : pathname.startsWith(item.href)

            return (
              <Link
                key={item.href}
                href={item.href}
                onClick={onClose}
                className={cn(
                  "flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition-colors",
                  isActive
                    ? "bg-primary text-primary-foreground"
                    : "text-muted-foreground hover:bg-accent hover:text-accent-foreground"
                )}
              >
                <item.icon className="h-4 w-4 shrink-0" />
                {item.label}
              </Link>
            )
          })}
        </nav>

        <div className="relative border-t p-3">
          <p className="px-3 py-1 text-[10px] text-muted-foreground/70 tracking-wide uppercase">
            PI0320251 — Ucompensar
          </p>
        </div>
      </aside>
    </>
  )
}

export default function DashboardLayout({
  children,
}: {
  children: React.ReactNode
}) {
  const [sidebarOpen, setSidebarOpen] = useState(false)
  const [chatOpen, setChatOpen] = useState(true)
  const { signOut, loading } = useAuth()
  const { user } = useAuthContext()

  useEffect(() => {
    if (typeof window === "undefined") return
    const mq = window.matchMedia("(min-width: 1024px)")
    if (!mq.matches) setChatOpen(false)
    const handleChange = (e: MediaQueryListEvent) => {
      if (!e.matches) setChatOpen(false)
    }
    mq.addEventListener("change", handleChange)
    return () => mq.removeEventListener("change", handleChange)
  }, [])

  const initials = user?.full_name
    ? user.full_name
        .split(" ")
        .map((n: string) => n[0])
        .slice(0, 2)
        .join("")
        .toUpperCase()
    : user?.email?.slice(0, 2).toUpperCase() ?? "US"

  return (
    <div className="flex h-dvh overflow-hidden bg-muted/20">
      <Sidebar open={sidebarOpen} onClose={() => setSidebarOpen(false)} />

      {/* Main content — se ajusta cuando el chat esta abierto */}
      <div className="flex flex-1 flex-col min-w-0 overflow-hidden">
        {/* Top navbar */}
        <header className="flex h-16 shrink-0 items-center gap-4 border-b bg-card px-4 lg:px-6">
          <Button
            variant="ghost"
            size="icon"
            className="lg:hidden"
            onClick={() => setSidebarOpen(true)}
          >
            <Menu className="h-5 w-5" />
            <span className="sr-only">Abrir menú</span>
          </Button>

          {/* Mobile logo — visible only when sidebar is hidden */}
          <Image
            src="/logo-ucompensar.png"
            alt="Compensar"
            width={110}
            height={28}
            className="h-6 w-auto lg:hidden"
          />

          <div className="flex-1" />

          {/* User dropdown */}
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button variant="ghost" className="flex items-center gap-2 h-auto py-1.5">
                <Avatar className="h-8 w-8">
                  <AvatarFallback className="text-xs bg-primary text-primary-foreground">
                    {initials}
                  </AvatarFallback>
                </Avatar>
                <span className="hidden sm:block text-sm font-medium max-w-32 truncate">
                  {user?.full_name || user?.email || "Usuario"}
                </span>
                <ChevronDown className="h-3.5 w-3.5 text-muted-foreground" />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end" className="w-48">
              <DropdownMenuItem asChild>
                <Link href="/settings">
                  <Settings className="mr-2 h-4 w-4" />
                  Configuración
                </Link>
              </DropdownMenuItem>
              <DropdownMenuSeparator />
              <DropdownMenuItem
                onClick={() => signOut()}
                disabled={loading}
                className="text-destructive focus:text-destructive"
              >
                <LogOut className="mr-2 h-4 w-4" />
                Cerrar sesión
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        </header>

        {/* Content + Chat side-by-side */}
        <div className="flex flex-1 min-h-0 overflow-hidden">
          {/* Page content — se expande o contrae */}
          <main className="flex-1 min-w-0 overflow-y-auto p-4 lg:p-6 transition-all duration-300">
            {children}
          </main>

          {/* Chat panel — parte del flow, no fixed */}
          <FloatingChat isOpen={chatOpen} onToggle={() => setChatOpen(prev => !prev)} />
        </div>
      </div>
    </div>
  )
}
