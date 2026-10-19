import { ApiError } from "@/lib/errors"

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000"

function redirectToLogin(): void {
  if (typeof window === "undefined") return
  // Avoid redirect loops if we're already on login/register pages.
  const path = window.location.pathname
  if (path.startsWith("/login") || path.startsWith("/register")) return
  window.location.href = "/login"
}

async function handleResponse<T>(res: Response): Promise<T> {
  if (!res.ok) {
    // ApiError conserva el texto crudo en `message` (lo leen los parsers de límites
    // del chat) y agrega el código HTTP para traducirlo con humanizeError().
    const raw = await res.text().catch(() => "")
    throw new ApiError(res.status, raw)
  }
  return res.json() as Promise<T>
}

function buildHeaders(isMultipart = false): HeadersInit {
  const headers: Record<string, string> = {}
  // No Authorization header: el backend lee tokens exclusivamente desde cookies HttpOnly.
  if (!isMultipart) {
    headers["Content-Type"] = "application/json"
  }
  return headers
}

// Single in-flight refresh promise to avoid stampedes when multiple requests
// receive 401 simultaneously. All concurrent 401s wait on the same refresh.
let refreshInFlight: Promise<boolean> | null = null

async function refreshAccessToken(): Promise<boolean> {
  if (refreshInFlight) return refreshInFlight

  refreshInFlight = (async () => {
    try {
      const res = await fetch(`${API_URL}/api/v1/auth/refresh`, {
        method: "POST",
        credentials: "include",
      })
      return res.ok
    } catch {
      return false
    } finally {
      // Release after microtask so waiters observe the resolved value first.
      setTimeout(() => {
        refreshInFlight = null
      }, 0)
    }
  })()

  return refreshInFlight
}

type FetchInit = Omit<RequestInit, "headers"> & { isMultipart?: boolean }

async function authedFetch(path: string, init: FetchInit = {}): Promise<Response> {
  const { isMultipart, ...rest } = init
  const url = `${API_URL}${path}`

  // credentials:"include" ensures HttpOnly cookies travel with every request.
  let res = await fetch(url, { ...rest, headers: buildHeaders(isMultipart), credentials: "include" })

  if (res.status !== 401) return res

  // 401: attempt single refresh + retry once. Never loop on /auth/refresh itself.
  if (path.startsWith("/api/v1/auth/refresh") || path.startsWith("/api/v1/auth/login")) {
    return res
  }

  const refreshed = await refreshAccessToken()
  if (!refreshed) {
    redirectToLogin()
    return res
  }

  res = await fetch(url, { ...rest, headers: buildHeaders(isMultipart), credentials: "include" })
  if (res.status === 401) {
    redirectToLogin()
  }
  return res
}

export const api = {
  async get<T>(path: string): Promise<T> {
    const res = await authedFetch(path, { method: "GET" })
    return handleResponse<T>(res)
  },

  async post<T>(path: string, body: unknown): Promise<T> {
    const res = await authedFetch(path, {
      method: "POST",
      body: JSON.stringify(body),
    })
    return handleResponse<T>(res)
  },

  async put<T>(path: string, body: unknown): Promise<T> {
    const res = await authedFetch(path, {
      method: "PUT",
      body: JSON.stringify(body),
    })
    return handleResponse<T>(res)
  },

  async delete<T>(path: string): Promise<T> {
    const res = await authedFetch(path, { method: "DELETE" })
    return handleResponse<T>(res)
  },

  async upload<T>(path: string, formData: FormData): Promise<T> {
    const res = await authedFetch(path, {
      method: "POST",
      body: formData,
      isMultipart: true,
    })
    return handleResponse<T>(res)
  },

  async putUpload<T>(path: string, formData: FormData): Promise<T> {
    const res = await authedFetch(path, {
      method: "PUT",
      body: formData,
      isMultipart: true,
    })
    return handleResponse<T>(res)
  },

  async downloadBlob(path: string, filename: string): Promise<void> {
    const res = await authedFetch(path, { method: "GET" })
    if (!res.ok) {
      const raw = await res.text().catch(() => "")
      throw new ApiError(res.status, raw)
    }
    const blob = await res.blob()
    const url = URL.createObjectURL(blob)
    try {
      const a = document.createElement("a")
      a.href = url
      a.download = filename
      document.body.appendChild(a)
      a.click()
      a.remove()
    } finally {
      // Garantiza la liberación del Blob aunque `click()` falle en entornos
      // restrictivos (sandbox, navegadores headless con políticas estrictas).
      URL.revokeObjectURL(url)
    }
  },
}
