import { useState, useEffect, useCallback } from 'react'
import { WORKSPACE_REF_DRAG_TYPE, workspaceRefAttachment, type AttachedFile } from '../lib/attachments'

interface KnowledgeFile {
  name: string
  type: string
  added_at: number
}

function knowledgeBaseName(name: string): string {
  return name.replace(/#chunk\d+$/, '')
}

function collapseKnowledgeFiles(files: KnowledgeFile[]): KnowledgeFile[] {
  const byBase = new Map<string, KnowledgeFile>()
  for (const file of files) {
    const base = knowledgeBaseName(file.name)
    const existing = byBase.get(base)
    if (!existing || file.added_at > existing.added_at) {
      byBase.set(base, { ...file, name: base })
    }
  }
  return [...byBase.values()].sort((a, b) => b.added_at - a.added_at)
}

interface ProjectKnowledgePanelProps {
  activeProjectId: string
  onAttachToComposer?: (file: AttachedFile) => void
}

export function ProjectKnowledgePanel({
  activeProjectId,
  onAttachToComposer,
}: ProjectKnowledgePanelProps) {
  const [files, setFiles] = useState<KnowledgeFile[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const loadKnowledgeFiles = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const response = await fetch(`/api/projects/${encodeURIComponent(activeProjectId)}`)
      if (!response.ok) {
        setError('Failed to load project details')
        setFiles([])
        return
      }
      const project = await response.json()
      const knowledgeFiles: KnowledgeFile[] = collapseKnowledgeFiles(
        (project.files ?? []).filter((f: KnowledgeFile) => f.type === 'knowledge')
      )
      setFiles(knowledgeFiles)
    } catch {
      setError('Failed to load knowledge files')
      setFiles([])
    } finally {
      setLoading(false)
    }
  }, [activeProjectId])

  useEffect(() => {
    if (activeProjectId) {
      loadKnowledgeFiles()
    }
  }, [activeProjectId, loadKnowledgeFiles])

  return (
    <section className="knowledge-panel">
      <div className="knowledge-panel-header">
        <h3>Knowledge</h3>
        <button
          type="button"
          className="knowledge-refresh"
          onClick={loadKnowledgeFiles}
          disabled={loading}
        >
          {loading ? '...' : 'Refresh'}
        </button>
      </div>
      {error && <p className="knowledge-error">{error}</p>}
      {!loading && !error && files.length === 0 && (
        <div className="knowledge-empty-wrap">
          <p className="knowledge-empty">No knowledge files indexed for this project.</p>
          <p className="knowledge-empty-hint">Try adding docs like README.md, ADR.md, or API notes.</p>
        </div>
      )}
      {files.length > 0 && (
        <>
          <p className="knowledge-hint">Drag a file to the prompt to reference it.</p>
          <ul className="knowledge-list">
            {files.map((file) => (
              <li
                key={file.name}
                className="knowledge-item knowledge-item-draggable"
                draggable
                title={`Drag to prompt: ${file.name}`}
                onDragStart={(e) => {
                  e.dataTransfer.setData(
                    WORKSPACE_REF_DRAG_TYPE,
                    JSON.stringify({ name: file.name })
                  )
                  e.dataTransfer.effectAllowed = 'copy'
                }}
                onDoubleClick={() => {
                  onAttachToComposer?.(workspaceRefAttachment(file.name))
                }}
              >
                <span className="knowledge-filename" title={file.name}>
                  {file.name}
                </span>
                <span className="knowledge-meta">
                  {new Date(file.added_at * 1000).toLocaleDateString()}
                </span>
              </li>
            ))}
          </ul>
        </>
      )}
    </section>
  )
}
