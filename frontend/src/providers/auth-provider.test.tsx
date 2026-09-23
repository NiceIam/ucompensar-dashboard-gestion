/**
 * Unit tests for AuthProvider (auth-provider.tsx).
 *
 * Strategy: mock the global `fetch` via vi.fn(), wrap the provider in a real
 * QueryClientProvider so TanStack Query lifecycle runs normally.
 *
 * Setup requires: vitest + @testing-library/react + jsdom
 */
import { describe, test, expect, vi, beforeEach, afterEach } from "vitest"
import { render, screen, waitFor, act } from "@testing-library/react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import * as React from "react"
import { AuthProvider, useAuthContext, type User } from "./auth-provider"

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------
const MOCK_USER: User = {
  user_id: "user-123",
  org_id: "org-456",
  email: "test@example.com",
  role: "admin",
  full_name: "Test User",
}

function makeQueryClient() {
  return new QueryClient({
    defaultOptions: {
      queries: {
        // Disable retries so tests resolve fast
        retry: false,
        // Disable stale-time so every test starts fresh
        staleTime: 0,
      },
    },
  })
}

function Wrapper({
  children,
  queryClient,
}: {
  children: React.ReactNode
  queryClient: QueryClient
}) {
  return (
    <QueryClientProvider client={queryClient}>
      <AuthProvider>{children}</AuthProvider>
    </QueryClientProvider>
  )
}

/** Consumer component that renders auth context values as data-testid attributes */
function AuthConsumer() {
  const { user, loading } = useAuthContext()
  return (
    <div>
      <div data-testid="loading">{String(loading)}</div>
      <div data-testid="user-id">{user?.user_id ?? "null"}</div>
      <div data-testid="user-name">{user?.full_name ?? "null"}</div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Setup / teardown
// ---------------------------------------------------------------------------
let queryClient: QueryClient

beforeEach(() => {
  queryClient = makeQueryClient()
  vi.stubGlobal("fetch", vi.fn())
})

afterEach(() => {
  vi.restoreAllMocks()
  queryClient.clear()
})

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------
describe("AuthProvider", () => {
  test("should_call_fetch_with_credentials_include_when_mounted", async () => {
    const mockFetch = vi.fn().mockResolvedValueOnce({
      ok: true,
      status: 200,
      json: async () => MOCK_USER,
    })
    vi.stubGlobal("fetch", mockFetch)

    render(
      <Wrapper queryClient={queryClient}>
        <AuthConsumer />
      </Wrapper>
    )

    await waitFor(() => {
      expect(mockFetch).toHaveBeenCalledOnce()
    })

    const [url, options] = mockFetch.mock.calls[0] as [string, RequestInit]
    expect(url).toContain("/api/v1/auth/me")
    expect(options.credentials).toBe("include")
    expect(options.method).toBe("GET")
  })

  test("should_expose_user_data_when_me_returns_200", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => MOCK_USER,
      })
    )

    render(
      <Wrapper queryClient={queryClient}>
        <AuthConsumer />
      </Wrapper>
    )

    await waitFor(() => {
      expect(screen.getByTestId("user-id").textContent).toBe(MOCK_USER.user_id)
    })

    expect(screen.getByTestId("user-name").textContent).toBe(MOCK_USER.full_name)
  })

  test("should_expose_null_user_when_me_returns_401", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValueOnce({
        ok: false,
        status: 401,
        json: async () => null,
      })
    )

    render(
      <Wrapper queryClient={queryClient}>
        <AuthConsumer />
      </Wrapper>
    )

    await waitFor(() => {
      expect(screen.getByTestId("loading").textContent).toBe("false")
    })

    expect(screen.getByTestId("user-id").textContent).toBe("null")
  })

  test("should_expose_null_user_when_me_returns_403", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValueOnce({
        ok: false,
        status: 403,
        json: async () => null,
      })
    )

    render(
      <Wrapper queryClient={queryClient}>
        <AuthConsumer />
      </Wrapper>
    )

    await waitFor(() => {
      expect(screen.getByTestId("loading").textContent).toBe("false")
    })

    expect(screen.getByTestId("user-id").textContent).toBe("null")
  })

  test("should_show_loading_true_while_query_is_pending", async () => {
    // fetchMe never resolves during this test
    let resolveFetch!: (v: unknown) => void
    const pendingPromise = new Promise((resolve) => {
      resolveFetch = resolve
    })

    vi.stubGlobal(
      "fetch",
      vi.fn().mockReturnValueOnce(pendingPromise)
    )

    render(
      <Wrapper queryClient={queryClient}>
        <AuthConsumer />
      </Wrapper>
    )

    // While fetch is pending, loading must be true
    expect(screen.getByTestId("loading").textContent).toBe("true")

    // Cleanup — resolve the promise so the QueryClient can GC cleanly
    await act(async () => {
      resolveFetch({
        ok: true,
        status: 200,
        json: async () => MOCK_USER,
      })
    })
  })

  test("should_store_user_in_query_cache_under_auth_me_key_when_200_received", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => MOCK_USER,
      })
    )

    render(
      <Wrapper queryClient={queryClient}>
        <AuthConsumer />
      </Wrapper>
    )

    await waitFor(() => {
      const cached = queryClient.getQueryData<User | null>(["auth", "me"])
      expect(cached).not.toBeUndefined()
      expect(cached?.user_id).toBe(MOCK_USER.user_id)
    })
  })

  test("should_invalidate_auth_me_when_invalidateQueries_called_on_key", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn()
        .mockResolvedValueOnce({
          ok: true,
          status: 200,
          json: async () => MOCK_USER,
        })
        .mockResolvedValueOnce({
          ok: true,
          status: 200,
          json: async () => ({ ...MOCK_USER, full_name: "Updated User" }),
        })
    )

    render(
      <Wrapper queryClient={queryClient}>
        <AuthConsumer />
      </Wrapper>
    )

    await waitFor(() => {
      expect(screen.getByTestId("user-name").textContent).toBe("Test User")
    })

    // Invalidate should trigger a refetch
    await act(async () => {
      await queryClient.invalidateQueries({ queryKey: ["auth", "me"] })
    })

    await waitFor(() => {
      expect(screen.getByTestId("user-name").textContent).toBe("Updated User")
    })
  })

  test("should_keep_token_null_in_context_always", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => MOCK_USER,
      })
    )

    function TokenConsumer() {
      const { token } = useAuthContext()
      return <div data-testid="token">{String(token)}</div>
    }

    render(
      <Wrapper queryClient={queryClient}>
        <TokenConsumer />
      </Wrapper>
    )

    await waitFor(() => {
      expect(screen.getByTestId("token").textContent).toBe("null")
    })
  })
})
