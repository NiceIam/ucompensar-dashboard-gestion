// ─── Auth & User ────────────────────────────────────────────────────────────

export interface User {
  id: string
  email: string
  full_name: string
  org_id: string
  created_at: string
}

export interface Organization {
  id: string
  name: string
  sector: string
  size: string
  plan: "free" | "pro"
  created_at: string
}

// ─── Files / Datasets ────────────────────────────────────────────────────────

export type FileStatus =
  | "uploaded"
  | "processing"
  | "ready"
  | "error"

export interface UploadedFile {
  id: string
  org_id: string
  name: string
  original_name: string
  file_type: "csv" | "xlsx" | "json"
  size_bytes: number
  row_count: number | null
  column_count: number | null
  status: FileStatus
  storage_path: string
  created_at: string
  updated_at: string
}

export interface FilePreview {
  columns: string[]
  rows: Record<string, unknown>[]
  total_rows: number
}

// ─── Agent / Analysis ────────────────────────────────────────────────────────

export type SessionStatus =
  | "pending"
  | "running"
  | "completed"
  | "failed"

export interface AgentSession {
  id: string
  org_id: string
  file_id: string
  file_name: string
  status: SessionStatus
  started_at: string | null
  completed_at: string | null
  created_at: string
}

export interface Insight {
  id: string
  session_id: string
  title: string
  description: string
  recommendation: string
  priority: "alta" | "media" | "baja"
  category: string
  created_at: string
}

export interface AgentResult {
  session: AgentSession
  insights: Insight[]
  dashboard_config: DashboardConfig | null
}

// ─── Dashboards & Widgets ────────────────────────────────────────────────────

export type ChartType =
  | "bar"
  | "line"
  | "pie"
  | "area"
  | "radar"
  | "metric"
  | "table"

export interface WidgetConfig {
  id: string
  dashboard_id: string
  title: string
  chart_type: ChartType
  data_key: string
  x_key: string
  y_keys: string[]
  color: string
  width: 1 | 2 | 3 | 4
  height: 1 | 2
  position: number
  data?: Record<string, unknown>[]
  created_at: string
}

export interface Dashboard {
  id: string
  dashboard_id: string
  org_id: string
  name: string
  description: string | null
  file_id: string | null
  widgets: WidgetConfig[]
  created_at: string
  updated_at: string
}

export interface DashboardConfig {
  recommended_charts: {
    title: string
    chart_type: ChartType
    x_key: string
    y_keys: string[]
    rationale: string
  }[]
}

// ─── Chat ────────────────────────────────────────────────────────────────────

export type MessageRole = "user" | "assistant"

export interface ChatMessage {
  id: string
  role: MessageRole
  content: string
  created_at: string
}

export interface ChatSession {
  id: string
  org_id: string
  file_id: string | null
  messages: ChatMessage[]
  created_at: string
}

// ─── Shared ──────────────────────────────────────────────────────────────────

export interface PaginatedResponse<T> {
  items: T[]
  total: number
  page: number
  size: number
}

export interface ApiError {
  detail: string
  status_code: number
}

export interface KPISummary {
  total_files: number
  total_records: number
  total_dashboards: number
  total_insights: number
  recent_uploads: UploadedFile[]
}
