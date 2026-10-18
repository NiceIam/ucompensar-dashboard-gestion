/**
 * Tipografía de Brújula: UNA línea elige el emparejamiento.
 *
 *   A (predeterminado) → export { fontPair } from "./font-pairs/outfit-inter"
 *   B                  → export { fontPair } from "./font-pairs/sora-dm-sans"
 *   C                  → export { fontPair } from "./font-pairs/urbanist-inter"
 *
 * Solo el par importado entra al paquete (next/font descarga y precarga
 * únicamente las familias que se usan).
 */
export { fontPair } from "./font-pairs/outfit-inter"
