import React, { useEffect, useState, useRef, useCallback } from 'react'
import ForceGraph2D, { type ForceGraphMethods } from 'react-force-graph-2d'
import { Sparkles, Shield, GraduationCap, Plus, RefreshCw, Maximize2, GitBranch, Trash2 } from 'lucide-react'
import { fetchWithAuth } from '../../lib/localRunToken'
import { useAppStore } from '../../state/useAppStore'
import toast from 'react-hot-toast'
import {
  branchRowOpacity,
  createClusterCohesionForce,
  createDormancyRadialForce,
  groupBranchNodes,
  hexToRgba,
  linkIsDormant,
  linkParticleCount,
  mergeRevivedNode,
  nodeDisplayAlpha,
} from './organicMap'

export interface GraphNode {
  id: string
  title: string
  summary?: string
  mode: 'normal' | 'pentest' | 'study' | string
  scenario_id?: string | null
  engagement_id?: string | null
  course_id?: string | null
  status?: string
  tags?: string[]
  canvas_x?: number | null
  canvas_y?: number | null
  pinned?: boolean
  /** Backend dormancy/cluster fields (optional until graph API ships them). */
  is_dormant?: boolean
  fade_alpha?: number
  dormancy_score?: number
  importance_score?: number
  topic_cluster_id?: string | null
  topic_label?: string | null
  visual_mode?: string
  radial_tier?: number
  allow_radial_drift?: boolean
  radial_multiplier?: number
  last_active_at?: number
  x?: number
  y?: number
  fx?: number
  fy?: number
  vx?: number
  vy?: number
}

export interface GraphEdge {
  id: number | string
  source: string | GraphNode
  target: string | GraphNode
  relation: string
  weight?: number
  auto_generated?: boolean
}

interface MindmapCanvasProps {
  activeNodeId?: string | null
  activeMode?: 'normal' | 'pentest' | 'study' | string
  onSelectNode: (node: GraphNode) => void
  /** Clear/start a local session when the last active thread is deleted. */
  onNewChat?: () => void
  className?: string
  /**
   * `auto` — hide branches until the cursor nears the left edge (graph views).
   * `docked` — keep branches always visible (chat-only layout).
   */
  branchSidebarMode?: 'auto' | 'docked'
  /** When false, only the branches UI is shown (no force-graph canvas). */
  showGraph?: boolean
}

interface FocusNodeOptions {
  /** Bypass the user-pan debounce (clicks, programmatic post-create). */
  force?: boolean
}

const FOCUS_ZOOM = 1.4
const FOCUS_ANIM_MS = 400
const FOCUS_RETRY_MAX_MS = 500
const USER_PAN_DEBOUNCE_MS = 3000

function resolveNodeCoords(node: GraphNode): { cx?: number; cy?: number } {
  const cx = node.fx ?? node.x
  const cy = node.fy ?? node.y
  return {
    cx: typeof cx === 'number' ? cx : undefined,
    cy: typeof cy === 'number' ? cy : undefined,
  }
}

async function waitForNodeCoords(node: GraphNode, maxMs = FOCUS_RETRY_MAX_MS): Promise<{ cx: number; cy: number } | null> {
  const start = Date.now()
  while (Date.now() - start < maxMs) {
    const { cx, cy } = resolveNodeCoords(node)
    if (typeof cx === 'number' && typeof cy === 'number') {
      return { cx, cy }
    }
    await new Promise<void>((resolve) => {
      requestAnimationFrame(() => resolve())
    })
  }
  return null
}

// Coggle Mindmap Branch Colors for Normal & Study modes
const COGGLE_COLORS = [
  '#84cc16', // Lime green
  '#eab308', // Sunshine yellow
  '#f97316', // Coral orange
  '#ec4899', // Berry pink
  '#06b6d4', // Cyan
  '#a855f7', // Lavender purple
  '#3b82f6', // Bright blue
  '#10b981', // Emerald
]

// Attack Graph Node Color Themes for Pentest mode
const ATTACK_GRAPH_NODE_TYPES: Record<string, { headerBg: string; border: string; headerText: string }> = {
  target: { headerBg: '#0f4c3a', border: '#10b981', headerText: 'TARGET / SCOPE' },
  recon: { headerBg: '#311b58', border: '#8b5cf6', headerText: 'RECON / ENUM' },
  vuln: { headerBg: '#542617', border: '#f97316', headerText: 'VULNERABILITY' },
  exploit: { headerBg: '#521422', border: '#f43f5e', headerText: 'EXPLOIT / ACCESS' },
  post_exploit: { headerBg: '#4a1236', border: '#ec4899', headerText: 'PIVOT / PRIVESC' },
  default: { headerBg: '#1e293b', border: '#64748b', headerText: 'ATTACK NODE' },
}

const BRANCH_SIDEBAR_WIDTH = 200
const BRANCH_HOTZONE_WIDTH = 16
const BRANCH_LEAVE_MS = 220

export const MindmapCanvas: React.FC<MindmapCanvasProps> = ({
  activeNodeId,
  activeMode = 'normal',
  onSelectNode,
  onNewChat,
  className = '',
  branchSidebarMode = 'auto',
  showGraph = true,
}) => {
  const activeEngagementId = useAppStore((s) => s.activeEngagementId)
  const fgRef = useRef<ForceGraphMethods | undefined>(undefined)
  const containerRef = useRef<HTMLDivElement | null>(null)
  const graphHostRef = useRef<HTMLDivElement | null>(null)
  const branchLeaveTimerRef = useRef<number | null>(null)
  const userPannedAtRef = useRef<number>(0)
  const programmaticCameraRef = useRef<boolean>(false)
  const activeNodeIdRef = useRef<string | null | undefined>(activeNodeId)
  activeNodeIdRef.current = activeNodeId

  const [graphData, setGraphData] = useState<{ nodes: GraphNode[]; links: GraphEdge[] }>({
    nodes: [],
    links: [],
  })
  const [filterMode, setFilterMode] = useState<string>(activeMode || 'all')
  const [searchQuery, setSearchQuery] = useState<string>('')
  const [debouncedSearch, setDebouncedSearch] = useState<string>('')
  const [focusRecent, setFocusRecent] = useState<boolean>(false)
  const [loading, setLoading] = useState<boolean>(true)
  const [dimensions, setDimensions] = useState({ width: 800, height: 600 })
  const [branchesOpen, setBranchesOpen] = useState(branchSidebarMode === 'docked')

  const branchesDocked = branchSidebarMode === 'docked'
  const branchesVisible = branchesDocked || branchesOpen

  const clearBranchLeaveTimer = useCallback(() => {
    if (branchLeaveTimerRef.current != null) {
      window.clearTimeout(branchLeaveTimerRef.current)
      branchLeaveTimerRef.current = null
    }
  }, [])

  const openBranches = useCallback(() => {
    clearBranchLeaveTimer()
    setBranchesOpen(true)
  }, [clearBranchLeaveTimer])

  const scheduleCloseBranches = useCallback(() => {
    if (branchesDocked) return
    clearBranchLeaveTimer()
    branchLeaveTimerRef.current = window.setTimeout(() => {
      setBranchesOpen(false)
      branchLeaveTimerRef.current = null
    }, BRANCH_LEAVE_MS)
  }, [branchesDocked, clearBranchLeaveTimer])

  useEffect(() => {
    setBranchesOpen(branchSidebarMode === 'docked')
  }, [branchSidebarMode])

  useEffect(() => () => clearBranchLeaveTimer(), [clearBranchLeaveTimer])

  useEffect(() => {
    const timer = window.setTimeout(() => setDebouncedSearch(searchQuery.trim()), 300)
    return () => window.clearTimeout(timer)
  }, [searchQuery])

  useEffect(() => {
    if (activeMode) {
      setFilterMode(activeMode)
    }
  }, [activeMode])

  const normalizeSharedGraph = useCallback((data: any) => {
    const nodes: GraphNode[] = (data.nodes || []).map((n: GraphNode) => {
      const node = { ...n }
      if (n.canvas_x != null && n.canvas_y != null) {
        node.fx = n.canvas_x
        node.fy = n.canvas_y
      }
      return node
    })
    const links: GraphEdge[] = (data.edges || []).map((e: any) => ({
      id: e.id,
      source: e.source,
      target: e.target,
      relation: e.relation,
      weight: e.weight,
    }))
    return { nodes, links }
  }, [])

  const normalizePentestGraph = useCallback((data: any) => {
    const nodes: GraphNode[] = (data.nodes || []).map((n: GraphNode) => ({
      ...n,
      fx: n.canvas_x ?? n.fx,
      fy: n.canvas_y ?? n.fy,
    }))
    const links: GraphEdge[] = (data.edges || []).map((e: any, idx: number) => ({
      id: e.id ?? `pentest-edge-${idx}`,
      source: e.source,
      target: e.target,
      relation: e.relation ?? 'depends_on',
      weight: e.weight,
      auto_generated: e.auto_generated,
    }))
    return { nodes, links }
  }, [])

  const applyNodeFocus = useCallback(async (node: GraphNode, opts?: FocusNodeOptions) => {
    const panBlocksFocus = () =>
      !opts?.force &&
      userPannedAtRef.current > 0 &&
      Date.now() - userPannedAtRef.current < USER_PAN_DEBOUNCE_MS

    if (panBlocksFocus()) return false
    if (!fgRef.current) return false

    const coords = await waitForNodeCoords(node)
    if (!coords) return false
    // Re-check after await — user may have panned while coords resolved
    if (panBlocksFocus()) return false
    if (!fgRef.current) return false

    programmaticCameraRef.current = true
    fgRef.current.centerAt(coords.cx, coords.cy, FOCUS_ANIM_MS)
    fgRef.current.zoom(FOCUS_ZOOM, FOCUS_ANIM_MS)
    window.setTimeout(() => {
      programmaticCameraRef.current = false
    }, FOCUS_ANIM_MS + 50)
    return true
  }, [])

  const focusNode = useCallback(
    async (nodeId: string, opts?: FocusNodeOptions) => {
      const node = graphData.nodes.find((n) => n.id === nodeId)
      if (!node) return false
      return applyNodeFocus(node, opts)
    },
    [applyNodeFocus, graphData.nodes],
  )

  const handleCameraInteraction = useCallback(() => {
    if (!programmaticCameraRef.current) {
      userPannedAtRef.current = Date.now()
    }
  }, [])

  const applyOrganicForces = useCallback(() => {
    const fg = fgRef.current
    if (!fg) return
    const pentest = filterMode === 'pentest'
    fg.d3Force('charge')?.strength(pentest ? -800 : -450)
    fg.d3Force('link')?.distance(pentest ? 150 : 110)
    if (pentest) {
      fg.d3Force('dormancyRadial', null)
      fg.d3Force('cluster', null)
      return
    }
    fg.d3Force('dormancyRadial', createDormancyRadialForce())
    fg.d3Force('cluster', createClusterCohesionForce())
  }, [filterMode])

  // Fetch graph data from backend
  const loadGraph = useCallback(async () => {
    try {
      setLoading(true)
      let nextGraph: { nodes: GraphNode[]; links: GraphEdge[] }

      if (activeMode === 'pentest' && !activeEngagementId) {
        nextGraph = { nodes: [], links: [] }
      } else if (activeMode === 'pentest' && activeEngagementId) {
        const res = await fetchWithAuth(
          `/api/pentest/engagements/${encodeURIComponent(activeEngagementId)}/graph`,
        )
        if (!res.ok) throw new Error('Failed to load pentest graph')
        const data = await res.json()
        nextGraph = normalizePentestGraph(data.graph || {})
      } else {
        const params = new URLSearchParams()
        if (filterMode !== 'all') {
          params.set('mode', filterMode)
        }
        params.set('clustered', 'true')
        params.set('show_dormant', focusRecent ? 'false' : 'true')
        if (activeNodeIdRef.current) {
          params.set('focus_node_id', activeNodeIdRef.current)
        }
        if (debouncedSearch) {
          params.set('search', debouncedSearch)
        }
        const url = `/api/graph/data?${params.toString()}`
        const res = await fetchWithAuth(url)
        if (!res.ok) throw new Error('Failed to load mindmap graph')
        const data = await res.json()
        nextGraph = normalizeSharedGraph(data)
      }

      setGraphData(nextGraph)
      setTimeout(() => {
        if (!fgRef.current) return
        applyOrganicForces()
        if (activeNodeIdRef.current) {
          const node = nextGraph.nodes.find((n) => n.id === activeNodeIdRef.current)
          if (node) {
            void applyNodeFocus(node, { force: true })
            return
          }
        }
        fgRef.current.zoomToFit(400, 60)
      }, 300)
    } catch (err: unknown) {
      console.error('[Mindmap] Load error:', err)
      toast.error(activeMode === 'pentest' ? 'Failed to load pentest graph' : 'Failed to load thought graph')
    } finally {
      setLoading(false)
    }
  }, [
    activeEngagementId,
    activeMode,
    applyNodeFocus,
    applyOrganicForces,
    debouncedSearch,
    filterMode,
    focusRecent,
    normalizePentestGraph,
    normalizeSharedGraph,
  ])

  useEffect(() => {
    void loadGraph()
  }, [loadGraph])

  // Auto-focus when activeNodeId changes externally (new turn, branch picker, reload)
  useEffect(() => {
    if (!activeNodeId) return
    const exists = graphData.nodes.some((n) => n.id === activeNodeId)
    if (!exists) return
    void focusNode(activeNodeId)
  }, [activeNodeId, graphData.nodes, focusNode])

  useEffect(() => {
    if (loading || filterMode === 'pentest') return
    applyOrganicForces()
  }, [applyOrganicForces, filterMode, graphData.nodes, loading])

  // Track canvas host dimensions for responsive force-graph
  useEffect(() => {
    if (!showGraph) return

    let ro: ResizeObserver | null = null
    let raf = 0
    let host: HTMLDivElement | null = null
    let cancelled = false

    const updateSize = () => {
      if (cancelled || !host) return
      const next = {
        width: Math.max(1, Math.floor(host.clientWidth) || 800),
        height: Math.max(1, Math.floor(host.clientHeight) || 600),
      }
      setDimensions((prev) =>
        prev.width === next.width && prev.height === next.height ? prev : next,
      )
    }

    const attach = () => {
      host = graphHostRef.current
      if (!host) {
        raf = window.requestAnimationFrame(attach)
        return
      }
      updateSize()
      ro = typeof ResizeObserver !== 'undefined' ? new ResizeObserver(updateSize) : null
      ro?.observe(host)
      window.addEventListener('resize', updateSize)
    }

    attach()

    return () => {
      cancelled = true
      window.cancelAnimationFrame(raf)
      ro?.disconnect()
      window.removeEventListener('resize', updateSize)
    }
  }, [showGraph, branchesDocked])

  // Filter nodes & edges
  const filteredNodes = graphData.nodes.filter((n) => {
    if (activeMode !== 'pentest' && n.mode === 'pentest') return false
    if (filterMode !== 'all' && n.mode !== filterMode) return false
    if (searchQuery.trim()) {
      const q = searchQuery.toLowerCase()
      return (
        n.title.toLowerCase().includes(q) ||
        (n.summary && n.summary.toLowerCase().includes(q)) ||
        (n.tags && n.tags.some((t) => t.toLowerCase().includes(q)))
      )
    }
    return true
  })

  const filteredNodeIds = new Set(filteredNodes.map((n) => n.id))
  const filteredLinks = graphData.links.filter((l) => {
    const sId = typeof l.source === 'object' ? (l.source as GraphNode).id : l.source
    const tId = typeof l.target === 'object' ? (l.target as GraphNode).id : l.target
    return filteredNodeIds.has(sId) && filteredNodeIds.has(tId)
  })
  const searching = Boolean(searchQuery.trim())
  const nodeById = new Map(filteredNodes.map((n) => [n.id, n]))
  const branchGroups = groupBranchNodes(filteredNodes)

  const selectNodeById = useCallback(
    async (nodeId: string) => {
      const node = graphData.nodes.find((n) => n.id === nodeId)
      if (!node) return

      let selected: GraphNode = node
      if (activeMode !== 'pentest' && node.is_dormant) {
        try {
          const res = await fetchWithAuth(`/api/graph/nodes/${encodeURIComponent(nodeId)}`)
          if (!res.ok) throw new Error('Failed to revive thread')
          const data = await res.json()
          const revived = data.node as GraphNode | undefined
          if (revived) {
            selected = mergeRevivedNode(node, revived)
            setGraphData((prev) => ({
              ...prev,
              nodes: prev.nodes.map((n) => (n.id === nodeId ? selected : n)),
            }))
          }
        } catch (err: unknown) {
          const message = err instanceof Error ? err.message : 'Failed to revive thread'
          toast.error(message)
        }
      }

      onSelectNode(selected)
      void focusNode(nodeId, { force: true })
    },
    [activeMode, focusNode, graphData.nodes, onSelectNode],
  )

  const getGraphViewport = useCallback(
    (nodeId?: string) => {
      const fg = fgRef.current
      if (!fg) return { ok: false, reason: 'no_graph' as const }

      const zoom = fg.zoom()
      const center = fg.centerAt()
      const canvas = containerRef.current?.querySelector('canvas')
      const rect = canvas?.getBoundingClientRect()
      const canvasCenterX = rect ? rect.width / 2 : dimensions.width / 2
      const canvasCenterY = rect ? rect.height / 2 : dimensions.height / 2

      if (!nodeId) {
        return { ok: true, zoom, center, canvasCenterX, canvasCenterY }
      }

      const node = graphData.nodes.find((n) => n.id === nodeId)
      if (!node) return { ok: false, reason: 'node_not_found' as const }

      const { cx, cy } = resolveNodeCoords(node)
      if (typeof cx !== 'number' || typeof cy !== 'number') {
        return { ok: false, reason: 'no_coords' as const, zoom, center }
      }

      const screen = fg.graph2ScreenCoords(cx, cy)
      const dist = Math.hypot(screen.x - canvasCenterX, screen.y - canvasCenterY)
      const maxDist = Math.min(dimensions.width, dimensions.height) * 0.25
      const focused = zoom >= 1.2 && dist <= maxDist

      return {
        ok: focused,
        zoom,
        center,
        screen,
        dist,
        maxDist,
        nodeId,
      }
    },
    [dimensions.height, dimensions.width, graphData.nodes],
  )

  useEffect(() => {
    if (!import.meta.env.DEV) return
    const w = window as Window & {
      __OWLYNN_TEST__?: {
        selectGraphNode?: (id: string) => void
        focusGraphNode?: (id: string) => Promise<boolean>
        getGraphViewport?: (nodeId?: string) => ReturnType<typeof getGraphViewport>
      }
    }
    w.__OWLYNN_TEST__ = w.__OWLYNN_TEST__ ?? {}
    w.__OWLYNN_TEST__.selectGraphNode = selectNodeById
    w.__OWLYNN_TEST__.focusGraphNode = (id: string) => focusNode(id, { force: true })
    w.__OWLYNN_TEST__.getGraphViewport = getGraphViewport
    return () => {
      if (w.__OWLYNN_TEST__?.selectGraphNode === selectNodeById) {
        delete w.__OWLYNN_TEST__.selectGraphNode
      }
      if (w.__OWLYNN_TEST__?.focusGraphNode) {
        delete w.__OWLYNN_TEST__.focusGraphNode
      }
      if (w.__OWLYNN_TEST__?.getGraphViewport === getGraphViewport) {
        delete w.__OWLYNN_TEST__.getGraphViewport
      }
    }
  }, [focusNode, getGraphViewport, selectNodeById])

  const renderModePill = (mode: string) => {
    if (mode === 'pentest') {
      return (
        <span style={{ display: 'inline-flex', alignItems: 'center', gap: 3, fontSize: 9, fontWeight: 600, color: '#f43f5e', background: 'rgba(244, 63, 94, 0.15)', padding: '1px 5px', borderRadius: 4 }}>
          <Shield size={9} /> Pentest
        </span>
      )
    }
    if (mode === 'study') {
      return (
        <span style={{ display: 'inline-flex', alignItems: 'center', gap: 3, fontSize: 9, fontWeight: 600, color: '#c084fc', background: 'rgba(192, 132, 252, 0.15)', padding: '1px 5px', borderRadius: 4 }}>
          <GraduationCap size={9} /> Study
        </span>
      )
    }
    return (
      <span style={{ display: 'inline-flex', alignItems: 'center', gap: 3, fontSize: 9, fontWeight: 600, color: '#38bdf8', background: 'rgba(56, 189, 248, 0.15)', padding: '1px 5px', borderRadius: 4 }}>
        <Sparkles size={9} /> Normal
      </span>
    )
  }

  // Handle node drag coordinate save
  const handleNodeDragEnd = useCallback((node: any) => {
    if (activeMode === 'pentest') return
    if (!node || !node.id) return
    node.fx = node.x
    node.fy = node.y
    void fetchWithAuth(`/api/graph/nodes/${encodeURIComponent(node.id)}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ canvas_x: node.x, canvas_y: node.y }),
    })
  }, [activeMode])

  const createThoughtNode = useCallback(
    async (title: string, parentId?: string | null) => {
      const mode = filterMode !== 'all' ? filterMode : activeMode && activeMode !== 'pentest' ? activeMode : 'normal'
      const body: Record<string, unknown> = { title, mode }
      if (parentId) {
        body.parent_id = parentId
      }
      const res = await fetchWithAuth('/api/graph/nodes', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      })
      if (!res.ok) throw new Error('Failed to create node')
      const data = await res.json()
      toast.success(parentId ? `Created branch "${title}"` : `Created thread "${title}"`)
      await loadGraph()
      if (data.node) {
        onSelectNode(data.node)
        void focusNode(data.node.id, { force: true })
      }
    },
    [activeMode, filterMode, focusNode, loadGraph, onSelectNode],
  )

  const handleCreateNewThread = useCallback(async () => {
    if (activeMode === 'pentest') {
      toast.error('Pentest graph threads must come from pentest engagement workflows')
      return
    }
    const title = prompt('Enter title for new thread:', 'New Thread')
    if (!title) return
    try {
      await createThoughtNode(title)
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : 'Failed to create thought thread'
      toast.error(message)
    }
  }, [activeMode, createThoughtNode])

  const handleCreateNewBranch = useCallback(async () => {
    if (activeMode === 'pentest') {
      toast.error('Pentest graph branches must come from pentest engagement workflows')
      return
    }
    if (!activeNodeId) {
      toast.error('Select a thread to branch from')
      return
    }
    const title = prompt('Enter title for new thought branch:', 'Investigation')
    if (!title) return
    try {
      await createThoughtNode(title, activeNodeId)
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : 'Failed to create thought node'
      toast.error(message)
    }
  }, [activeMode, activeNodeId, createThoughtNode])

  const handleDeleteNode = useCallback(
    async (nodeId: string) => {
      if (activeMode === 'pentest') {
        toast.error('Pentest graph nodes must be managed from pentest engagement workflows')
        return
      }
      const node = graphData.nodes.find((n) => n.id === nodeId)
      const label = node?.title || 'this thread'
      if (!window.confirm(`Delete "${label}"? This cannot be undone.`)) return

      try {
        const res = await fetchWithAuth(`/api/graph/nodes/${encodeURIComponent(nodeId)}`, {
          method: 'DELETE',
        })
        if (!res.ok) throw new Error('Failed to delete node')
        toast.success(`Deleted "${label}"`)
        const remaining = graphData.nodes.filter((n) => n.id !== nodeId)
        await loadGraph()
        if (nodeId === activeNodeId) {
          if (remaining[0]) {
            onSelectNode(remaining[0])
            void focusNode(remaining[0].id, { force: true })
          } else {
            onNewChat?.()
          }
        }
      } catch (err: unknown) {
        const message = err instanceof Error ? err.message : 'Failed to delete thread'
        toast.error(message)
      }
    },
    [activeMode, activeNodeId, focusNode, graphData.nodes, loadGraph, onNewChat, onSelectNode],
  )

  // ── 1. Coggle Style Organic Mindmap Renderer (Normal & Study Mode) ──
  const drawCoggleNode = (node: GraphNode, ctx: CanvasRenderingContext2D, globalScale: number, colorIdx: number) => {
    const isActive = node.id === activeNodeId
    const branchColor = COGGLE_COLORS[colorIdx % COGGLE_COLORS.length]
    const label = node.title || 'Thought'
    const fontSize = Math.max(13 / globalScale, 4.5)
    const fade = nodeDisplayAlpha(node, { isActive, searching })
    const dormantLook = !searching && !isActive && (node.is_dormant || node.visual_mode === 'dormant')
    ctx.save()
    ctx.globalAlpha = fade

    ctx.font = `${isActive ? 'bold' : '500'} ${fontSize}px system-ui, -apple-system, sans-serif`
    const textWidth = ctx.measureText(label).width
    const paddingX = 14
    const paddingY = 6
    const boxW = textWidth + paddingX * 2
    const boxH = fontSize + paddingY * 2
    const radius = 8

    // Glowing aura if active
    if (isActive) {
      ctx.shadowColor = branchColor
      ctx.shadowBlur = 16
    } else {
      ctx.shadowBlur = 0
    }

    // Pill background
    ctx.beginPath()
    ctx.roundRect(node.x! - boxW / 2, node.y! - boxH / 2, boxW, boxH, radius)
    ctx.fillStyle = isActive
      ? 'rgba(15, 23, 42, 0.95)'
      : dormantLook
        ? 'rgba(13, 26, 45, 0.55)'
        : 'rgba(13, 26, 45, 0.88)'
    ctx.fill()
    ctx.lineWidth = isActive ? 2.5 : dormantLook ? 1 : 1.5
    ctx.strokeStyle = dormantLook ? hexToRgba(branchColor, 0.55) : branchColor
    ctx.stroke()
    ctx.shadowBlur = 0

    // Label text
    ctx.textAlign = 'center'
    ctx.textBaseline = 'middle'
    ctx.fillStyle = isActive ? '#ffffff' : dormantLook ? '#94a3b8' : '#e2e8f0'
    ctx.fillText(label, node.x!, node.y!)

    // Mode mini badge
    if (node.mode === 'study' && globalScale > 0.7) {
      ctx.font = `600 ${fontSize * 0.7}px sans-serif`
      ctx.fillStyle = '#c084fc'
      ctx.fillText('STUDY', node.x!, node.y! + boxH / 2 + 8)
    }
    ctx.restore()
  }

  // ── 2. Attack Graph / Blueprint Style Node Renderer (Pentest Mode) ──
  const drawAttackGraphNode = (node: any, ctx: CanvasRenderingContext2D, globalScale: number) => {
    const isActive = node.id === activeNodeId
    const nodeType = node.tags?.includes('exploit')
      ? 'exploit'
      : node.tags?.includes('vuln')
        ? 'vuln'
        : node.tags?.includes('target')
          ? 'target'
          : 'recon'
    const theme = ATTACK_GRAPH_NODE_TYPES[nodeType] || ATTACK_GRAPH_NODE_TYPES.default

    const width = 140
    const headerHeight = 22
    const bodyHeight = 54
    const totalHeight = headerHeight + bodyHeight
    const radius = 4

    const x = node.x - width / 2
    const y = node.y - totalHeight / 2

    // Shadow / active glow
    if (isActive) {
      ctx.shadowColor = '#f43f5e'
      ctx.shadowBlur = 18
    } else {
      ctx.shadowColor = 'rgba(0,0,0,0.5)'
      ctx.shadowBlur = 8
    }

    // Outer container
    ctx.beginPath()
    ctx.roundRect(x, y, width, totalHeight, radius)
    ctx.fillStyle = '#0f172a'
    ctx.fill()
    ctx.lineWidth = isActive ? 2 : 1
    ctx.strokeStyle = isActive ? '#f43f5e' : theme.border
    ctx.stroke()
    ctx.shadowBlur = 0

    // Header Bar
    ctx.beginPath()
    ctx.roundRect(x, y, width, headerHeight, [radius, radius, 0, 0])
    ctx.fillStyle = theme.headerBg
    ctx.fill()

    // Header Title
    ctx.font = `bold 9px system-ui, sans-serif`
    ctx.textAlign = 'left'
    ctx.textBaseline = 'middle'
    ctx.fillStyle = '#f8fafc'
    ctx.fillText(theme.headerText, x + 8, y + headerHeight / 2)

    // Body Label (Node Title)
    ctx.font = `600 11px system-ui, sans-serif`
    ctx.fillStyle = '#e2e8f0'
    const title = node.title || 'Target / Port'
    ctx.fillText(title.length > 18 ? title.slice(0, 17) + '…' : title, x + 10, y + headerHeight + 16)

    // Port Pins (Left Input Pin & Right Output Pin)
    // Left input pin
    ctx.beginPath()
    ctx.arc(x, y + totalHeight / 2, 4, 0, 2 * Math.PI)
    ctx.fillStyle = '#10b981'
    ctx.fill()
    ctx.strokeStyle = '#022c22'
    ctx.stroke()

    // Right output pin
    ctx.beginPath()
    ctx.arc(x + width, y + totalHeight / 2, 4, 0, 2 * Math.PI)
    ctx.fillStyle = '#f59e0b'
    ctx.fill()
    ctx.strokeStyle = '#451a03'
    ctx.stroke()

    // Minor pin labels
    if (globalScale > 0.8) {
      ctx.font = `8px monospace`
      ctx.fillStyle = '#64748b'
      ctx.fillText('in', x + 8, y + totalHeight / 2 + 1)
      ctx.textAlign = 'right'
      ctx.fillText('out', x + width - 8, y + totalHeight / 2 + 1)
    }
  }

  // Custom node rendering router
  const drawNode = useCallback(
    (node: GraphNode, ctx: CanvasRenderingContext2D, globalScale: number) => {
      const isPentest = filterMode === 'pentest' || node.mode === 'pentest'
      if (isPentest) {
        drawAttackGraphNode(node, ctx, globalScale)
      } else {
        const colorKey = node.topic_cluster_id || node.id || '0'
        const idx = Math.abs(hashCode(colorKey))
        drawCoggleNode(node, ctx, globalScale, idx)
      }
    },
    // drawCoggleNode closes over activeNodeId / searching
    [activeNodeId, filterMode, searching],
  )

  // Custom background renderer for CAD grid in pentest mode
  const drawBackground = useCallback(
    (ctx: CanvasRenderingContext2D) => {
      const isPentest = filterMode === 'pentest'
      if (isPentest) {
        // Draw CAD / Attack Graph grid pattern
        ctx.fillStyle = '#080d1a'
        ctx.fillRect(-2000, -2000, 4000, 4000)

        ctx.lineWidth = 0.5
        ctx.strokeStyle = 'rgba(255, 255, 255, 0.04)'
        const gridSize = 30
        for (let x = -2000; x < 2000; x += gridSize) {
          ctx.beginPath()
          ctx.moveTo(x, -2000)
          ctx.lineTo(x, 2000)
          ctx.stroke()
        }
        for (let y = -2000; y < 2000; y += gridSize) {
          ctx.beginPath()
          ctx.moveTo(-2000, y)
          ctx.lineTo(2000, y)
          ctx.stroke()
        }
      }
    },
    [filterMode]
  )

  return (
    <div
      ref={containerRef}
      className={`mindmap-container relative w-full h-full overflow-hidden flex flex-col ${className}`}
      style={{
        background:
          filterMode === 'pentest'
            ? '#080d1a'
            : 'radial-gradient(circle at center, #0f1c30 0%, #080d1a 100%)',
      }}
    >
      {/* Top Floating Control Bar */}
      <div
        style={{
          position: 'absolute',
          top: 12,
          left: 12,
          right: 12,
          zIndex: 10,
          display: 'flex',
          alignItems: 'flex-start',
          justifyContent: 'space-between',
          flexWrap: 'wrap',
          gap: 8,
          minWidth: 0,
          maxWidth: '100%',
          pointerEvents: 'none',
        }}
      >
        {/* Mode Filter Tabs */}
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: 4,
            padding: '4px',
            borderRadius: 10,
            background: 'rgba(13, 26, 45, 0.95)',
            border: '1px solid rgba(255, 255, 255, 0.1)',
            backdropFilter: 'blur(12px)',
            pointerEvents: 'auto',
            boxShadow: '0 8px 24px rgba(0,0,0,0.4)',
            flexShrink: 0,
          }}
        >
          <button
            onClick={() => setFilterMode(activeMode === 'pentest' ? 'pentest' : 'all')}
            style={{
              padding: '4px 10px',
              fontSize: 11,
              fontWeight: 500,
              borderRadius: 6,
              background: filterMode === 'all' ? 'rgba(56, 189, 248, 0.25)' : 'transparent',
              color: filterMode === 'all' ? '#38bdf8' : '#94a3b8',
              border: filterMode === 'all' ? '1px solid rgba(56, 189, 248, 0.4)' : 'none',
              cursor: 'pointer',
            }}
          >
            All
          </button>
          {activeMode === 'pentest' ? (
            <button
              onClick={() => setFilterMode('pentest')}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: 4,
                padding: '4px 10px',
                fontSize: 11,
                fontWeight: 500,
                borderRadius: 6,
                background: filterMode === 'pentest' ? 'rgba(244, 63, 94, 0.25)' : 'transparent',
                color: filterMode === 'pentest' ? '#f43f5e' : '#94a3b8',
                border: filterMode === 'pentest' ? '1px solid rgba(244, 63, 94, 0.4)' : 'none',
                cursor: 'pointer',
              }}
            >
              <Shield size={12} />
              Attack Graph
            </button>
          ) : activeMode === 'study' ? (
            <button
              onClick={() => setFilterMode('study')}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: 4,
                padding: '4px 10px',
                fontSize: 11,
                fontWeight: 500,
                borderRadius: 6,
                background: filterMode === 'study' ? 'rgba(192, 132, 252, 0.25)' : 'transparent',
                color: filterMode === 'study' ? '#c084fc' : '#94a3b8',
                border: filterMode === 'study' ? '1px solid rgba(192, 132, 252, 0.4)' : 'none',
                cursor: 'pointer',
              }}
            >
              <GraduationCap size={12} />
              Mastery Tree
            </button>
          ) : (
            <button
              onClick={() => setFilterMode('normal')}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: 4,
                padding: '4px 10px',
                fontSize: 11,
                fontWeight: 500,
                borderRadius: 6,
                background: filterMode === 'normal' ? 'rgba(56, 189, 248, 0.25)' : 'transparent',
                color: filterMode === 'normal' ? '#38bdf8' : '#94a3b8',
                border: filterMode === 'normal' ? '1px solid rgba(56, 189, 248, 0.4)' : 'none',
                cursor: 'pointer',
              }}
            >
              <Sparkles size={12} />
              Organic Mindmap
            </button>
          )}
        </div>

        {/* Action Controls */}
        <div
          data-testid="mindmap-action-bar"
          style={{
            display: 'flex',
            alignItems: 'center',
            flexWrap: 'wrap',
            justifyContent: 'flex-end',
            gap: 6,
            minWidth: 0,
            flex: '1 1 220px',
            pointerEvents: 'auto',
          }}
        >
          <input
            type="text"
            placeholder="Search mindmap..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            style={{
              padding: '5px 10px',
              fontSize: 11,
              background: 'rgba(13, 26, 45, 0.95)',
              color: '#f1f5f9',
              border: '1px solid rgba(255, 255, 255, 0.1)',
              borderRadius: 8,
              outline: 'none',
              flex: '1 1 110px',
              minWidth: 90,
              maxWidth: 160,
              boxShadow: '0 4px 12px rgba(0,0,0,0.3)',
            }}
          />
          {activeMode !== 'pentest' ? (
            <button
              type="button"
              data-testid="focus-recent"
              onClick={() => setFocusRecent((v) => !v)}
              style={{
                padding: '5px 10px',
                fontSize: 11,
                fontWeight: 600,
                background: focusRecent ? 'rgba(56, 189, 248, 0.25)' : 'rgba(13, 26, 45, 0.95)',
                color: focusRecent ? '#38bdf8' : '#94a3b8',
                border: focusRecent
                  ? '1px solid rgba(56, 189, 248, 0.45)'
                  : '1px solid rgba(255, 255, 255, 0.1)',
                borderRadius: 8,
                cursor: 'pointer',
                boxShadow: '0 4px 12px rgba(0,0,0,0.3)',
                flexShrink: 0,
                whiteSpace: 'nowrap',
              }}
              title="Hide faded dormant threads; keep pinned and the active chat"
            >
              Focus recent
            </button>
          ) : null}
          <button
            type="button"
            onClick={() => void handleCreateNewThread()}
            disabled={activeMode === 'pentest'}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: 4,
              padding: '5px 12px',
              fontSize: 11,
              fontWeight: 600,
              background: '#0369a1',
              color: '#ffffff',
              borderRadius: 8,
              border: 'none',
              cursor: activeMode === 'pentest' ? 'not-allowed' : 'pointer',
              opacity: activeMode === 'pentest' ? 0.5 : 1,
              boxShadow: '0 4px 12px rgba(2, 132, 199, 0.3)',
              flexShrink: 0,
              whiteSpace: 'nowrap',
            }}
            title={activeMode === 'pentest' ? 'Pentest graph is derived from engagement state' : 'Create a new root thread'}
          >
            <Plus size={13} />
            New Thread
          </button>
          <button
            type="button"
            onClick={() => void handleCreateNewBranch()}
            disabled={activeMode === 'pentest'}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: 4,
              padding: '5px 12px',
              fontSize: 11,
              fontWeight: 600,
              background: '#0284c7',
              color: '#ffffff',
              borderRadius: 8,
              border: 'none',
              cursor: activeMode === 'pentest' ? 'not-allowed' : 'pointer',
              opacity: activeMode === 'pentest' ? 0.5 : 1,
              boxShadow: '0 4px 12px rgba(2, 132, 199, 0.3)',
              flexShrink: 0,
              whiteSpace: 'nowrap',
            }}
            title={activeMode === 'pentest' ? 'Pentest graph is derived from engagement state' : 'Create a child branch from the active thread'}
          >
            <GitBranch size={13} />
            New Branch
          </button>
          <button
            onClick={() => void loadGraph()}
            style={{
              padding: '5px 8px',
              background: 'rgba(13, 26, 45, 0.95)',
              color: '#94a3b8',
              border: '1px solid rgba(255, 255, 255, 0.1)',
              borderRadius: 8,
              cursor: 'pointer',
            }}
            title="Refresh graph"
          >
            <RefreshCw size={13} className={loading ? 'animate-spin' : ''} />
          </button>
          {showGraph ? (
            <button
              onClick={() => fgRef.current?.zoomToFit(400, 50)}
              style={{
                padding: '5px 8px',
                background: 'rgba(13, 26, 45, 0.95)',
                color: '#94a3b8',
                border: '1px solid rgba(255, 255, 255, 0.1)',
                borderRadius: 8,
                cursor: 'pointer',
              }}
              title="Fit to screen"
            >
              <Maximize2 size={13} />
            </button>
          ) : null}
        </div>
      </div>

      {/* Branch picker + Force Graph 2D Canvas */}
      <div
        style={{
          flex: 1,
          display: 'flex',
          width: '100%',
          minHeight: 0,
          overflow: 'hidden',
          position: 'relative',
        }}
      >
        {!branchesDocked && showGraph ? (
          <div
            data-testid="branches-hotzone"
            onMouseEnter={openBranches}
            style={{
              position: 'absolute',
              left: 0,
              top: 0,
              bottom: 0,
              width: BRANCH_HOTZONE_WIDTH,
              zIndex: 6,
              pointerEvents: branchesVisible ? 'none' : 'auto',
            }}
            title="Branches"
          />
        ) : null}
        <aside
          data-testid="branches-sidebar"
          data-mode={branchSidebarMode}
          data-open={branchesVisible ? 'true' : 'false'}
          onMouseEnter={openBranches}
          onMouseLeave={scheduleCloseBranches}
          style={{
            flexShrink: 0,
            display: 'flex',
            flexDirection: 'column',
            borderRight: '1px solid rgba(255, 255, 255, 0.08)',
            background: 'rgba(13, 26, 45, 0.92)',
            backdropFilter: 'blur(10px)',
            zIndex: 7,
            ...(branchesDocked
              ? {
                  position: 'relative' as const,
                  width: showGraph ? BRANCH_SIDEBAR_WIDTH : '100%',
                  height: '100%',
                  transform: 'none',
                  boxShadow: 'none',
                }
              : {
                  position: 'absolute' as const,
                  width: BRANCH_SIDEBAR_WIDTH,
                  left: 0,
                  top: 0,
                  bottom: 0,
                  transform: branchesVisible ? 'translateX(0)' : 'translateX(-100%)',
                  transition: 'transform 180ms ease',
                  boxShadow: branchesVisible ? '8px 0 24px rgba(0, 0, 0, 0.35)' : 'none',
                  pointerEvents: branchesVisible ? 'auto' : 'none',
                }),
          }}
        >
          <div style={{ padding: '8px 10px', fontSize: 10, fontWeight: 600, color: '#64748b', textTransform: 'uppercase', letterSpacing: '0.05em', borderBottom: '1px solid rgba(255,255,255,0.06)' }}>
            Branches ({filteredNodes.length})
          </div>
          <div style={{ flex: 1, overflowY: 'auto', padding: '6px 4px' }}>
            {filteredNodes.length === 0 ? (
              <div style={{ padding: '12px 8px', fontSize: 11, color: '#64748b', textAlign: 'center' }}>
                No branches match
              </div>
            ) : (
              branchGroups.map((group) => (
                <div key={group.id} data-testid={`cluster-group-${group.id}`}>
                  {branchGroups.length > 1 || group.id !== '_ungrouped' ? (
                    <div
                      style={{
                        padding: '6px 8px 2px',
                        fontSize: 9,
                        fontWeight: 600,
                        color: '#64748b',
                        textTransform: 'uppercase',
                        letterSpacing: '0.04em',
                      }}
                    >
                      {group.label}
                    </div>
                  ) : null}
                  {group.nodes.map((node) => {
                    const isActive = node.id === activeNodeId
                    const allowDelete = activeMode !== 'pentest'
                    const rowOpacity = branchRowOpacity(node, { isActive, searching })
                    const dormant = Boolean(node.is_dormant || node.visual_mode === 'dormant')
                    return (
                      <div
                        key={node.id}
                        style={{
                          display: 'flex',
                          alignItems: 'stretch',
                          gap: 2,
                          marginBottom: 2,
                          opacity: rowOpacity,
                        }}
                      >
                        <button
                          type="button"
                          data-testid={`branch-option-${node.id}`}
                          data-dormant={dormant ? 'true' : 'false'}
                          onClick={() => void selectNodeById(node.id)}
                          style={{
                            display: 'flex',
                            flexDirection: 'column',
                            alignItems: 'flex-start',
                            gap: 4,
                            flex: 1,
                            minWidth: 0,
                            padding: '7px 8px',
                            borderRadius: 6,
                            border: isActive ? '1px solid rgba(56, 189, 248, 0.45)' : '1px solid transparent',
                            background: isActive ? 'rgba(56, 189, 248, 0.12)' : 'transparent',
                            cursor: 'pointer',
                            textAlign: 'left',
                          }}
                        >
                          <span
                            style={{
                              fontSize: 11,
                              fontWeight: isActive ? 600 : 500,
                              color: isActive ? '#f1f5f9' : dormant && !searching ? '#94a3b8' : '#cbd5e1',
                              overflow: 'hidden',
                              textOverflow: 'ellipsis',
                              whiteSpace: 'nowrap',
                              width: '100%',
                            }}
                            title={node.title}
                          >
                            {node.title || 'Thought'}
                            {dormant && !searching && !isActive ? ' · dormant' : ''}
                          </span>
                          {renderModePill(node.mode || 'normal')}
                        </button>
                        {allowDelete ? (
                          <button
                            type="button"
                            data-testid={`delete-branch-${node.id}`}
                            aria-label={`Delete ${node.title || 'thread'}`}
                            onClick={() => void handleDeleteNode(node.id)}
                            style={{
                              display: 'flex',
                              alignItems: 'center',
                              justifyContent: 'center',
                              width: 26,
                              flexShrink: 0,
                              border: 'none',
                              borderRadius: 6,
                              background: 'transparent',
                              color: '#64748b',
                              cursor: 'pointer',
                            }}
                            title="Delete thread"
                          >
                            <Trash2 size={12} />
                          </button>
                        ) : null}
                      </div>
                    )
                  })}
                </div>
              ))
            )}
          </div>
        </aside>
        {showGraph ? (
        <div
          ref={graphHostRef}
          className="flex-1 w-full h-full cursor-grab active:cursor-grabbing"
          style={{ minWidth: 0, minHeight: 0, position: 'relative', overflow: 'hidden' }}
        >
        <ForceGraph2D
          ref={fgRef as any}
          width={dimensions.width}
          height={dimensions.height}
          graphData={{ nodes: filteredNodes, links: filteredLinks }}
          nodeCanvasObject={drawNode}
          nodePointerAreaPaint={(node: any, color, ctx) => {
            ctx.fillStyle = color
            if (filterMode === 'pentest' || node.mode === 'pentest') {
              ctx.fillRect(node.x - 70, node.y - 38, 140, 76)
            } else {
              ctx.font = '500 13px system-ui, -apple-system, sans-serif'
              const textWidth = ctx.measureText(node.title || 'Thought').width
              const boxW = Math.max(textWidth + 28, 60)
              const boxH = 28
              ctx.beginPath()
              ctx.roundRect(node.x - boxW / 2, node.y - boxH / 2, boxW, boxH, 8)
              ctx.fill()
            }
          }}
          onRenderFramePre={drawBackground}
          linkCurvature={0.25}
          linkColor={(link: GraphEdge) => {
            const base =
              filterMode === 'pentest'
                ? '#f59e0b'
                : COGGLE_COLORS[Math.abs(hashCode(String(link.id || '0'))) % COGGLE_COLORS.length]
            const dormant = linkIsDormant(link, nodeById)
            const alpha = filterMode === 'pentest' || searching ? 1 : dormant ? 0.22 : 0.85
            return hexToRgba(base, alpha)
          }}
          linkWidth={(link: GraphEdge) => {
            if (filterMode === 'pentest') return 2
            return linkIsDormant(link, nodeById) && !searching ? 1.2 : 2.5
          }}
          linkDirectionalParticles={(link: GraphEdge) =>
            linkParticleCount({
              pentest: filterMode === 'pentest',
              searching,
              dormantLink: linkIsDormant(link, nodeById),
            })
          }
          linkDirectionalParticleSpeed={0.006}
          linkDirectionalParticleWidth={filterMode === 'pentest' ? 3 : 2}
          linkDirectionalParticleColor={() => (filterMode === 'pentest' ? '#10b981' : '#ffffff')}
          onNodeClick={(node: GraphNode) => {
            if (node?.id) {
              void selectNodeById(node.id)
            }
          }}
          onNodeRightClick={(node: GraphNode, event: MouseEvent) => {
            event.preventDefault()
            if (node?.id) {
              void handleDeleteNode(node.id)
            }
          }}
          onZoom={handleCameraInteraction}
          onBackgroundClick={handleCameraInteraction}
          onNodeDragEnd={handleNodeDragEnd}
          cooldownTicks={120}
          d3AlphaDecay={0.02}
          d3VelocityDecay={0.25}
        />
        </div>
        ) : null}
      </div>

      {/* Bottom Info HUD */}
      {showGraph ? (
      <div
        style={{
          position: 'absolute',
          bottom: 12,
          left: 16,
          fontSize: 11,
          color: '#94a3b8',
          background: 'rgba(13, 26, 45, 0.9)',
          padding: '4px 10px',
          borderRadius: 8,
          border: '1px solid rgba(255, 255, 255, 0.08)',
          backdropFilter: 'blur(8px)',
          pointerEvents: 'none',
          zIndex: 10,
        }}
      >
        {filteredNodes.length} Nodes • {filteredLinks.length} Connections •{' '}
        {filterMode === 'pentest'
          ? 'Attack Graph Active'
          : focusRecent
            ? 'Focus recent'
            : 'Bright = active · Dim = dormant · Groups = related'}
      </div>
      ) : null}
    </div>
  )
}

function hashCode(str: string): number {
  let hash = 0
  for (let i = 0; i < str.length; i++) {
    hash = (hash << 5) - hash + str.charCodeAt(i)
    hash |= 0
  }
  return hash
}
