import type { ContentSegment, InteractiveBlockLang } from './types'

const INTERACTIVE_LANGS = new Set<InteractiveBlockLang>([
  'owlynn-quiz',
  'owlynn-steps',
  'owlynn-callout',
  'owlynn-embed',
  'owlynn-cell',
  'owlynn-template',
  'mermaid',
])

const FENCE_OPEN = /^```([\w-]+)\s*\n?/

function isInteractiveLang(lang: string): lang is InteractiveBlockLang {
  return INTERACTIVE_LANGS.has(lang as InteractiveBlockLang)
}

/**
 * Split markdown into plain segments and interactive fenced blocks.
 * Incomplete trailing fences (streaming) are kept as markdown until closed.
 */
export function parseInteractiveBlocks(content: string): ContentSegment[] {
  const segments: ContentSegment[] = []
  let cursor = 0

  while (cursor < content.length) {
    const rest = content.slice(cursor)
    const openMatch = rest.match(FENCE_OPEN)
    if (!openMatch || openMatch.index !== 0) {
      const nextFence = rest.indexOf('```')
      if (nextFence === -1) {
        if (rest) segments.push({ type: 'markdown', content: rest })
        break
      }
      if (nextFence > 0) {
        segments.push({ type: 'markdown', content: rest.slice(0, nextFence) })
        cursor += nextFence
        continue
      }

      // We are exactly at ``` but it didn't match FENCE_OPEN (e.g. no language, or streaming).
      const endFence = rest.indexOf('```', 3)
      if (endFence === -1) {
        segments.push({ type: 'markdown', content: rest })
        break
      }
      
      const consumeLen = endFence + 3
      segments.push({ type: 'markdown', content: rest.slice(0, consumeLen) })
      cursor += consumeLen
      continue
    }

    const lang = openMatch[1]
    const openLen = openMatch[0].length
    const afterOpen = rest.slice(openLen)
    const closeIdx = afterOpen.indexOf('\n```')

    if (!isInteractiveLang(lang)) {
      if (closeIdx === -1) {
        segments.push({ type: 'markdown', content: rest })
        break
      }
      const blockEnd = openLen + closeIdx + 4
      segments.push({ type: 'markdown', content: rest.slice(0, blockEnd) })
      cursor += blockEnd
      continue
    }

    if (closeIdx === -1) {
      segments.push({
        type: 'block',
        lang,
        body: afterOpen,
        complete: false,
      })
      break
    }

    const body = afterOpen.slice(0, closeIdx).trimEnd()
    segments.push({
      type: 'block',
      lang,
      body,
      complete: true,
    })
    cursor += openLen + closeIdx + 4
  }

  // Merge adjacent markdown segments to avoid breaking react-markdown contexts
  const merged: ContentSegment[] = []
  for (const seg of segments) {
    const last = merged[merged.length - 1]
    if (last && last.type === 'markdown' && seg.type === 'markdown') {
      last.content += seg.content
    } else {
      merged.push(seg)
    }
  }

  return merged
}
