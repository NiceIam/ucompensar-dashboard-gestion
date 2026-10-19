import type { ReactNode } from "react"
import { MessageCircleQuestion, Sparkles, Upload } from "lucide-react"
import { BrandMark, BrandName, UniversityLogo } from "@/components/kit/logo"
import { DotCluster, DotField } from "@/components/kit/dots"
import { BRAND } from "@/config/brand"

const BENEFITS = [
  { icon: Upload, title: "Sube tu Excel tal como lo tienes", text: "Sin plantillas ni pasos técnicos." },
  { icon: Sparkles, title: "Entiende tus números de un vistazo", text: "Te contamos lo importante en frases claras." },
  { icon: MessageCircleQuestion, title: "Pregúntale en tus palabras", text: "Y te responde con tus cifras y gráficos." },
]

/** La frase de marca con su punto final en el naranja de la universidad. */
function Tagline() {
  const text = BRAND.tagline
  const dotted = text.endsWith(".")
  return (
    <>
      {dotted ? text.slice(0, -1) : text}
      {dotted && <span className="text-primary">.</span>}
    </>
  )
}

/** Portada de acceso: panel de marca a la izquierda (escritorio) y formulario a la derecha. */
export default function AuthLayout({ children }: { children: ReactNode }) {
  return (
    <div className="flex min-h-dvh bg-background">
      <aside className="relative hidden w-[46%] max-w-[640px] flex-col overflow-hidden border-r bg-brand p-10 text-brand-foreground lg:flex xl:p-14">
        <DotField fade="top-right" className="[--dots-alpha:0.3] [--dots-gap:22px] [--dots-size:2px]" />
        <DotCluster className="absolute -bottom-14 -right-14 h-56 w-56 xl:h-64 xl:w-64" />

        {/* Producto e institución, lado a lado */}
        <div className="relative flex flex-wrap items-center gap-x-5 gap-y-3">
          <span className="flex items-center gap-3">
            <BrandMark className="h-11 w-11" />
            <BrandName size="lg" />
          </span>
          <span className="hidden h-9 w-px bg-brand-foreground/15 xl:block" aria-hidden="true" />
          <UniversityLogo height={30} />
        </div>

        <div className="relative flex flex-1 flex-col justify-center space-y-9 py-12">
          <h1 className="font-display text-5xl font-semibold leading-[1.05] text-balance xl:text-6xl">
            <Tagline />
          </h1>
          <ul className="space-y-5">
            {BENEFITS.map((b) => (
              <li key={b.title} className="flex items-start gap-4">
                <span className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-card text-primary shadow-card">
                  <b.icon className="h-5 w-5" aria-hidden="true" />
                </span>
                <div>
                  <p className="font-semibold">{b.title}</p>
                  <p className="text-sm text-brand-foreground/75">{b.text}</p>
                </div>
              </li>
            ))}
          </ul>
        </div>
      </aside>

      <main className="paper-glow flex flex-1 flex-col items-center justify-center px-4 py-10 sm:px-8">
        <div className="mb-8 flex items-center gap-3 lg:hidden" role="img" aria-label={BRAND.name}>
          <BrandMark className="h-11 w-11" />
          <BrandName size="lg" />
        </div>
        <div className="w-full max-w-[26rem] animate-rise-in">{children}</div>
        <div className="mt-12 flex flex-col items-center gap-2 lg:hidden">
          <p className="text-xs text-muted-foreground">Un proyecto de</p>
          <UniversityLogo height={26} />
        </div>
      </main>
    </div>
  )
}
