import type { ReactNode } from "react"
import { MessageCircleQuestion, Sparkles, Upload } from "lucide-react"
import { BrandMark } from "@/components/kit/logo"
import { BRAND } from "@/config/brand"

const BENEFITS = [
  { icon: Upload, title: "Sube tu Excel tal como lo tienes", text: "Sin plantillas ni pasos técnicos." },
  { icon: Sparkles, title: "Entiende tus números de un vistazo", text: "Te contamos lo importante en frases claras." },
  { icon: MessageCircleQuestion, title: "Pregúntale en tus palabras", text: "Y te responde con tus cifras y gráficos." },
]

/** Portada de acceso: panel de marca a la izquierda (escritorio) y formulario a la derecha. */
export default function AuthLayout({ children }: { children: ReactNode }) {
  return (
    <div className="flex min-h-dvh bg-background">
      <aside className="relative hidden w-[46%] max-w-[640px] flex-col justify-between overflow-hidden bg-primary p-10 text-primary-foreground lg:flex xl:p-14">
        {/* Rosa de los vientos decorativa */}
        <svg viewBox="0 0 400 400" aria-hidden="true" className="pointer-events-none absolute -bottom-32 -right-40 h-[560px] w-[560px] text-primary-foreground/[0.07]">
          <circle cx="200" cy="200" r="190" fill="none" stroke="currentColor" strokeWidth="2" />
          <circle cx="200" cy="200" r="140" fill="none" stroke="currentColor" strokeWidth="1.5" strokeDasharray="4 10" />
          <circle cx="200" cy="200" r="90" fill="none" stroke="currentColor" strokeWidth="1.5" />
          <path d="M200 0 L224 200 L200 400 L176 200 Z" fill="currentColor" />
          <path d="M0 200 L200 176 L400 200 L200 224 Z" fill="currentColor" />
          <path d="M60 60 L214 186 L340 340 L186 214 Z" fill="currentColor" opacity="0.6" />
        </svg>
        <div className="pointer-events-none absolute -left-24 -top-24 h-72 w-72 rounded-full bg-highlight/20 blur-3xl" aria-hidden="true" />

        <div className="relative flex items-center gap-3">
          <BrandMark className="h-11 w-11 [&_rect]:fill-primary-foreground/10" />
          <span className="font-display text-2xl font-semibold">{BRAND.name}</span>
        </div>

        <div className="relative space-y-8">
          <h1 className="font-display text-5xl font-semibold leading-[1.05] text-balance xl:text-6xl">{BRAND.tagline}</h1>
          <ul className="space-y-5">
            {BENEFITS.map((b) => (
              <li key={b.title} className="flex items-start gap-4">
                <span className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-primary-foreground/10 text-highlight">
                  <b.icon className="h-5 w-5" aria-hidden="true" />
                </span>
                <div>
                  <p className="font-semibold">{b.title}</p>
                  <p className="text-sm text-primary-foreground/75">{b.text}</p>
                </div>
              </li>
            ))}
          </ul>
        </div>

        <p className="relative min-h-4 text-xs text-primary-foreground/60">{BRAND.credit}</p>
      </aside>

      <main className="paper-glow flex flex-1 flex-col items-center justify-center px-4 py-10 sm:px-8">
        <div className="mb-8 flex items-center gap-2.5 lg:hidden">
          <BrandMark className="h-10 w-10" />
          <span className="font-display text-2xl font-semibold">{BRAND.name}</span>
        </div>
        <div className="w-full max-w-[26rem] animate-rise-in">{children}</div>
        {BRAND.credit && <p className="mt-10 text-xs text-muted-foreground lg:hidden">{BRAND.credit}</p>}
      </main>
    </div>
  )
}
