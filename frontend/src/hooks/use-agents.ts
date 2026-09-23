"use client"

import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import { api } from "@/lib/api"
import type { AgentSession, AgentResult } from "@/types/api"

export function useAgentSessions() {
  return useQuery<AgentSession[]>({
    queryKey: ["agent-sessions"],
    queryFn: (): Promise<AgentSession[]> => api.get("/api/v1/agents/sessions"),
  })
}

export function useAgentSession(id: string) {
  return useQuery<AgentResult>({
    queryKey: ["agent-sessions", id],
    queryFn: (): Promise<AgentResult> =>
      api.get(`/api/v1/agents/sessions/${id}`),
    enabled: Boolean(id),
    refetchInterval: (query) => {
      const status = query.state.data?.session?.status
      if (status === "running" || status === "pending") return 3000
      return false
    },
  })
}

export function useRunAnalysis() {
  const queryClient = useQueryClient()

  return useMutation<AgentSession, Error, string>({
    mutationFn: (fileId: string): Promise<AgentSession> =>
      api.post(`/api/v1/agents/analyze`, { file_id: fileId }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["agent-sessions"] })
    },
  })
}
