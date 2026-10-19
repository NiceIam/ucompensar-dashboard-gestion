"use client"

import Link from "next/link"
import { ChevronDown, LogOut, Settings } from "lucide-react"
import { Avatar, AvatarFallback } from "@/components/ui/avatar"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import { ThemeSwitcher } from "@/components/kit/theme-toggle"
import { useAuth } from "@/hooks/use-auth"
import { useAuthContext } from "@/providers/auth-provider"
import { cn } from "@/lib/utils"

export function initialsOf(name?: string | null, email?: string | null): string {
  const source = name?.trim()
  if (source) {
    return source
      .split(/\s+/)
      .map((n) => n[0])
      .slice(0, 2)
      .join("")
      .toUpperCase()
  }
  return email?.slice(0, 2).toUpperCase() ?? "TÚ"
}

export function firstName(name?: string | null): string | null {
  const first = name?.trim().split(/\s+/)[0]
  return first ? first.charAt(0).toUpperCase() + first.slice(1) : null
}

/** Menú de la persona: quién es, apariencia, configuración y cerrar sesión. */
export function UserMenu({ compact = false }: { compact?: boolean }) {
  const { user } = useAuthContext()
  const { signOut, loading } = useAuth()
  const initials = initialsOf(user?.full_name, user?.email)

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <button
          type="button"
          data-testid="user-menu"
          className={cn(
            "flex h-11 items-center gap-2 rounded-xl px-1.5 text-left transition-colors hover:bg-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
            !compact && "pr-2.5"
          )}
          aria-label="Menú de tu cuenta"
        >
          <Avatar className="h-8 w-8">
            <AvatarFallback className="bg-highlight-soft text-[13px] font-bold text-highlight-strong">
              {initials}
            </AvatarFallback>
          </Avatar>
          {!compact && (
            <>
              <span className="hidden max-w-[10rem] truncate text-sm font-semibold sm:block">
                {user?.full_name || user?.email || "Tu cuenta"}
              </span>
              <ChevronDown className="hidden h-4 w-4 text-muted-foreground sm:block" aria-hidden="true" />
            </>
          )}
        </button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-72">
        <DropdownMenuLabel className="px-2.5 py-2">
          <p className="truncate text-sm font-semibold">{user?.full_name || "Tu cuenta"}</p>
          <p className="truncate text-xs font-normal text-muted-foreground">{user?.email}</p>
        </DropdownMenuLabel>
        <DropdownMenuSeparator />
        <div className="px-2.5 py-2">
          <p className="mb-2 text-xs font-medium text-muted-foreground">Apariencia</p>
          <ThemeSwitcher className="w-full justify-between [&>button]:flex-1" />
        </div>
        <DropdownMenuSeparator />
        <DropdownMenuItem asChild>
          <Link href="/settings" className="cursor-pointer">
            <Settings className="h-4 w-4" aria-hidden="true" />
            Configuración
          </Link>
        </DropdownMenuItem>
        <DropdownMenuItem
          onClick={() => void signOut()}
          disabled={loading}
          className="cursor-pointer text-danger-strong focus:bg-danger-soft focus:text-danger-strong"
        >
          <LogOut className="h-4 w-4" aria-hidden="true" />
          Cerrar sesión
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  )
}
