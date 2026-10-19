/**
 * Identidad del producto en UN solo lugar. Cambiar el nombre, la frase o el
 * crédito aquí lo cambia en toda la interfaz (títulos, login, barra lateral,
 * metadatos de la página).
 */
export const BRAND = {
  /** Nombre visible del producto: el del proyecto de investigación oficial. */
  name: "Proyecto PI0320251",
  /** Código oficial del proyecto: la versión corta del nombre (wordmark, títulos de pestaña). */
  code: "PI0320251",
  /** Palabra que acompaña al código en el wordmark de dos niveles. */
  kicker: "Proyecto",
  /** Frase corta que acompaña al nombre. */
  tagline: "Tu negocio, explicado.",
  /** Descripción para metadatos y la portada del login. */
  description:
    "Sube tus archivos, entiende tus números y pregúntale a tus datos en lenguaje natural.",
  /**
   * Institución que respalda el proyecto. Su logo oficial se muestra en el
   * login, en el pie de la barra lateral y en Configuración › Acerca de.
   */
  institution: "Fundación Universitaria Compensar",
  /**
   * Código del proyecto de investigación (el mismo de `code`); déjalo en
   * `null` para ocultar la línea de Configuración › Acerca de.
   */
  projectCode: "PI0320251" as string | null,
} as const

/** Título de pestaña: "Página · Proyecto PI0320251". */
export function pageTitle(section?: string): string {
  return section ? `${section} · ${BRAND.name}` : `${BRAND.name} · ${BRAND.tagline}`
}
