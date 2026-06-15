import { useEffect, useId, useRef, useState } from 'react'

interface Props {
  source: string
}

export function InteractiveMermaid({ source }: Props) {
  const containerRef = useRef<HTMLDivElement>(null)
  const uniqueId = useId().replace(/:/g, '')
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    const render = async () => {
      try {
        const mermaid = (await import('mermaid')).default
        mermaid.initialize({ startOnLoad: false, theme: 'dark', securityLevel: 'strict' })
        const { svg } = await mermaid.render(`owlynn-mmd-${uniqueId}`, source.trim())
        if (!cancelled && containerRef.current) {
          containerRef.current.innerHTML = svg
          setError(null)
        }
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : 'Failed to render diagram')
        }
      }
    }
    void render()
    return () => {
      cancelled = true
    }
  }, [source, uniqueId])

  if (error) {
    return (
      <div className="owlynn-block owlynn-block-mermaid owlynn-block-error">
        <pre className="owlynn-block-mermaid-fallback">{source}</pre>
        <p className="owlynn-block-error-msg">{error}</p>
      </div>
    )
  }

  return (
    <div className="owlynn-block owlynn-block-mermaid">
      <div ref={containerRef} className="owlynn-block-mermaid-svg" />
    </div>
  )
}
