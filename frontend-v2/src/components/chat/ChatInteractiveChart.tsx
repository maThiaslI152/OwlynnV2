import { useCallback, useEffect, useState } from 'react'
import { createPortal } from 'react-dom'

interface ChatInteractiveChartProps {
  src: string
  title?: string
}

function ChartFrame({ src, title, className }: { src: string; title: string; className: string }) {
  return (
    <iframe
      className={className}
      src={src}
      title={title}
      loading="lazy"
      sandbox="allow-scripts allow-same-origin allow-popups"
    />
  )
}

export function ChatInteractiveChart({ src, title = 'Interactive chart' }: ChatInteractiveChartProps) {
  const [expanded, setExpanded] = useState(false)

  const closeExpanded = useCallback(() => setExpanded(false), [])

  useEffect(() => {
    if (!expanded) return undefined
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') closeExpanded()
    }
    const previousOverflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    window.addEventListener('keydown', onKeyDown)
    return () => {
      document.body.style.overflow = previousOverflow
      window.removeEventListener('keydown', onKeyDown)
    }
  }, [closeExpanded, expanded])

  return (
    <>
      <div className="msg-interactive-chart">
        <ChartFrame src={src} title={title} className="msg-interactive-chart-frame" />
        <div className="msg-interactive-chart-actions">
          <button type="button" className="msg-interactive-chart-btn" onClick={() => setExpanded(true)}>
            Expand
          </button>
          <a
            className="msg-interactive-chart-btn"
            href={src}
            target="_blank"
            rel="noopener noreferrer"
          >
            Open in new tab
          </a>
        </div>
      </div>
      {expanded &&
        createPortal(
          <div
            className="chat-interactive-chart-lightbox"
            onClick={closeExpanded}
            role="dialog"
            aria-modal="true"
            aria-label={`${title} expanded view`}
          >
            <div className="chat-interactive-chart-lightbox-toolbar" onClick={(event) => event.stopPropagation()}>
              <span className="chat-interactive-chart-lightbox-title">{title}</span>
              <button type="button" className="chat-interactive-chart-lightbox-btn" onClick={closeExpanded}>
                Close
              </button>
            </div>
            <div className="chat-interactive-chart-lightbox-stage" onClick={(event) => event.stopPropagation()}>
              <ChartFrame src={src} title={title} className="msg-interactive-chart-frame is-expanded" />
            </div>
          </div>,
          document.body,
        )}
    </>
  )
}
