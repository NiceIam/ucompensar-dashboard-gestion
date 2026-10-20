const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i

/** true solo para un UUID real: es lo único con lo que se arma un enlace a un tablero. */
export function isUuid(value: unknown): value is string {
  return typeof value === "string" && UUID.test(value)
}
