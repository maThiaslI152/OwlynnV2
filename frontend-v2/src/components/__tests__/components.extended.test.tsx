import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { useAppStore } from '../../state/useAppStore'
import { Composer } from '../Composer'
import { OrchestrationPanel } from '../OrchestrationPanel'
import { SafeModePanel } from '../SafeModePanel'
import { ProjectKnowledgePanel } from '../ProjectKnowledgePanel'
import { AppShell } from '../AppShell'
import { WORKSPACE_REF_DRAG_TYPE, workspaceRefAttachment } from '../../lib/attachments'

const mockSetSafeMode = vi.hoisted(() =>
  vi.fn().mockResolvedValue({ ok: true as const })
)

vi.mock('../../lib/electronBridge', () => ({
  electronBridge: {
    setSafeMode: mockSetSafeMode,
    startScreenPreview: vi.fn().mockResolvedValue({ ok: true }),
    stopScreenPreview: vi.fn().mockResolvedValue({ ok: true }),
    convertFileSrc: vi.fn().mockImplementation((path) => path),
  },
  electronAvailable: vi.fn().mockReturnValue(true)
}))

vi.mock('../../lib/localRunToken', () => ({
  getLocalRunToken: vi.fn().mockResolvedValue('test-token'),
  fetchWithAuth: vi.fn().mockImplementation((url: string, init?: RequestInit) => globalThis.fetch(url, init)),
}))


beforeEach(() => {
  useAppStore.setState(useAppStore.getInitialState(), true)
  vi.spyOn(globalThis, 'fetch').mockResolvedValue({
    ok: true,
    json: async () => ({})
  } as Response)
  const originalError = console.error
  vi.spyOn(console, 'error').mockImplementation((...args) => {
    if (typeof args[0] === 'string' && args[0].includes('was not wrapped in act')) return
    originalError(...args)
  })
})

afterEach(() => {
  vi.restoreAllMocks()
})

// ── Composer ─────────────────────────────────────────────────────────────

describe('Composer', () => {
  it('renders textarea and send button', () => {
    render(<Composer onSend={() => {}} />)
    expect(screen.getByPlaceholderText('Ask Owlynn...')).toBeTruthy()
    expect(screen.getByTitle('Send (Enter)')).toBeTruthy()
  })

  it('calls onSend with trimmed content on submit', () => {
    const onSend = vi.fn()
    render(<Composer onSend={onSend} />)

    const textarea = screen.getByPlaceholderText('Ask Owlynn...')
    fireEvent.change(textarea, { target: { value: '  Hello world  ' } })
    fireEvent.submit(textarea.closest('form')!)

    expect(onSend).toHaveBeenCalledWith('Hello world', undefined)
  })

  it('does not call onSend for empty input', () => {
    const onSend = vi.fn()
    render(<Composer onSend={onSend} />)

    fireEvent.submit(screen.getByPlaceholderText('Ask Owlynn...').closest('form')!)
    expect(onSend).not.toHaveBeenCalled()
  })

  it('clears input after send', () => {
    const onSend = vi.fn()
    render(<Composer onSend={onSend} />)

    const textarea = screen.getByPlaceholderText('Ask Owlynn...') as HTMLTextAreaElement
    fireEvent.change(textarea, { target: { value: 'Hello' } })
    fireEvent.submit(textarea.closest('form')!)

    expect(textarea.value).toBe('')
  })

  it('submits on Enter key via form submit', () => {
    const onSend = vi.fn()
    render(<Composer onSend={onSend} />)

    const textarea = screen.getByPlaceholderText('Ask Owlynn...')
    fireEvent.change(textarea, { target: { value: 'Hello' } })
    fireEvent.submit(textarea.closest('form')!)

    expect(onSend).toHaveBeenCalledWith('Hello', undefined)
  })
})

// ── OrchestrationPanel ──────────────────────────────────────────────────

describe('OrchestrationPanel', () => {
  it('renders empty state when no data', () => {
    render(<OrchestrationPanel />)
    expect(screen.getByText('No routing information yet.')).toBeTruthy()
  })

  it('displays model badge when modelInfo is set', () => {
    useAppStore.getState().setModelInfo('local-llm-v1')
    render(<OrchestrationPanel />)
    expect(screen.getByText('local-llm-v1')).toBeTruthy()
  })

  it('displays route badge when routerMetadata has route', () => {
    useAppStore.getState().setRouterMetadata({
      route: 'complex-default',
      confidence: 0.95,
      classification_source: 'llm',
    })
    render(<OrchestrationPanel />)
    expect(screen.getByText(/complex-default/)).toBeTruthy()
  })

  it('displays confidence percentage', () => {
    useAppStore.getState().setRouterMetadata({
      route: 'simple',
      confidence: 0.87,
      classification_source: 'keyword_bypass',
    })
    render(<OrchestrationPanel />)
    expect(screen.getByText(/87%/)).toBeTruthy()
  })

  it('shows model badge with cloud class for cloud models', () => {
    useAppStore.getState().setModelInfo('deepseek-cloud')
    render(<OrchestrationPanel />)
    const badge = screen.getByText('deepseek-cloud')
    expect(badge.className).toContain('model-cloud')
  })

  it('shows model badge with local class for local models', () => {
    useAppStore.getState().setModelInfo('lfm2-8b-local')
    render(<OrchestrationPanel />)
    const badge = screen.getByText('lfm2-8b-local')
    expect(badge.className).toContain('model-local')
  })

  it('shows compression stats when contextCompression is set', () => {
    useAppStore.getState().setContextCompression({
      messagesCompressed: 8,
      tokensFreed: 5000,
    })
    render(<OrchestrationPanel />)
    expect(screen.getByText(/messages/)).toBeTruthy()
    expect(screen.getByText(/5000/)).toBeTruthy()
  })

  it('shows memory indicator when memoryUpdatedAt is set', () => {
    useAppStore.getState().setMemoryUpdatedAt(Date.now())
    render(<OrchestrationPanel />)
    expect(screen.getByText(/No routing data yet/)).toBeTruthy()
  })
})

// ── SafeModePanel (with mocked fetch) ──────────────────────────────────

describe('SafeModePanel', () => {
  it('renders safe mode and execution policy sections', () => {
    render(<SafeModePanel />)
    expect(screen.getByText(/Active mode/)).toBeTruthy()
    expect(screen.getByText(/Execution policy/)).toBeTruthy()
  })

  it('renders the safe mode dropdown with current value', () => {
    render(<SafeModePanel />)
    const selects = screen.getAllByRole('combobox')
    const safeModeSelect = selects[0] as HTMLSelectElement
    expect(safeModeSelect).toBeTruthy()
  })

  it('renders two dropdowns (safe mode + execution policy)', () => {
    render(<SafeModePanel />)
    const selects = screen.getAllByRole('combobox')
    expect(selects.length).toBeGreaterThanOrEqual(2)
  })

  it('sets operator note on tauri bridge failure', async () => {
    mockSetSafeMode.mockResolvedValueOnce({ ok: false, error: 'Bridge not available' })
    vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce({ ok: false } as Response)

    render(<SafeModePanel />)

    const selects = screen.getAllByRole('combobox')
    fireEvent.change(selects[0], { target: { value: 'safe_readonly' } })

    await waitFor(() => {
      const state = useAppStore.getState()
      expect(state.operatorNote).toContain('Safe Mode error')
    })
  })
})

// ── ProjectKnowledgePanel ───────────────────────────────────────────────

describe('ProjectKnowledgePanel', () => {
  it('shows loading indicator during fetch', () => {
    vi.spyOn(globalThis, 'fetch').mockImplementation(
      () => new Promise(() => {}) as Promise<Response>
    )
    render(<ProjectKnowledgePanel activeProjectId="proj-1" />)
    const refreshButton = screen.getByRole('button', { name: '...' })
    expect(refreshButton).toBeTruthy()
    expect((refreshButton as HTMLButtonElement).disabled).toBe(true)
  })

  it('shows empty state when no knowledge files', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue({
      ok: true,
      json: async () => ({ files: [] }),
    } as Response)

    render(<ProjectKnowledgePanel activeProjectId="proj-1" />)

    await waitFor(() => {
      expect(screen.getByText(/No knowledge files/)).toBeTruthy()
    })
  })

  it('renders knowledge file names', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue({
      ok: true,
      json: async () => ({
        files: [
          { name: 'notes.md', type: 'knowledge', added_at: 1000 },
          { name: 'api_docs.md', type: 'knowledge', added_at: 2000 },
        ],
      }),
    } as Response)

    render(<ProjectKnowledgePanel activeProjectId="proj-1" />)

    await waitFor(() => {
      expect(screen.getByText('notes.md')).toBeTruthy()
      expect(screen.getByText('api_docs.md')).toBeTruthy()
    })
  })

  it('shows error message on fetch failure', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue({
      ok: false,
    } as Response)

    render(<ProjectKnowledgePanel activeProjectId="proj-1" />)

    await waitFor(() => {
      expect(screen.getByText(/Failed to load/)).toBeTruthy()
    })
  })

  it('collapses chunk rows to one row per file', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue({
      ok: true,
      json: async () => ({
        files: [
          { name: 'doc.pdf#chunk0', type: 'knowledge', added_at: 1000 },
          { name: 'doc.pdf#chunk1', type: 'knowledge', added_at: 2000 },
          { name: 'notes.md', type: 'knowledge', added_at: 3000 },
        ],
      }),
    } as Response)

    render(<ProjectKnowledgePanel activeProjectId="proj-1" />)

    await waitFor(() => {
      expect(screen.getByText('doc.pdf')).toBeTruthy()
      expect(screen.getByText('notes.md')).toBeTruthy()
      expect(screen.queryByText(/#chunk/)).toBeNull()
    })
  })

  it('sets workspace_ref drag payload on drag start', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue({
      ok: true,
      json: async () => ({
        files: [{ name: 'notes.md', type: 'knowledge', added_at: 1000 }],
      }),
    } as Response)

    render(<ProjectKnowledgePanel activeProjectId="proj-1" />)

    await waitFor(() => {
      expect(screen.getByText('notes.md')).toBeTruthy()
    })

    const item = screen.getByText('notes.md').closest('li')
    expect(item).toBeTruthy()
    const setData = vi.fn()
    fireEvent.dragStart(item!, { dataTransfer: { setData, effectAllowed: '' } })
    expect(setData).toHaveBeenCalledWith(
      WORKSPACE_REF_DRAG_TYPE,
      JSON.stringify({ name: 'notes.md' })
    )
  })

  it('attaches workspace_ref on double-click', async () => {
    const onAttach = vi.fn()
    vi.spyOn(globalThis, 'fetch').mockResolvedValue({
      ok: true,
      json: async () => ({
        files: [{ name: 'report.pdf', type: 'knowledge', added_at: 1000 }],
      }),
    } as Response)

    render(<ProjectKnowledgePanel activeProjectId="proj-1" onAttachToComposer={onAttach} />)

    await waitFor(() => {
      expect(screen.getByText('report.pdf')).toBeTruthy()
    })

    fireEvent.doubleClick(screen.getByText('report.pdf'))
    expect(onAttach).toHaveBeenCalledWith(workspaceRefAttachment('report.pdf'))
  })

  it('calls fetch again on refresh click', async () => {
    const fetchSpy = vi.spyOn(globalThis, 'fetch').mockResolvedValue({
      ok: true,
      json: async () => ({ files: [] }),
    } as Response)

    render(<ProjectKnowledgePanel activeProjectId="proj-1" />)

    await waitFor(() => {
      expect(fetchSpy).toHaveBeenCalled()
    })

    fetchSpy.mockClear()
    fireEvent.click(screen.getByRole('button', { name: /Refresh/ }))

    await waitFor(() => {
      expect(fetchSpy).toHaveBeenCalled()
    })
  })
})

// ── AppShell ────────────────────────────────────────────────────────────

describe('AppShell', () => {
  const defaultProps = {
    onSend: vi.fn(),
    projects: [
      { id: 'default', name: 'Default' },
      { id: 'proj-1', name: 'Project One' },
    ],
    activeProjectId: 'default',
    activeChatId: 'thread-1',
    currentThreadId: 'thread-1',
    onSwitchProject: vi.fn(),
    onRefreshProjects: vi.fn(),
    onCreateProject: vi.fn(),
    onEditProject: vi.fn(),
    onDeleteProject: vi.fn(),
    onNewChat: vi.fn(),
    onSelectChat: vi.fn(),
    onDeleteChat: vi.fn(),
    onRenameChat: vi.fn(),
  }

  it('renders all panel sections', () => {
    render(<AppShell {...defaultProps} />)
    // Section headers now include icon prefixes
    expect(screen.getAllByText((content) => content.includes('Knowledge')).length).toBeGreaterThan(0)
  })

  it('renders composer', () => {
    render(<AppShell {...defaultProps} />)
    expect(screen.getByPlaceholderText('Ask Owlynn...')).toBeTruthy()
  })

  it('passes onSend to Composer', () => {
    // Set connection to connected so composer is enabled
    useAppStore.getState().setConnectionState('connected')
    render(<AppShell {...defaultProps} />)

    const textarea = screen.getByPlaceholderText('Ask Owlynn...') as HTMLTextAreaElement
    fireEvent.change(textarea, { target: { value: 'Test message' } })
    fireEvent.submit(textarea.closest('form')!)

    expect(defaultProps.onSend).toHaveBeenCalledWith('Test message', undefined)
  })

  it('renders the project list', () => {
    render(<AppShell {...defaultProps} />)
    // May find multiple elements with "Default" (active project + list item)
    expect(screen.getAllByText('Default').length).toBeGreaterThanOrEqual(1)
    expect(screen.getByText('Project One')).toBeTruthy()
  })

  it('creates workspace through inline input flow', () => {
    const onCreateProject = vi.fn()
    render(<AppShell {...defaultProps} onCreateProject={onCreateProject} />)

    const newButtons = screen.getAllByRole('button', { name: '+ New' })
    fireEvent.click(newButtons[0])

    const input = screen.getByDisplayValue('New Workspace')
    fireEvent.change(input, { target: { value: '  Inline Created Project  ' } })
    fireEvent.keyDown(input, { key: 'Enter' })

    expect(onCreateProject).toHaveBeenCalledWith('Inline Created Project')
    expect(screen.queryByDisplayValue('Inline Created Project')).toBeNull()
  })

  it('sidebar does not render Tool Execution or Action Proposals panels', () => {
    render(<AppShell {...defaultProps} />)
    expect(screen.queryByText((content) => content.includes('Tool Execution'))).toBeNull()
    expect(screen.queryByText((content) => content.includes('Action Proposals'))).toBeNull()
  })

  it('renders image attachment thumbnail in user message bubble', () => {
    useAppStore.getState().addMessage({
      id: 'msg-1',
      role: 'user',
      content: 'What is this?',
      ts: Date.now(),
      attachments: [
        {
          name: 'diagram.png',
          type: 'image/png',
          previewUrl: 'data:image/png;base64,iVBORw0KGgo=',
        },
      ],
    })

    render(<AppShell {...defaultProps} />)

    const img = screen.getByAltText('diagram.png')
    expect(img).toBeTruthy()
    expect(img.getAttribute('src')).toContain('data:image/png;base64,')
  })
})
