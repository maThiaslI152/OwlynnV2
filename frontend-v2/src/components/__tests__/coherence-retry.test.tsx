import { beforeEach, describe, expect, it } from 'vitest'
import { useAppStore } from '../../state/useAppStore'

beforeEach(() => {
  useAppStore.setState(useAppStore.getInitialState(), true)
})

describe('coherence retry indicator state', () => {
  it('starts inactive', () => {
    const state = useAppStore.getState()
    expect(state.coherenceRetryActive).toBe(false)
    expect(state.coherenceRetryAttempt).toBe(0)
    expect(state.coherenceRetryOriginalConfidence).toBeNull()
  })

  it('setCoherenceRetryActive(true) sets attempt and confidence', () => {
    useAppStore.getState().setCoherenceRetryActive(true, 1, 0.22)
    const state = useAppStore.getState()
    expect(state.coherenceRetryActive).toBe(true)
    expect(state.coherenceRetryAttempt).toBe(1)
    expect(state.coherenceRetryOriginalConfidence).toBe(0.22)
  })

  it('setCoherenceRetryActive(false) resets indicator', () => {
    useAppStore.getState().setCoherenceRetryActive(true, 1, 0.22)
    useAppStore.getState().setCoherenceRetryActive(false)
    const state = useAppStore.getState()
    expect(state.coherenceRetryActive).toBe(false)
    expect(state.coherenceRetryAttempt).toBe(0)
    expect(state.coherenceRetryOriginalConfidence).toBeNull()
  })

  it('clearSession resets retry indicator', () => {
    useAppStore.getState().setCoherenceRetryActive(true, 1, 0.22)
    useAppStore.getState().clearSession()
    const state = useAppStore.getState()
    expect(state.coherenceRetryActive).toBe(false)
    expect(state.coherenceRetryAttempt).toBe(0)
    expect(state.coherenceRetryOriginalConfidence).toBeNull()
  })
})
