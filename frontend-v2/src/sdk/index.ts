import { fetchWithAuth } from '../lib/localRunToken'

/**
 * Helper to handle JSON responses safely and standardize API calls.
 */
async function fetchJson<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetchWithAuth(url, init)
  if (!response.ok) {
    throw new Error(`API Error: ${response.status} ${response.statusText}`)
  }
  return response.json()
}

export const SystemAPI = {
  /** Prefer `agent === 'ready'` for readiness; `status` may be `degraded` while chat works. */
  health: () =>
    fetchJson<{
      status: 'ok' | 'degraded'
      agent: 'ready' | 'initializing'
      postgres?: string
      checkpointer?: string
    }>('/api/health'),
  getLocalRunToken: () => fetchJson<{ token: string }>('/api/local-run-token'),
}

export const CloudAPI = {
  getStatus: () => fetchJson<{ enabled: boolean }>('/api/cloud-status'),
  getUsage: () => fetchJson<any>('/api/usage'),
}

export const StudyAPI = {
  getDashboard: () => fetchJson<any>('/api/study/dashboard'),
  getAnalytics: () => fetchJson<any>('/api/study/analytics'),
  getExamCountdown: () => fetchJson<any>('/api/study/exam-countdown'),
  searchNotes: (query: string = '') =>
    fetchJson<any>(query.trim() ? `/api/study/notes?q=${encodeURIComponent(query)}` : '/api/study/notes'),
}

export const PentestAPI = {
  getStatus: () => fetchJson<any>('/api/pentest/status'),
  getTaskGraph: (engagementId: string) => fetchJson<any>(`/api/pentest/engagements/${engagementId}/task-graph`),
}

export const TemplatesAPI = {
  getTemplate: (templateId: string) => fetchJson<any>(`/api/templates/${templateId}`),
}
