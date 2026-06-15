import { describe, expect, it } from 'vitest'
import { isToolPreambleText } from './toolPreamble'

describe('isToolPreambleText', () => {
  it('detects read_workspace placeholder', () => {
    expect(isToolPreambleText('Reading workspace file…')).toBe(true)
  })

  it('allows real assistant answers', () => {
    expect(isToolPreambleText('Here is your study guide for chapter 1.')).toBe(false)
  })
})
