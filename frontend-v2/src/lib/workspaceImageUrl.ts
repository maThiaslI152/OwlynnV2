const IMAGE_EXT = /\.(png|jpe?g|gif|webp|svg)$/i
const INTERACTIVE_CHART_EXT = /\.html$/i

/** Map workspace / bare paths to the Owlynn files API. */
export function resolveWorkspaceFileUrl(src: string, projectId: string): string {
  const trimmed = src.trim()
  if (!trimmed) return trimmed

  if (trimmed.startsWith('data:') || /^https?:\/\//i.test(trimmed)) {
    return trimmed
  }

  if (trimmed.startsWith('/api/files/')) {
    if (trimmed.includes('project_id=')) return trimmed
    const sep = trimmed.includes('?') ? '&' : '?'
    return `${trimmed}${sep}project_id=${encodeURIComponent(projectId)}`
  }

  const normalized = trimmed.replace(/\\/g, '/')
  const workspaceTail = normalized.match(/(?:^|\/)projects\/[^/]+\/([^/?#]+)$/i)
  const filename = workspaceTail?.[1] ?? normalized.split('/').pop() ?? trimmed

  if (IMAGE_EXT.test(filename) || INTERACTIVE_CHART_EXT.test(filename)) {
    return `/api/files/${encodeURIComponent(filename)}?project_id=${encodeURIComponent(projectId)}`
  }

  return trimmed
}

/** @deprecated Use resolveWorkspaceFileUrl */
export const resolveWorkspaceImageUrl = resolveWorkspaceFileUrl

export function isInteractiveChartUrl(url: string): boolean {
  return INTERACTIVE_CHART_EXT.test(url.split('?')[0]?.split('#')[0] ?? '')
}

export function isWorkspaceImageUrl(url: string): boolean {
  const path = url.split('?')[0]?.split('#')[0] ?? ''
  return IMAGE_EXT.test(path) && !INTERACTIVE_CHART_EXT.test(path)
}

/** Rewrite markdown image targets before ReactMarkdown parses them. */
export function rewriteWorkspaceImageMarkdown(content: string, projectId: string): string {
  return content.replace(/!\[([^\]]*)\]\(([^)]+)\)/g, (match, alt, src) => {
    const resolved = resolveWorkspaceFileUrl(src, projectId)
    return resolved === src ? match : `![${alt}](${resolved})`
  })
}
