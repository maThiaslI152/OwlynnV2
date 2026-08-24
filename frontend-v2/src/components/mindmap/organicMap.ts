/** Organic mindmap fade, grouping, and force helpers (no thread-ID merge). */

export interface OrganicVisualNode {
  id: string
  title?: string
  mode?: string
  pinned?: boolean
  is_dormant?: boolean
  fade_alpha?: number
  visual_mode?: string
  topic_cluster_id?: string | null
  topic_label?: string | null
  allow_radial_drift?: boolean
  radial_tier?: number
  radial_multiplier?: number
  canvas_x?: number | null
  canvas_y?: number | null
  importance_score?: number
  last_active_at?: number
  dormancy_score?: number
  fx?: number
  fy?: number
  x?: number
  y?: number
  vx?: number
  vy?: number
}

export interface BranchGroup {
  id: string
  label: string
  nodes: OrganicVisualNode[]
}

const UNGROUPED_ID = '_ungrouped'

export function nodeDisplayAlpha(
  node: OrganicVisualNode,
  opts: { isActive: boolean; searching: boolean },
): number {
  if (opts.searching || opts.isActive || node.pinned || node.visual_mode === 'pinned') {
    return 1
  }
  if (typeof node.fade_alpha === 'number') {
    return Math.min(1, Math.max(0.28, node.fade_alpha))
  }
  if (node.is_dormant || node.visual_mode === 'dormant') {
    return 0.4
  }
  return 1
}

export function branchRowOpacity(
  node: OrganicVisualNode,
  opts: { isActive: boolean; searching: boolean },
): number {
  if (opts.searching || opts.isActive || node.pinned) return 1
  if (node.is_dormant || node.visual_mode === 'dormant') {
    return Math.max(0.4, typeof node.fade_alpha === 'number' ? node.fade_alpha : 0.45)
  }
  if (typeof node.fade_alpha === 'number' && node.fade_alpha < 0.9) {
    return Math.max(0.55, node.fade_alpha)
  }
  return 1
}

export function shouldRadialDrift(node: OrganicVisualNode): boolean {
  if (node.pinned || node.visual_mode === 'pinned') return false
  if (node.fx != null || node.fy != null) return false
  if (node.canvas_x != null && node.canvas_y != null) return false
  return Boolean(node.allow_radial_drift)
}

export function linkParticleCount(opts: {
  pentest: boolean
  searching: boolean
  dormantLink: boolean
}): number {
  if (opts.pentest) return 3
  if (opts.searching) return 2
  if (opts.dormantLink) return 0
  return 2
}

export function hexToRgba(hex: string, alpha: number): string {
  const raw = hex.replace('#', '')
  if (raw.length !== 6) return `rgba(148, 163, 184, ${alpha})`
  const n = Number.parseInt(raw, 16)
  const r = (n >> 16) & 255
  const g = (n >> 8) & 255
  const b = n & 255
  return `rgba(${r}, ${g}, ${b}, ${alpha})`
}

export function resolveLinkNodeId(end: unknown): string | null {
  if (typeof end === 'string') return end
  if (end && typeof end === 'object' && 'id' in end) {
    const id = (end as { id?: unknown }).id
    return typeof id === 'string' ? id : null
  }
  return null
}

export function linkIsDormant(
  link: { source?: unknown; target?: unknown },
  nodeById: Map<string, OrganicVisualNode>,
): boolean {
  const s = resolveLinkNodeId(link.source)
  const t = resolveLinkNodeId(link.target)
  const sn = s ? nodeById.get(s) : undefined
  const tn = t ? nodeById.get(t) : undefined
  const dormant = (n?: OrganicVisualNode) =>
    Boolean(n?.is_dormant || n?.visual_mode === 'dormant')
  return dormant(sn) || dormant(tn)
}

export function groupBranchNodes(nodes: OrganicVisualNode[]): BranchGroup[] {
  const buckets = new Map<string, BranchGroup>()
  for (const node of nodes) {
    const id = node.topic_cluster_id || UNGROUPED_ID
    const label =
      id === UNGROUPED_ID ? 'Other' : node.topic_label?.trim() || 'Related theme'
    const bucket = buckets.get(id) ?? { id, label, nodes: [] }
    if (node.topic_label?.trim()) bucket.label = node.topic_label.trim()
    bucket.nodes.push(node)
    buckets.set(id, bucket)
  }

  const dormantRank = (n: OrganicVisualNode) =>
    n.is_dormant || n.visual_mode === 'dormant' ? 1 : 0

  for (const group of buckets.values()) {
    group.nodes.sort((a, b) => {
      const d = dormantRank(a) - dormantRank(b)
      if (d !== 0) return d
      const imp = (b.importance_score ?? 0) - (a.importance_score ?? 0)
      if (imp !== 0) return imp
      return (a.title || '').localeCompare(b.title || '')
    })
  }

  return [...buckets.values()].sort((a, b) => {
    if (a.id === UNGROUPED_ID) return 1
    if (b.id === UNGROUPED_ID) return -1
    const aActive = a.nodes.some((n) => dormantRank(n) === 0)
    const bActive = b.nodes.some((n) => dormantRank(n) === 0)
    if (aActive !== bActive) return aActive ? -1 : 1
    return a.label.localeCompare(b.label)
  })
}

export function mergeRevivedNode<T extends OrganicVisualNode>(current: T, revived: T): T {
  return {
    ...current,
    ...revived,
    fx: current.fx,
    fy: current.fy,
    x: current.x,
    y: current.y,
    is_dormant: false,
    fade_alpha: 1,
    dormancy_score: 0,
    visual_mode: revived.pinned ? 'pinned' : 'active',
    allow_radial_drift: false,
    radial_tier: 0,
    radial_multiplier: 1,
  } as T & { dormancy_score?: number }
}

type SimNode = OrganicVisualNode

/** Compatible with react-force-graph ForceFn initialize signature. */
function createForce(tick: (nodes: SimNode[], alpha: number) => void) {
  let nodes: SimNode[] = []
  const force = (alpha: number) => {
    tick(nodes, alpha)
  }
  force.initialize = (next: object[]) => {
    nodes = next as SimNode[]
  }
  return force
}

/** Push unplaced dormant nodes outward; never fights saved canvas_x/y (fx/fy). */
export function createDormancyRadialForce() {
  return createForce((nodes, alpha) => {
    const k = 0.05 * alpha
    for (const node of nodes) {
      if (!shouldRadialDrift(node)) continue
      const x = node.x ?? 0
      const y = node.y ?? 0
      const r = Math.hypot(x, y) || 0.001
      const tier = node.radial_tier ?? 0
      const mult = node.radial_multiplier ?? 1
      const target = 50 + tier * 70 * mult
      const delta = target - r
      node.vx = (node.vx ?? 0) + (x / r) * delta * k
      node.vy = (node.vy ?? 0) + (y / r) * delta * k
    }
  })
}

/** Gentle pull among same-cluster siblings without merging identities. */
export function createClusterCohesionForce() {
  return createForce((nodes, alpha) => {
    const groups = new Map<string, SimNode[]>()
    for (const node of nodes) {
      const cid = node.topic_cluster_id
      if (!cid) continue
      const list = groups.get(cid)
      if (list) list.push(node)
      else groups.set(cid, [node])
    }
    const k = 0.025 * alpha
    for (const members of groups.values()) {
      if (members.length < 2) continue
      let sx = 0
      let sy = 0
      let count = 0
      for (const node of members) {
        if (typeof node.x !== 'number' || typeof node.y !== 'number') continue
        sx += node.x
        sy += node.y
        count += 1
      }
      if (!count) continue
      const cx = sx / count
      const cy = sy / count
      for (const node of members) {
        if (node.fx != null || node.fy != null) continue
        if (typeof node.x !== 'number' || typeof node.y !== 'number') continue
        node.vx = (node.vx ?? 0) + (cx - node.x) * k
        node.vy = (node.vy ?? 0) + (cy - node.y) * k
      }
    }
  })
}
