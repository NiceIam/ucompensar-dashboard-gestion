/**
 * Traductor central de errores a lenguaje humano.
 *
 * Todo error que vea la persona pasa por `humanizeError`: nunca se muestra el
 * JSON crudo del servidor ni mensajes técnicos en inglés. Cada error dice
 * QUÉ PASÓ (título) y QUÉ HACER (descripción), y si tiene sentido reintentar.
 */

/** Error de la API con el código HTTP. `message` conserva el texto crudo de la respuesta. */
export class ApiError extends Error {
  readonly status: number
  readonly body: unknown

  constructor(status: number, rawText: string) {
    super(rawText || `HTTP ${status}`)
    this.name = "ApiError"
    this.status = status
    this.body = parseJson(rawText)
  }
}

export type ErrorContext =
  | "general"
  | "upload"
  | "analyze"
  | "chat"
  | "login"
  | "register"
  | "load"
  | "save"
  | "delete"
  | "download"

export interface HumanError {
  /** Qué pasó, en una frase corta. */
  title: string
  /** Qué puede hacer la persona ahora. */
  description: string
  /** Si volver a intentar tiene sentido. */
  retryable: boolean
  /** Siguiente paso sugerido. */
  action: "retry" | "login" | "choose-file" | "wait" | "none"
  /** Detalle técnico breve, para mostrar pequeño o colapsado (soporte). */
  technical?: string
}

function parseJson(text: string): unknown {
  if (!text) return null
  try {
    return JSON.parse(text)
  } catch {
    return null
  }
}

/** Título genérico de "no se pudo" según lo que se intentaba hacer. */
const FAILED_TITLE: Record<ErrorContext, string> = {
  general: "No pudimos completar la acción",
  upload: "No pudimos guardar tu archivo",
  analyze: "No pudimos leer tu archivo",
  chat: "El asistente no pudo responder",
  login: "No pudimos iniciar sesión",
  register: "No pudimos crear tu cuenta",
  load: "No pudimos cargar esta información",
  save: "No pudimos guardar los cambios",
  delete: "No pudimos borrarlo",
  download: "No pudimos descargar el archivo",
}

const NETWORK_PATTERNS = [/failed to fetch/i, /networkerror/i, /load failed/i, /network request failed/i, /fetch failed/i]

interface DetailRule {
  test: RegExp
  build: (ctx: ErrorContext) => Omit<HumanError, "technical">
}

/** Mensajes conocidos del backend (en español sin tildes o en inglés) -> versión humana. */
const DETAIL_RULES: DetailRule[] = [
  {
    test: /tipo de archivo no soportado|unsupported file|file type/i,
    build: () => ({
      title: "Ese tipo de archivo no lo podemos leer",
      description: "Sube un Excel (.xlsx), un CSV o un JSON. Si tienes un .xls antiguo, ábrelo en Excel y guárdalo como .xlsx.",
      retryable: false,
      action: "choose-file",
    }),
  },
  {
    test: /no tiene columnas|encabezados|file is empty|archivo (est[aá] )?vac[ií]o/i,
    build: () => ({
      title: "Tu archivo parece vacío",
      description: "Revisa que la primera fila tenga los nombres de las columnas (por ejemplo: fecha, producto, total) y que debajo haya datos.",
      retryable: false,
      action: "choose-file",
    }),
  },
  {
    test: /error al procesar el archivo|verifique el formato|could not parse|no se pudo leer/i,
    build: () => ({
      title: "No pudimos leer tu archivo",
      description: "Puede estar dañado o protegido con contraseña. Ábrelo en Excel, guárdalo de nuevo como .xlsx o .csv e inténtalo otra vez.",
      retryable: false,
      action: "choose-file",
    }),
  },
  {
    test: /demasiado grande|too large|excede|exceeds|max(imo)? .*(mb|filas|rows)/i,
    build: () => ({
      title: "El archivo es muy grande",
      description: "Puedes subir archivos de hasta 10 MB. Prueba dividiéndolo en partes (por ejemplo, un archivo por año).",
      retryable: false,
      action: "choose-file",
    }),
  },
  {
    test: /credenciales|invalid credentials|incorrect|contrase[nñ]a incorrecta/i,
    build: () => ({
      title: "El correo o la contraseña no coinciden",
      description: "Revísalos con calma; las mayúsculas cuentan.",
      retryable: false,
      action: "none",
    }),
  },
  {
    test: /ya (existe|est[aá] registrad)|already (exists|registered)|duplicate/i,
    build: (ctx) =>
      ctx === "register"
        ? {
            title: "Ya existe una cuenta con ese correo",
            description: "Inicia sesión con ese correo o usa uno diferente para la cuenta nueva.",
            retryable: false,
            action: "login",
          }
        : {
            title: "Ya existe algo con ese nombre",
            description: "Prueba con un nombre diferente.",
            retryable: false,
            action: "none",
          },
  },
  {
    test: /no encontrad|not found/i,
    build: () => ({
      title: "Ya no encontramos esa información",
      description: "Puede que se haya borrado hace un momento. Actualiza la página para ver lo más reciente.",
      retryable: false,
      action: "none",
    }),
  },
]

/** Respuestas que podemos mostrar tal cual: texto corto, sin JSON, sin HTML, sin trazas. */
function looksHuman(text: string): boolean {
  const t = text.trim()
  if (!t || t.length > 220) return false
  if (/^[[{<]/.test(t)) return false
  if (/traceback|exception|error:|sql|asyncpg|psycopg|undefined|null|stack/i.test(t)) return false
  return true
}

function extractDetail(body: unknown): string | null {
  if (!body || typeof body !== "object") return null
  const detail = (body as { detail?: unknown }).detail
  if (typeof detail === "string") return detail
  if (detail && typeof detail === "object" && !Array.isArray(detail)) {
    const msg = (detail as { message?: unknown }).message
    if (typeof msg === "string") return msg
  }
  const error = (body as { error?: unknown }).error
  if (typeof error === "string") return error
  const message = (body as { message?: unknown }).message
  if (typeof message === "string") return message
  return null
}

function isValidationArray(body: unknown): boolean {
  return Boolean(body && typeof body === "object" && Array.isArray((body as { detail?: unknown }).detail))
}

function byStatus(status: number, ctx: ErrorContext): Omit<HumanError, "technical"> {
  if (status === 401)
    return ctx === "login"
      ? {
          title: "El correo o la contraseña no coinciden",
          description: "Revísalos con calma; las mayúsculas cuentan.",
          retryable: false,
          action: "none",
        }
      : {
          title: "Tu sesión terminó",
          description: "Por seguridad cerramos tu sesión después de un tiempo. Vuelve a entrar para continuar.",
          retryable: false,
          action: "login",
        }
  if (status === 403)
    return {
      title: "No tienes permiso para esto",
      description: "Si crees que es un error, pide acceso a la persona que administra tu cuenta.",
      retryable: false,
      action: "none",
    }
  if (status === 404)
    return {
      title: "Ya no encontramos esa información",
      description: "Puede que se haya borrado hace un momento. Actualiza la página para ver lo más reciente.",
      retryable: false,
      action: "none",
    }
  if (status === 409)
    return {
      title: "Ya existe algo con ese nombre",
      description: "Prueba con un nombre diferente.",
      retryable: false,
      action: "none",
    }
  if (status === 413)
    return {
      title: "El archivo es muy grande",
      description: "Puedes subir archivos de hasta 10 MB. Prueba dividiéndolo en partes.",
      retryable: false,
      action: "choose-file",
    }
  if (status === 422 || status === 400)
    return ctx === "upload" || ctx === "analyze"
      ? {
          title: "No pudimos leer tu archivo",
          description: "Revisa que la primera fila tenga los nombres de las columnas y que el archivo no esté protegido. Luego inténtalo de nuevo.",
          retryable: false,
          action: "choose-file",
        }
      : {
          title: FAILED_TITLE[ctx],
          description: "Algún dato no tiene el formato esperado. Revísalo e inténtalo de nuevo.",
          retryable: false,
          action: "none",
        }
  if (status === 429)
    return {
      title: "Vamos muy rápido",
      description: "Espera unos segundos y vuelve a intentarlo.",
      retryable: true,
      action: "wait",
    }
  if (status >= 500)
    return {
      title: FAILED_TITLE[ctx],
      description: "Algo falló de nuestro lado. Inténtalo de nuevo en un momento; si sigue pasando, avísanos.",
      retryable: true,
      action: "retry",
    }
  return {
    title: FAILED_TITLE[ctx],
    description: "Inténtalo de nuevo en un momento.",
    retryable: true,
    action: "retry",
  }
}

function technicalOf(status: number | null, raw: string): string | undefined {
  const snippet = raw.replace(/\s+/g, " ").trim().slice(0, 160)
  if (status && snippet) return `HTTP ${status} · ${snippet}`
  if (status) return `HTTP ${status}`
  return snippet || undefined
}

/** Convierte cualquier error en un mensaje humano con la acción siguiente. */
export function humanizeError(err: unknown, context: ErrorContext = "general"): HumanError {
  if (!(err instanceof Error)) {
    return {
      title: FAILED_TITLE[context],
      description: "Inténtalo de nuevo en un momento.",
      retryable: true,
      action: "retry",
    }
  }

  const raw = err.message ?? ""

  // Sin conexión o servidor inalcanzable
  if (!(err instanceof ApiError) && NETWORK_PATTERNS.some((p) => p.test(raw))) {
    return {
      title: "No pudimos conectarnos",
      description:
        context === "upload" || context === "analyze"
          ? "Revisa tu conexión a internet e inténtalo de nuevo. Tu archivo sigue aquí: no tienes que elegirlo otra vez."
          : "Revisa tu conexión a internet e inténtalo de nuevo en un momento.",
      retryable: true,
      action: "retry",
      technical: raw,
    }
  }

  const status = err instanceof ApiError ? err.status : null
  const body = err instanceof ApiError ? err.body : parseJson(raw)
  const detail = extractDetail(body) ?? (body === null && looksHuman(raw) && !/^HTTP \d+$/.test(raw) ? raw : null)
  const technical = technicalOf(status, raw)

  if (detail) {
    const rule = DETAIL_RULES.find((r) => r.test.test(detail))
    // En login, un 401 siempre es "no coinciden", aunque el detalle diga otra cosa.
    if (rule && !(context === "login" && status === 401)) return { ...rule.build(context), technical }
  }

  if (status !== null) {
    const base = byStatus(status, context)
    // Si el servidor mandó una frase clara en español, úsala como descripción.
    if (detail && looksHuman(detail) && status !== 401 && status < 500 && !isValidationArray(body)) {
      return { ...base, description: ensurePeriod(detail), technical }
    }
    return { ...base, technical }
  }

  if (detail && looksHuman(detail)) {
    return {
      title: FAILED_TITLE[context],
      description: ensurePeriod(detail),
      retryable: true,
      action: "retry",
      technical,
    }
  }

  return {
    title: FAILED_TITLE[context],
    description: "Inténtalo de nuevo en un momento. Si sigue pasando, avísanos.",
    retryable: true,
    action: "retry",
    technical,
  }
}

function ensurePeriod(text: string): string {
  const t = text.trim()
  const capitalized = t.charAt(0).toUpperCase() + t.slice(1)
  return /[.!?…]$/.test(capitalized) ? capitalized : `${capitalized}.`
}

/** Atajo: "Título. Descripción" en una sola línea (para toasts). */
export function humanizeErrorText(err: unknown, context: ErrorContext = "general"): string {
  const h = humanizeError(err, context)
  return `${h.title}. ${h.description}`
}
