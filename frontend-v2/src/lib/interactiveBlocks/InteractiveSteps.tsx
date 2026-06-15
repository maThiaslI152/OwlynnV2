import { useState } from 'react'
import type { StepsPayload } from './types'

interface Props {
  payload: StepsPayload
}

export function InteractiveSteps({ payload }: Props) {
  const [openIdx, setOpenIdx] = useState(0)

  return (
    <div className="owlynn-block owlynn-block-steps">
      {payload.title && <h4 className="owlynn-block-steps-title">{payload.title}</h4>}
      <ol className="owlynn-block-steps-list">
        {payload.steps.map((step, idx) => {
          const isOpen = openIdx === idx
          return (
            <li key={idx} className={isOpen ? 'is-open' : ''}>
              <button
                type="button"
                className="owlynn-block-steps-heading"
                onClick={() => setOpenIdx(isOpen ? -1 : idx)}
                aria-expanded={isOpen}
              >
                <span className="owlynn-block-steps-num">{idx + 1}</span>
                {step.heading}
              </button>
              {isOpen && <div className="owlynn-block-steps-body">{step.body}</div>}
            </li>
          )
        })}
      </ol>
    </div>
  )
}
