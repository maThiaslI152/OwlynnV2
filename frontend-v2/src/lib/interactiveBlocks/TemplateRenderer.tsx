import { useEffect, useState } from 'react'
import { InteractiveBlockRenderer } from './InteractiveBlockRenderer'
import type { ParsedBlockSegment } from './types'

const templateCache = new Map<string, ParsedBlockSegment>()

interface Props {
  templateId: string
  projectId: string
  threadId: string
}

export function TemplateRenderer({ templateId, projectId, threadId }: Props) {
  const [segment, setSegment] = useState<ParsedBlockSegment | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let mounted = true

    async function fetchTemplate() {
      if (templateCache.has(templateId)) {
        setSegment(templateCache.get(templateId)!)
        return
      }

      try {
        const res = await fetch(`/api/templates/${templateId}`)
        if (!res.ok) {
          throw new Error('Template not found')
        }
        const data = await res.json()
        if (mounted && data.template) {
          const seg: ParsedBlockSegment = {
            type: 'block',
            lang: `owlynn-${data.template.type}` as any,
            body: JSON.stringify(data.template.payload),
            complete: true
          }
          templateCache.set(templateId, seg)
          setSegment(seg)
        }
      } catch (err: any) {
        if (mounted) setError(err.message)
      }
    }

    void fetchTemplate()

    return () => {
      mounted = false
    }
  }, [templateId])

  if (error) {
    return <div className="owlynn-block owlynn-block-error">Failed to load template: {error}</div>
  }

  if (!segment) {
    return <div className="owlynn-block owlynn-block-pending">Loading template {templateId}…</div>
  }

  return <InteractiveBlockRenderer segment={segment} projectId={projectId} threadId={threadId} />
}
