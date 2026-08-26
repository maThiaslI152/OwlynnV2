import { useState, useEffect, useRef } from 'react'
import toast from 'react-hot-toast'
import { fetchWithAuth } from './localRunToken'

export type ServiceStatus = 'ok' | 'error' | 'unavailable' | 'loading' | 'off' | 'degraded'
export type PodmanStatus = 'running' | 'stopped' | 'unavailable' | 'loading'
export type CheckpointerBackend = 'postgres' | 'memory' | 'unknown'

export interface SystemHealth {
  modelName: string
  lmStudioUrl: string
  lmStudio: ServiceStatus
  postgres: ServiceStatus
  checkpointer: CheckpointerBackend
  stirling: ServiceStatus
  podman: PodmanStatus
  podmanContainers: number
  pentestEnabled: boolean
  lastChecked: number | null
}

const POLL_INTERVAL = 30_000

const INITIAL: SystemHealth = {
  modelName: '',
  lmStudioUrl: 'http://127.0.0.1:1234/v1',
  lmStudio: 'loading',
  postgres: 'loading',
  checkpointer: 'unknown',
  stirling: 'loading',
  podman: 'loading',
  podmanContainers: 0,
  pentestEnabled: false,
  lastChecked: null,
}

function parseResponse(data: Record<string, unknown>): SystemHealth {
  const features = (data.features as Record<string, unknown> | undefined) || {}
  const cp = data.checkpointer
  return {
    modelName: (data.model_name as string) || '',
    lmStudioUrl: (data.lm_studio_url as string) || 'http://127.0.0.1:1234/v1',
    lmStudio: (data.lm_studio as ServiceStatus) ?? 'error',
    postgres: (data.postgres as ServiceStatus) ?? 'error',
    checkpointer:
      cp === 'postgres' || cp === 'memory' ? cp : 'unknown',
    stirling: (data.stirling as ServiceStatus) ?? 'off',
    podman: (data.podman as PodmanStatus) ?? 'unavailable',
    podmanContainers: (data.podman_containers as number) ?? 0,
    pentestEnabled: Boolean(features.pentest_enabled),
    lastChecked: Date.now(),
  }
}

function isPostgresDegraded(status: ServiceStatus): boolean {
  return status === 'degraded' || status === 'error'
}

export function useSystemHealth(): SystemHealth {
  const [health, setHealth] = useState<SystemHealth>(INITIAL)
  const prevPostgres = useRef<ServiceStatus>('loading')
  const toastedDegraded = useRef(false)

  useEffect(() => {
    let active = true

    const check = async () => {
      try {
        const res = await fetchWithAuth('/api/system-info')
        if (!res.ok || !active) return
        const data = (await res.json()) as Record<string, unknown>
        if (!active) return
        const next = parseResponse(data)
        setHealth(next)

        const prev = prevPostgres.current
        const cur = next.postgres
        prevPostgres.current = cur

        if (isPostgresDegraded(cur) && !isPostgresDegraded(prev)) {
          if (!toastedDegraded.current) {
            toastedDegraded.current = true
            toast(
              'Postgres degraded — memory/history may not persist',
              { duration: 6000, id: 'postgres-degraded' },
            )
          }
        } else if (cur === 'ok' && isPostgresDegraded(prev)) {
          toastedDegraded.current = false
          toast.success('Postgres recovered — memory online again', {
            id: 'postgres-recovered',
            duration: 4000,
          })
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
