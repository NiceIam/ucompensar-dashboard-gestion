"use client"

import { useEffect, useState, type ReactNode } from "react"
import { toast } from "sonner"
import { Building2, Info, LogOut, Palette, UserRound, type LucideIcon } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Skeleton } from "@/components/ui/skeleton"
import { Field } from "@/components/kit/field"
import { UniversityLogo } from "@/components/kit/logo"
import { PageHeader } from "@/components/kit/page-header"
import { StatusBadge } from "@/components/kit/status-badge"
import { ThemeSwitcher } from "@/components/kit/theme-toggle"
import { useAuth } from "@/hooks/use-auth"
import { usePageTitle } from "@/hooks/use-page-title"
import { useProfile, useUpdateProfile } from "@/hooks/use-profile"
import { useAuthContext } from "@/providers/auth-provider"
import { humanizeError } from "@/lib/errors"
import { formatDate } from "@/lib/format"
import { BRAND } from "@/config/brand"

const SECTOR_LABELS: Record<string, string> = {
  comercio: "Comercio",
  terciario: "Servicios",
  salud: "Salud",
  educacion: "Educación",
  TIC: "Tecnología e informática",
  cuaternario: "Conocimiento (educación, salud o TIC)",
}

const PLAN_LABELS: Record<string, string> = {
  free: "Plan gratuito",
  pro: "Plan Pro",
}

function SettingsCard({
  icon: Icon,
  title,
  description,
  children,
  badge,
}: {
  icon: LucideIcon
  title: string
  description?: string
  children: ReactNode
  badge?: ReactNode
}) {
  return (
    <section className="surface p-5 sm:p-6">
      <div className="mb-5 flex flex-wrap items-start gap-3">
        <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-primary-soft text-primary-strong">
          <Icon className="h-5 w-5" aria-hidden="true" />
        </span>
        <div className="min-w-0 flex-1">
          <h2 className="font-display text-xl font-semibold leading-tight">{title}</h2>
          {description && <p className="mt-0.5 text-sm text-muted-foreground">{description}</p>}
        </div>
        {badge}
      </div>
      {children}
    </section>
  )
}

function ReadOnlyRow({ label, value, loading }: { label: string; value?: ReactNode; loading?: boolean }) {
  return (
    <div className="flex flex-col gap-1 py-3 sm:flex-row sm:items-center sm:justify-between">
      <dt className="text-sm text-muted-foreground">{label}</dt>
      <dd className="text-[15px] font-medium sm:text-right">{loading ? <Skeleton className="h-5 w-40" /> : value || "—"}</dd>
    </div>
  )
}

export default function SettingsPage() {
  usePageTitle("Configuración")
  const { user } = useAuthContext()
  const { signOut, loading: signingOut } = useAuth()
  const profile = useProfile()
  const update = useUpdateProfile()
  const [name, setName] = useState("")
  const [nameError, setNameError] = useState<string | null>(null)

  useEffect(() => {
    if (user?.full_name) setName(user.full_name)
  }, [user?.full_name])

  async function saveName(e: React.FormEvent) {
    e.preventDefault()
    const trimmed = name.trim()
    if (trimmed.length < 2) {
      setNameError("Escribe tu nombre (al menos 2 letras).")
      return
    }
    setNameError(null)
    try {
      await update.mutateAsync({ full_name: trimmed })
      toast.success("Listo, guardamos tu nombre")
    } catch (err) {
      const h = humanizeError(err, "save")
      setNameError(`${h.title}. ${h.description}`)
    }
  }

  const p = profile.data
  const plan = p?.org_plan ? PLAN_LABELS[p.org_plan] ?? p.org_plan : undefined

  return (
    <div className="max-w-3xl space-y-8">
      <PageHeader eyebrow="Configuración" title="Tu cuenta" description="Tus datos personales, los de tu empresa y cómo quieres ver la aplicación." />

      <SettingsCard icon={UserRound} title="Tu perfil" description="Así te saludamos y te identificamos.">
        <form onSubmit={saveName} className="space-y-5">
          <Field label="Tu nombre" error={nameError ?? undefined}>
            {({ id, describedBy, invalid }) => (
              <Input id={id} value={name} onChange={(e) => setName(e.target.value)} aria-describedby={describedBy} aria-invalid={invalid} maxLength={120} autoComplete="name" />
            )}
          </Field>
          <Field label="Correo electrónico" hint="Con este correo entras a tu cuenta. Por ahora no se puede cambiar desde aquí.">
            {({ id, describedBy }) => <Input id={id} value={user?.email ?? ""} readOnly aria-describedby={describedBy} className="bg-muted/60 text-muted-foreground" />}
          </Field>
          <Button type="submit" loading={update.isPending} loadingText="Guardando…" disabled={name.trim() === (user?.full_name ?? "").trim()}>
            Guardar cambios
          </Button>
        </form>
      </SettingsCard>

      <SettingsCard
        icon={Building2}
        title="Tu empresa"
        description="Los datos con los que creaste tu cuenta."
        badge={<StatusBadge tone="neutral">Edición próximamente</StatusBadge>}
      >
        {profile.isError ? (
          <p className="text-sm text-muted-foreground">No pudimos cargar los datos de tu empresa ahora mismo. Intenta más tarde.</p>
        ) : (
          <dl className="divide-y">
            <ReadOnlyRow label="Nombre" value={p?.org_name} loading={profile.isLoading} />
            <ReadOnlyRow label="Sector" value={p?.org_sector ? SECTOR_LABELS[p.org_sector] ?? p.org_sector : undefined} loading={profile.isLoading} />
            <ReadOnlyRow label="Plan" value={plan} loading={profile.isLoading} />
            <ReadOnlyRow label="Cuenta creada" value={p?.created_at ? formatDate(p.created_at, "long") : undefined} loading={profile.isLoading} />
          </dl>
        )}
        <p className="mt-4 text-[13px] text-muted-foreground">
          Pronto podrás cambiar estos datos aquí. Si necesitas hacerlo antes, pídeselo a quien administra la plataforma.
        </p>
      </SettingsCard>

      <SettingsCard icon={Palette} title="Apariencia" description="Elige claro, oscuro o lo que use tu dispositivo.">
        <ThemeSwitcher showLabels className="flex-wrap" />
      </SettingsCard>

      <SettingsCard icon={Info} title={`Acerca de ${BRAND.name}`} description={BRAND.description}>
        <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
          <div className="space-y-1">
            <p className="text-[15px]">
              {BRAND.name} es un proyecto de la {BRAND.institution}.
            </p>
            {BRAND.projectCode && <p className="text-xs text-muted-foreground">Proyecto de investigación {BRAND.projectCode}</p>}
          </div>
          <UniversityLogo height={30} />
        </div>
      </SettingsCard>

      <SettingsCard icon={LogOut} title="Sesión" description="Cierra tu sesión en este dispositivo.">
        <Button variant="outline" onClick={() => void signOut()} loading={signingOut} className="text-danger-strong hover:text-danger-strong">
          <LogOut aria-hidden="true" />
          Cerrar sesión
        </Button>
      </SettingsCard>
    </div>
  )
}
