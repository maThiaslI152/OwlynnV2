import toast from 'react-hot-toast'
import type { ClientEvent, ServerEvent } from '../types/protocol'

type EventHandler = (event: ServerEvent) => void

interface ConnectHandlers {
  onOpen?: () => void
  onClose?: () => void
  onError?: () => void
  onEvent?: (event: ServerEvent) => void
}

export class WsClient {
  private socket: WebSocket | null = null
  private readonly url: string
  private listeners: Map<string, Set<EventHandler>> = new Map()

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

  connect(handlers: ConnectHandlers): () => void {
    this.socket = new WebSocket(this.url)

    this.socket.addEventListener('open', () => handlers.onOpen?.())
    this.socket.addEventListener('close', () => handlers.onClose?.())
    this.socket.addEventListener('error', () => {
      toast.error('WebSocket connection error')
      handlers.onError?.()
    })
    this.socket.addEventListener('message', (event) => {
      try {
        const payload = JSON.parse(event.data) as ServerEvent
        handlers.onEvent?.(payload)
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

    return () => {
      this.socket?.close()
      this.socket = null
    }
  }

  send(event: ClientEvent): void {
    if (!this.socket || this.socket.readyState !== WebSocket.OPEN) return
    this.socket.send(JSON.stringify(event))
  }
}
