export type EventType =
  | 'ABORT_STREAM'
  | 'FOCUS_COMPOSER'
  | 'CLEAR_ATTACHMENTS'

export const EventBus = {
  emit: (type: EventType, detail?: any) => {
    window.dispatchEvent(new CustomEvent(type, { detail }))
  },
  on: (type: EventType, callback: (event: CustomEvent) => void) => {
    window.addEventListener(type as string, callback as EventListener)
  },
  off: (type: EventType, callback: (event: CustomEvent) => void) => {
    window.removeEventListener(type as string, callback as EventListener)
  },
}
