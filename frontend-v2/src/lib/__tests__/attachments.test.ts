import { describe, expect, it } from 'vitest'
import { isWorkspaceRef, toWsFilePayload, workspaceRefAttachment } from '../attachments'

describe('attachments', () => {
  it('builds workspace_ref ws payload', () => {
    const file = workspaceRefAttachment('report.pdf')
    expect(isWorkspaceRef(file)).toBe(true)
    expect(toWsFilePayload(file)).toEqual({
      type: 'workspace_ref',
      name: 'report.pdf',
      path: 'report.pdf',
      data: '',
    })
  })
})
