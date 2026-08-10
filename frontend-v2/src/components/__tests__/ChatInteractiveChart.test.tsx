import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { ChatInteractiveChart } from '../chat/ChatInteractiveChart'

describe('ChatInteractiveChart', () => {
  it('renders iframe and expand dialog', () => {
    render(
      <ChatInteractiveChart
        src="/api/files/chart.html?project_id=default"
        title="Sitrep chart"
      />,
    )

    expect(screen.getByTitle('Sitrep chart')).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: 'Expand' }))
    expect(screen.getByRole('dialog', { name: 'Sitrep chart expanded view' })).toBeTruthy()
  })
})
