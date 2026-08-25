import { useState, useEffect } from 'react'
import { fetchWithAuth } from './localRunToken'

export type ServiceStatus = 'ok' | 'error' | 'unavailable' | 'loading' | 'off'
export type PodmanStatus = 'running' | 'stopped' | 'unavailable' | 'loading'

export interface SystemHealth {
  modelName: string
  lmStudioUrl: string
  lmStudio: ServiceStatus
  postgres: ServiceStatus
  stirling: ServiceStatus
  podman: PodmanStatus
  podmanContainers: number
  redis: ServiceStatus
  qdrant: ServiceStatus
  pentestEnabled: boolean
  lastChecked: number | null
}

const POLL_INTERVAL = 30_000

const INITIAL: SystemHealth = {
  modelName: '',
  lmStudioUrl: 'http://127.0.0.1:1234/v1',
  lmStudio: 'loading',
  postgres: 'loading',
  stirling: 'loading',
  podman: 'loading',
  podmanContainers: 0,
  redis: 'off',
  qdrant: 'off',
  pentestEnabled: false,
  lastChecked: null,
}

function parseResponse(data: Record<string, unknown>): SystemHealth {
  const features = (data.features as Record<string, unknown> | undefined) || {}
  return {
    modelName: (data.model_name as string) || '',
    lmStudioUrl: (data.lm_studio_url as string) || 'http://127.0.0.1:1234/v1',
    lmStudio: (data.lm_studio as ServiceStatus) ?? 'error',
    postgres: (data.postgres as ServiceStatus) ?? 'error',
    stirling: (data.stirling as ServiceStatus) ?? 'off',
    podman: (data.podman as PodmanStatus) ?? 'unavailable',
    podmanContainers: (data.podman_containers as number) ?? 0,
    redis: (data.redis as ServiceStatus) ?? 'off',
    qdrant: (data.qdrant as ServiceStatus) ?? 'off',
    pentestEnabled: Boolean(features.pentest_enabled),
    lastChecked: Date.now(),
  }
}

export function useSystemHealth(): SystemHealth {
  const [health, setHealth] = useState<SystemHealth>(INITIAL)

  useEffect(() => {
    let active = true

    const check = async () => {
      try {
        const res = await fetchWithAuth('/api/system-info')
        if (!res.ok || !active) return
        const data = (await res.json()) as Record<string, unknown>
        if (active) {
          setHealth(parseResponse(data))
        }
      } catch {
        /* silently ignore — keep last known state */
      }
    }

    void check()
    const timer = setInterval(() => {
      void check()
    }, POLL_INTERVAL)

    return () => {
      active = false
      clearInterval(timer)
    }
  }, [])

  return health
}
