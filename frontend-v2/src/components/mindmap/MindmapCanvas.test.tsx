import React from 'react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'

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
const mockAppStoreState = vi.hoisted(() => ({ activeEngagementId: null as string | null }))

vi.mock('react-hot-toast', () => ({
  default: {
    error: vi.fn(),
    success: vi.fn(),
  },
}))

vi.mock('../../lib/localRunToken', () => ({
  fetchWithAuth: vi.fn(),
}))

vi.mock('../../state/useAppStore', () => ({
  useAppStore: (selector: (state: { activeEngagementId: string | null }) => unknown) =>
    selector(mockAppStoreState),
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
import toast from 'react-hot-toast'
import { MindmapCanvas } from './MindmapCanvas'
import {
  branchRowOpacity,
  groupBranchNodes,
  linkParticleCount,
  mergeRevivedNode,
  nodeDisplayAlpha,
  shouldRadialDrift,
} from './organicMap'

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
    mockAppStoreState.activeEngagementId = null
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

  it('loads pentest graph from engagement endpoint', async () => {
    mockAppStoreState.activeEngagementId = 'eng-123'
    vi.mocked(fetchWithAuth).mockResolvedValue({
      ok: true,
      json: async () => ({
        graph: {
          nodes: [{ id: 'task-1', title: 'Scan target', mode: 'pentest' }],
          edges: [],
        },
      }),
    } as Response)

    render(<MindmapCanvas activeMode="pentest" onSelectNode={() => {}} />)

    await waitFor(() => {
      expect(fetchWithAuth).toHaveBeenCalledWith('/api/pentest/engagements/eng-123/graph')
    })

    expect(screen.getByRole('button', { name: /new branch/i }).hasAttribute('disabled')).toBe(true)
    expect(screen.getByRole('button', { name: /new thread/i }).hasAttribute('disabled')).toBe(true)
    expect(screen.queryByTestId('delete-branch-task-1')).toBeNull()
  })
})

function parsePostBody() {
  const post = vi.mocked(fetchWithAuth).mock.calls.find(([, init]) => init?.method === 'POST')
  expect(post).toBeTruthy()
  return JSON.parse(String(post![1]!.body)) as Record<string, unknown>
}

describe('MindmapCanvas thread lifecycle', () => {
  beforeEach(() => {
    vi.useFakeTimers({ shouldAdvanceTime: true })
    mockCenterAt.mockClear()
    mockZoom.mockClear()
    mockZoomToFit.mockClear()
    mockD3Force.mockClear()
    latestForceGraphProps.current = null
    mockAppStoreState.activeEngagementId = null
    mockGraphResponse()
  })

  afterEach(() => {
    vi.useRealTimers()
    vi.clearAllMocks()
  })

  it('creates a root thread without parent_id and selects it', async () => {
    const onSelectNode = vi.fn()
    const created = { id: 'thread-root', title: 'Root Thread', mode: 'normal' }
    vi.spyOn(window, 'prompt').mockReturnValue('Root Thread')
    vi.mocked(fetchWithAuth).mockImplementation(async (url, init) => {
      if (init?.method === 'POST') {
        return { ok: true, json: async () => ({ node: created }) } as Response
      }
      return { ok: true, json: async () => ({ nodes: sampleNodes, edges: [] }) } as Response
    })

    render(<MindmapCanvas onSelectNode={onSelectNode} />)

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /new thread/i })).toBeTruthy()
    })

    await act(async () => {
      screen.getByRole('button', { name: /new thread/i }).click()
    })

    await waitFor(() => {
      const body = parsePostBody()
      expect(body.title).toBe('Root Thread')
      expect(body).not.toHaveProperty('parent_id')
    })
    await waitFor(() => {
      expect(onSelectNode).toHaveBeenCalledWith(created)
    })
  })

  it('creates a child branch with parent_id set to the active node', async () => {
    const onSelectNode = vi.fn()
    const created = { id: 'thread-child', title: 'Investigation', mode: 'normal' }
    vi.spyOn(window, 'prompt').mockReturnValue('Investigation')
    vi.mocked(fetchWithAuth).mockImplementation(async (_url, init) => {
      if (init?.method === 'POST') {
        return { ok: true, json: async () => ({ node: created }) } as Response
      }
      return { ok: true, json: async () => ({ nodes: sampleNodes, edges: [] }) } as Response
    })

    render(<MindmapCanvas activeNodeId="node-a" onSelectNode={onSelectNode} />)

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /new branch/i })).toBeTruthy()
    })

    await act(async () => {
      screen.getByRole('button', { name: /new branch/i }).click()
    })

    await waitFor(() => {
      const body = parsePostBody()
      expect(body.parent_id).toBe('node-a')
      expect(body.title).toBe('Investigation')
    })
  })

  it('deletes a branch after confirm and refreshes the graph', async () => {
    vi.spyOn(window, 'confirm').mockReturnValue(true)
    const remaining = [sampleNodes[0]]
    vi.mocked(fetchWithAuth).mockImplementation(async (url, init) => {
      if (init?.method === 'DELETE') {
        return { ok: true, json: async () => ({ status: 'ok' }) } as Response
      }
      const nodes = String(url).includes('/api/graph/data') && vi.mocked(fetchWithAuth).mock.calls.some((c) => c[1]?.method === 'DELETE')
        ? remaining
        : sampleNodes
      return { ok: true, json: async () => ({ nodes, edges: [] }) } as Response
    })

    render(<MindmapCanvas activeNodeId="node-a" onSelectNode={() => {}} />)

    await waitFor(() => {
      expect(screen.getByTestId('delete-branch-node-b')).toBeTruthy()
    })

    await act(async () => {
      screen.getByTestId('delete-branch-node-b').click()
    })

    await waitFor(() => {
      expect(fetchWithAuth).toHaveBeenCalledWith('/api/graph/nodes/node-b', { method: 'DELETE' })
    })
    await waitFor(() => {
      expect(toast.success).toHaveBeenCalled()
    })
  })

  it('does not delete when confirm is cancelled', async () => {
    vi.spyOn(window, 'confirm').mockReturnValue(false)
    render(<MindmapCanvas activeNodeId="node-a" onSelectNode={() => {}} />)

    await waitFor(() => {
      expect(screen.getByTestId('delete-branch-node-b')).toBeTruthy()
    })

    await act(async () => {
      screen.getByTestId('delete-branch-node-b').click()
    })

    expect(vi.mocked(fetchWithAuth).mock.calls.some(([, init]) => init?.method === 'DELETE')).toBe(false)
  })

  it('selects another thread when the active node is deleted', async () => {
    const onSelectNode = vi.fn()
    const onNewChat = vi.fn()
    vi.spyOn(window, 'confirm').mockReturnValue(true)
    vi.mocked(fetchWithAuth).mockImplementation(async (_url, init) => {
      if (init?.method === 'DELETE') {
        return { ok: true, json: async () => ({ status: 'ok' }) } as Response
      }
      return { ok: true, json: async () => ({ nodes: sampleNodes, edges: [] }) } as Response
    })

    render(
      <MindmapCanvas activeNodeId="node-a" onSelectNode={onSelectNode} onNewChat={onNewChat} />,
    )

    await waitFor(() => {
      expect(screen.getByTestId('delete-branch-node-a')).toBeTruthy()
    })

    await act(async () => {
      screen.getByTestId('delete-branch-node-a').click()
    })

    await waitFor(() => {
      expect(onSelectNode).toHaveBeenCalled()
    })
    expect(onNewChat).not.toHaveBeenCalled()
    const selected = onSelectNode.mock.calls[0][0] as { id: string }
    expect(selected.id).toBe('node-b')
  })

  it('calls onNewChat when the last active thread is deleted', async () => {
    const onNewChat = vi.fn()
    vi.spyOn(window, 'confirm').mockReturnValue(true)
    const onlyNode = [sampleNodes[0]]
    vi.mocked(fetchWithAuth).mockImplementation(async (_url, init) => {
      if (init?.method === 'DELETE') {
        return { ok: true, json: async () => ({ status: 'ok' }) } as Response
      }
      return { ok: true, json: async () => ({ nodes: onlyNode, edges: [] }) } as Response
    })

    render(<MindmapCanvas activeNodeId="node-a" onSelectNode={() => {}} onNewChat={onNewChat} />)

    await waitFor(() => {
      expect(screen.getByTestId('delete-branch-node-a')).toBeTruthy()
    })

    await act(async () => {
      screen.getByTestId('delete-branch-node-a').click()
    })

    await waitFor(() => {
      expect(onNewChat).toHaveBeenCalled()
    })
  })
})

describe('organic map helpers', () => {
  it('fades dormant nodes unless searching or active', () => {
    const dormant = {
      id: 'd1',
      is_dormant: true,
      fade_alpha: 0.35,
      visual_mode: 'dormant',
    }
    expect(nodeDisplayAlpha(dormant, { isActive: false, searching: false })).toBe(0.35)
    expect(nodeDisplayAlpha(dormant, { isActive: false, searching: true })).toBe(1)
    expect(nodeDisplayAlpha(dormant, { isActive: true, searching: false })).toBe(1)
    expect(branchRowOpacity(dormant, { isActive: false, searching: false })).toBeLessThan(1)
    expect(branchRowOpacity(dormant, { isActive: false, searching: true })).toBe(1)
  })

  it('only radial-drifts when allowed and unplaced', () => {
    expect(
      shouldRadialDrift({
        id: 'a',
        allow_radial_drift: true,
        radial_tier: 2,
      }),
    ).toBe(true)
    expect(
      shouldRadialDrift({
        id: 'b',
        allow_radial_drift: true,
        fx: 10,
        fy: 20,
      }),
    ).toBe(false)
    expect(
      shouldRadialDrift({
        id: 'c',
        allow_radial_drift: false,
      }),
    ).toBe(false)
  })

  it('reduces particle count on dormant links', () => {
    expect(
      linkParticleCount({ pentest: false, searching: false, dormantLink: true }),
    ).toBe(0)
    expect(
      linkParticleCount({ pentest: false, searching: true, dormantLink: true }),
    ).toBe(2)
  })

  it('groups branches by cluster and de-emphasizes dormant order', () => {
    const groups = groupBranchNodes([
      {
        id: '1',
        title: 'Old',
        topic_cluster_id: 'c1',
        topic_label: 'Auth',
        is_dormant: true,
        importance_score: 0.2,
      },
      {
        id: '2',
        title: 'Fresh',
        topic_cluster_id: 'c1',
        topic_label: 'Auth',
        is_dormant: false,
        importance_score: 0.9,
      },
      { id: '3', title: 'Lone', is_dormant: false },
    ])
    expect(groups[0].id).toBe('c1')
    expect(groups[0].nodes.map((n) => n.id)).toEqual(['2', '1'])
    expect(groups.some((g) => g.id === '_ungrouped')).toBe(true)
  })

  it('mergeRevivedNode brightens without dropping layout pins', () => {
    const merged = mergeRevivedNode(
      {
        id: 'x',
        is_dormant: true,
        fade_alpha: 0.3,
        fx: 12,
        fy: 34,
        allow_radial_drift: true,
      },
      {
        id: 'x',
        is_dormant: false,
        fade_alpha: 1,
        canvas_x: null,
        canvas_y: null,
      },
    )
    expect(merged.is_dormant).toBe(false)
    expect(merged.fade_alpha).toBe(1)
    expect(merged.fx).toBe(12)
    expect(merged.fy).toBe(34)
    expect(merged.allow_radial_drift).toBe(false)
  })
})

describe('MindmapCanvas organic decay and search', () => {
  const dormantNodes = [
    {
      id: 'node-active',
      title: 'Active Auth',
      mode: 'normal',
      fx: 50,
      fy: 80,
      topic_cluster_id: 'auth-cluster',
      topic_label: 'Auth',
      is_dormant: false,
      fade_alpha: 1,
      visual_mode: 'active',
    },
    {
      id: 'node-dormant',
      title: 'Sleepy Auth',
      mode: 'normal',
      fx: 220,
      fy: 140,
      topic_cluster_id: 'auth-cluster',
      topic_label: 'Auth',
      is_dormant: true,
      fade_alpha: 0.32,
      visual_mode: 'dormant',
      allow_radial_drift: false,
    },
  ]

  beforeEach(() => {
    vi.useFakeTimers({ shouldAdvanceTime: true })
    mockCenterAt.mockClear()
    mockZoom.mockClear()
    mockZoomToFit.mockClear()
    mockD3Force.mockClear()
    latestForceGraphProps.current = null
    mockAppStoreState.activeEngagementId = null
    mockGraphResponse(dormantNodes)
  })

  afterEach(() => {
    vi.useRealTimers()
    vi.clearAllMocks()
  })

  it('de-emphasizes dormant branches in the list', async () => {
    render(<MindmapCanvas onSelectNode={() => {}} />)

    await waitFor(() => {
      expect(screen.getByTestId('branch-option-node-dormant')).toBeTruthy()
    })

    const dormantBtn = screen.getByTestId('branch-option-node-dormant')
    expect(dormantBtn.getAttribute('data-dormant')).toBe('true')
    expect(dormantBtn.textContent).toMatch(/dormant/i)
    const row = dormantBtn.parentElement
    expect(row?.style.opacity).not.toBe('')
    expect(Number(row?.style.opacity)).toBeLessThan(1)
    expect(screen.getByTestId('cluster-group-auth-cluster')).toBeTruthy()
  })

  it('revives a dormant node on select via GET', async () => {
    const onSelectNode = vi.fn()
    const revived = {
      id: 'node-dormant',
      title: 'Sleepy Auth',
      mode: 'normal',
      is_dormant: false,
      fade_alpha: 1,
      dormancy_score: 0,
      visual_mode: 'active',
    }
    vi.mocked(fetchWithAuth).mockImplementation(async (url, init) => {
      if (String(url).includes('/api/graph/nodes/node-dormant') && !init?.method) {
        return { ok: true, json: async () => ({ node: revived }) } as Response
      }
      return { ok: true, json: async () => ({ nodes: dormantNodes, edges: [] }) } as Response
    })

    render(<MindmapCanvas onSelectNode={onSelectNode} />)

    await waitFor(() => {
      expect(screen.getByTestId('branch-option-node-dormant')).toBeTruthy()
    })

    await act(async () => {
      screen.getByTestId('branch-option-node-dormant').click()
    })

    await waitFor(() => {
      expect(fetchWithAuth).toHaveBeenCalledWith('/api/graph/nodes/node-dormant')
    })
    await waitFor(() => {
      expect(onSelectNode).toHaveBeenCalled()
    })
    const selected = onSelectNode.mock.calls[0][0] as { is_dormant?: boolean; fade_alpha?: number }
    expect(selected.is_dormant).toBe(false)
    expect(selected.fade_alpha).toBe(1)
  })

  it('passes search= to the graph API and restores dormant row opacity', async () => {
    render(<MindmapCanvas onSelectNode={() => {}} />)

    await waitFor(() => {
      expect(screen.getByPlaceholderText(/search mindmap/i)).toBeTruthy()
    })

    const input = screen.getByPlaceholderText(/search mindmap/i)
    await act(async () => {
      fireEvent.change(input, { target: { value: 'Sleepy' } })
    })

    await act(async () => {
      await vi.advanceTimersByTimeAsync(350)
    })

    await waitFor(() => {
      const urls = vi.mocked(fetchWithAuth).mock.calls.map((c) => String(c[0]))
      expect(urls.some((u) => u.includes('search=Sleepy'))).toBe(true)
    })

    const dormantBtn = screen.getByTestId('branch-option-node-dormant')
    const row = dormantBtn.parentElement
    expect(Number(row?.style.opacity || '1')).toBe(1)
  })

  it('Focus recent reloads with show_dormant=false', async () => {
    render(<MindmapCanvas onSelectNode={() => {}} />)

    await waitFor(() => {
      expect(screen.getByTestId('focus-recent')).toBeTruthy()
    })

    await act(async () => {
      screen.getByTestId('focus-recent').click()
    })

    await waitFor(() => {
      const urls = vi.mocked(fetchWithAuth).mock.calls.map((c) => String(c[0]))
      expect(urls.some((u) => u.includes('show_dormant=false'))).toBe(true)
    })
  })

  it('zeros link particles for dormant endpoints', async () => {
    render(<MindmapCanvas onSelectNode={() => {}} />)

    await waitFor(() => {
      expect(latestForceGraphProps.current).toBeTruthy()
    })

    const particles = latestForceGraphProps.current?.linkDirectionalParticles as
      | ((link: { source: string; target: string }) => number)
      | undefined
    expect(particles).toBeTypeOf('function')
    expect(particles!({ source: 'node-dormant', target: 'node-active' })).toBe(0)
  })
})
