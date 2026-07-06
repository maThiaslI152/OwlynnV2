import type { StateCreator } from 'zustand'
import type { ChatMessage, ConnectionState } from '../../types/protocol'
import type { ConversationItem, ConversationHitlPrompt, ConversationToolActivity } from '../../appEventHandlers'
import type { CompressionInfo } from '../types'

function uuid() {
  if (typeof crypto !== 'undefined' && crypto.randomUUID) return crypto.randomUUID()
  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (c) => {
    const r = (Math.random() * 16) | 0
    return (c === 'x' ? r : (r & 0x3) | 0x8).toString(16)
  })
}

export interface ChatSlice {
  connectionState: ConnectionState
  messages: ChatMessage[]
  conversationItems: ConversationItem[]
  pendingCorrelationId: string | null
  evalResponseStyle: string | null
  responseStyle: string | null
  activePersonaId: string
  memoryUpdatedAt: number | null
  ttsSpeaking: boolean
  contextCompression: CompressionInfo | null
  
  setConnectionState: (state: ConnectionState) => void
  addMessage: (message: ChatMessage) => void
  appendStreamChunk: (chunk: string) => void
  setPendingCorrelationId: (id: string | null) => void
  setEvalResponseStyle: (style: string | null) => void
  setResponseStyle: (style: string | null) => void
  setActivePersonaId: (id: string) => void
  setMemoryUpdatedAt: (ts: number) => void
  setTtsSpeaking: (speaking: boolean) => void
  setContextCompression: (info: CompressionInfo | null) => void
  appendConversationItem: (item: ConversationItem) => void
  updateConversationItemStatus: (id: string, status: 'pending' | 'approved' | 'rejected' | 'dismissed' | 'running' | 'success' | 'error') => void
  clearChatSession: () => void
}

export const createChatSlice: StateCreator<ChatSlice, [], [], ChatSlice> = (set) => ({
  connectionState: 'disconnected',
  messages: [],
  conversationItems: [],
  pendingCorrelationId: null,
  evalResponseStyle: null,
  responseStyle: null,
  activePersonaId: 'default',
  memoryUpdatedAt: null,
  ttsSpeaking: false,
  contextCompression: null,

  setConnectionState: (connectionState) => set({ connectionState }),
  addMessage: (message) =>
    set((state) => ({
      messages: [...state.messages, message],
    })),
  appendStreamChunk: (chunk) =>
    set((state) => {
      const messages = [...state.messages]
      const last = messages[messages.length - 1]
      if (last && last.role === 'assistant') {
        messages[messages.length - 1] = { ...last, content: last.content + chunk }
      } else {
        messages.push({
          id: `stream-${uuid()}`,
          role: 'assistant',
          content: chunk,
          ts: Date.now(),
        })
      }
      return { messages }
    }),
  setPendingCorrelationId: (pendingCorrelationId) => set({ pendingCorrelationId }),
  setEvalResponseStyle: (evalResponseStyle) => set({ evalResponseStyle }),
  setResponseStyle: (responseStyle) => set({ responseStyle }),
  setActivePersonaId: (activePersonaId) => set({ activePersonaId }),
  setMemoryUpdatedAt: (memoryUpdatedAt) => set({ memoryUpdatedAt }),
  setTtsSpeaking: (ttsSpeaking) => set({ ttsSpeaking }),
  setContextCompression: (contextCompression) => set({ contextCompression }),
  appendConversationItem: (item) =>
    set((state) => ({
      conversationItems: [...state.conversationItems, item],
    })),
  updateConversationItemStatus: (id, status) =>
    set((state) => ({
      conversationItems: state.conversationItems.map((item) =>
        item.kind === 'hitl_prompt' && item.id === id
          ? { ...item, status: status as ConversationHitlPrompt['status'] }
          : item.kind === 'tool_activity' && item.id === id
            ? { ...item, status: status as ConversationToolActivity['status'] }
            : item
      ),
    })),
  clearChatSession: () =>
    set({
      messages: [],
      conversationItems: [],
      contextCompression: null,
      ttsSpeaking: false,
      pendingCorrelationId: null,
    }),
})
