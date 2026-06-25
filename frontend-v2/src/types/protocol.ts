export * from './protocol.generated'

export type ConnectionState = 'connecting' | 'connected' | 'disconnected' | 'error'

export interface ChatMessageAttachment {
  name: string
  type: string
  previewUrl: string
}

export interface ChatMessage {
  id: string
  role: 'user' | 'assistant'
  content: string
  ts: number
  attachments?: ChatMessageAttachment[]
}
