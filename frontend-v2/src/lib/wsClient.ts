import toast from 'react-hot-toast'
import type { ClientEvent, ServerEvent } from '../types/protocol'

type EventHandler = (event: ServerEvent) => void

interface ConnectHandlers {
  onOpen?: () => void
  onClose?: () => void
  onError?: () => void
  onEvent?: (event: ServerEvent) => void
  onReconnecting?: (attempt: number, maxRetries: number) => void
  onReconnected?: () => void
  onReconnectFailed?: () => void
}

export class WsClient {
  private socket: WebSocket | null = null
  private readonly url: string
  private listeners: Map<string, Set<EventHandler>> = new Map()

  // Auto-reconnect state
  private reconnectAttempt = 0
  private maxReconnectRetries = 5
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null
  private lastSentMessage: ClientEvent | null = null
  private lastThreadId: string | null = null
  private connectHandlers: ConnectHandlers | null = null
  private intentionalClose = false

  constructor(url: string) {
    this.url = url
  }

  /** Subscribe to events by type. Use '*' for all events. Returns unsubscribe fn. */
  on(type: string, handler: EventHandler): () => void {
    if (!this.listeners.has(type)) {
      this.listeners.set(type, new Set())
    }
    this.listeners.get(type)!.add(handler)
    return () => this.off(type, handler)
  }

  /** Unsubscribe a handler for a given event type. */
  off(type: string, handler: EventHandler): void {
    this.listeners.get(type)?.delete(handler)
  }

  /** Emit an event to all registered listeners. */
  private emit(type: string, event: ServerEvent): void {
    this.listeners.get(type)?.forEach((h) => h(event))
    if (type !== '*') {
      this.listeners.get('*')?.forEach((h) => h(event))
    }
  }

  connect(handlers: ConnectHandlers, threadId?: string): () => void {
    this.connectHandlers = handlers
    this.lastThreadId = threadId || this.lastThreadId
    this.intentionalClose = false
    this._doConnect()

    return () => {
      this.intentionalClose = true
      this._clearReconnectTimer()
      this.socket?.close()
      this.socket = null
    }
  }

  /** Update the thread ID for reconnection (call when switching chats). */
  setThreadId(threadId: string): void {
    this.lastThreadId = threadId
  }

  private _doConnect(): void {
    this.socket = new WebSocket(this.url)

    this.socket.addEventListener('open', () => {
      this.reconnectAttempt = 0
      this._clearReconnectTimer()
      this.connectHandlers?.onOpen?.()
      // Replay last message on reconnect if we have one
      if (this.lastSentMessage && this.connectHandlers?.onReconnected) {
        this.connectHandlers.onReconnected()
        // Re-send the last user message to retry the failed graph run
        this.send(this.lastSentMessage)
      }
    })

    this.socket.addEventListener('close', () => {
      if (this.intentionalClose) {
        this.connectHandlers?.onClose?.()
        return
      }
      // Attempt auto-reconnect
      if (this.reconnectAttempt < this.maxReconnectRetries) {
        this.reconnectAttempt++
        const delay = Math.min(1000 * Math.pow(2, this.reconnectAttempt - 1), 16000)
        this.connectHandlers?.onReconnecting?.(this.reconnectAttempt, this.maxReconnectRetries)
        this.reconnectTimer = setTimeout(() => {
          this._doConnect()
        }, delay)
      } else {
        // All retries exhausted
        toast.error('Connection lost. Please start a new chat.')
        this.connectHandlers?.onReconnectFailed?.()
        this.connectHandlers?.onClose?.()
        this.lastSentMessage = null
      }
    })

    this.socket.addEventListener('error', () => {
      this.connectHandlers?.onError?.()
    })

    this.socket.addEventListener('message', (event) => {
      try {
        const payload = JSON.parse(event.data) as ServerEvent
        this.connectHandlers?.onEvent?.(payload)
        // Emit to typed listeners
        const eventType = (payload as Record<string, unknown>).type as string
        if (eventType) {
          this.emit(eventType, payload)
        }
      } catch (e) {
        console.warn('[wsClient] failed to parse event', e)
        toast.error('Failed to parse WebSocket message')
      }
    })
  }

  private _clearReconnectTimer(): void {
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer)
      this.reconnectTimer = null
    }
  }

  send(event: ClientEvent): void {
    // Store the last user message for replay on reconnect
    if ((event as any).type === 'user.message') {
      this.lastSentMessage = event
    }
    if (!this.socket || this.socket.readyState !== WebSocket.OPEN) return
    this.socket.send(JSON.stringify(event))
  }
}
