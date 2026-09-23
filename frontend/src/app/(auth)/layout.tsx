import type { ReactNode } from "react"
import Image from "next/image"

export default function AuthLayout({ children }: { children: ReactNode }) {
  return (
    <div className="relative min-h-screen flex items-center justify-center px-4 overflow-hidden bg-gradient-to-br from-orange-50 via-white to-orange-50/40">
      {/* Background logo watermark */}
      <div className="pointer-events-none absolute inset-0 flex items-center justify-center">
        <Image
          src="/logo-ucompensar-small.png"
          alt=""
          width={480}
          height={480}
          className="opacity-[0.04] select-none"
          priority
        />
      </div>

      {/* Subtle geometric accents */}
      <div className="pointer-events-none absolute -top-32 -right-32 h-96 w-96 rounded-full bg-primary/5 blur-3xl" />
      <div className="pointer-events-none absolute -bottom-24 -left-24 h-72 w-72 rounded-full bg-primary/4 blur-3xl" />

      <div className="relative z-10 w-full max-w-md">{children}</div>
    </div>
  )
}
