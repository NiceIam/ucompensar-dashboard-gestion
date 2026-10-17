"use client"

import { useEffect } from "react"
import { pageTitle } from "@/config/brand"

/** Título de la pestaña del navegador para páginas cliente ("Mis datos · Brújula"). */
export function usePageTitle(section?: string) {
  useEffect(() => {
    document.title = pageTitle(section)
  }, [section])
}
