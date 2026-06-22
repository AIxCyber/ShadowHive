export interface DashboardStats {
  active_companies: number
  threat_events_total: number
  threat_events_new_hour: number
  active_sessions: number
  high_risk_sessions: number
  mitre_coverage_pct: number
  mitre_tactics_mapped: number
  techniques_identified: number
  avg_confidence: number
  total_commands_today: number
  files_accessed_today: number
  unique_ips_24h: number
  threat_timeline: { hour: string; threats: number; critical: number }[]
}

export interface ThreatEvent {
  threat_id: string
  severity: string
  tactic: string
  technique: string
  confidence: number
  source_ip: string
  detected_at: string
}

export interface Session {
  session_id: string
  source_ip: string
  protocol: string
  risk_score: number
  commands_executed: number
  duration_minutes: number
  last_seen: string
  bytes_sent: number
  bytes_received: number
}

export interface TaskInfo {
  task_id: string
  status: "pending" | "running" | "paused" | "completed" | "failed" | "cancelled"
  progress: number
  message: string
  error?: string
  result?: any
  params?: any
  created_at: string
  started_at?: string
  completed_at?: string
}

export interface CompanyProfile {
  id: string
  name: string
  industry?: string
  size?: string
  company_name?: string
  description?: string
  location?: string
  technologies?: string[]
  security_posture?: string
  created_at?: string
  updated_at?: string
}

export interface GenerateOptions {
  industry: string
  size: string
  seed?: string
  enrich?: boolean
  overrides?: {
    company_name?: string
    description?: string
    location?: string
    technologies?: string[]
    security_posture?: string
  }
}

const BASE = "/api"

let _refreshPromise: Promise<boolean> | null = null

export async function refreshTokens(): Promise<boolean> {
  if (_refreshPromise) return _refreshPromise
  _refreshPromise = (async () => {
    const refreshToken = localStorage.getItem("refresh_token")
    if (!refreshToken) return false
    try {
      const res = await fetch(`${BASE}/auth/refresh`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ refresh_token: refreshToken }),
      })
      if (res.ok) {
        const data = await res.json()
        localStorage.setItem("access_token", data.access_token)
        localStorage.setItem("refresh_token", data.refresh_token)
        return true
      }
      if (res.status !== 401) return false
      localStorage.removeItem("access_token")
      localStorage.removeItem("refresh_token")
      return false
    } catch {
      return false
    }
  })()
  const result = await _refreshPromise
  _refreshPromise = null
  return result
}

function authHeaders(): Record<string, string> {
  if (typeof window === "undefined") return {}
  const token = localStorage.getItem("access_token")
  return token ? { Authorization: `Bearer ${token}` } : {}
}

function timezoneHeader(): Record<string, string> {
  if (typeof window === "undefined") return {}
  try {
    const tz = Intl.DateTimeFormat().resolvedOptions().timeZone
    return tz ? { "X-Timezone": tz } : {}
  } catch {
    return {}
  }
}

async function fetchJson<T>(url: string, opts?: RequestInit): Promise<T> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...authHeaders(),
    ...timezoneHeader(),
    ...((opts?.headers as Record<string, string>) || {}),
  }
  const res = await fetch(`${BASE}${url}`, {
    ...opts,
    headers,
  })
  if (!res.ok) {
    const body = await res.text().catch(() => "")
    if (res.status === 401) {
      const refreshed = await refreshTokens()
      if (refreshed) {
        const newToken = localStorage.getItem("access_token")
        if (newToken) headers.Authorization = `Bearer ${newToken}`
        const retry = await fetch(`${BASE}${url}`, { ...opts, headers })
        if (retry.ok) return retry.json()
      }
    }
    throw new Error(body || `Request failed (${res.status})`)
  }
  return res.json()
}

export function fetchStats(range?: string): Promise<DashboardStats> {
  const q = range ? `?range=${range}` : ""
  return fetchJson<DashboardStats>(`/stats${q}`)
}

export function fetchThreats(severity?: string, tactic?: string): Promise<ThreatEvent[]> {
  const q = new URLSearchParams()
  if (severity) q.set("severity", severity)
  if (tactic) q.set("tactic", tactic)
  const qs = q.toString()
  return fetchJson<ThreatEvent[]>(`/threats${qs ? `?${qs}` : ""}`)
}

export function fetchSessions(minRisk?: number): Promise<Session[]> {
  const q = new URLSearchParams()
  if (minRisk !== undefined) q.set("min_risk", String(minRisk))
  const qs = q.toString()
  return fetchJson<Session[]>(`/sessions${qs ? `?${qs}` : ""}`)
}

export function generateCompany(opts: GenerateOptions): Promise<{ task_id: string }> {
  return fetchJson<{ task_id: string }>("/companies/generate", {
    method: "POST",
    body: JSON.stringify(opts),
  })
}

export function cancelTask(taskId: string): Promise<TaskInfo> {
  return fetchJson<TaskInfo>(`/companies/tasks/${taskId}/cancel`, { method: "POST" })
}

export function pauseTask(taskId: string): Promise<TaskInfo> {
  return fetchJson<TaskInfo>(`/companies/tasks/${taskId}/pause`, { method: "POST" })
}

export function resumeTask(taskId: string): Promise<TaskInfo> {
  return fetchJson<TaskInfo>(`/companies/tasks/${taskId}/resume`, { method: "POST" })
}

export function deleteTask(taskId: string): Promise<{ deleted: boolean }> {
  return fetchJson<{ deleted: boolean }>(`/companies/tasks/${taskId}`, { method: "DELETE" })
}

export function fetchTask(taskId: string): Promise<TaskInfo> {
  return fetchJson<TaskInfo>(`/companies/tasks/${taskId}`)
}

export function fetchTasks(): Promise<TaskInfo[]> {
  return fetchJson<TaskInfo[]>("/companies/tasks")
}

// ── Company Profiles (templates) ──────────────────────────────────────────

export function saveProfile(data: {
  name: string
  industry?: string
  size?: string
  company_name?: string
  description?: string
  location?: string
  technologies?: string[]
  security_posture?: string
}): Promise<CompanyProfile> {
  return fetchJson<CompanyProfile>("/companies/profiles", {
    method: "POST",
    body: JSON.stringify(data),
  })
}

export function fetchProfiles(): Promise<CompanyProfile[]> {
  return fetchJson<CompanyProfile[]>("/companies/profiles")
}

export function deleteProfile(profileId: string): Promise<{ deleted: boolean }> {
  return fetchJson<{ deleted: boolean }>(`/companies/profiles/${profileId}`, { method: "DELETE" })
}

// ── Honeypot Deployment ─────────────────────────────────────────────────

export interface DeployResult {
  company_id: string
  company_name: string
  deployed_at: string
  employee_count: number
  cowrie_restarted: boolean
}

export interface DeployStatus {
  active: boolean
  company_id?: string
  company_name?: string
  deployed_at?: string
  employee_count?: number
}

export function deployCompany(companyId: string): Promise<DeployResult> {
  return fetchJson<DeployResult>(`/deploy/${companyId}`, { method: "POST" })
}

export function undeployCompany(): Promise<{ undeployed: boolean; previous?: string }> {
  return fetchJson<{ undeployed: boolean; previous?: string }>("/deploy/undeploy", { method: "POST" })
}

export function fetchDeployStatus(): Promise<DeployStatus> {
  return fetchJson<DeployStatus>("/deploy/status")
}

// ── Logs ────────────────────────────────────────────────────────────────────

export interface LogEntry {
  id?: string
  timestamp: string
  level: "DEBUG" | "INFO" | "WARNING" | "ERROR" | "CRITICAL"
  logger_name: string
  module: string
  func_name: string
  line_no: number
  message: string
  traceback?: string
  task_id?: string
  request_id?: string
}

export interface LogStats {
  total: number
  by_level: Record<string, number>
  by_logger: Record<string, number>
}

export interface LogResponse {
  items: LogEntry[]
  total: number
}

export interface LogFilters {
  level?: string
  logger?: string
  search?: string
  task_id?: string
  since?: string
  until?: string
  limit?: number
  offset?: number
  order?: "asc" | "desc"
}

export function fetchLogs(filters: LogFilters = {}): Promise<LogResponse> {
  const q = new URLSearchParams()
  if (filters.level) q.set("level", filters.level)
  if (filters.logger) q.set("logger", filters.logger)
  if (filters.search) q.set("search", filters.search)
  if (filters.task_id) q.set("task_id", filters.task_id)
  if (filters.since) q.set("since", filters.since)
  if (filters.until) q.set("until", filters.until)
  if (filters.limit) q.set("limit", String(filters.limit))
  if (filters.offset) q.set("offset", String(filters.offset))
  if (filters.order) q.set("order", filters.order)
  const qs = q.toString()
  return fetchJson<LogResponse>(`/logs${qs ? `?${qs}` : ""}`)
}

export function fetchLogStats(): Promise<LogStats> {
  return fetchJson<LogStats>("/logs/stats")
}

export function clearLogs(olderThanDays: number = 7): Promise<{ deleted: boolean }> {
  return fetchJson<{ deleted: boolean }>(`/logs?older_than=${olderThanDays}`, { method: "DELETE" })
}
