import { useCallback, useEffect, useRef, useState, type WheelEvent } from 'react'
import { createPortal } from 'react-dom'

interface ChatImageViewerProps {
  src: string
  alt?: string
}

export function ChatImageViewer({ src, alt = 'Chart' }: ChatImageViewerProps) {
  const [open, setOpen] = useState(false)
  const [scale, setScale] = useState(1)
  const [offset, setOffset] = useState({ x: 0, y: 0 })
  const dragRef = useRef<{ active: boolean; startX: number; startY: number; baseX: number; baseY: number }>({
    active: false,
    startX: 0,
    startY: 0,
    baseX: 0,
    baseY: 0,
  })

  const resetView = useCallback(() => {
    setScale(1)
    setOffset({ x: 0, y: 0 })
  }, [])

  const openViewer = () => {
    resetView()
    setOpen(true)
  }

  const closeViewer = useCallback(() => setOpen(false), [])

  const clampScale = (value: number) => Math.min(4, Math.max(0.5, value))

  const zoomBy = useCallback((delta: number) => {
    setScale((current) => clampScale(+(current + delta).toFixed(2)))
  }, [])

  useEffect(() => {
    if (!open) return undefined
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') closeViewer()
    }
    const previousOverflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    window.addEventListener('keydown', onKeyDown)
    return () => {
      document.body.style.overflow = previousOverflow
      window.removeEventListener('keydown', onKeyDown)
    }
  }, [closeViewer, open])

  const onWheel = (event: WheelEvent<HTMLDivElement>) => {
    event.preventDefault()
    zoomBy(event.deltaY < 0 ? 0.12 : -0.12)
  }

  const onPointerDown = (event: React.PointerEvent<HTMLImageElement>) => {
    if (scale <= 1) return
    dragRef.current = {
      active: true,
      startX: event.clientX,
      startY: event.clientY,
      baseX: offset.x,
      baseY: offset.y,
    }
    event.currentTarget.setPointerCapture(event.pointerId)
  }

  const onPointerMove = (event: React.PointerEvent<HTMLImageElement>) => {
    if (!dragRef.current.active) return
    setOffset({
      x: dragRef.current.baseX + (event.clientX - dragRef.current.startX),
      y: dragRef.current.baseY + (event.clientY - dragRef.current.startY),
    })
  }

  const onPointerUp = (event: React.PointerEvent<HTMLImageElement>) => {
    dragRef.current.active = false
    if (event.currentTarget.hasPointerCapture(event.pointerId)) {
      event.currentTarget.releasePointerCapture(event.pointerId)
    }
  }

  return (
    <>
      <button
        type="button"
        className="msg-inline-image-wrap"
        onClick={openViewer}
        aria-label={`Expand ${alt}`}
      >
        <img className="msg-inline-image" src={src} alt={alt} loading="lazy" />
        <span className="msg-inline-image-hint">Click to expand · scroll or drag when zoomed</span>
      </button>
      {open &&
        createPortal(
          <div
            className="chat-image-lightbox"
            onClick={closeViewer}
            role="dialog"
            aria-modal="true"
            aria-label={`${alt} viewer`}
          >
            <div className="chat-image-lightbox-toolbar" onClick={(event) => event.stopPropagation()}>
              <button type="button" className="chat-image-lightbox-btn" onClick={() => zoomBy(-0.25)}>
                −
              </button>
              <span className="chat-image-lightbox-scale">{Math.round(scale * 100)}%</span>
              <button type="button" className="chat-image-lightbox-btn" onClick={() => zoomBy(0.25)}>
                +
              </button>
              <button type="button" className="chat-image-lightbox-btn" onClick={resetView}>
                Reset
              </button>
              <a
                className="chat-image-lightbox-btn chat-image-lightbox-link"
                href={src}
                target="_blank"
                rel="noopener noreferrer"
              >
                Open original
              </a>
              <button type="button" className="chat-image-lightbox-btn" onClick={closeViewer}>
                Close
              </button>
            </div>
            <div
              className="chat-image-lightbox-stage"
              onClick={(event) => event.stopPropagation()}
              onWheel={onWheel}
            >
              <img
                className={`chat-image-lightbox-image${scale > 1 ? ' is-pannable' : ''}`}
                src={src}
                alt={alt}
                draggable={false}
                style={{ transform: `translate(${offset.x}px, ${offset.y}px) scale(${scale})` }}
                onPointerDown={onPointerDown}
                onPointerMove={onPointerMove}
                onPointerUp={onPointerUp}
                onPointerCancel={onPointerUp}
              />
            </div>
          </div>,
          document.body,
        )}
    </>
  )
}
