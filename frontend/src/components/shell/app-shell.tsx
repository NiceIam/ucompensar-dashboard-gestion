"use client"

import Link from "next/link"
import { usePathname } from "next/navigation"
import { useEffect, useState, type ReactNode } from "react"
import { ChevronRight, MessageCircle, Moon, Sparkles, Sun } from "lucide-react"
import { useTheme } from "next-themes"
import { BrandMark, Wordmark } from "@/components/kit/logo"
import { UserMenu } from "@/components/shell/user-menu"
import { NAV_ITEMS, breadcrumbsFor, isActive } from "@/components/shell/nav"
import { useChat } from "@/providers/chat-provider"
import { useDashboardMeta } from "@/hooks/use-dashboards"
import { BRAND } from "@/config/brand"
import { cn } from "@/lib/utils"

function ShortcutHint({ className }: { className?: string }) {
  const [mac, setMac] = useState(false)
  useEffect(() => setMac(/Mac|iPhone|iPad/.test(navigator.platform)), [])
  return (
    <kbd
      className={cn(
        "hidden rounded-md border bg-card px-1.5 py-0.5 font-sans text-[11px] font-semibold text-muted-foreground lg:inline",
        className
      )}
    >
      {mac ? "⌘" : "Ctrl"} K
    </kbd>
  )
}

/** Barra lateral de escritorio. */
function Sidebar() {
  const pathname = usePathname()
  const { open, isOpen } = useChat()
  return (
    <aside className="hidden w-[264px] shrink-0 flex-col border-r bg-sidebar lg:flex">
      <div className="flex h-[72px] items-center px-5">
        <Link href="/" className="rounded-xl focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring" aria-label={`${BRAND.name}: ir al inicio`}>
          <Wordmark showTagline />
        </Link>
      </div>

      <div className="px-3 pb-3">
        <button
          type="button"
          onClick={open}
          aria-pressed={isOpen}
          className="group flex h-12 w-full items-center gap-3 rounded-xl bg-primary px-3.5 text-left text-sm font-semibold text-primary-foreground shadow-raised transition hover:bg-primary/90 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
        >
          <Sparkles className="h-[18px] w-[18px] text-highlight" aria-hidden="true" />
          <span className="flex-1">Pregúntale a tus datos</span>
        </button>
      </div>

      <nav aria-label="Principal" className="flex-1 space-y-1 px-3 py-2">
        {NAV_ITEMS.map((item) => {
          const active = isActive(pathname, item.href)
          return (
            <Link
              key={item.href}
              href={item.href}
              aria-current={active ? "page" : undefined}
              className={cn(
                "relative flex h-11 items-center gap-3 rounded-xl px-3.5 text-[15px] font-medium transition-colors",
                active
                  ? "bg-card text-foreground shadow-card"
                  : "text-sidebar-foreground/75 hover:bg-sidebar-accent hover:text-sidebar-foreground"
              )}
            >
              {active && <span className="absolute left-0 top-2.5 h-6 w-1 rounded-r-full bg-highlight" aria-hidden="true" />}
              <item.icon className={cn("h-[18px] w-[18px]", active ? "text-primary" : "")} aria-hidden="true" />
              {item.label}
            </Link>
          )
        })}
      </nav>

      {BRAND.credit && (
        <p className="px-6 pb-5 pt-3 text-[11px] leading-snug text-muted-foreground">{BRAND.credit}</p>
      )}
    </aside>
  )
}

function ThemeQuickToggle() {
  const { resolvedTheme, setTheme } = useTheme()
  const [mounted, setMounted] = useState(false)
  useEffect(() => setMounted(true), [])
  const dark = mounted && resolvedTheme === "dark"
  return (
    <button
      type="button"
      onClick={() => setTheme(dark ? "light" : "dark")}
      className="hidden h-10 w-10 items-center justify-center rounded-xl text-muted-foreground transition hover:bg-accent hover:text-foreground sm:flex"
      aria-label={dark ? "Cambiar a modo claro" : "Cambiar a modo oscuro"}
      title={dark ? "Modo claro" : "Modo oscuro"}
    >
      {dark ? <Sun className="h-[18px] w-[18px]" aria-hidden="true" /> : <Moon className="h-[18px] w-[18px]" aria-hidden="true" />}
    </button>
  )
}

/** Barra superior: migas en escritorio, marca en el celular, acceso al chat y menú de cuenta. */
function TopBar() {
  const pathname = usePathname()
  const dashboardId = pathname.match(/^\/dashboards\/([^/]+)/)?.[1] ?? ""
  const { data: dashboardMeta } = useDashboardMeta(dashboardId)
  const crumbs = breadcrumbsFor(pathname).map((c, i, all) =>
    i === all.length - 1 && dashboardId && dashboardMeta?.name ? { ...c, label: dashboardMeta.name } : c
  )
  const { open, isOpen } = useChat()
  return (
    <header className="sticky top-0 z-30 flex h-16 shrink-0 items-center gap-3 border-b bg-background/85 px-4 backdrop-blur-md supports-[backdrop-filter]:bg-background/70 sm:px-6 lg:h-[72px] lg:px-8">
      <Link href="/" className="flex items-center gap-2 rounded-xl lg:hidden" aria-label={`${BRAND.name}: ir al inicio`}>
        <BrandMark className="h-8 w-8" />
        <span className="font-display text-xl font-semibold">{BRAND.name}</span>
      </Link>

      <nav aria-label="Ruta" className="hidden min-w-0 lg:block">
        <ol className="flex items-center gap-1.5 text-sm">
          {crumbs.map((c, i) => (
            <li key={`${c.label}-${i}`} className="flex min-w-0 items-center gap-1.5">
              {i > 0 && <ChevronRight className="h-3.5 w-3.5 text-muted-foreground/60" aria-hidden="true" />}
              {c.href ? (
                <Link href={c.href} className="truncate text-muted-foreground transition hover:text-foreground">
                  {c.label}
                </Link>
              ) : (
                <span className="truncate font-semibold" aria-current="page">
                  {c.label}
                </span>
              )}
            </li>
          ))}
        </ol>
      </nav>

      <div className="flex-1" />

      {!isOpen && (
        <button
          type="button"
          onClick={open}
          className="hidden h-10 items-center gap-2 rounded-xl border bg-card px-3.5 text-sm font-semibold shadow-card transition hover:border-primary/40 hover:bg-primary-soft/40 md:flex lg:hidden"
        >
          <Sparkles className="h-4 w-4 text-primary" aria-hidden="true" />
          Pregúntale
          <ShortcutHint />
        </button>
      )}
      <ThemeQuickToggle />
      <UserMenu />
    </header>
  )
}

/** Barra inferior para celular y tableta, con el chat en el centro. */
function BottomNav() {
  const pathname = usePathname()
  const { toggle, isOpen } = useChat()
  const [first, second, third, fourth] = NAV_ITEMS
  const item = (it: (typeof NAV_ITEMS)[number]) => {
    const active = isActive(pathname, it.href)
    return (
      <Link
        key={it.href}
        href={it.href}
        aria-current={active ? "page" : undefined}
        className={cn(
          "flex min-h-[56px] flex-1 flex-col items-center justify-center gap-1 rounded-xl text-[11px] font-semibold transition-colors",
          active ? "text-primary" : "text-muted-foreground hover:text-foreground"
        )}
      >
        <span className={cn("flex h-7 w-12 items-center justify-center rounded-full transition-colors", active && "bg-primary-soft")}>
          <it.icon className="h-5 w-5" aria-hidden="true" />
        </span>
        {it.short}
      </Link>
    )
  }
  return (
    <nav
      aria-label="Principal"
      data-shell="bottom-nav"
      className="fixed inset-x-0 bottom-0 z-40 border-t bg-card/95 px-2 pb-safe backdrop-blur-md lg:hidden"
    >
      <div className="mx-auto flex max-w-xl items-center gap-1 pt-1">
        {item(first)}
        {item(second)}
        <div className="flex flex-1 justify-center">
          <button
            type="button"
            onClick={toggle}
            aria-expanded={isOpen}
            aria-label="Abrir asistente IA"
            className="-mt-6 flex h-14 w-14 items-center justify-center rounded-2xl bg-primary text-primary-foreground shadow-float ring-4 ring-background transition active:scale-95"
          >
            <MessageCircle className="h-6 w-6" aria-hidden="true" />
          </button>
        </div>
        {item(third)}
        {item(fourth)}
      </div>
    </nav>
  )
}

/** Esqueleto de la aplicación: barra lateral, barra superior, contenido y chat acoplado. */
export function AppShell({ children, chat }: { children: ReactNode; chat: ReactNode }) {
  const pathname = usePathname()
  return (
    <div data-shell="root" className="flex h-dvh overflow-hidden bg-background">
      <a
        href="#contenido"
        className="sr-only z-50 rounded-xl bg-primary px-4 py-2 font-semibold text-primary-foreground focus:not-sr-only focus:absolute focus:left-4 focus:top-4"
      >
        Saltar al contenido
      </a>
      <Sidebar />
      <div data-shell="body" className="flex min-w-0 flex-1 overflow-hidden">
        <div data-shell="column" className="flex min-w-0 flex-1 flex-col overflow-hidden">
          <main id="contenido" data-shell="main" tabIndex={-1} className="paper-glow relative flex-1 overflow-y-auto outline-none">
            <TopBar />
            <div
              key={pathname}
              className="mx-auto w-full max-w-6xl animate-rise-in px-4 pb-28 pt-6 sm:px-6 sm:pt-8 lg:px-10 lg:pb-16 lg:pt-10"
            >
              {children}
            </div>
          </main>
        </div>
        {chat}
      </div>
      <BottomNav />
    </div>
  )
}
