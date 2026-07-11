import { useState, useEffect, useCallback } from 'react'
import { FileText } from 'lucide-react'

interface FileViewerModalProps {
  filename: string
  projectId: string
  onClose: () => void
}

const IMAGE_EXT = /\.(png|jpe?g|gif|webp|svg)$/i
const TEXT_EXT = /\.(txt|md|json|yaml|yml|csv|log|py|js|ts|tsx|jsx|html|css|sh|bash)$/i

export function FileViewerModal({ filename, projectId, onClose }: FileViewerModalProps) {
  const fileUrl = `/api/files/${encodeURIComponent(filename)}?project_id=${encodeURIComponent(projectId)}`

  const handleKeyDown = useCallback(
    (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    },
    [onClose],
  )

  useEffect(() => {
    document.addEventListener('keydown', handleKeyDown)
    return () => document.removeEventListener('keydown', handleKeyDown)
  }, [handleKeyDown])

  const isImage = IMAGE_EXT.test(filename)
  const isText = TEXT_EXT.test(filename)
  const isPdf = filename.toLowerCase().endsWith('.pdf')

  return (
    <div
      onClick={onClose}
      style={{
        position: 'fixed',
        inset: 0,
        zIndex: 9999,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        background: 'rgba(0,0,0,0.7)',
        backdropFilter: 'blur(4px)',
      }}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        style={{
          background: '#1a1a2e',
          border: '1px solid rgba(255,255,255,0.1)',
          borderRadius: 12,
          width: '90vw',
          height: '85vh',
          display: 'flex',
          flexDirection: 'column',
          overflow: 'hidden',
          boxShadow: '0 8px 32px rgba(0,0,0,0.5)',
        }}
      >
        {/* Header */}
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            padding: '12px 16px',
            borderBottom: '1px solid rgba(255,255,255,0.06)',
          }}
        >
          <span style={{ fontSize: 14, fontWeight: 600, color: '#e0e0e0' }}>{filename}</span>
          <div style={{ display: 'flex', gap: 8 }}>
            <a
              href={fileUrl}
              target="_blank"
              rel="noopener noreferrer"
              style={{ fontSize: 12, color: '#e94560', textDecoration: 'none' }}
            >
              Open in browser ↗
            </a>
            <button
              onClick={onClose}
              style={{
                background: 'none',
                border: 'none',
                color: '#888',
                cursor: 'pointer',
                fontSize: 16,
              }}
            >
              ✕
            </button>
          </div>
        </div>
        {/* Content */}
        <div style={{ flex: 1, overflow: 'auto' }}>
          {isPdf && (
            <iframe
              src={fileUrl}
              style={{ width: '100%', height: '100%', border: 'none' }}
              title={filename}
            />
          )}
          {isImage && (
            <div
              style={{
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                height: '100%',
                padding: 16,
              }}
            >
              <img
                src={fileUrl}
                alt={filename}
                style={{ maxWidth: '100%', maxHeight: '100%', objectFit: 'contain' }}
              />
            </div>
          )}
          {isText && <TextFileViewer url={fileUrl} />}
          {!isPdf && !isImage && !isText && (
            <div
              style={{
                display: 'flex',
                flexDirection: 'column',
                alignItems: 'center',
                justifyContent: 'center',
                height: '100%',
                gap: 16,
                color: '#888',
              }}
            >
              <FileText size={48} color="#888" />
              <p>Preview not available for this file type</p>
              <a
                href={fileUrl}
                download
                style={{
                  color: '#e94560',
                  textDecoration: 'none',
                  padding: '8px 16px',
                  border: '1px solid #e94560',
                  borderRadius: 8,
                }}
              >
                Download file
              </a>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

function TextFileViewer({ url }: { url: string }) {
  const [content, setContent] = useState<string | null>(null)
  const [error, setError] = useState(false)

  useEffect(() => {
    fetch(`${url}&mode=text`)
      .then((r) => (r.ok ? r.text() : Promise.reject()))
      .then(setContent)
      .catch(() => setError(true))
  }, [url])

  if (error) return <div style={{ padding: 16, color: '#888' }}>Failed to load file</div>
  if (content === null) return <div style={{ padding: 16, color: '#888' }}>Loading...</div>

  return (
    <pre
      style={{
        padding: 16,
        margin: 0,
        fontSize: 13,
        lineHeight: 1.5,
        color: '#e0e0e0',
        whiteSpace: 'pre-wrap',
        wordBreak: 'break-word',
      }}
    >
      {content}
    </pre>
  )
}
