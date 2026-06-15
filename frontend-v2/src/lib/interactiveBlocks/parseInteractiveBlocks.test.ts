import { describe, expect, it } from 'vitest'
import { parseInteractiveBlocks } from './parseInteractiveBlocks'

describe('parseInteractiveBlocks', () => {
  it('splits markdown around owlynn-quiz fence', () => {
    const input = 'Intro\n\n```owlynn-quiz\n{"question":"Q?","options":["A","B"],"correctIndex":0}\n```\n\nOutro'
    const segments = parseInteractiveBlocks(input)
    expect(segments).toHaveLength(3)
    expect(segments[0]).toMatchObject({ type: 'markdown', content: 'Intro\n\n' })
    expect(segments[1]).toMatchObject({ type: 'block', lang: 'owlynn-quiz', complete: true })
    expect(segments[2]).toMatchObject({ type: 'markdown', content: '\n\nOutro' })
  })

  it('keeps incomplete fence as pending block', () => {
    const input = '```owlynn-steps\n{"steps":[{"heading":"One","body":"Body"}'
    const segments = parseInteractiveBlocks(input)
    expect(segments).toHaveLength(1)
    expect(segments[0]).toMatchObject({ type: 'block', lang: 'owlynn-steps', complete: false })
  })

  it('passes regular code fences through as markdown', () => {
    const input = '```python\nprint("hi")\n```'
    const segments = parseInteractiveBlocks(input)
    expect(segments).toHaveLength(1)
    expect(segments[0]).toMatchObject({ type: 'markdown' })
  })

  it('parses mermaid blocks', () => {
    const input = '```mermaid\ngraph LR\n  A --> B\n```'
    const segments = parseInteractiveBlocks(input)
    expect(segments[0]).toMatchObject({ type: 'block', lang: 'mermaid', complete: true })
  })
})
