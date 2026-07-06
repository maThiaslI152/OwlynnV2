import { create } from 'zustand'
import { createChatSlice } from './slices/chatSlice'
import type { ChatSlice } from './slices/chatSlice'
import { createCloudSlice } from './slices/cloudSlice'
import type { CloudSlice } from './slices/cloudSlice'
import { createToolsSlice } from './slices/toolsSlice'
import type { ToolsSlice } from './slices/toolsSlice'
import { createModesSlice } from './slices/modesSlice'
import type { ModesSlice } from './slices/modesSlice'

export * from './types'

export interface AppState extends ChatSlice, CloudSlice, ToolsSlice, ModesSlice {
  clearSession: () => void
}

export const useAppStore = create<AppState>()((...a) => ({
  ...createChatSlice(...a),
  ...createCloudSlice(...a),
  ...createToolsSlice(...a),
  ...createModesSlice(...a),
  
  clearSession: () => {
    a[0]({
      messages: [],
      conversationItems: [],
      contextCompression: null,
      ttsSpeaking: false,
      pendingCorrelationId: null,
      
      routerMetadata: null,
      modelInfo: null,
      contextBreakdown: null,
      coherenceRetryActive: false,
      coherenceRetryAttempt: 0,
      coherenceRetryOriginalConfidence: null,
      cloudFallback: null,
      
      toolExecutionHistory: [],
      latestToolExecution: null,
      actionProposals: [],
      operatorNote: '',
      interruptQuestion: null,
      interruptChoices: null,
      inlineSecurityPrompt: null,
    })
  }
}))
