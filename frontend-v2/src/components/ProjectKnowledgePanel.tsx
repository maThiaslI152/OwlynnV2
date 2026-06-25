import { useState, useEffect, useCallback } from 'react'
import toast from 'react-hot-toast'
import { WORKSPACE_REF_DRAG_TYPE, workspaceRefAttachment, type AttachedFile } from '../lib/attachments'
import { collapseKnowledgeFiles, type KnowledgeFileRow } from '../lib/knowledgeFiles'

type KnowledgeFile = KnowledgeFileRow

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
  const [indexingStates, setIndexingStates] = useState<Record<string, { status: string; chunks?: number; error?: string; timestamp?: number }>>({})

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
      toast.error('Failed to load knowledge files')
      setFiles([])
    } finally {
      setLoading(false)
    }
  }, [activeProjectId])

  useEffect(() => {
    if (activeProjectId) {
      // eslint-disable-next-line react-hooks/set-state-in-effect
      loadKnowledgeFiles()
    }
  }, [activeProjectId, loadKnowledgeFiles])

  useEffect(() => {
    const handleFileStatus = (e: Event) => {
      const detail = (e as CustomEvent).detail
      if (detail && detail.name) {
        const nowSec = Math.floor(Date.now() / 1000)
        setIndexingStates((prev) => ({
          ...prev,
          [detail.name]: {
            status: detail.status,
            chunks: detail.chunks,
            error: detail.error,
            timestamp: prev[detail.name]?.timestamp || nowSec,
          },
        }))
        if (
          detail.status === 'indexed' ||
          detail.status === 'indexing_failed' ||
          detail.status === 'deleted'
        ) {
          void loadKnowledgeFiles()
        }
      }
    }
    window.addEventListener('owlynn:file_status', handleFileStatus)
    return () => {
      window.removeEventListener('owlynn:file_status', handleFileStatus)
    }
  }, [loadKnowledgeFiles])

  const renderedFiles = [...files]
  Object.entries(indexingStates).forEach(([name, state]) => {
    if (state.status === 'indexing' && !files.some((f) => f.name === name)) {
      renderedFiles.push({
        name,
        type: 'knowledge',
        added_at: (state as any).timestamp || 0,
      })
    }
  })

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
      {!loading && !error && renderedFiles.length === 0 && (
        <div className="knowledge-empty-wrap">
          <p className="knowledge-empty">No knowledge files indexed for this project.</p>
          <p className="knowledge-empty-hint">Try adding docs like README.md, ADR.md, or API notes.</p>
        </div>
      )}
      {renderedFiles.length > 0 && (
        <>
          <p className="knowledge-hint">Drag a file to the prompt to reference it.</p>
          <ul className="knowledge-list">
            {renderedFiles.map((file) => {
              const indexing = indexingStates[file.name]
              return (
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
                  <div className="knowledge-item-left">
                    <span className="knowledge-filename" title={file.name}>
                      {file.name}
                    </span>
                    {indexing && (
                      <span className={`knowledge-status-chip ${indexing.status}`} style={{ fontSize: '0.7rem', opacity: 0.85 }}>
                        {indexing.status === 'indexing' && ' ⏳ indexing...'}
                        {indexing.status === 'indexed' && ` ✅ (${indexing.chunks || 0} chk)`}
                        {indexing.status === 'indexing_failed' && ' ❌ failed'}
                      </span>
                    )}
                  </div>
                  <span className="knowledge-meta">
                    {file.added_at > 0 ? new Date(file.added_at * 1000).toLocaleDateString() : 'Just now'}
                  </span>
                </li>
              )
            })}
          </ul>
        </>
      )}
    </section>
  )
}
