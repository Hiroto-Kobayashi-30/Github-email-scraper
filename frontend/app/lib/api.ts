export type Progress = {
  status: string
  run_id?: string
  location?: string
  min_repos?: number
  max_repos?: number

  target: number
  extracted: number
  skipped: number

  skipped_no_email: number
  skipped_not_gmail: number
  skipped_duplicate: number
  skipped_repo_range: number

  profile_email_fallbacks?: number
  profile_email_found?: number
  profile_email_missing?: number

  errors: number
  scanned_users: number
  progress_percent: number

  current_username?: string | null
  current_stage?: string

  elapsed_seconds: number
  profile_seconds?: number
  gmail_filter_seconds?: number
  dedup_seconds?: number

  run_csv?: string | null
  last_error?: string | null

  recent: Array<{
    login: string
    email: string
    account_creation_year: number
  }>
}

export type HistoryRecord = {
  username: string
  email: string
  github_username: string
  account_creation_year: string | number
  run_id: string
  scraped_at: string
}

export type ExportEntry = {
  path: string
  name: string
  size_bytes: number
  modified: string
}

export type RunForm = {
  location: string
  min_repos: number
  max_repos: number
  target_count: number
  start_year: number
  end_year: number
  strict_quality_gmail: boolean
}

const API =
  process.env.NEXT_PUBLIC_API_URL
  || 'http://localhost:8000'

export const apiBase = API

export async function fetchProgress(): Promise<Progress> {
  const r = await fetch(
    `${API}/api/runs/current`,
    { cache: 'no-store' }
  )
  if (!r.ok) throw new Error('Failed to fetch current run')
  return r.json()
}

export async function fetchStats(): Promise<{
  historical_records: number
  run: Progress
}> {
  const r = await fetch(
    `${API}/api/stats`,
    { cache: 'no-store' }
  )
  if (!r.ok) throw new Error('Failed to fetch stats')
  return r.json()
}

export async function startRun(
  form: RunForm
): Promise<{ accepted: boolean }> {
  const r = await fetch(
    `${API}/api/runs`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(form),
    }
  )
  const body = await r.json()
  if (!r.ok) throw new Error(body.detail || 'Could not start run')
  return body
}

export async function cancelRun(): Promise<{
  cancelled: boolean
}> {
  const r = await fetch(
    `${API}/api/runs/cancel`,
    { method: 'POST' }
  )
  if (!r.ok) throw new Error('Failed to cancel run')
  return r.json()
}

export async function fetchHistory(
  limit = 100,
  offset = 0,
  q = ''
): Promise<{
  total: number
  records: HistoryRecord[]
}> {
  const params = new URLSearchParams({
    limit: String(limit),
    offset: String(offset),
  })
  if (q) params.set('q', q)

  const r = await fetch(
    `${API}/api/history?${params}`,
    { cache: 'no-store' }
  )
  if (!r.ok) throw new Error('Failed to fetch history')
  return r.json()
}

export async function fetchExports(): Promise<{
  exports: ExportEntry[]
}> {
  const r = await fetch(
    `${API}/api/exports`,
    { cache: 'no-store' }
  )
  if (!r.ok) throw new Error('Failed to fetch exports')
  return r.json()
}

export function downloadUrl(path: string): string {
  return `${API}/api/exports/download?path=` + encodeURIComponent(path)
}

export function runFileUrl(path: string): string {
  return `${API}/api/runs/file?path=` + encodeURIComponent(path)
}

export type TokenStatus = {
  token_index: number
  label: string
  masked: string

  usage_percent: number | null
  remaining: number | null
  limit: number | null

  reset_seconds: number
  cooldown_seconds: number
  cooldown_active: boolean

  in_flight: number

  last_cost: number
  last_status: number | null

  invalid: boolean
  initialized: boolean
}

export async function fetchTokenStatus(): Promise<{
  tokens: TokenStatus[]
}> {
  const r = await fetch(
    `${API}/api/tokens/status`,
    { cache: 'no-store' }
  )
  if (!r.ok) throw new Error('Failed to fetch token status')
  return r.json()
}
