import { useState } from 'react'
import { getLocalRunToken } from '../localRunToken'
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
  const [confirmed, setConfirmed] = useState(false)
  const runnable = payload.runnable === true && payload.language !== 'text'

  const runCell = async () => {
    if (!runnable || running) return
    if (!confirmed) {
      const ok = window.confirm(
        'Run this Python code on your Mac? It executes with your user permissions in the Owlynn notebook worker.',
      )
      if (!ok) return
      setConfirmed(true)
    }
    setRunning(true)
    setError(null)
    try {
      const token = await getLocalRunToken()
      const res = await fetch('/api/notebook/run', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-Owlynn-Run-Token': token,
        },
        body: JSON.stringify({
          code: payload.code,
          project_id: projectId,
          thread_id: threadId,
        }),
      })
      const data = (await res.json()) as { status?: string; output?: string; message?: string; detail?: string }
      if (!res.ok || data.status === 'error') {
        setError(data.message ?? data.detail ?? 'Execution failed')
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
      {!runnable && payload.output == null && (
        <p className="owlynn-block-cell-hint">Display-only cell (not runnable).</p>
      )}
      {error && <div className="owlynn-block-cell-error">{error}</div>}
      {output && (
        <pre className="owlynn-block-cell-output">{output}</pre>
      )}
    </div>
  )
}
