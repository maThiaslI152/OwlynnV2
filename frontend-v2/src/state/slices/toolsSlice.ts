import type { StateCreator } from 'zustand'
import type {
  ToolExecutionSnapshot,
  ActionProposal,
  InterruptChoice,
  InlineSecurityPrompt,
  ScreenAssistState
} from '../types'

export interface ToolsSlice {
  screenAssist: ScreenAssistState
  screenAssistEnabled: boolean
  actionProposals: ActionProposal[]
  latestToolExecution: ToolExecutionSnapshot | null
  toolExecutionHistory: ToolExecutionSnapshot[]
  operatorNote: string
  interruptQuestion: string | null
  interruptChoices: InterruptChoice[] | null
  inlineSecurityPrompt: InlineSecurityPrompt | null

  setScreenAssistMode: (mode: ScreenAssistState['mode']) => void
  setScreenAssistSource: (source: ScreenAssistState['source']) => void
  setScreenAssistPreviewPath: (previewPath: string | null) => void
  setScreenAssistEnabled: (enabled: boolean) => void
  upsertActionProposal: (proposal: ActionProposal) => void
  updateActionProposalStatus: (id: string, status: ActionProposal['status']) => void
  setLatestToolExecution: (tool: ToolExecutionSnapshot | null) => void
  pushToolExecution: (tool: ToolExecutionSnapshot) => void
  setOperatorNote: (note: string) => void
  setInterruptPrompt: (question: string | null, choices: InterruptChoice[] | null) => void
  clearInterruptPrompt: () => void
  setInlineSecurityPrompt: (prompt: InlineSecurityPrompt | null) => void
  clearInlineSecurityPrompt: () => void
  clearToolsSession: () => void
}

export const createToolsSlice: StateCreator<ToolsSlice, [], [], ToolsSlice> = (set) => ({
  screenAssist: {
    mode: 'off',
    source: 'screen',
    previewPath: null,
  },
  screenAssistEnabled: false,
  actionProposals: [],
  latestToolExecution: null,
  toolExecutionHistory: [],
  operatorNote: '',
  interruptQuestion: null,
  interruptChoices: null,
  inlineSecurityPrompt: null,

  setScreenAssistMode: (mode) =>
    set((state) => ({
      screenAssist: {
        ...state.screenAssist,
        mode,
      },
    })),
  setScreenAssistSource: (source) =>
    set((state) => ({
      screenAssist: {
        ...state.screenAssist,
        source,
      },
    })),
  setScreenAssistPreviewPath: (previewPath) =>
    set((state) => ({
      screenAssist: {
        ...state.screenAssist,
        previewPath,
      },
    })),
  setScreenAssistEnabled: (enabled) => set({ screenAssistEnabled: enabled }),
  upsertActionProposal: (proposal) =>
    set((state) => {
      const existing = state.actionProposals.find((p) => p.id === proposal.id)
      if (!existing) {
        return { actionProposals: [proposal, ...state.actionProposals] }
      }
      return {
        actionProposals: state.actionProposals.map((p) => (p.id === proposal.id ? proposal : p)),
      }
    }),
  updateActionProposalStatus: (id, status) =>
    set((state) => ({
      actionProposals: state.actionProposals.map((p) =>
        p.id === id ? { ...p, status } : p
      ),
    })),
  setLatestToolExecution: (latestToolExecution) => set({ latestToolExecution }),
  pushToolExecution: (tool) =>
    set((state) => {
      const history = [...state.toolExecutionHistory]
      const key = tool.toolCallId || `${tool.toolName}-${tool.status}`
      const idx = history.findIndex(
        (entry) => (entry.toolCallId || `${entry.toolName}-${entry.status}`) === key
      )
      if (idx >= 0) {
        history[idx] = tool
      } else {
        history.unshift(tool)
      }
      return {
        latestToolExecution: tool,
        toolExecutionHistory: history.slice(0, 25),
      }
    }),
  setOperatorNote: (operatorNote) => set({ operatorNote }),
  setInterruptPrompt: (interruptQuestion, interruptChoices) =>
    set({ interruptQuestion, interruptChoices }),
  clearInterruptPrompt: () =>
    set({ interruptQuestion: null, interruptChoices: null }),
  setInlineSecurityPrompt: (inlineSecurityPrompt) => set({ inlineSecurityPrompt }),
  clearInlineSecurityPrompt: () => set({ inlineSecurityPrompt: null }),
  clearToolsSession: () =>
    set({
      toolExecutionHistory: [],
      latestToolExecution: null,
      actionProposals: [],
      operatorNote: '',
      interruptQuestion: null,
      interruptChoices: null,
      inlineSecurityPrompt: null,
    }),
})
