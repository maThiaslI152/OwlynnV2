import type { CalloutPayload } from './types'

interface Props {
  payload: CalloutPayload
}

const VARIANT_LABEL: Record<string, string> = {
  tip: 'Tip',
  warning: 'Warning',
  note: 'Note',
}

export function InteractiveCallout({ payload }: Props) {
  const variant = payload.variant ?? 'note'
  return (
    <div className={`owlynn-block owlynn-block-callout owlynn-block-callout-${variant}`}>
      <div className="owlynn-block-callout-label">{payload.title ?? VARIANT_LABEL[variant]}</div>
      <div className="owlynn-block-callout-body">{payload.body}</div>
    </div>
  )
}
