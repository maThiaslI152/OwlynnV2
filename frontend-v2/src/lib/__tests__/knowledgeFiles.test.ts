import { describe, expect, it } from 'vitest'
import { collapseKnowledgeFiles, knowledgeBaseName } from '../knowledgeFiles'

describe('knowledgeFiles', () => {
  it('strips chunk suffix from indexed names', () => {
    expect(knowledgeBaseName('report.pdf#chunk3')).toBe('report.pdf')
  })

  it('collapses chunk rows to one entry per source file', () => {
    const collapsed = collapseKnowledgeFiles([
      { name: 'doc.pdf#chunk0', type: 'knowledge', added_at: 1 },
      { name: 'doc.pdf#chunk1', type: 'knowledge', added_at: 2 },
      { name: 'notes.md', type: 'knowledge', added_at: 3 },
    ])
    expect(collapsed.map((f) => f.name).sort()).toEqual(['doc.pdf', 'notes.md'])
    const doc = collapsed.find((f) => f.name === 'doc.pdf')
    expect(doc?.added_at).toBe(2)
  })
})
