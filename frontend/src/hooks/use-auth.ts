"use client"

import { useState } from "react"
import { useRouter } from "next/navigation"
import { useQueryClient } from "@tanstack/react-query"
import { toast } from "sonner"
import { ApiError, humanizeError, type HumanError } from "@/lib/errors"

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000"

interface SignUpData {
  email: string
  password: string
  full_name: string
  org_name: string
  org_sector: string
  org_size: string
  business_type_id: string
}

async function failIfNotOk(res: Response): Promise<void> {
  if (res.ok) return
  const raw = await res.text().catch(() => "")
  throw new ApiError(res.status, raw)
}

export function useAuth() {
  const [loading, setLoading] = useState(false)
  const [errorInfo, setErrorInfo] = useState<HumanError | null>(null)
  const router = useRouter()
  const queryClient = useQueryClient()

  async function signIn(email: string, password: string): Promise<void> {
    setLoading(true)
    setErrorInfo(null)
    try {
      // credentials:"include" makes the browser store the HttpOnly cookies set by the backend.
      const res = await fetch(`${API_URL}/api/v1/auth/login`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({ email, password }),
      })
      await failIfNotOk(res)

      // Tokens now live in HttpOnly cookies — nothing to store client-side.
      // Invalidate /me so AuthProvider refetches with the new session cookie.
      await queryClient.invalidateQueries({ queryKey: ["auth", "me"] })

      router.push("/")
      router.refresh()
    } catch (err) {
      // 4xx en el login = credenciales; el resto (red, 5xx, 429) se explica tal cual.
      const human =
        err instanceof ApiError && err.status >= 400 && err.status < 500 && err.status !== 429
          ? humanizeError(new ApiError(401, ""), "login")
          : humanizeError(err, "login")
      setErrorInfo(human)
    } finally {
      setLoading(false)
    }
  }

  async function signUp(data: SignUpData): Promise<void> {
    setLoading(true)
    setErrorInfo(null)
    try {
      // credentials:"include" stores HttpOnly cookies returned by /register.
      const res = await fetch(`${API_URL}/api/v1/auth/register`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({
          email: data.email,
          password: data.password,
          full_name: data.full_name,
          org_name: data.org_name,
          sector: data.org_sector,
          size: data.org_size,
        }),
      })
      await failIfNotOk(res)
    } catch (err) {
      setErrorInfo(humanizeError(err, "register"))
      setLoading(false)
      return
    }

    // La cuenta ya existe. Preparar las hojas del tipo de negocio es un extra:
    // si falla, se avisa con calma y se entra igual (se pueden subir archivos sin plantillas).
    try {
      const initRes = await fetch(`${API_URL}/api/v1/templates/initialize`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({ business_type_id: data.business_type_id }),
      })
      await failIfNotOk(initRes)
    } catch {
      toast.warning("Tu cuenta quedó creada", {
        description: "No pudimos preparar las hojas de tu tipo de negocio, pero puedes subir tus archivos igual.",
      })
    }

    // Invalidate /me so AuthProvider refetches with the new session cookie.
    await queryClient.invalidateQueries({ queryKey: ["auth", "me"] })
    router.push("/")
    router.refresh()
    setLoading(false)
  }

  async function signOut(): Promise<void> {
    setLoading(true)
    // Crítico: limpiar la caché de TanStack Query para evitar que un
    // usuario B vea datos residuales de un usuario A en el mismo navegador.
    queryClient.clear()

    // POST /logout tells the backend to delete the HttpOnly cookies server-side.
    try {
      await fetch(`${API_URL}/api/v1/auth/logout`, {
        method: "POST",
        credentials: "include",
      })
    } catch {
      // Best-effort — navigate to login regardless.
    }

    router.push("/login")
    router.refresh()
    setLoading(false)
  }

  return {
    signIn,
    signUp,
    signOut,
    loading,
    /** Error traducido (título + qué hacer). */
    errorInfo,
    /** Compatibilidad: el mismo error en una línea. */
    error: errorInfo ? `${errorInfo.title}. ${errorInfo.description}` : null,
    clearError: () => setErrorInfo(null),
  }
}
