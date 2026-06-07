import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { useAppStore } from '../../state/useAppStore'
import { CloudSettingsPanel } from '../CloudSettingsPanel'
import { CloudUsagePanel } from '../CloudUsagePanel'

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
})
