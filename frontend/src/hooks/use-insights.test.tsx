import type { ReactNode } from "react"
import { beforeEach, describe, expect, test, vi } from "vitest"
import { renderHook, waitFor } from "@testing-library/react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"

const { get } = vi.hoisted(() => ({ get: vi.fn() }))
vi.mock("@/lib/api", () => ({ api: { get } }))

import { useInsights } from "./use-insights"

function wrapper() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return ({ children }: { children: ReactNode }) => <QueryClientProvider client={client}>{children}</QueryClientProvider>
}

describe("useInsights", () => {
  beforeEach(() => get.mockReset())

  test("pide /api/v1/insights y entrega la respuesta normalizada", async () => {
    get.mockResolvedValue({ generated_at: "2026-10-19T14:05:00Z", items: [{ id: "a", title: "t" }] })
    const { result } = renderHook(() => useInsights(), { wrapper: wrapper() })
    expect(result.current.isLoading).toBe(true)
    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(get).toHaveBeenCalledWith("/api/v1/insights")
    expect(result.current.data?.missing).toEqual([])
    expect(result.current.data?.items[0].how.notes).toEqual([])
  })

  test("vacío: items y missing vacíos no son un error", async () => {
    get.mockResolvedValue({ generated_at: "2026-10-19T14:05:00Z", items: [], missing: [] })
    const { result } = renderHook(() => useInsights(), { wrapper: wrapper() })
    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(result.current.data?.items).toEqual([])
    expect(result.current.isError).toBe(false)
  })
})
