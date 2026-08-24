import React, { useEffect, useState, useRef, useCallback } from 'react'
import ForceGraph2D, { type ForceGraphMethods } from 'react-force-graph-2d'
import { Sparkles, Shield, GraduationCap, Plus, RefreshCw, Maximize2 } from 'lucide-react'
import { fetchWithAuth } from '../../lib/localRunToken'
import { useAppStore } from '../../state/useAppStore'
import toast from 'react-hot-toast'

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
  className?: string
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

export const MindmapCanvas: React.FC<MindmapCanvasProps> = ({
  activeNodeId,
  activeMode = 'normal',
  onSelectNode,
  className = '',
}) => {
  const activeEngagementId = useAppStore((s) => s.activeEngagementId)
  const fgRef = useRef<ForceGraphMethods | undefined>(undefined)
  const containerRef = useRef<HTMLDivElement | null>(null)
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
  const [loading, setLoading] = useState<boolean>(true)
  const [dimensions, setDimensions] = useState({ width: 800, height: 600 })

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
        const url = params.toString() ? `/api/graph/data?${params.toString()}` : '/api/graph/data'
        const res = await fetchWithAuth(url)
        if (!res.ok) throw new Error('Failed to load mindmap graph')
        const data = await res.json()
        nextGraph = normalizeSharedGraph(data)
      }

      setGraphData(nextGraph)
      setTimeout(() => {
        if (!fgRef.current) return
        fgRef.current.d3Force('charge')?.strength(filterMode === 'pentest' ? -800 : -450)
        fgRef.current.d3Force('link')?.distance(filterMode === 'pentest' ? 150 : 100)
        if (activeNodeIdRef.current) {
          const node = nextGraph.nodes.find((n) => n.id === activeNodeIdRef.current)
          if (node) {
            void applyNodeFocus(node, { force: true })
            return
          }
        }
        fgRef.current.zoomToFit(400, 60)
      }, 300)
    } catch (err: any) {
      console.error('[Mindmap] Load error:', err)
      toast.error(activeMode === 'pentest' ? 'Failed to load pentest graph' : 'Failed to load thought graph')
    } finally {
      setLoading(false)
    }
  }, [
    activeEngagementId,
    activeMode,
    applyNodeFocus,
    filterMode,
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

  // Track container dimensions for responsive canvas
  useEffect(() => {
    const updateSize = () => {
      if (containerRef.current) {
        setDimensions({
          width: containerRef.current.clientWidth || 800,
          height: containerRef.current.clientHeight || 600,
        })
      }
    }
    updateSize()
    window.addEventListener('resize', updateSize)
    return () => window.removeEventListener('resize', updateSize)
  }, [])

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
    const sId = typeof l.source === 'object' ? (l.source as any).id : l.source
    const tId = typeof l.target === 'object' ? (l.target as any).id : l.target
    return filteredNodeIds.has(sId) && filteredNodeIds.has(tId)
  })

  const selectNodeById = useCallback(
    (nodeId: string) => {
      const node = graphData.nodes.find((n) => n.id === nodeId)
      if (!node) return
      onSelectNode(node)
      void focusNode(nodeId, { force: true })
    },
    [graphData.nodes, onSelectNode, focusNode],
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

  // Create a new thought node
  const handleCreateNewNode = async () => {
    if (activeMode === 'pentest') {
      toast.error('Pentest graph branches must come from pentest engagement workflows')
      return
    }
    const title = prompt('Enter title for new thought branch:', 'Investigation')
    if (!title) return

    try {
      const res = await fetchWithAuth('/api/graph/nodes', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          title,
          mode: filterMode !== 'all' ? filterMode : 'normal',
          parent_id: activeNodeId || undefined,
        }),
      })
      if (!res.ok) throw new Error('Failed to create node')
      const data = await res.json()
      toast.success(`Created node "${title}"`)
      await loadGraph()
      if (data.node) {
        onSelectNode(data.node)
        void focusNode(data.node.id, { force: true })
      }
    } catch (err: any) {
      toast.error(err.message || 'Failed to create thought node')
    }
  }

  // ── 1. Coggle Style Organic Mindmap Renderer (Normal & Study Mode) ──
  const drawCoggleNode = (node: any, ctx: CanvasRenderingContext2D, globalScale: number, colorIdx: number) => {
    const isActive = node.id === activeNodeId
    const branchColor = COGGLE_COLORS[colorIdx % COGGLE_COLORS.length]
    const label = node.title || 'Thought'
    const fontSize = Math.max(13 / globalScale, 4.5)

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
    ctx.roundRect(node.x - boxW / 2, node.y - boxH / 2, boxW, boxH, radius)
    ctx.fillStyle = isActive ? 'rgba(15, 23, 42, 0.95)' : 'rgba(13, 26, 45, 0.88)'
    ctx.fill()
    ctx.lineWidth = isActive ? 2.5 : 1.5
    ctx.strokeStyle = branchColor
    ctx.stroke()
    ctx.shadowBlur = 0

    // Label text
    ctx.textAlign = 'center'
    ctx.textBaseline = 'middle'
    ctx.fillStyle = isActive ? '#ffffff' : '#e2e8f0'
    ctx.fillText(label, node.x, node.y)

    // Mode mini badge
    if (node.mode === 'study' && globalScale > 0.7) {
      ctx.font = `600 ${fontSize * 0.7}px sans-serif`
      ctx.fillStyle = '#c084fc'
      ctx.fillText('STUDY', node.x, node.y + boxH / 2 + 8)
    }
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
    (node: any, ctx: CanvasRenderingContext2D, globalScale: number) => {
      const isPentest = filterMode === 'pentest' || node.mode === 'pentest'
      if (isPentest) {
        drawAttackGraphNode(node, ctx, globalScale)
      } else {
        const idx = Math.abs(hashCode(node.id || '0'))
        drawCoggleNode(node, ctx, globalScale, idx)
      }
    },
    [activeNodeId, filterMode]
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
          alignItems: 'center',
          justifyContent: 'space-between',
          gap: 10,
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
        <div style={{ display: 'flex', alignItems: 'center', gap: 6, pointerEvents: 'auto' }}>
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
              width: 150,
              boxShadow: '0 4px 12px rgba(0,0,0,0.3)',
            }}
          />
          <button
            onClick={handleCreateNewNode}
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
            }}
            title={activeMode === 'pentest' ? 'Pentest graph is derived from engagement state' : 'Create a new thought branch'}
          >
            <Plus size={13} />
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
        </div>
      </div>

      {/* Branch picker + Force Graph 2D Canvas */}
      <div style={{ flex: 1, display: 'flex', width: '100%', minHeight: 0, overflow: 'hidden' }}>
        <aside
          style={{
            width: 200,
            flexShrink: 0,
            display: 'flex',
            flexDirection: 'column',
            borderRight: '1px solid rgba(255, 255, 255, 0.08)',
            background: 'rgba(13, 26, 45, 0.85)',
            backdropFilter: 'blur(8px)',
            zIndex: 5,
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
              filteredNodes.map((node) => {
                const isActive = node.id === activeNodeId
                return (
                  <button
                    key={node.id}
                    type="button"
                    data-testid={`branch-option-${node.id}`}
                    onClick={() => selectNodeById(node.id)}
                    style={{
                      display: 'flex',
                      flexDirection: 'column',
                      alignItems: 'flex-start',
                      gap: 4,
                      width: '100%',
                      padding: '7px 8px',
                      marginBottom: 2,
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
                        color: isActive ? '#f1f5f9' : '#cbd5e1',
                        overflow: 'hidden',
                        textOverflow: 'ellipsis',
                        whiteSpace: 'nowrap',
                        width: '100%',
                      }}
                      title={node.title}
                    >
                      {node.title || 'Thought'}
                    </span>
                    {renderModePill(node.mode || 'normal')}
                  </button>
                )
              })
            )}
          </div>
        </aside>
        <div className="flex-1 w-full h-full cursor-grab active:cursor-grabbing">
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
          linkColor={(link: any) =>
            filterMode === 'pentest'
              ? '#f59e0b'
              : COGGLE_COLORS[Math.abs(hashCode(String(link.id || '0'))) % COGGLE_COLORS.length]
          }
          linkWidth={filterMode === 'pentest' ? 2 : 2.5}
          linkDirectionalParticles={filterMode === 'pentest' ? 3 : 2}
          linkDirectionalParticleSpeed={0.006}
          linkDirectionalParticleWidth={filterMode === 'pentest' ? 3 : 2}
          linkDirectionalParticleColor={() => (filterMode === 'pentest' ? '#10b981' : '#ffffff')}
          onNodeClick={(node: any) => {
            if (node?.id) {
              selectNodeById(node.id)
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
      </div>

      {/* Bottom Info HUD */}
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
        {filterMode === 'pentest' ? 'Attack Graph Active' : 'Organic Mindmap Active'}
      </div>
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
