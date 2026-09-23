"use client"

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { api } from "@/lib/api"

export type ETLStatus =
  | "pending"
  | "extracting"
  | "transforming"
  | "loading"
  | "completed"
  | "failed"

export interface ETLJob {
  job_id: string
  source_type: string
  filename: string
  status: ETLStatus
  rows_extracted: number
  rows_loaded: number
  error_message?: string
  started_at?: string
  completed_at?: string
}

interface ETLJobList {
  jobs: ETLJob[]
  total: number
}

export interface UploadResponse {
  job_id: string
  filename: string
  source_type: string
  status: string
  message: string
}

export function useUploadFile() {
  const queryClient = useQueryClient()

  return useMutation<UploadResponse, Error, { file: File; targetTable?: string }>({
    mutationFn: async ({ file, targetTable }) => {
      const formData = new FormData()
      formData.append("file", file)
      if (targetTable) formData.append("target_table", targetTable)
      return api.upload<UploadResponse>("/api/v1/etl/upload", formData)
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["etl", "jobs"] })
    },
  })
}

export function useETLJobs() {
  return useQuery<ETLJobList>({
    queryKey: ["etl", "jobs"],
    queryFn: () => api.get<ETLJobList>("/api/v1/etl/jobs"),
    refetchInterval: 5000,
  })
}
