import { useMemo, useState } from 'react'
import { useAppStore } from '../state/useAppStore'

interface VerifyReport {
  schema_version: 'owlynn.audit.verify-report.v1'
  ts: number
  status: 'pass' | 'fail'
  reason: string
  records_checked: number
  root_hash?: string
  manifest_file?: string
  bundle_file?: string
  trace?: string[]
}

export function ToolExecutionPanel() {
  const tool = useAppStore((s) => s.latestToolExecution)
  const history = useAppStore((s) => s.toolExecutionHistory)
  const setOperatorNote = useAppStore((s) => s.setOperatorNote)
  const [filter, setFilter] = useState<'all' | 'risky' | 'error'>('all')
  const [showAdvanced, setShowAdvanced] = useState(false)
  const [signingKeyId, setSigningKeyId] = useState('')
  const [signingSecret, setSigningSecret] = useState('')
  const [verifyManifestFile, setVerifyManifestFile] = useState<File | null>(null)
  const [verifyJsonlFile, setVerifyJsonlFile] = useState<File | null>(null)
  const [verifySecret, setVerifySecret] = useState('')
  const [lastVerifyReport, setLastVerifyReport] = useState<VerifyReport | null>(null)

  const filteredHistory = useMemo(() => {
    if (filter === 'risky') return history.filter((entry) => Boolean(entry.riskLabel))
    if (filter === 'error') return history.filter((entry) => entry.status === 'error')
    return history
  }, [filter, history])

  const formatTs = (ts: number) => new Date(ts).toLocaleTimeString()
  const formatDuration = (duration?: number) =>
    typeof duration === 'number' ? `${Math.round(duration * 1000)}ms` : 'n/a'

  const toHex = (bytes: Uint8Array) => [...bytes].map((b) => b.toString(16).padStart(2, '0')).join('')

  const exportAuditJsonl = async () => {
    if (filteredHistory.length === 0) {
      setOperatorNote('Audit export skipped: no tool events in current filter.')
      return
    }
    const encoder = new TextEncoder()
    const rows: string[] = []
    let prevHash = '0'.repeat(64)
    const exportTs = Date.now()
    for (let i = 0; i < filteredHistory.length; i += 1) {
      const entry = filteredHistory[i]
      const canonical = {
        schema_version: 'owlynn.audit.tool_execution.v1',
        export_ts: exportTs,
        sequence: i + 1,
        ts: entry.ts,
        tool_name: entry.toolName,
        tool_call_id: entry.toolCallId ?? null,
        status: entry.status,
        duration: entry.duration ?? null,
        risk_label: entry.riskLabel ?? null,
        risk_confidence: entry.riskConfidence ?? null,
        risk_rationale: entry.riskRationale ?? null,
        remediation_hint: entry.remediationHint ?? null,
      }
      const canonicalString = JSON.stringify(canonical)
      const hashInput = `${prevHash}:${canonicalString}`
      const digest = await crypto.subtle.digest('SHA-256', encoder.encode(hashInput))
      const entryHash = toHex(new Uint8Array(digest))
      rows.push(JSON.stringify({ ...canonical, prev_hash: prevHash, entry_hash: entryHash }))
      prevHash = entryHash
    }
    const blob = new Blob([rows.join('\n')], { type: 'application/x-ndjson' })
    const bundleName = `owlynn-tool-audit-${exportTs}.jsonl`
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url; a.download = bundleName; a.click(); a.remove()
    URL.revokeObjectURL(url)

    const manifestBase = {
      schema_version: 'owlynn.audit.manifest.v1',
      export_ts: exportTs,
      session_id: crypto.randomUUID(),
      records_count: rows.length,
      filter,
      bundle_file: bundleName,
      root_hash: prevHash,
      chain_algo: 'sha256',
      signature_scheme: signingKeyId && signingSecret ? 'hmac-sha256' : 'sha256-manifest-digest',
    }
    const manifestCanonical = JSON.stringify(manifestBase)
    const manifestDigest = await crypto.subtle.digest('SHA-256', encoder.encode(manifestCanonical))
    const manifestHash = toHex(new Uint8Array(manifestDigest))
    let manifestSignature: string | null = null
    if (signingKeyId && signingSecret) {
      const hmacKey = await crypto.subtle.importKey('raw', encoder.encode(signingSecret), { name: 'HMAC', hash: 'SHA-256' }, false, ['sign'])
      const sig = await crypto.subtle.sign('HMAC', hmacKey, encoder.encode(manifestCanonical))
      manifestSignature = toHex(new Uint8Array(sig))
    }
    const manifestBlob = new Blob([JSON.stringify({ ...manifestBase, signing_key_id: signingKeyId || null, manifest_hash: manifestHash, manifest_signature: manifestSignature }, null, 2)], { type: 'application/json' })
    const manifestUrl = URL.createObjectURL(manifestBlob)
    const manifestAnchor = document.createElement('a')
    manifestAnchor.href = manifestUrl; manifestAnchor.download = `${bundleName}.manifest.json`; manifestAnchor.click(); manifestAnchor.remove()
    URL.revokeObjectURL(manifestUrl)
    setOperatorNote(`Exported ${rows.length} events (hash: ${prevHash.slice(0, 12)}…)`)
  }

  const copyVerifySnippet = async () => {
    const snippet = `import { readFileSync } from 'node:fs'
import { createHash, createHmac } from 'node:crypto'

const manifest = JSON.parse(readFileSync(process.argv[2], 'utf8'))
const rows = readFileSync(process.argv[3], 'utf8').trim().split('\\n').filter(Boolean).map(j=>JSON.parse(j))

let prev = '0'.repeat(64)
for (const row of rows) {
  const c = {schema_version:row.schema_version,export_ts:row.export_ts,sequence:row.sequence,ts:row.ts,tool_name:row.tool_name,tool_call_id:row.tool_call_id,status:row.status,duration:row.duration,risk_label:row.risk_label,risk_confidence:row.risk_confidence,risk_rationale:row.risk_rationale,remediation_hint:row.remediation_hint}
  const exp = createHash('sha256').update(prev+':'+JSON.stringify(c)).digest('hex')
  if (row.prev_hash !== prev || row.entry_hash !== exp) throw new Error('Chain fail at seq '+row.sequence)
  prev = row.entry_hash
}
if (manifest.root_hash !== prev) throw new Error('Root hash mismatch')
if (manifest.signature_scheme === 'hmac-sha256') {
  const secret = process.argv[4]
  const mb = {schema_version:manifest.schema_version,export_ts:manifest.export_ts,session_id:manifest.session_id,records_count:manifest.records_count,filter:manifest.filter,bundle_file:manifest.bundle_file,root_hash:manifest.root_hash,chain_algo:manifest.chain_algo,signature_scheme:manifest.signature_scheme}
  const sig = createHmac('sha256', secret).update(JSON.stringify(mb)).digest('hex')
  if (sig !== manifest.manifest_signature) throw new Error('Signature mismatch')
}
console.log('Verification OK')`
    await navigator.clipboard.writeText(snippet)
    setOperatorNote('Copied verification snippet.')
  }

  const verifyBundle = async () => {
    if (!verifyManifestFile || !verifyJsonlFile) {
      setOperatorNote('Select both manifest and JSONL files.')
      return
    }
    try {
      const encoder = new TextEncoder()
      const trace: string[] = []
      const manifest = JSON.parse(await verifyManifestFile.text())
      const rows = (await verifyJsonlFile.text()).split('\n').map(l=>l.trim()).filter(Boolean).map(l=>JSON.parse(l))
      trace.push(`parsed ${rows.length} rows`)
      let prev = '0'.repeat(64)
      for (const row of rows) {
        const canonical = {schema_version:row.schema_version,export_ts:row.export_ts,sequence:row.sequence,ts:row.ts,tool_name:row.tool_name,tool_call_id:row.tool_call_id,status:row.status,duration:row.duration,risk_label:row.risk_label,risk_confidence:row.risk_confidence,risk_rationale:row.risk_rationale,remediation_hint:row.remediation_hint}
        const digest = await crypto.subtle.digest('SHA-256', encoder.encode(`${prev}:${JSON.stringify(canonical)}`))
        const expected = toHex(new Uint8Array(digest))
        if (row.prev_hash !== prev || row.entry_hash !== expected) throw new Error(`Hash chain fail at seq ${String(row.sequence)}`)
        prev = String(row.entry_hash)
      }
      if (manifest.root_hash !== prev) throw new Error('Manifest root hash mismatch')
      const manifestBase = {schema_version:manifest.schema_version,export_ts:manifest.export_ts,session_id:manifest.session_id,records_count:manifest.records_count,filter:manifest.filter,bundle_file:manifest.bundle_file,root_hash:manifest.root_hash,chain_algo:manifest.chain_algo,signature_scheme:manifest.signature_scheme}
      const manifestDigest = await crypto.subtle.digest('SHA-256', encoder.encode(JSON.stringify(manifestBase)))
      const manifestHash = toHex(new Uint8Array(manifestDigest))
      if (manifest.manifest_hash !== manifestHash) throw new Error('Manifest digest mismatch')
      if (manifest.signature_scheme === 'hmac-sha256') {
        if (!verifySecret) throw new Error('Missing HMAC secret')
        const key = await crypto.subtle.importKey('raw', encoder.encode(verifySecret), {name:'HMAC',hash:'SHA-256'}, false, ['sign'])
        const sig = await crypto.subtle.sign('HMAC', key, encoder.encode(JSON.stringify(manifestBase)))
        if (manifest.manifest_signature !== toHex(new Uint8Array(sig))) throw new Error('Manifest signature mismatch')
      }
      setOperatorNote(`Verification OK: ${rows.length} records`)
      setLastVerifyReport({schema_version:'owlynn.audit.verify-report.v1', ts:Date.now(), status:'pass', reason:'Verification completed successfully.', records_checked:rows.length, root_hash:prev, manifest_file:verifyManifestFile.name, bundle_file:verifyJsonlFile.name, trace})
    } catch (error) {
      setOperatorNote(`Verify failed: ${(error as Error).message}`)
      setLastVerifyReport(prev => prev?.status === 'fail' ? prev : ({schema_version:'owlynn.audit.verify-report.v1', ts:Date.now(), status:'fail', reason:(error as Error).message, records_checked:0, manifest_file:verifyManifestFile?.name??'', bundle_file:verifyJsonlFile?.name??'', trace:['failed']}))
    }
  }

  const exportVerifyReport = () => {
    if (!lastVerifyReport) { setOperatorNote('No verification report.'); return }
    const blob = new Blob([JSON.stringify(lastVerifyReport, null, 2)], {type:'application/json'})
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url; a.download = `owlynn-verify-report-${lastVerifyReport.ts}.json`; a.click(); a.remove()
    URL.revokeObjectURL(url)
    setOperatorNote('Report exported.')
  }

  return (
    <div>
      <div className="row">
        <button type="button" className={filter==='all' ? 'active-filter' : ''} onClick={()=>setFilter('all')}>All</button>
        <button type="button" onClick={()=>setFilter('risky')}>Risky</button>
        <button type="button" onClick={()=>setFilter('error')}>Error</button>
        <button type="button" onClick={()=>void exportAuditJsonl()}>Export</button>
      </div>
      {!tool && history.length === 0 ? (
        <p className="empty">No tool activity yet.</p>
      ) : tool ? (
        <div className="tool-exec-item">
          <div className="tool-exec-header">
            <span className="tool-exec-name">{tool.toolName}</span>
            <span className={`badge badge-${tool.status}`}>{tool.status}</span>
          </div>
          <div className="tool-exec-detail">
            {formatTs(tool.ts)} · {formatDuration(tool.duration)}
            {tool.riskLabel ? ` · Risk: ${tool.riskLabel}` : ''}
          </div>
        </div>
      ) : null}
      {filteredHistory.length > 0 && (
        <div className="tool-history" style={{marginTop:6}}>
          {filteredHistory.slice(0, 5).map((entry, idx) => (
            <div key={`${entry.toolCallId ?? entry.toolName}-${idx}`} className="tool-exec-item">
              <div className="tool-exec-header">
                <span className="tool-exec-name">{entry.toolName}</span>
                <span className={`badge badge-${entry.status}`}>{entry.status}</span>
              </div>
              <div className="tool-exec-detail">
                {formatTs(entry.ts)} · {formatDuration(entry.duration)}
                {entry.riskLabel ? ` · ${entry.riskLabel}` : ''}
              </div>
            </div>
          ))}
        </div>
      )}
      <div style={{marginTop:4}}>
        <button
          type="button"
          onClick={() => setShowAdvanced(!showAdvanced)}
          style={{border:'none', background:'transparent', color:'var(--text-muted)', fontSize:'0.7rem', cursor:'pointer', padding:0}}
        >
          {showAdvanced ? '−' : '+'} Audit & Verify
        </button>
      </div>
      {showAdvanced && (
        <div className="signing-section">
          <div className="row">
            <button type="button" onClick={()=>void copyVerifySnippet()}>Copy verify script</button>
          </div>
          <label>Signing key
            <input value={signingKeyId} onChange={e=>setSigningKeyId(e.target.value)} placeholder="operator-key-1" />
          </label>
          <label>Signing secret
            <input type="password" value={signingSecret} onChange={e=>setSigningSecret(e.target.value)} placeholder="hmac secret" />
          </label>
          <label>Manifest file
            <input type="file" accept=".json,.manifest.json" onChange={e=>setVerifyManifestFile(e.target.files?.[0]??null)} />
          </label>
          <label>JSONL file
            <input type="file" accept=".jsonl,.ndjson" onChange={e=>setVerifyJsonlFile(e.target.files?.[0]??null)} />
          </label>
          <label>Verify secret
            <input type="password" value={verifySecret} onChange={e=>setVerifySecret(e.target.value)} placeholder="hmac secret" />
          </label>
          <div className="row">
            <button type="button" onClick={()=>void verifyBundle()}>Verify bundle</button>
            <button type="button" onClick={exportVerifyReport}>Export report</button>
          </div>
          {lastVerifyReport ? (
            <p className={lastVerifyReport.status === 'pass' ? 'signing-verified' : 'meta'}>
              Last: {lastVerifyReport.status} · {new Date(lastVerifyReport.ts).toLocaleTimeString()}
            </p>
          ) : null}
        </div>
      )}
    </div>
  )
}
