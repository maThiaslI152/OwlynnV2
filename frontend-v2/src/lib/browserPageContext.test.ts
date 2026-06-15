import { describe, expect, it } from 'vitest'
import { buildPageContextDraft } from './browserPageContext'

describe('buildPageContextDraft', () => {
  it('builds prompt with title and url', () => {
    const draft = buildPageContextDraft({
      url: 'https://example.com',
      title: 'Example',
      text: '',
      selection: '',
    })
    expect(draft).toContain('Help me with this page: Example')
    expect(draft).toContain('https://example.com')
  })

  it('prefers selection over full page text', () => {
    const draft = buildPageContextDraft({
      url: 'https://example.com',
      title: 'Example',
      text: 'Full page body',
      selection: 'Highlighted phrase',
    })
    expect(draft).toContain('Selected text:')
    expect(draft).toContain('Highlighted phrase')
    expect(draft).not.toContain('Page excerpt:')
  })

  it('includes page excerpt when no selection', () => {
    const draft = buildPageContextDraft({
      url: 'https://example.com',
      title: 'Example',
      text: 'Article body content',
      selection: '',
    })
    expect(draft).toContain('Page excerpt:')
    expect(draft).toContain('Article body content')
  })
})
