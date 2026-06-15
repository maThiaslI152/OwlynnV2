import { describe, expect, it } from 'vitest'
import {
  isInteractiveChartUrl,
  isWorkspaceImageUrl,
  resolveWorkspaceFileUrl,
  rewriteWorkspaceImageMarkdown,
} from '../workspaceImageUrl'

describe('resolveWorkspaceImageUrl', () => {
  it('maps bare png filename to files API', () => {
    expect(resolveWorkspaceFileUrl('ukraine_war_sitrep_2026.png', 'default')).toBe(
      '/api/files/ukraine_war_sitrep_2026.png?project_id=default',
    )
  })

  it('maps plotly html filename to files API', () => {
    expect(resolveWorkspaceFileUrl('ukraine_sitrep.html', 'default')).toBe(
      '/api/files/ukraine_sitrep.html?project_id=default',
    )
  })

  it('detects interactive chart urls', () => {
    expect(isInteractiveChartUrl('/api/files/chart.html?project_id=default')).toBe(true)
    expect(isWorkspaceImageUrl('/api/files/chart.png?project_id=default')).toBe(true)
  })

  it('maps absolute workspace path to files API', () => {
    expect(
      resolveWorkspaceFileUrl(
        '/Users/tim/Works/OwlynnV2/workspace/projects/default/chart.png',
        'proj-1',
      ),
    ).toBe('/api/files/chart.png?project_id=proj-1')
  })

  it('adds project_id to existing api path', () => {
    expect(resolveWorkspaceFileUrl('/api/files/chart.png', 'default')).toBe(
      '/api/files/chart.png?project_id=default',
    )
  })

  it('leaves external http urls unchanged', () => {
    expect(resolveWorkspaceFileUrl('https://example.com/a.png', 'default')).toBe(
      'https://example.com/a.png',
    )
  })
})

describe('rewriteWorkspaceImageMarkdown', () => {
  it('rewrites markdown image syntax', () => {
    const input = '![Sitrep](ukraine_war_sitrep_2026.png)'
    expect(rewriteWorkspaceImageMarkdown(input, 'default')).toBe(
      '![Sitrep](/api/files/ukraine_war_sitrep_2026.png?project_id=default)',
    )
  })
})
