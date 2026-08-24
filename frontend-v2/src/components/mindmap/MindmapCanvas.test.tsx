import React from 'react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { act, render, screen, waitFor } from '@testing-library/react'

const mockCenterAt = vi.hoisted(() => vi.fn())
const mockZoom = vi.hoisted(() => vi.fn().mockReturnValue(1.4))
const mockZoomToFit = vi.hoisted(() => vi.fn())
const mockD3Force = vi.hoisted(() =>
  vi.fn().mockReturnValue({
    strength: vi.fn(),
    distance: vi.fn(),
  }),
)
const mockGraph2ScreenCoords = vi.hoisted(() => vi.fn().mockReturnValue({ x: 400, y: 300 }))
const latestForceGraphProps = vi.hoisted(() => ({ current: null as Record<string, unknown> | null }))

vi.mock('react-hot-toast', () => ({
  default: {
    error: vi.fn(),
    success: vi.fn(),
  },
}))

vi.mock('../../lib/localRunToken', () => ({
  fetchWithAuth: vi.fn(),
}))

vi.mock('react-force-graph-2d', () => ({
  default: React.forwardRef(function MockForceGraph2D(props: Record<string, unknown>, ref) {
    latestForceGraphProps.current = props
    React.useImperativeHandle(ref, () => ({
      centerAt: mockCenterAt,
      zoom: mockZoom,
      zoomToFit: mockZoomToFit,
      d3Force: mockD3Force,
      graph2ScreenCoords: mockGraph2ScreenCoords,
    }))
    return React.createElement('div', { 'data-testid': 'force-graph' })
  }),
}))

import { fetchWithAuth } from '../../lib/localRunToken'
import { MindmapCanvas } from './MindmapCanvas'

const sampleNodes = [
  { id: 'node-a', title: 'Alpha', mode: 'normal', fx: 50, fy: 80 },
  { id: 'node-b', title: 'Beta', mode: 'normal', fx: 220, fy: 140 },
]

function mockGraphResponse(nodes = sampleNodes) {
  vi.mocked(fetchWithAuth).mockResolvedValue({
    ok: true,
    json: async () => ({ nodes, edges: [] }),
  } as Response)
}

describe('MindmapCanvas focus behavior', () => {
  beforeEach(() => {
    vi.useFakeTimers({ shouldAdvanceTime: true })
    mockCenterAt.mockClear()
    mockZoom.mockClear()
    mockZoomToFit.mockClear()
    mockD3Force.mockClear()
    latestForceGraphProps.current = null
    mockGraphResponse()
  })

  afterEach(() => {
    vi.useRealTimers()
    vi.clearAllMocks()
  })

  it('zooms to fit when graph loads without an active node', async () => {
    render(<MindmapCanvas onSelectNode={() => {}} />)

    await waitFor(() => {
      expect(screen.getByTestId('force-graph')).toBeTruthy()
    })

    await act(async () => {
      await vi.advanceTimersByTimeAsync(350)
    })

    expect(mockZoomToFit).toHaveBeenCalledWith(400, 60)
    expect(mockCenterAt).not.toHaveBeenCalled()
    expect(mockZoom).not.toHaveBeenCalled()
  })

  it('centers and zooms when graph loads with activeNodeId', async () => {
    render(<MindmapCanvas activeNodeId="node-b" onSelectNode={() => {}} />)

    await waitFor(() => {
      expect(screen.getByTestId('force-graph')).toBeTruthy()
    })

    await act(async () => {
      await vi.advanceTimersByTimeAsync(350)
    })

    expect(mockCenterAt).toHaveBeenCalledWith(220, 140, 400)
    expect(mockZoom).toHaveBeenCalledWith(1.4, 400)
    expect(mockZoomToFit).not.toHaveBeenCalled()
  })

  it('auto-focuses when activeNodeId changes', async () => {
    const { rerender } = render(
      <MindmapCanvas activeNodeId="node-a" onSelectNode={() => {}} />,
    )

    await waitFor(() => {
      expect(screen.getByTestId('force-graph')).toBeTruthy()
    })

    await act(async () => {
      await vi.advanceTimersByTimeAsync(350)
    })

    mockCenterAt.mockClear()
    mockZoom.mockClear()

    rerender(<MindmapCanvas activeNodeId="node-b" onSelectNode={() => {}} />)

    await act(async () => {
      await vi.advanceTimersByTimeAsync(50)
    })

    expect(mockCenterAt).toHaveBeenCalledWith(220, 140, 400)
    expect(mockZoom).toHaveBeenCalledWith(1.4, 400)
  })

  it('skips auto-focus after recent user pan', async () => {
    const { rerender } = render(
      <MindmapCanvas activeNodeId="node-a" onSelectNode={() => {}} />,
    )

    await waitFor(() => {
      expect(latestForceGraphProps.current).toBeTruthy()
    })

    // Let load + async focus finish, then flush unlock timeouts scheduled after awaits
    await act(async () => {
      await vi.advanceTimersByTimeAsync(1200)
    })
    await act(async () => {
      await Promise.resolve()
      await vi.advanceTimersByTimeAsync(600)
    })

    mockCenterAt.mockClear()
    mockZoom.mockClear()

    const panAt = 1_700_000_000_000
    vi.setSystemTime(panAt)

    const onZoom = latestForceGraphProps.current?.onZoom as (() => void) | undefined
    const onBackgroundClick = latestForceGraphProps.current?.onBackgroundClick as
      | (() => void)
      | undefined
    expect(onZoom).toBeTypeOf('function')
    act(() => {
      onBackgroundClick?.()
      onZoom?.()
    })

    rerender(<MindmapCanvas activeNodeId="node-b" onSelectNode={() => {}} />)

    await act(async () => {
      vi.setSystemTime(panAt + 50)
      await vi.advanceTimersByTimeAsync(50)
      await Promise.resolve()
    })

    expect(mockCenterAt).not.toHaveBeenCalled()
    expect(mockZoom).not.toHaveBeenCalled()
  })

  it('branch picker selection forces focus despite recent pan', async () => {
    render(<MindmapCanvas activeNodeId="node-a" onSelectNode={() => {}} />)

    await waitFor(() => {
      expect(screen.getByTestId('branch-option-node-b')).toBeTruthy()
    })

    await act(async () => {
      await vi.advanceTimersByTimeAsync(900)
    })

    const onZoom = latestForceGraphProps.current?.onZoom as (() => void) | undefined
    act(() => {
      onZoom?.()
    })

    mockCenterAt.mockClear()
    mockZoom.mockClear()

    const branchBtn = screen.getByTestId('branch-option-node-b')
    act(() => {
      branchBtn.click()
    })

    await act(async () => {
      await vi.advanceTimersByTimeAsync(50)
    })

    expect(mockCenterAt).toHaveBeenCalledWith(220, 140, 400)
    expect(mockZoom).toHaveBeenCalledWith(1.4, 400)
  })
})
