import { beforeEach, describe, expect, it } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { useAppStore } from '../../state/useAppStore'
import { CloudUsageChip } from '../shared/CloudUsageChip'

beforeEach(() => {
  useAppStore.setState(useAppStore.getInitialState(), true)
})

describe('CloudUsageChip', () => {
  it('opens popover with context breakdown on click', () => {
    useAppStore.setState({
      cloudUsage: {
        session: {
          prompt_tokens: 12000,
          completion_tokens: 800,
          prompt_cache_hit_tokens: 0,
          prompt_cache_miss_tokens: 12000,
          reasoning_tokens: 0,
          total_tokens: 12800,
          cache_hit_ratio: 0,
          total_calls: 1,
          failed_calls: 0,
          estimated_cost_usd: 0.01,
          elapsed_seconds: 10,
        },
        budget: {
          daily_token_limit: 500000,
          used_tokens: 12800,
          remaining_tokens: 487200,
          used_pct: 0.0256,
        },
        lastTurn: null,
      },
      contextBreakdown: {
        max_context: 1_048_576,
        categories: {
          system: 2000,
          conversation: 3000,
          tools: 7000,
          output: 800,
          reasoning: 0,
        },
        category_pct: {
          system: 0.2,
          conversation: 0.3,
          tools: 0.7,
          output: 0.1,
          reasoning: 0,
        },
        input_estimated: 12000,
        total_used: 12800,
        used_pct: 1.2,
      },
    })

    render(<CloudUsageChip />)
    fireEvent.click(screen.getByTestId('cloud-usage-chip'))
    expect(screen.getByTestId('cloud-usage-popover')).toBeTruthy()
    expect(screen.getByTestId('context-breakdown')).toBeTruthy()
    expect(screen.getByText('System')).toBeTruthy()
    expect(screen.getByText('Tools')).toBeTruthy()
  })

  it('renders nothing without session calls', () => {
    const { container } = render(<CloudUsageChip />)
    expect(container.firstChild).toBeNull()
  })
})
