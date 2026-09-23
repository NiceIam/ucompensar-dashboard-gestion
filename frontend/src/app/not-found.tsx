import Link from "next/link"
import { Button } from "@/components/ui/button"

export default function NotFound() {
  return (
    <div className="flex flex-col items-center justify-center min-h-screen gap-6 text-center px-4">
      <h1 className="text-6xl font-bold text-muted-foreground">404</h1>
      <p className="text-xl font-semibold">Página no encontrada</p>
      <p className="text-muted-foreground max-w-sm">
        La página que buscas no existe o fue movida.
      </p>
      <Button asChild>
        <Link href="/">Volver al inicio</Link>
      </Button>
    </div>
  )
}
