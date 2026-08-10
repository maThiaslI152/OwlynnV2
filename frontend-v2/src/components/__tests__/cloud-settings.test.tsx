import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { useAppStore } from '../../state/useAppStore'
import { parseCloudUsagePayload } from '../../lib/cloudUsage'
import { CloudSettingsPanel } from '../shared/CloudSettingsPanel'
import { CloudUsagePanel } from '../shared/CloudUsagePanel'

vi.mock('../../lib/localRunToken', () => ({
  getLocalRunToken: vi.fn().mockResolvedValue('test-token'),
  fetchWithAuth: vi.fn().mockImplementation((url: string, init?: RequestInit) => fetch(url, init)),
}))

beforeEach(() => {
  useAppStore.setState(useAppStore.getInitialState(), true)
})

afterEach(() => {
  vi.restoreAllMocks()
})

describe('CloudSettingsPanel', () => {
  it('loads and saves cloud escalation toggle', async () => {
    const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
      if (url === '/api/unified-settings' && !init) {
        return {
          ok: true,
          json: async () => ({
            cloud_model_tier: 'flash',
            cloud_thinking_mode: 'auto',
            cloud_reasoning_effort: 'high',
            cloud_escalation_enabled: true,
          }),
        }
      }
      if (url === '/api/unified-settings' && init?.method === 'PUT') {
        return { ok: true, json: async () => ({ status: 'ok' }) }
      }
      if (url === '/api/cloud-status') {
        return {
          ok: true,
          json: async () => ({
            available: true,
            key_valid: true,
            model: 'deepseek-v4-flash',
            error: '',
          }),
        }
      }
      return { ok: false, json: async () => ({}) }
    })
    vi.stubGlobal('fetch', fetchMock)

    render(<CloudSettingsPanel />)
    await waitFor(() => {
      expect(screen.getByTestId('cloud-escalation-enabled')).toBeTruthy()
    })

    fireEvent.change(screen.getByTestId('cloud-escalation-enabled'), {
      target: { value: 'off' },
    })

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        '/api/unified-settings',
        expect.objectContaining({
          method: 'PUT',
          body: JSON.stringify({ cloud_escalation_enabled: false }),
        })
      )
    })
  })

  it('disables reasoning effort when thinking mode is never', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async (url: string) => {
        if (url === '/api/unified-settings') {
          return {
            ok: true,
            json: async () => ({
              cloud_model_tier: 'pro',
              cloud_thinking_mode: 'never',
              cloud_reasoning_effort: 'max',
              cloud_escalation_enabled: true,
            }),
          }
        }
        return { ok: false, json: async () => ({}) }
      })
    )

    render(<CloudSettingsPanel />)
    await waitFor(() => {
      const effort = screen.getByTestId('cloud-reasoning-effort') as HTMLSelectElement
      expect(effort.disabled).toBe(true)
    })
  })
})

describe('parseCloudUsagePayload', () => {
  it('merges /api/usage session tokens with cost tracker fields', () => {
    const parsed = parseCloudUsagePayload({
      session: {
        prompt_tokens: 50000,
        completion_tokens: 1200,
        total_tokens: 51200,
      },
      cost: {
        prompt_tokens: 48000,
        completion_tokens: 1100,
        total_tokens: 49100,
        total_calls: 7,
        estimated_cost_usd: 0.042,
        cache_hit_ratio: 0.25,
      },
      budget: { daily_token_limit: 500000, used_tokens: 51200, used_pct: 0.1 },
    })
    expect(parsed.session.total_calls).toBe(7)
    expect(parsed.session.estimated_cost_usd).toBe(0.042)
    expect(parsed.session.prompt_tokens).toBe(50000)
  })
})

describe('CloudUsagePanel', () => {
  it('shows session cost and budget bar', () => {
    useAppStore.setState({
      cloudUsage: {
        session: {
          prompt_tokens: 12000,
          completion_tokens: 800,
          prompt_cache_hit_tokens: 6000,
          prompt_cache_miss_tokens: 6000,
          reasoning_tokens: 0,
          total_tokens: 12800,
          cache_hit_ratio: 0.5,
          total_calls: 2,
          failed_calls: 0,
          estimated_cost_usd: 0.0123,
          elapsed_seconds: 42,
        },
        budget: {
          daily_token_limit: 500000,
          used_tokens: 12800,
          remaining_tokens: 487200,
          used_pct: 0.0256,
        },
        lastTurn: {
          prompt_tokens: 5000,
          completion_tokens: 400,
          estimated_cost_usd: 0.004,
          model_tier: 'flash',
        },
      },
    })

    render(<CloudUsagePanel />)
    expect(screen.getByTestId('cloud-usage-cost').textContent).toContain('$')
    expect(screen.getByTestId('cloud-usage-budget-fill')).toBeTruthy()
  })

  it('shows empty state when no usage', () => {
    render(<CloudUsagePanel />)
    expect(screen.getByTestId('cloud-usage-empty')).toBeTruthy()
  })

  it('shows session totals, daily budget, call count, and last call log', () => {
    useAppStore.setState({
      cloudUsage: {
        session: {
          prompt_tokens: 52799,
          completion_tokens: 5296,
          prompt_cache_hit_tokens: 0,
          prompt_cache_miss_tokens: 52799,
          reasoning_tokens: 0,
          total_tokens: 58095,
          cache_hit_ratio: 0,
          total_calls: 7,
          failed_calls: 0,
          estimated_cost_usd: 0.010019,
          elapsed_seconds: 2524,
        },
        budget: {
          daily_token_limit: 500000,
          used_tokens: 67116,
          remaining_tokens: 432884,
          used_pct: 0.134,
        },
        lastTurn: {
          prompt_tokens: 10630,
          completion_tokens: 1397,
          estimated_cost_usd: 0.001879,
          model_tier: 'flash',
        },
      },
    })

    render(<CloudUsagePanel />)
    expect(screen.getByTestId('cloud-usage-cost').textContent).toBe('$0.0100')
    expect(screen.getByText(/in 52\.8k · out 5\.3k/)).toBeTruthy()
    expect(screen.getByText(/67\.1k \/ 500\.0k daily \(13%\)/)).toBeTruthy()
    expect(screen.getByText('7 calls')).toBeTruthy()
    expect(screen.getByText(/\$0\.001879 · in 10\.6k · out 1\.4k · flash/)).toBeTruthy()
  })
})
