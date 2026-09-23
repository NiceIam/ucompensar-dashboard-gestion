"use client"

import { useState } from "react"
import { useRouter } from "next/navigation"
import { useQueryClient } from "@tanstack/react-query"

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

export function useAuth() {
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const router = useRouter()
  const queryClient = useQueryClient()

  async function signIn(email: string, password: string): Promise<void> {
    setLoading(true)
    setError(null)
    try {
      // credentials:"include" makes the browser store the HttpOnly cookies set by the backend.
      const res = await fetch(`${API_URL}/api/v1/auth/login`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({ email, password }),
      })

      if (!res.ok) {
        if (res.status >= 500) {
          throw new Error("Servidor no disponible. Intenta más tarde.")
        }
        throw new Error("Email o contraseña incorrectos")
      }

      // Tokens now live in HttpOnly cookies — nothing to store client-side.
      // Invalidate /me so AuthProvider refetches with the new session cookie.
      await queryClient.invalidateQueries({ queryKey: ["auth", "me"] })

      router.push("/")
      router.refresh()
    } catch (err) {
      const message =
        err instanceof Error ? err.message : "Email o contraseña incorrectos"
      setError(message)
    } finally {
      setLoading(false)
    }
  }

  async function signUp(data: SignUpData): Promise<void> {
    setLoading(true)
    setError(null)
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

      if (!res.ok) {
        const errorBody = await res.text().catch(() => "Error desconocido")
        throw new Error(errorBody || `HTTP ${res.status}`)
      }

      // Initialize org schema — cookie is already set, no manual token needed.
      const initRes = await fetch(`${API_URL}/api/v1/templates/initialize`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({ business_type_id: data.business_type_id }),
      })
      if (!initRes.ok) {
        const initError = await initRes.text().catch(() => "Error al inicializar")
        throw new Error(initError || `HTTP ${initRes.status}`)
      }

      // Invalidate /me so AuthProvider refetches with the new session cookie.
      await queryClient.invalidateQueries({ queryKey: ["auth", "me"] })

      router.push("/")
      router.refresh()
    } catch (err) {
      const message =
        err instanceof Error ? err.message : "Error al registrarse"
      setError(message)
    } finally {
      setLoading(false)
    }
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

  return { signIn, signUp, signOut, loading, error }
}
