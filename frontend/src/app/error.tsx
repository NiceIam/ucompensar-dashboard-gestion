"use client"

import Link from "next/link"
import { useEffect } from "react"
import { Home, RotateCcw } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Illustration } from "@/components/kit/illustrations"

/** Pantalla amable cuando algo falla al dibujar una página (en vez de la pantalla técnica). */
export default function ErrorPage({ error, reset }: { error: Error & { digest?: string }; reset: () => void }) {
  useEffect(() => {
    console.error(error)
  }, [error])

  return (
    <main className="paper-glow flex min-h-dvh flex-col items-center justify-center px-4 py-12 text-center">
      <Illustration name="error" className="h-36 sm:h-44" />
      <h1 className="mt-6 max-w-xl font-display text-[32px] font-semibold leading-tight text-balance sm:text-[40px]">
        Algo se descuadró por aquí
      </h1>
      <p className="mt-3 max-w-md text-[15px] text-muted-foreground">
        No es tu culpa: algo falló al mostrar esta página. Lo que ya habías guardado sigue intacto. Intenta de nuevo o vuelve al inicio.
      </p>
      <div className="mt-8 flex flex-col gap-2 sm:flex-row">
        <Button size="lg" onClick={reset}>
          <RotateCcw aria-hidden="true" />
          Intentar de nuevo
        </Button>
        <Button asChild size="lg" variant="outline">
          <Link href="/">
            <Home aria-hidden="true" />
            Ir al inicio
          </Link>
        </Button>
      </div>
      {error.digest && <p className="mt-8 font-mono text-xs text-muted-foreground">Código para soporte: {error.digest}</p>}
    </main>
  )
}
