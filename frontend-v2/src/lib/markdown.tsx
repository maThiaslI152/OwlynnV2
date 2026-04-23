interface MarkdownSegment {
  type: 'text' | 'bold' | 'inline-code' | 'code-block' | 'link'
  content: string
  href?: string
  language?: string
}

/**
 * Lightweight markdown parser that handles common patterns.
 * Intentionally minimal — no full spec compliance, just the most useful
 * subset for chat messages: code blocks, bold, inline code, links.
 */
export function parseMarkdown(text: string): MarkdownSegment[] {
  const segments: MarkdownSegment[] = []
  let remaining = text

  while (remaining.length > 0) {
    // Code block (```lang\\n...\\n```)
    const codeBlockMatch = remaining.match(/^```(\w*)\n([\s\S]*?)```/)
    if (codeBlockMatch) {
      if (codeBlockMatch.index !== 0) {
        segments.push({ type: 'text', content: remaining.slice(0, codeBlockMatch.index) })
      }
      segments.push({
        type: 'code-block',
        content: codeBlockMatch[2],
        language: codeBlockMatch[1] || undefined,
      })
      remaining = remaining.slice(codeBlockMatch.index! + codeBlockMatch[0].length)
      continue
    }

    // Inline code (`code`)
    const inlineCodeMatch = remaining.match(/^`([^`]+)`/)
    if (inlineCodeMatch) {
      if (inlineCodeMatch.index !== 0) {
        segments.push({ type: 'text', content: remaining.slice(0, inlineCodeMatch.index) })
      }
      segments.push({ type: 'inline-code', content: inlineCodeMatch[1] })
      remaining = remaining.slice(inlineCodeMatch.index! + inlineCodeMatch[0].length)
      continue
    }

    // Bold (**text**)
    const boldMatch = remaining.match(/^\*\*([^*]+)\*\*/)
    if (boldMatch) {
      if (boldMatch.index !== 0) {
        segments.push({ type: 'text', content: remaining.slice(0, boldMatch.index) })
      }
      segments.push({ type: 'bold', content: boldMatch[1] })
      remaining = remaining.slice(boldMatch.index! + boldMatch[0].length)
      continue
    }

    // Link ([text](url))
    const linkMatch = remaining.match(/^\[([^\]]+)\]\(([^)]+)\)/)
    if (linkMatch) {
      if (linkMatch.index !== 0) {
        segments.push({ type: 'text', content: remaining.slice(0, linkMatch.index) })
      }
      segments.push({ type: 'link', content: linkMatch[1], href: linkMatch[2] })
      remaining = remaining.slice(linkMatch.index! + linkMatch[0].length)
      continue
    }

    // Plain text up to next special char
    const nextSpecial = remaining.search(/(?:\*\*|`|\[|```)/)
    if (nextSpecial === 0) {
      // Shouldn't happen with the above checks, but safety valve
      segments.push({ type: 'text', content: remaining[0] })
      remaining = remaining.slice(1)
    } else if (nextSpecial > 0) {
      segments.push({ type: 'text', content: remaining.slice(0, nextSpecial) })
      remaining = remaining.slice(nextSpecial)
    } else {
      segments.push({ type: 'text', content: remaining })
      remaining = ''
    }
  }

  return segments
}

/**
 * Renders markdown segments into an array of React nodes.
 */
export function renderMarkdownSegments(
  segments: MarkdownSegment[],
  keyPrefix: string
): React.ReactNode[] {
  return segments.map((seg, i) => {
    const key = `${keyPrefix}-seg-${i}`
    switch (seg.type) {
      case 'bold':
        return <strong key={key}>{seg.content}</strong>
      case 'inline-code':
        return <code key={key} className="msg-inline-code">{seg.content}</code>
      case 'code-block':
        return (
          <pre key={key} className="msg-code-block">
            {seg.language && <span className="msg-code-lang">{seg.language}</span>}
            <code>{seg.content}</code>
          </pre>
        )
      case 'link':
        return (
          <a key={key} className="msg-link" href={seg.href} target="_blank" rel="noopener noreferrer">
            {seg.content}
          </a>
        )
      default:
        return renderTextWithNewlines(seg.content, key)
    }
  })
}

function renderTextWithNewlines(text: string, key: string): React.ReactNode {
  const parts = text.split('\n')
  if (parts.length === 1) return text
  return parts.map((part, i) => (
    <span key={`${key}-nl-${i}`}>
      {part}
      {i < parts.length - 1 && <br />}
    </span>
  ))
}
