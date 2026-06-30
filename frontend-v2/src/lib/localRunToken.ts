let cachedToken: string | null = null

/** Fetch loopback-only token for privileged local API routes (notebook run). */
export async function getLocalRunToken(): Promise<string> {
  if (cachedToken) return cachedToken
  const res = await fetch('/api/local-run-token')
  if (!res.ok) {
    throw new Error('Could not obtain local run token')
  }
  const data = (await res.json()) as { token?: string }
  if (!data.token) {
    throw new Error('Local run token missing in response')
  }
  cachedToken = data.token
  return cachedToken
}

export function getCachedToken(): string | null {
  return cachedToken
}

/** Fetch with X-Owlynn-Run-Token header for authenticated API calls. */
export async function fetchWithAuth(url: string, init?: RequestInit): Promise<Response> {
  const token = await getLocalRunToken()
  const headers = new Headers(init?.headers)
  headers.set('X-Owlynn-Run-Token', token)
  return fetch(url, { ...init, headers })
}
