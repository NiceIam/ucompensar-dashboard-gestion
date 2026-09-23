"use client"

import { createContext, useContext, type ReactNode } from "react"
import { useQuery } from "@tanstack/react-query"

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000"

export interface User {
  user_id: string
  org_id: string
  email: string
  role: string
  full_name: string
  avatar_url?: string | null
}

interface AuthContextValue {
  user: User | null
  loading: boolean
  /** Always null — tokens live in HttpOnly cookies, not accessible client-side. */
  token: null
}

const AuthContext = createContext<AuthContextValue>({
  user: null,
  loading: true,
  token: null,
})

export function useAuthContext() {
  return useContext(AuthContext)
}

interface AuthProviderProps {
  children: ReactNode
}

async function fetchMe(): Promise<User | null> {
  const res = await fetch(`${API_URL}/api/v1/auth/me`, {
    method: "GET",
    credentials: "include",
  })
  if (res.status === 401 || res.status === 403) return null
  if (!res.ok) throw new Error(`Error al obtener perfil: HTTP ${res.status}`)
  return res.json() as Promise<User>
}

export function AuthProvider({ children }: AuthProviderProps) {
  const { data: user = null, isLoading } = useQuery<User | null>({
    queryKey: ["auth", "me"],
    queryFn: fetchMe,
    // Never treat a null (unauthenticated) response as a stale refetch target
    // — only refetch when the window regains focus after a background silence.
    staleTime: 1000 * 60 * 5,
    retry: false,
  })

  return (
    <AuthContext.Provider value={{ user, loading: isLoading, token: null }}>
      {children}
    </AuthContext.Provider>
  )
}
