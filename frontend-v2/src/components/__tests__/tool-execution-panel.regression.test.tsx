import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { useAppStore } from '../../state/useAppStore'
import { ToolExecutionPanel } from '../chat/ToolExecutionPanel'

beforeEach(() => {
  useAppStore.setState(useAppStore.getInitialState(), true)
})

afterEach(() => {
})

describe('ToolExecutionPanel rendering regression', () => {
  it('renders empty state when no tool activity exists', () => {
    render(<ToolExecutionPanel />)
    expect(screen.getByText('No tool activity yet.')).toBeTruthy()
  })

  it('shows latest tool execution details when a tool is active', () => {
    useAppStore.getState().pushToolExecution({
      toolName: 'read_workspace_file',
      ts: Date.now(),
      toolCallId: 'call-1',
      status: 'running',
      input: '{"path":"README.md"}',
      riskLabel: 'read_operation',
      riskConfidence: 0.15,
      riskRationale: 'standard file read',
      remediationHint: 'verify path',
    })

    render(<ToolExecutionPanel />)
    expect(screen.getAllByText(/read_workspace_file/).length).toBeGreaterThanOrEqual(1)
    // risk label appears in the collapsed detail
    expect(screen.getAllByText(/read_operation/).length).toBeGreaterThanOrEqual(1)
  })

  it('shows status badge and tool name for errored tools', () => {
    useAppStore.getState().pushToolExecution({
      toolName: 'delete_workspace',
      ts: Date.now(),
      toolCallId: 'call-err',
      status: 'error',
    })

    render(<ToolExecutionPanel />)
    expect(screen.getAllByText(/delete_workspace/).length).toBeGreaterThanOrEqual(1)
  })

  it('renders filter buttons', () => {
    render(<ToolExecutionPanel />)
    expect(screen.getByText('All')).toBeTruthy()
    expect(screen.getByText('Risky')).toBeTruthy()
    expect(screen.getByText('Error')).toBeTruthy()
  })

  it('renders multiple history entries when available', () => {
    useAppStore.getState().pushToolExecution({
      toolName: 'read_file',
      ts: 1000,
      toolCallId: 'call-1',
      status: 'success',
      riskLabel: 'read',
    })
    useAppStore.getState().pushToolExecution({
      toolName: 'delete_file',
      ts: 2000,
      toolCallId: 'call-2',
      status: 'running',
      riskLabel: 'destructive',
    })

    render(<ToolExecutionPanel />)
    expect(screen.getAllByText(/delete_file/).length).toBeGreaterThanOrEqual(1)
  })

  it('renders signing key and secret input fields when audit section expanded', () => {
    render(<ToolExecutionPanel />)
    // Expand the audit section
    fireEvent.click(screen.getByText(/Audit & Verify/))
    expect(screen.getByPlaceholderText('operator-key-1')).toBeTruthy()
    const secretInputs = screen.getAllByPlaceholderText('hmac secret')
    expect(secretInputs.length).toBeGreaterThanOrEqual(2)
  })

  it('renders verify file inputs and action buttons when audit section expanded', () => {
    render(<ToolExecutionPanel />)
    fireEvent.click(screen.getByText(/Audit & Verify/))
    expect(screen.getByText('Verify bundle')).toBeTruthy()
    expect(screen.getByText('Export report')).toBeTruthy()
    expect(screen.getByText('Copy verify script')).toBeTruthy()
  })

  it('starts with no verify result shown', () => {
    render(<ToolExecutionPanel />)
    fireEvent.click(screen.getByText(/Audit & Verify/))
    expect(screen.queryByText(/Last:/)).toBeNull()
  })

  it('shows operator note on empty export attempt', () => {
    render(<ToolExecutionPanel />)
    fireEvent.click(screen.getByText('Export'))
    expect(useAppStore.getState().operatorNote).toContain('skipped')
  })
})

describe('ToolExecutionPanel history filter regression', () => {
  it('applies risky filter via button click', () => {
    useAppStore.getState().pushToolExecution({
      toolName: 'safe_read',
      ts: 1000,
      toolCallId: 'safe-1',
      status: 'success',
    })
    useAppStore.getState().pushToolExecution({
      toolName: 'delete_workspace',
      ts: 2000,
      toolCallId: 'risky-1',
      status: 'running',
      riskLabel: 'destructive',
    })

    render(<ToolExecutionPanel />)

    fireEvent.click(screen.getByText('Risky'))
    expect(screen.getAllByText(/delete_workspace/).length).toBeGreaterThanOrEqual(1)
  })

  it('applies error filter via button click', () => {
    useAppStore.getState().pushToolExecution({
      toolName: 'good_tool',
      ts: 1000,
      toolCallId: 'good-1',
      status: 'success',
    })
    useAppStore.getState().pushToolExecution({
      toolName: 'failed_tool',
      ts: 2000,
      toolCallId: 'fail-1',
      status: 'error',
    })

    render(<ToolExecutionPanel />)

    const buttons = screen.getAllByRole('button')
    const errorButton = buttons.find((b) => b.textContent === 'Error')
    expect(errorButton).toBeTruthy()
    fireEvent.click(errorButton!)
    expect(screen.getAllByText(/failed_tool/).length).toBeGreaterThanOrEqual(1)
  })

  it('copes with empty history under any filter', () => {
    render(<ToolExecutionPanel />)

    fireEvent.click(screen.getByText('Risky'))
    fireEvent.click(screen.getByText('All'))

    expect(screen.getByText('No tool activity yet.')).toBeTruthy()
  })
})

describe('ToolExecutionPanel input field regression', () => {
  it('updates signing key input value', () => {
    render(<ToolExecutionPanel />)
    fireEvent.click(screen.getByText(/Audit & Verify/))
    const input = screen.getByPlaceholderText('operator-key-1') as HTMLInputElement
    fireEvent.change(input, { target: { value: 'my-key-1' } })
    expect(input.value).toBe('my-key-1')
  })

  it('updates signing secret input value', () => {
    render(<ToolExecutionPanel />)
    fireEvent.click(screen.getByText(/Audit & Verify/))
    const secretInputs = screen.getAllByPlaceholderText('hmac secret') as HTMLInputElement[]
    fireEvent.change(secretInputs[0], { target: { value: 'supersecret' } })
    expect(secretInputs[0].value).toBe('supersecret')
  })

  it('updates verify secret input value', () => {
    render(<ToolExecutionPanel />)
    fireEvent.click(screen.getByText(/Audit & Verify/))
    const secretInputs = screen.getAllByPlaceholderText('hmac secret') as HTMLInputElement[]
    const lastInput = secretInputs[secretInputs.length - 1]
    fireEvent.change(lastInput, { target: { value: 'verifysecret' } })
    expect(lastInput.value).toBe('verifysecret')
  })
})
