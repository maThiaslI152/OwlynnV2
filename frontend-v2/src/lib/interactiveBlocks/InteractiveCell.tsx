import { useState } from 'react'
import type { CellPayload } from './types'

interface Props {
  payload: CellPayload
  projectId: string
  threadId: string
}

export function InteractiveCell({ payload, projectId, threadId }: Props) {
  const [output, setOutput] = useState(payload.output ?? '')
  const [running, setRunning] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const runnable = payload.runnable !== false && payload.language !== 'text'

  const runCell = async () => {
    if (!runnable || running) return
    setRunning(true)
    setError(null)
    try {
      const res = await fetch('/api/notebook/run', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          code: payload.code,
          project_id: projectId,
          thread_id: threadId,
        }),
      })
      const data = (await res.json()) as { status?: string; output?: string; message?: string }
      if (!res.ok || data.status === 'error') {
        setError(data.message ?? 'Execution failed')
      } else {
        setOutput(data.output ?? '')
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Network error')
    } finally {
      setRunning(false)
    }
  }

  return (
    <div className="owlynn-block owlynn-block-cell">
      <div className="owlynn-block-cell-header">
        <span className="owlynn-block-cell-lang">{payload.language ?? 'python'}</span>
        {runnable && (
          <button
            type="button"
            className="owlynn-block-cell-run"
            disabled={running}
            onClick={() => void runCell()}
          >
            {running ? 'Running…' : 'Run'}
          </button>
        )}
      </div>
      <pre className="owlynn-block-cell-code"><code>{payload.code}</code></pre>
      {error && <div className="owlynn-block-cell-error">{error}</div>}
      {output && (
        <pre className="owlynn-block-cell-output">{output}</pre>
      )}
    </div>
  )
}
