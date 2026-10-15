import { useEffect, useRef, useState } from 'react'
import { ApiError, diagnosticError, mutation, requestJson } from './api'
import { ageLabel, formatDate } from './format'

type RunState = 'planned' | 'running' | 'awaiting_review' | 'completed' | 'cancelled' | 'expired' | 'interrupted' | 'stopped_transport' | 'stopped_protocol' | 'stopped_data' | 'stopped_storage'
type Review = { verdict: 'continue' | 'finish' | 'anomaly'; observation: string | null }
type Evidence = {
  step_index: number; outcome: string; started_at: string; completed_at: string | null
  raw_words: number[] | null; error_class: string | null; received_bytes: number; review: Review | null
  interpretation_status: 'confirmed_core' | 'raw_only'
  decoded_signals: { signal_id: string; value: number; unit: string; offset: number; raw_words: number[]; profile_id: string; profile_version: string; decoder_version: string; source: string }[]
}
type Run = {
  run_id: string; state: RunState; source: 'device' | 'simulator'; target_changed: boolean
  plan: { register_ids: string[]; purpose: string; target_alias: string; blocks: { offset: number; count: number }[]; function_code: number; unit_id: number; deadline_seconds: number; request_budget: number; min_interval_seconds: number; max_duration_seconds: number; stop_conditions: string[]; catalog_sha256: string }
  requests_reserved: number; requests: Evidence[]; next_step_index: number | null
  wait_remaining_seconds: number; duration_remaining_seconds: number; created_at: string; updated_at: string
  started_at: string | null; ended_at: string | null; acknowledged_at: string | null; resolution_note: string | null
}
type RunPage = { total: number; limit: number; offset: number; items: Run[] }
const base = '/api/diagnostics/runs'
const storageKey = 'sommerauer.diagnostics.lastRun'
const blocking: Partial<Record<RunState, true>> = { interrupted: true, stopped_transport: true, stopped_protocol: true, stopped_data: true, stopped_storage: true }
const descriptions: Record<RunState, string> = {
  planned: 'Geplant: noch nicht gestartet. Planung und Start senden keine Geräteanfrage.',
  running: 'Prüflauf geöffnet: jede fällige Anfrage muss einzeln bewusst ausgelöst werden.',
  awaiting_review: 'Antwort gespeichert: Betreiberbewertung erforderlich, bevor eine weitere Anfrage möglich ist.',
  completed: 'Abgeschlossen: alle vorgesehenen Antworten wurden bewertet. Keine weiteren Anfragen.',
  cancelled: 'Bewusst beendet oder sicher abgebrochen. Kein erfolgreicher vollständiger Prüflauf.',
  expired: 'Gesamtfrist abgelaufen: der Prüflauf wurde beendet, nicht pausiert.',
  interrupted: 'Unterbrochen: der vorherige Lauf konnte nicht regulär beendet werden. Ursache klären und quittieren.',
  stopped_transport: 'Transportfehler: sofort gestoppt, keine Wiederholung. Verbindung und Ursache klären und quittieren.',
  stopped_protocol: 'Protokollfehler: sofort gestoppt, keine Wiederholung. Antwort und Ursache klären und quittieren.',
  stopped_data: 'Datenfehler oder Auffälligkeit: sofort gestoppt. Belege prüfen, Ursache klären und quittieren.',
  stopped_storage: 'Speicherfehler: sichere Speicherung nicht gewährleistet. Keine weiteren Anfragen; Speicherursache klären und quittieren.',
}
const sourceLabel = (source: Run['source']) => source === 'simulator' ? 'Simulator, synthetisch' : 'Gerät'
const hex = (word: number) => `0x${word.toString(16).toUpperCase().padStart(4, '0')}`

export default function ReadRuns({ registerIds, timeZone, onCollectorChange, onEvidenceChange }: {
  registerIds: string[]; timeZone: string; onCollectorChange: () => Promise<void>; onEvidenceChange: () => Promise<void>
}) {
  const [purpose, setPurpose] = useState('')
  const [page, setPage] = useState<RunPage | null>(null)
  const [run, setRun] = useState<Run | null>(null)
  const [loading, setLoading] = useState(false)
  const [historyLoading, setHistoryLoading] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [storageError, setStorageError] = useState('')
  const [uncertain, setUncertain] = useState(false)
  const [otherReaders, setOtherReaders] = useState(false)
  const [observation, setObservation] = useState('')
  const [resolution, setResolution] = useState('')
  const [elapsed, setElapsed] = useState(0)
  const mutationGuard = useRef(false)
  const selectedId = useRef<string | null>(null)
  const loadSequence = useRef(0)
  const anchor = useRef(performance.now())
  const date = (value: string | null) => value ? formatDate(value, timeZone) : '—'

  function remember(id: string) {
    try { localStorage.setItem(storageKey, id) } catch { setStorageError('Browser-Speicher nicht verfügbar: zuletzt betrachteter Lauf kann nicht dauerhaft gemerkt werden.') }
  }
  function accept(document: Run) {
    const changed = selectedId.current !== document.run_id
    selectedId.current = document.run_id
    setRun(document)
    anchor.current = performance.now()
    setElapsed(0)
    if (changed) { setObservation(''); setResolution(''); setOtherReaders(false) }
    remember(document.run_id)
  }
  async function loadRun(id: string) {
    const sequence = ++loadSequence.current
    setLoading(true)
    try {
      const document = await requestJson<Run>(`${base}/${encodeURIComponent(id)}`)
      if (sequence === loadSequence.current) { accept(document); setUncertain(false) }
    } catch (failure) {
      if (sequence === loadSequence.current) setError(`Lauf konnte nicht geladen werden: ${diagnosticError(failure)}. Gespeicherte Anzeige bleibt erhalten.`)
    } finally { if (sequence === loadSequence.current) setLoading(false) }
  }
  async function loadPage(offset: number) {
    setHistoryLoading(true)
    try { setPage(await requestJson<RunPage>(`${base}?limit=50&offset=${offset}`)) }
    catch (failure) { setError(`Historie konnte nicht geladen werden: ${diagnosticError(failure)}`) }
    finally { setHistoryLoading(false) }
  }
  useEffect(() => {
    let cancelled = false
    setHistoryLoading(true)
    void (async () => {
      try {
        const result = await requestJson<RunPage>(`${base}?limit=50&offset=0`)
        if (cancelled) return
        setPage(result)
        let stored: string | null = null
        try { stored = localStorage.getItem(storageKey) } catch { setStorageError('Browser-Speicher nicht lesbar: Auswahl wird nicht wiederhergestellt.') }
        const current = result.items.find(item => item.state === 'running' || item.state === 'awaiting_review' || (blocking[item.state] && !item.acknowledged_at))
        const id = stored || current?.run_id || result.items[0]?.run_id
        if (id && !mutationGuard.current && !selectedId.current) await loadRun(id)
      } catch (failure) { if (!cancelled) setError(`Historie konnte nicht geladen werden: ${diagnosticError(failure)}`) }
      finally { if (!cancelled) setHistoryLoading(false) }
    })()
    return () => { cancelled = true; ++loadSequence.current }
  }, [])
  useEffect(() => {
    if (run?.state !== 'running' && run?.state !== 'awaiting_review') return
    const timer = window.setInterval(() => setElapsed((performance.now() - anchor.current) / 1000), 1000)
    return () => window.clearInterval(timer)
  }, [run?.state])

  async function act(action: 'create' | 'start' | 'read' | 'review' | 'stop' | 'acknowledge', body: unknown) {
    if (mutationGuard.current || loading || uncertain || (action !== 'create' && !run)) return
    mutationGuard.current = true
    setBusy(true)
    setError('')
    ++loadSequence.current
    try {
      const url = action === 'create' ? base : `${base}/${encodeURIComponent(run!.run_id)}/${action}`
      const document = await requestJson<Run>(url, mutation('POST', body))
      accept(document)
      setOtherReaders(false)
      if (action === 'review') setObservation('')
      if (action === 'acknowledge') setResolution('')
    } catch (failure) {
      setUncertain(true)
      const prefix = failure instanceof ApiError && failure.status === 409 ? 'Konflikt' : 'API-/Speicher- oder Netzwerkfehler'
      setError(`${prefix}: ${diagnosticError(failure)}. Keine automatische Wiederholung. Ausgang gegebenenfalls unklar; gespeicherten Zustand per GET neu laden, bevor Sie weitere Aktionen ausführen.`)
    } finally {
      // Auch ein fehlgeschlagener HTTP-Aufruf kann den serverseitigen Modus geändert haben.
      const refreshes = await Promise.allSettled([onCollectorChange(), onEvidenceChange()])
      if (refreshes.some(result => result.status === 'rejected')) setError(previous => `${previous ? `${previous} ` : ''}Erfassungsstatus oder Katalogbelege konnten nicht aktualisiert werden; bitte bewusst neu laden.`)
      await loadPage(page?.offset ?? 0)
      mutationGuard.current = false
      setBusy(false)
    }
  }

  const wait = run ? Math.max(0, run.wait_remaining_seconds - elapsed) : 0
  const remaining = run ? Math.max(0, run.duration_remaining_seconds - elapsed) : 0
  const active = run?.state === 'running' || run?.state === 'awaiting_review'
  const needsAck = !!run && !!blocking[run.state] && !run.acknowledged_at
  const unreviewed = run?.requests.find(item => !item.review && item.step_index === run.requests_reserved - 1)
  const disabled = busy || loading || uncertain
  const knownBlockade = page?.items.some(item => item.state === 'running' || item.state === 'awaiting_review' || (blocking[item.state] && !item.acknowledged_at))

  return <section className="diagnostics-panel" aria-labelledby="diagnostics-runs-title">
    <h2 id="diagnostics-runs-title">Manuelle Leseprüfläufe</h2>
    <p className="diagnostics-warning">Kein Dauerbetrieb, keine automatische Anfrage und keine automatische Monitoringfortsetzung. Auch erfolgreiche Antworten bestätigen weder ein neues Liveprofil noch die Anzeige. Andere Leser außerhalb des gemeinsamen Volumes werden technisch nicht erkannt.</p>
    {error && <div className="alert danger" role="alert">{error}</div>}
    {uncertain && !run && <button className="button secondary" disabled={busy || historyLoading} onClick={() => {
      setHistoryLoading(true)
      void requestJson<RunPage>(`${base}?limit=50&offset=0`).then(result => {
        setPage(result)
        if (result.items[0]) accept(result.items[0])
        setUncertain(false)
      }).catch(failure => setError(`Gespeicherter Zustand weiterhin unklar: ${diagnosticError(failure)}`)).finally(() => setHistoryLoading(false))
    }}>Gespeicherten Zustand nach unklarem Ausgang neu laden (GET)</button>}
    {storageError && <div className="diagnostics-warning" role="alert">{storageError}</div>}
    {(active || needsAck || knownBlockade) && <p className="diagnostics-warning" role="status">Diagnoseblockade: Ein aktiver oder noch nicht quittierter Lauf sperrt weitere Planung und Geräteaktionen. Eine neue Planung oder ein Refresh hebt die Blockade nicht auf. Sammlerblockaden bleiben unabhängig bestehen.</p>}
    <form className="diagnostics-fields" onSubmit={event => { event.preventDefault(); void act('create', { register_ids: registerIds, purpose }) }}>
      <label>Zweck (1–2000 Zeichen)<textarea required minLength={1} maxLength={2000} value={purpose} onChange={event => setPurpose(event.target.value)} disabled={busy} /></label>
      <p>{registerIds.length} Register ausgewählt. Der Server erweitert Kernworte zu vollständigen Kernblöcken, dedupliziert und sortiert. Nur der aufgelöste Serverplan zählt; höchstens drei Blöcke, keine Nachbar- oder Lückenbündelung.</p>
      <button className="button primary" disabled={disabled || historyLoading || !!knownBlockade || !!active || needsAck || !registerIds.length || !purpose.trim()}>Prüfplan erstellen (ohne Geräteanfrage)</button>
    </form>
    <h3>Gespeicherte Historie</h3>
    <div className="diagnostics-actions"><button className="button secondary" disabled={busy || historyLoading} onClick={() => void loadPage(page?.offset ?? 0)}>Historie neu laden (GET)</button></div>
    {historyLoading && <p role="status">Historie wird geladen …</p>}
    {page && !page.items.length && <p>Keine gespeicherten Prüfläufe auf dieser Seite.</p>}
    {page && <>
      <div className="diagnostics-table-wrap" tabIndex={0} role="region" aria-label="Prüfdaten, horizontal scrollbar"><table><caption>Prüfläufe: {page.total} insgesamt, höchstens 50 je Seite</caption><thead><tr><th>Lauf / Zeitpunkt</th><th>Zweck</th><th>Zustand / Quelle</th><th>Aktion</th></tr></thead><tbody>{page.items.map(item => <tr key={item.run_id}><td>{item.run_id}<br />{date(item.created_at)}</td><td>{item.plan.purpose}</td><td>{item.state}<br />{sourceLabel(item.source)}{blocking[item.state] && !item.acknowledged_at ? ' · Quittierung offen' : ''}</td><td><button className="button secondary" disabled={busy || loading} onClick={() => void loadRun(item.run_id)}>Ansehen</button></td></tr>)}</tbody></table></div>
      <div className="diagnostics-actions"><button className="button secondary" disabled={busy || loading || historyLoading || page.offset === 0} onClick={() => void loadPage(Math.max(0, page.offset - 50))}>Vorherige 50</button><span>{page.total ? `${page.offset + 1}–${Math.min(page.offset + page.items.length, page.total)} von ${page.total}` : '0 Läufe'}</span><button className="button secondary" disabled={busy || loading || historyLoading || page.offset + 50 >= page.total} onClick={() => void loadPage(page.offset + 50)}>Nächste 50</button></div>
    </>}
    {loading && <p role="status">Gespeicherten Lauf laden …</p>}
    {run && <article className="diagnostics-panel" aria-labelledby="diagnostics-run-detail">
      <h3 id="diagnostics-run-detail">Prüflauf {run.run_id}</h3>
      <div className="diagnostics-actions"><button className="button secondary" disabled={busy || loading} onClick={() => void loadRun(run.run_id)}>Laufzustand neu laden (GET)</button><a href={`${base}/${encodeURIComponent(run.run_id)}/export`} download>Bereinigten JSON-Beleg herunterladen (GET)</a></div>
      <p role="status"><strong>{run.state}</strong> — {descriptions[run.state]}</p>
      <p><strong>{sourceLabel(run.source)}</strong> · Alias: {run.plan.target_alias}</p>
      {run.target_changed && <p className="diagnostics-warning">Ziel geändert: Diese gespeicherten Belege stammen von einem abweichenden Ziel. Nicht als aktuelle Gerätewerte verwenden.</p>}
      <dl className="diagnostics-meta"><dt>Zweck</dt><dd>{run.plan.purpose}</dd><dt>Erstellt / zuletzt gespeichert</dt><dd>{date(run.created_at)} / {date(run.updated_at)}</dd><dt>Gestartet / beendet</dt><dd>{date(run.started_at)} / {date(run.ended_at)}</dd><dt>Anfragebudget (reserviert / gesamt)</dt><dd>{run.requests_reserved}/{run.plan.request_budget}</dd><dt>Nächste Schritt-ID (nullbasiert)</dt><dd>{run.next_step_index ?? 'keine'}</dd><dt>Verbleibende Wartezeit / Gesamtlaufzeit</dt><dd>{active ? `${Math.ceil(wait)} s / ${Math.ceil(remaining)} s` : 'nicht aktiv'}</dd><dt>Kataloghash</dt><dd>{run.plan.catalog_sha256}</dd></dl>
      <p className="muted">Countdown nur lokale Anzeige ab letztem Serverstatus. Der Server entscheidet über Fälligkeit; Ablauf sendet weder Anfrage noch Statusabfrage. Bei 0 s Gesamtlaufzeit Zustand per GET neu laden.</p>
      <h4>Verbindlich aufgelöste Serverblöcke</h4>
      <div className="diagnostics-table-wrap" tabIndex={0} role="region" aria-label="Prüfdaten, horizontal scrollbar"><table><thead><tr><th>Schritt-ID</th><th>Offset dezimal / hex</th><th>Worte</th></tr></thead><tbody>{run.plan.blocks.map((block, index) => <tr key={index}><td>{index}</td><td>{block.offset} / {hex(block.offset)}</td><td>{block.count}</td></tr>)}</tbody></table></div>
      <p>FC{String(run.plan.function_code).padStart(2, '0')} / Unit {run.plan.unit_id}; maximal zwei Worte je Anfrage; Budget {run.plan.request_budget} (höchstens 3). Gesamtdeadline {run.plan.deadline_seconds} s je Anfrage. Mindestens {run.plan.min_interval_seconds} s vor der ersten Anfrage und nach Abschluss/Speicherung jeder Antwort. Gesamtdauer höchstens {run.plan.max_duration_seconds} s ab Start.</p>
      <p className="diagnostics-warning">Sofortiger Stopp bei Fehler oder Auffälligkeit; keine Retries. Server-Stopbedingungen: {run.plan.stop_conditions.join(', ')}. Eine laufende Anfrage darf beim sicheren Stopp ihre Deadline beenden. Monitoring bleibt nach Ende und Quittierung angehalten und darf nur über die bestehende bewusste Sammleraktion wieder gestartet werden.</p>
      {run.state === 'planned' && <div className="diagnostics-fields"><label><input type="checkbox" checked={otherReaders} disabled={disabled} onChange={event => setOtherReaders(event.target.checked)} /> Ich bestätige ausdrücklich, dass andere Leser beendet sind, auch außerhalb des gemeinsamen Volumes.</label><button className="button primary" disabled={disabled || !otherReaders || run.target_changed || !!knownBlockade} onClick={() => void act('start', { other_readers_stopped: true })}>Monitoring anhalten und Prüflauf öffnen</button></div>}
      {run.state === 'running' && <button className="button primary" disabled={disabled || wait > 0 || remaining <= 0 || run.next_step_index === null} onClick={() => void act('read', { step_index: run.next_step_index })}>Nächste Anfrage lesen</button>}
      {run.state === 'awaiting_review' && <div className="diagnostics-fields"><h4>Letzte unbewertete Antwort: Schritt {unreviewed?.step_index ?? 'nicht verfügbar — Zustand neu laden'}</h4><label>Beobachtung (optional)<textarea value={observation} disabled={disabled} onChange={event => setObservation(event.target.value)} /></label><div className="diagnostics-actions">{(['continue', 'finish', 'anomaly'] as const).map(verdict => <button key={verdict} className="button secondary" disabled={disabled || !unreviewed || remaining <= 0} onClick={() => void act('review', { step_index: unreviewed!.step_index, verdict, observation: observation || null })}>{verdict === 'continue' ? 'Geprüft, weiter' : verdict === 'finish' ? 'Beenden' : 'Auffälligkeit, stoppen'}</button>)}</div><p>„Weiter“ erlaubt nur den nächsten manuellen Schritt; nach dem letzten Ergebnis wird abgeschlossen. „Beenden“ bricht ab; eine Auffälligkeit erfordert Ursachenklärung und Quittierung.</p></div>}
      {active && <button className="button secondary" disabled={disabled} onClick={() => void act('stop', {})}>Prüflauf sicher abbrechen</button>}
      {needsAck && <form className="diagnostics-fields" onSubmit={event => { event.preventDefault(); void act('acknowledge', { resolution }) }}><label>Ursachenklärung / Lösung (Pflicht)<textarea required value={resolution} disabled={disabled} onChange={event => setResolution(event.target.value)} /></label><button className="button secondary" disabled={disabled || !resolution.trim()}>Fehler nach Ursachenklärung quittieren</button><p>Quittierung startet weder diesen alten Lauf noch Monitoring. Für weitere Prüfungen ist ein neuer Plan erforderlich.</p></form>}
      {run.acknowledged_at && <p>Quittiert: {date(run.acknowledged_at)} · Ursachenklärung: {run.resolution_note}</p>}
      <h4>Gespeicherte Antworten und Bewertungen</h4>
      {!run.requests.length && <p>Noch keine Anfrage reserviert oder Antwort gespeichert.</p>}
      {run.requests.map(item => <section className="diagnostics-evidence" key={item.step_index}>
        <h4>Schritt {item.step_index}: {item.outcome}</h4>
        <p><strong>{sourceLabel(run.source)}</strong> · Beginn {date(item.started_at)} · Abschluss {date(item.completed_at)} · Datenalter {item.completed_at ? ageLabel(Math.max(0, (Date.now() - Date.parse(item.completed_at)) / 1000)) : 'noch kein abgeschlossener Beleg'}</p>
        {run.target_changed && <p className="diagnostics-warning">Abweichendes Ziel; historischer Beleg.</p>}
        <p>Empfangene Bytes: {item.received_bytes}; Fehlerklasse: {item.error_class ?? 'keine gespeichert'}</p>
        <h5>Unveränderte Rohworte</h5>
        {item.raw_words === null ? <p>Keine Rohworte gespeichert (kein Ersatzwert).</p> : <div className="diagnostics-table-wrap" tabIndex={0} role="region" aria-label="Prüfdaten, horizontal scrollbar"><table><thead><tr><th>Wortindex</th><th>Dezimal</th><th>Hexadezimal</th></tr></thead><tbody>{item.raw_words.map((word, index) => <tr key={index}><td>{index}</td><td>{word}</td><td>{hex(word)}</td></tr>)}</tbody></table></div>}
        {item.interpretation_status === 'raw_only' ? <p>raw_only — nur Rohwerte. Einheit ungeklärt; keine physikalische Interpretation und kein bestätigtes Messsignal.</p> : <div className="diagnostics-panel"><h5>Getrennte serverseitige Kerninterpretation (confirmed_core)</h5>{item.decoded_signals.length === 0 && <p>Keine dekodierten Signale geliefert.</p>}{item.decoded_signals.map(signal => <p key={signal.signal_id}><strong>{signal.signal_id}: {signal.value} {signal.unit}</strong><br />Offset {signal.offset}; Rohworte {signal.raw_words.join(', ')}; Profil {signal.profile_id}/{signal.profile_version}; Decoder {signal.decoder_version}; gelieferte Signalquelle {signal.source}. {sourceLabel(run.source)}.</p>)}</div>}
        <p>Betreiberbewertung: {item.review ? `${item.review.verdict === 'continue' ? 'Geprüft, weiter' : item.review.verdict === 'finish' ? 'Beenden' : 'Auffälligkeit, stoppen'} · ${item.review.observation || 'keine Beobachtung angegeben'}` : 'noch nicht bewertet'}</p>
      </section>)}
    </article>}
  </section>
}
