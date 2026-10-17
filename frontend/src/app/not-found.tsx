import Link from "next/link"
import { FolderOpen, Home } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Illustration } from "@/components/kit/illustrations"
import { BrandMark } from "@/components/kit/logo"
import { BRAND } from "@/config/brand"

export const metadata = { title: "Página no encontrada" }

export default function NotFound() {
  return (
    <main className="paper-glow flex min-h-dvh flex-col items-center justify-center px-4 py-12 text-center">
      <Link href="/" className="mb-10 flex items-center gap-2.5" aria-label={`${BRAND.name}: ir al inicio`}>
        <BrandMark className="h-9 w-9" />
        <span className="font-display text-xl font-semibold">{BRAND.name}</span>
      </Link>
      <Illustration name="compass" className="h-40 sm:h-48" />
      <p className="mt-6 text-[13px] font-semibold uppercase tracking-[0.08em] text-highlight-strong">Error 404</p>
      <h1 className="mt-2 max-w-xl font-display text-[34px] font-semibold leading-tight text-balance sm:text-[42px]">
        Esta página se salió del mapa
      </h1>
      <p className="mt-3 max-w-md text-[15px] text-muted-foreground">
        Puede que el enlace esté mal escrito o que la página ya no exista. Te ayudamos a volver.
      </p>
      <div className="mt-8 flex flex-col gap-2 sm:flex-row">
        <Button asChild size="lg">
          <Link href="/">
            <Home aria-hidden="true" />
            Ir al inicio
          </Link>
        </Button>
        <Button asChild size="lg" variant="outline">
          <Link href="/data">
            <FolderOpen aria-hidden="true" />
            Ver mis datos
          </Link>
        </Button>
      </div>
    </main>
  )
}
