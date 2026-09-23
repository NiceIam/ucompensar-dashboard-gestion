"use client"

import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import { api } from "@/lib/api"
import type { UploadedFile, FilePreview } from "@/types/api"

export function useFiles() {
  return useQuery<UploadedFile[]>({
    queryKey: ["files"],
    queryFn: (): Promise<UploadedFile[]> => api.get("/api/v1/files"),
  })
}

export function useFile(id: string) {
  return useQuery<UploadedFile>({
    queryKey: ["files", id],
    queryFn: (): Promise<UploadedFile> => api.get(`/api/v1/files/${id}`),
    enabled: Boolean(id),
  })
}

export function useFilePreview(id: string) {
  return useQuery<FilePreview>({
    queryKey: ["files", id, "preview"],
    queryFn: (): Promise<FilePreview> => api.get(`/api/v1/files/${id}/preview`),
    enabled: Boolean(id),
  })
}

export function useUploadFile() {
  const queryClient = useQueryClient()

  return useMutation<UploadedFile, Error, FormData>({
    mutationFn: (formData: FormData): Promise<UploadedFile> =>
      api.upload("/api/v1/files/upload", formData),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["files"] })
    },
  })
}

export function useDeleteFile() {
  const queryClient = useQueryClient()

  return useMutation<void, Error, string>({
    mutationFn: (id: string): Promise<void> =>
      api.delete(`/api/v1/files/${id}`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["files"] })
    },
  })
}
