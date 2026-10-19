"use client"

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { api } from "@/lib/api"

/** GET /api/v1/auth/profile (contrato existente del backend). */
export interface Profile {
  user_id: string
  org_id: string
  email: string
  full_name: string
  role: string
  phone?: string | null
  avatar_url?: string | null
  preferences?: Record<string, unknown>
  org_name?: string | null
  org_sector?: string | null
  org_plan?: string
  created_at: string
  last_login_at?: string | null
}

export function useProfile() {
  return useQuery<Profile>({
    queryKey: ["auth", "profile"],
    queryFn: () => api.get<Profile>("/api/v1/auth/profile"),
    staleTime: 60_000,
  })
}

/** PUT /api/v1/auth/profile — hoy solo se usa para cambiar el nombre. */
export function useUpdateProfile() {
  const qc = useQueryClient()
  return useMutation<unknown, Error, { full_name: string }>({
    mutationFn: (body) => api.put("/api/v1/auth/profile", body),
    onSuccess: async () => {
      await qc.invalidateQueries({ queryKey: ["auth", "me"] })
      await qc.invalidateQueries({ queryKey: ["auth", "profile"] })
    },
  })
}
