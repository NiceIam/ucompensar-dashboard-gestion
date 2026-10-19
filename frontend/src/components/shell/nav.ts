import { ClipboardList, FolderOpen, Home, LayoutDashboard, Settings, type LucideIcon } from "lucide-react"

export interface NavItem {
  href: string
  label: string
  /** Etiqueta corta para la barra inferior del celular. */
  short: string
  icon: LucideIcon
  /**
   * false = no va en la barra inferior del celular (que tiene 4 lugares + el botón del chat).
   * Configuración se alcanza desde el menú de la cuenta (avatar), que ya la trae.
   */
  mobile?: boolean
}

export const NAV_ITEMS: NavItem[] = [
  { href: "/", label: "Inicio", short: "Inicio", icon: Home },
  { href: "/resumen", label: "Resumen de la semana", short: "Resumen", icon: ClipboardList },
  { href: "/data", label: "Mis datos", short: "Datos", icon: FolderOpen },
  { href: "/dashboards", label: "Tableros", short: "Tableros", icon: LayoutDashboard },
  { href: "/settings", label: "Configuración", short: "Ajustes", icon: Settings, mobile: false },
]

export function isActive(pathname: string, href: string): boolean {
  return href === "/" ? pathname === "/" : pathname === href || pathname.startsWith(`${href}/`)
}

/** Migas de pan a partir de la ruta: [{label, href?}] */
export function breadcrumbsFor(pathname: string): { label: string; href?: string }[] {
  const crumbs: { label: string; href?: string }[] = []
  if (pathname === "/") return [{ label: "Inicio" }]
  const item = NAV_ITEMS.find((n) => n.href !== "/" && isActive(pathname, n.href))
  if (item) {
    const isRoot = pathname === item.href
    crumbs.push({ label: item.label, href: isRoot ? undefined : item.href })
    if (!isRoot && item.href === "/dashboards") crumbs.push({ label: "Tablero" })
  }
  return crumbs
}
