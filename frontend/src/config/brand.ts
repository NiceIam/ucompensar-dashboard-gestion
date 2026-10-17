/**
 * Identidad del producto en UN solo lugar. Cambiar el nombre, la frase o el
 * crédito aquí lo cambia en toda la interfaz (títulos, login, barra lateral,
 * metadatos de la página).
 */
export const BRAND = {
  /** Nombre visible del producto. */
  name: "Brújula",
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
   * Código del proyecto de investigación. Solo aparece, pequeño, en
   * Configuración › Acerca de; déjalo en `null` para ocultarlo.
   */
  projectCode: "PI0320251" as string | null,
} as const

/** Título de pestaña: "Página · Brújula". */
export function pageTitle(section?: string): string {
  return section ? `${section} · ${BRAND.name}` : `${BRAND.name} · ${BRAND.tagline}`
}
