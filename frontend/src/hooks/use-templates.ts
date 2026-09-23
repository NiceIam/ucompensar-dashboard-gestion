"use client"

import { useQuery } from "@tanstack/react-query"
import { api } from "@/lib/api"

export interface OrgTable {
  id: string
  table_name: string
  display_name: string
  columns_definition: Array<{ name: string; type: string; label: string; required?: boolean }>
  row_count: number
}

interface OrgTableList {
  tables: OrgTable[]
  total: number
}

export interface BusinessType {
  id: string
  name: string
  display_name: string
  description?: string
  icon?: string
}

interface BusinessTypeList {
  types: BusinessType[]
  total: number
}

export function useOrgTables() {
  return useQuery<OrgTableList>({
    queryKey: ["templates", "org-tables"],
    queryFn: () => api.get<OrgTableList>("/api/v1/templates/org-tables"),
  })
}

export function useBusinessTypes() {
  return useQuery<BusinessTypeList>({
    queryKey: ["templates", "business-types"],
    queryFn: () => api.get<BusinessTypeList>("/api/v1/templates/business-types"),
  })
}
