import { useState } from 'react'
import type { QuizPayload } from './types'

interface Props {
  payload: QuizPayload
}

export function InteractiveQuiz({ payload }: Props) {
  const [selected, setSelected] = useState<number | null>(null)
  const answered = selected !== null
  const isCorrect = selected === payload.correctIndex

  return (
    <div className="owlynn-block owlynn-block-quiz">
      <p className="owlynn-block-quiz-question">{payload.question}</p>
      <ul className="owlynn-block-quiz-options">
        {payload.options.map((option, idx) => {
          let stateClass = ''
          if (answered) {
            if (idx === payload.correctIndex) stateClass = ' is-correct'
            else if (idx === selected) stateClass = ' is-wrong'
          }
          return (
            <li key={idx}>
              <button
                type="button"
                className={`owlynn-block-quiz-option${stateClass}`}
                disabled={answered}
                onClick={() => setSelected(idx)}
              >
                <span className="owlynn-block-quiz-letter">{String.fromCharCode(65 + idx)}</span>
                {option}
              </button>
            </li>
          )
        })}
      </ul>
      {answered && (
        <div className={`owlynn-block-quiz-feedback${isCorrect ? ' is-correct' : ' is-wrong'}`}>
          {isCorrect ? 'Correct!' : 'Not quite.'}
          {payload.explanation && <p>{payload.explanation}</p>}
        </div>
      )}
    </div>
  )
}
