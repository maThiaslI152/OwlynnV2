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
