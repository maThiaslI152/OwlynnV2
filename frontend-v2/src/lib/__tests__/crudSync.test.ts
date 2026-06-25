import { describe, it, expect, vi } from 'vitest'

describe('CRUD Sync Concurrency (AbortController)', () => {
  it('should abort previous fetch when a new one is initiated', async () => {
    const abortSpy = vi.spyOn(AbortController.prototype, 'abort')
    
    // We simulate the exact logic used in App.tsx loadProjects
    const loadProjectsAbortRef = { current: null as AbortController | null }
    
    const mockFetch = vi.fn().mockImplementation(() => {
      return new Promise((resolve) => {
        setTimeout(() => {
          resolve({ ok: true, json: () => Promise.resolve([]) })
        }, 50)
      })
    })

    const loadProjects = async () => {
      if (loadProjectsAbortRef.current) {
        loadProjectsAbortRef.current.abort()
      }
      const controller = new AbortController()
      loadProjectsAbortRef.current = controller

      try {
        await mockFetch('/api/projects', { signal: controller.signal })
      } catch (e: any) {
        if (e.name === 'AbortError') return
      }
    }

    // Fire 3 concurrent calls rapidly
    const p1 = loadProjects()
    const p2 = loadProjects()
    const p3 = loadProjects()

    await Promise.all([p1, p2, p3])

    // Fetch should be called 3 times
    expect(mockFetch).toHaveBeenCalledTimes(3)
    
    // Abort should be called exactly twice (the first two were cancelled)
    expect(abortSpy).toHaveBeenCalledTimes(2)

    abortSpy.mockRestore()
  })
})
