import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { ChatImageViewer } from '../chat/ChatImageViewer'

describe('ChatImageViewer', () => {
  it('opens lightbox on click', () => {
    render(<ChatImageViewer src="/api/files/chart.png?project_id=default" alt="Sitrep chart" />)

    fireEvent.click(screen.getByRole('button', { name: 'Expand Sitrep chart' }))

    expect(screen.getByRole('dialog', { name: 'Sitrep chart viewer' })).toBeTruthy()
    expect(screen.getByText('Open original')).toBeTruthy()
  })
})
