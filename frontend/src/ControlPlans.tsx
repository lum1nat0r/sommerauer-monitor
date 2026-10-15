import { useCallback, useEffect, useRef, useState } from 'react';
import type { FormEvent } from 'react';
import { ApiError, diagnosticError, mutation, requestJson } from './api';
import { formatDate } from './format';

const fields = [
  { name: 'candidate_id', label: 'Kandidaten-ID', required: true },
  { name: 'purpose', label: 'Zweck', required: true },
  { name: 'source_reference', label: 'Quellenreferenz' },
  { name: 'address_evidence', label: 'Adress- und Stellwegnachweis' },
  { name: 'function_code', label: 'Funktionscode (1 bis 127)', numeric: true, integer: true },
  { name: 'encoding_evidence', label: 'Kodierungsnachweis' },
  { name: 'before_value', label: 'Vorherwert (Text)' },
  { name: 'test_value', label: 'Testwert (Text)' },
  { name: 'restore_value', label: 'Rückstellwert (Text)' },
  { name: 'value_unit', label: 'Einheit der Werte' },
  { name: 'allowed_range_evidence', label: 'Nachweis des zulässigen Bereichs' },
  { name: 'max_duration_seconds', label: 'Maximale Dauer (Sekunden, positiv)', numeric: true },
  { name: 'max_write_requests', label: 'Maximale Schreibanfragen (positive ganze Zahl)', numeric: true, integer: true },
  { name: 'stop_conditions', label: 'Stopbedingungen' },
  { name: 'verification_steps', label: 'Prüfschritte' },
  { name: 'restore_steps', label: 'Rückstellschritte' },
  { name: 'host_loss_behavior', label: 'Verhalten bei Hostausfall' },
  { name: 'network_loss_behavior', label: 'Verhalten bei Netzausfall' },
  { name: 'device_restart_behavior', label: 'Verhalten bei Geräteneustart' },
  { name: 'operator_approval_reference', label: 'Referenz der konkreten Betreiberfreigabe' },
] as const;

type FieldName = typeof fields[number]['name'];
type FormValues = Record<FieldName, string>;
type Draft = Record<FieldName, string | number | null>;
type Assessment = { status: 'draft' | 'ready_for_review'; missing_fields: string[]; blockers: string[] };
type ControlDocument = {
  plan_id: string;
  revision: number;
  created_at: string;
  draft: Draft;
  source_status: { kind: 'operator_provided'; independently_verified: false };
  assessment: Assessment;
  execution_enabled: false;
};
const endpoint = '/api/diagnostics/control-plans';
const documentUrl = (id: string) => `${endpoint}/${encodeURIComponent(id)}`;
const labels: Record<string, string> = Object.fromEntries(fields.map(field => [field.name, field.label]));
const blockerLabels: Record<string, string> = {
  actuation_path_requires_source_evidence: 'Stellweg benötigt einen belastbaren Quellennachweis',
  encoding_requires_source_evidence: 'Kodierung benötigt einen belastbaren Quellennachweis',
  device_change_requires_separate_approval: 'Konkrete Geräteänderung benötigt eine gesonderte Freigabe',
  execution_not_available: 'Keine Ausführungsfunktion verfügbar',
  autonomous_fallback_on_host_or_network_loss_unverified: 'Autonomer Rückfall bei Host- oder Netzausfall ungeklärt',
  sensor_value_must_not_be_overridden: 'Echte Sensormesswerte dürfen nicht überschrieben werden',
};
function emptyForm(candidateId: string | null): FormValues {
  return Object.fromEntries(fields.map(field => [field.name, field.name === 'candidate_id' ? candidateId ?? '' : ''])) as FormValues;
}
function formFromDraft(draft: Draft): FormValues {
  return Object.fromEntries(fields.map(field => [field.name, draft[field.name] == null ? '' : String(draft[field.name])])) as FormValues;
}
function draftFromForm(form: FormValues): Draft {
  return Object.fromEntries(fields.map(field => {
    const value = form[field.name];
    return [field.name, !value.trim() ? null : 'numeric' in field ? Number(value) : value];
  })) as Draft;
}
function AssessmentView({ assessment }: { assessment: Assessment }) {
  return <div className="diagnostics-evidence">
    <p><strong>{assessment.status === 'ready_for_review' ? 'Formal bereit zur fachlichen Prüfung' : 'Unvollständiger Entwurf'}</strong> <code>{assessment.status}</code></p>
    <h5>Fehlende Angaben</h5>
    {assessment.missing_fields.length === 0 ? <p>Keine formalen Angaben fehlen. Das ist keine Gerätefreigabe.</p> : <ul>{assessment.missing_fields.map(name => <li key={name}>{labels[name] ?? 'Unbekanntes Feld'} <code>{name}</code></li>)}</ul>}
    <h5>Unveränderliche Blockaden</h5>
    {assessment.blockers.length === 0 ? <p>Keine Blockaden geliefert. Eine Ausführung ist trotzdem nicht verfügbar.</p> : <ul>{assessment.blockers.map(code => <li key={code}>{blockerLabels[code] ?? 'Weitere serverseitige Blockade'} <code>{code}</code></li>)}</ul>}
  </div>;
}
function SavedDocument({ document, timeZone }: { document: ControlDocument; timeZone: string }) {
  return <div className="diagnostics-evidence">
    <p>Plan <code>{document.plan_id}</code>, Revision <strong>{document.revision}</strong>, gespeichert {formatDate(document.created_at, timeZone)}</p>
    <p>Quelle: Betreiberangaben (<code>{document.source_status.kind}</code>); unabhängig verifiziert: {document.source_status.independently_verified ? 'ja' : 'nein'}. <code>execution_enabled: false</code></p>
    <AssessmentView assessment={document.assessment} />
    <details><summary>Alle gespeicherten Angaben dieser Revision</summary>
      <dl className="diagnostics-meta">{fields.map(field => <div key={field.name}><dt>{field.label} <code>{field.name}</code></dt><dd>{document.draft[field.name] == null ? 'Unbekannt (null)' : String(document.draft[field.name])}</dd></div>)}</dl>
    </details>
    <p><a href={`${documentUrl(document.plan_id)}/export`} download>Aktuelle Serverrevision des Steuerplans als JSON exportieren (GET)</a></p>
  </div>;
}

export default function ControlPlans({ candidateId, timeZone }: { candidateId: string | null; timeZone: string }) {
  const [form, setForm] = useState<FormValues>(() => emptyForm(candidateId));
  const [baseline, setBaseline] = useState(() => JSON.stringify(emptyForm(candidateId)));
  const [saved, setSaved] = useState<ControlDocument | null>(null);
  const [serverDocument, setServerDocument] = useState<ControlDocument | null>(null);
  const [items, setItems] = useState<ControlDocument[]>([]);
  const [selectedId, setSelectedId] = useState('');
  const [listLoading, setListLoading] = useState(true);
  const [listLoaded, setListLoaded] = useState(false);
  const [listError, setListError] = useState('');
  const [loadingDocument, setLoadingDocument] = useState(false);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [mustAdopt, setMustAdopt] = useState(false);
  const [replaceConfirmed, setReplaceConfirmed] = useState(false);
  const mutationLock = useRef(false);
  const documentLock = useRef(false);
  const listVersion = useRef(0);
  const dirty = JSON.stringify(form) !== baseline;
  const canReplace = !dirty || replaceConfirmed;

  const refreshList = useCallback(async () => {
    const version = ++listVersion.current;
    setListLoading(true);
    setListError('');
    try {
      const result = await requestJson<{ items: ControlDocument[] }>(endpoint);
      if (version === listVersion.current) {
        setItems(result.items);
        setListLoaded(true);
      }
    } catch (failure) {
      if (version === listVersion.current) setListError(diagnosticError(failure));
    } finally {
      if (version === listVersion.current) setListLoading(false);
    }
  }, []);

  useEffect(() => {
    void refreshList();
    return () => { listVersion.current += 1; };
  }, [refreshList]);

  async function loadDocument(id: string) {
    if (!id || mutationLock.current || documentLock.current) return;
    documentLock.current = true;
    setLoadingDocument(true);
    setError('');
    try {
      const result = await requestJson<ControlDocument>(documentUrl(id));
      setServerDocument(result);
      setNotice('Serverstand geladen. Die Formulareingaben bleiben unverändert, bis Sie die Revision ausdrücklich übernehmen.');
    } catch (failure) {
      setError(diagnosticError(failure));
    } finally {
      documentLock.current = false;
      setLoadingDocument(false);
    }
  }

  function prepareDraft() {
    if (mutationLock.current || documentLock.current || !canReplace) return;
    const next = emptyForm(candidateId);
    setForm(next);
    setBaseline(JSON.stringify(next));
    setSaved(null);
    setServerDocument(null);
    setMustAdopt(false);
    setReplaceConfirmed(false);
    setError('');
    setNotice('Neuer Offline-Entwurf vorbereitet. Es wurde nichts gespeichert und keine Geräteanfrage ausgeführt.');
  }

  function adoptDocument() {
    if (!serverDocument || mutationLock.current || documentLock.current || !canReplace) return;
    const next = formFromDraft(serverDocument.draft);
    setForm(next);
    setBaseline(JSON.stringify(next));
    setSaved(serverDocument);
    setSelectedId(serverDocument.plan_id);
    setMustAdopt(false);
    setReplaceConfirmed(false);
    setError('');
    setNotice(`Serverrevision ${serverDocument.revision} ausdrücklich in das Formular übernommen.`);
  }

  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (mutationLock.current || documentLock.current || mustAdopt) return;
    mutationLock.current = true;
    setPending(true);
    setError('');
    setNotice('');
    const draft = draftFromForm(form);
    try {
      const result = await requestJson<ControlDocument>(saved ? documentUrl(saved.plan_id) : endpoint,
        saved ? mutation('PUT', { expected_revision: saved.revision, draft }) : mutation('POST', draft));
      setSaved(result);
      setServerDocument(null);
      setSelectedId(result.plan_id);
      const next = formFromDraft(result.draft);
      setForm(next);
      setBaseline(JSON.stringify(next));
      setReplaceConfirmed(false);
      setNotice(`Revision ${result.revision} gespeichert. Die Bewertung betrifft nur formale Vollständigkeit, keine Ausführbarkeit.`);
      await refreshList();
    } catch (failure) {
      const conflict = failure instanceof ApiError && failure.status === 409;
      const uncertain = !(failure instanceof ApiError) || failure.status >= 500;
      if (conflict || uncertain) setMustAdopt(true);
      setError(`${conflict ? 'Revisionskonflikt: Ihr Konfliktentwurf bleibt vollständig im Formular erhalten. ' : ''}${diagnosticError(failure)}`);
      setNotice('Kein automatischer Speicherversuch. Gespeicherter Zustand wird nur per GET nachgeladen; Ihre Eingaben und die bisherige Bewertung bleiben erhalten.');
      if (saved) {
        try {
          setServerDocument(await requestJson<ControlDocument>(documentUrl(saved.plan_id)));
        } catch (reloadFailure) {
          setError(previous => `${previous} Serverrevision konnte nicht geladen werden: ${diagnosticError(reloadFailure)}`);
        }
      }
      await refreshList();
    } finally {
      mutationLock.current = false;
      setPending(false);
    }
  }

  return <section className="diagnostics-panel" aria-labelledby="diagnostics-control-heading">
    <h3 id="diagnostics-control-heading">Offline-Steuerpläne</h3>
    <div className="diagnostics-warning">
      <p><strong>Keine Geräteänderung und keine Ausführung.</strong> <code>execution_enabled: false</code></p>
      <p>Stellweg und Kodierung benötigen belastbare Quellennachweise. Jede konkrete Geräteänderung benötigt eine gesonderte Gerätefreigabe. Hier gibt es keine Ausführungsfunktion, auch nicht bei vollständig ausgefülltem Formular.</p>
      <p>Betreibertexte sind keine unabhängig verifizierten Quellen und kein Nachweis eines autonomen Timers. LAN, Tailscale und Same-Origin sind weder Benutzeridentität noch Geräteänderungsfreigabe.</p>
      <p>Für Sensorkanäle gilt unveränderlich: Echte Sensormesswerte dürfen nicht überschrieben werden (<code>sensor_value_must_not_be_overridden</code>).</p>
      {(form.candidate_id === 'control:buffer.start' || form.candidate_id === 'control:buffer.target') && <p><strong>START/SOLL:</strong> Autonomer Rückfall bei Host- oder Netzausfall ist ungeklärt (<code>autonomous_fallback_on_host_or_network_loss_unverified</code>). Potenzielle Offsets sind keine freigegebenen Schreibadressen.</p>}
    </div>

    <h4>Gespeicherte Entwürfe</h4>
    <div className="diagnostics-actions">
      <button type="button" className="button secondary" disabled={listLoading || pending} onClick={() => void refreshList()}>Liste neu laden (GET)</button>
    </div>
    {listLoading && <p role="status">Gespeicherte Steuerpläne werden geladen …</p>}
    {listError && <p className="alert danger" role="alert">{listError} Die bisherige Liste bleibt erhalten.</p>}
    {listLoaded && !listLoading && items.length === 0 && <p>Noch keine gespeicherten Steuerpläne. Bereiten Sie einen Entwurf vor und speichern Sie ihn ausdrücklich.</p>}
    {items.length > 0 && <div className="diagnostics-fields">
      <label htmlFor="diagnostics-control-select">Gespeicherten Plan auswählen</label>
      <select id="diagnostics-control-select" value={selectedId} disabled={pending || loadingDocument} onChange={event => setSelectedId(event.target.value)}>
        <option value="">Bitte auswählen</option>
        {items.map(item => <option key={item.plan_id} value={item.plan_id}>{String(item.draft.candidate_id)} · Revision {item.revision} · {String(item.draft.purpose)} · {item.plan_id}</option>)}
      </select>
      <button type="button" className="button secondary" disabled={!selectedId || pending || loadingDocument} onClick={() => void loadDocument(selectedId)}>Ausgewählten Serverstand laden (GET)</button>
    </div>}
    {loadingDocument && <p role="status">Serverrevision wird geladen; Eingaben bleiben erhalten …</p>}
    {error && <p className="alert danger" role="alert">{error}</p>}
    {notice && <p role="status">{notice}</p>}
    {saved && <div className="diagnostics-evidence"><h4>Bisher gespeicherte Basis des Formulars</h4><SavedDocument document={saved} timeZone={timeZone} /></div>}
    {mustAdopt && <p className="diagnostics-warning" role="alert">Speichern gesperrt: Der Ausgang oder die Revision ist nicht verlässlich geklärt. Vergleichen Sie Ihren unveränderten Entwurf unten mit dem aktuellen Serverstand. Laden und übernehmen Sie einen gespeicherten Plan ausdrücklich oder bereiten Sie bewusst einen neuen Entwurf vor. Nach unklarem Anlegen zuerst die Liste prüfen, um keine Dublette zu erzeugen.</p>}
    {serverDocument && <div className="diagnostics-evidence">
      <h4>Aktueller geladener Serverstand: Revision {serverDocument.revision}</h4>
      <p>Dieser Serverstand ersetzt Ihre Formulareingaben nicht automatisch.</p>
      <SavedDocument document={serverDocument} timeZone={timeZone} />
    </div>}

    <h4>{saved ? `Arbeitsentwurf auf Basis von Revision ${saved.revision}` : 'Neuer Arbeitsentwurf'}</h4>
    <p>Aktuelle Katalogauswahl: <code>{candidateId ?? 'keine'}</code>. Ein Auswahlwechsel ersetzt niemals automatisch Eingaben. „Neuen Entwurf vorbereiten“ übernimmt diese Auswahl und leert die übrigen Felder.</p>
    {dirty && <label className="diagnostics-warning"><input type="checkbox" checked={replaceConfirmed} disabled={pending || loadingDocument} onChange={event => setReplaceConfirmed(event.target.checked)} /> Ich möchte meine ungespeicherten Eingaben beim Vorbereiten oder Übernehmen ausdrücklich verwerfen.</label>}
    <div className="diagnostics-actions">
      <button type="button" className="button secondary" disabled={pending || loadingDocument || !canReplace} onClick={prepareDraft}>Neuen Entwurf vorbereiten</button>
      {saved && <button type="button" className="button secondary" disabled={pending || loadingDocument} onClick={() => void loadDocument(saved.plan_id)}>Aktuelle Serverrevision laden (GET)</button>}
      {serverDocument && <button type="button" className="button secondary" disabled={pending || loadingDocument || !canReplace} onClick={adoptDocument}>Serverrevision {serverDocument.revision} ausdrücklich übernehmen</button>}
    </div>
    <p>Nur Kandidaten-ID und Zweck sind Pflicht. Unbekannte optionale Angaben bleiben leer und werden als <code>null</code> gespeichert. Texte: maximal 4000 Zeichen. Vorher-, Test- und Rückstellwert sind unveränderte Texte mit separater Einheit, ohne automatische Registerkodierung oder erfundene Sollwertgrenzen.</p>
    <form onSubmit={event => void save(event)}>
      <fieldset disabled={pending || loadingDocument} className="diagnostics-fields">
        <legend>Alle Angaben zum Offline-Entwurf{dirty ? ' (ungespeicherte Änderungen)' : ''}</legend>
        {fields.map(field => <label key={field.name} htmlFor={`diagnostics-control-${field.name}`}>
          {field.label}{'required' in field ? ' (Pflichtfeld)' : ' (optional)'} <code>{field.name}</code>
          {'numeric' in field ? <input id={`diagnostics-control-${field.name}`} name={field.name} type="number" value={form[field.name]} min={field.name === 'max_duration_seconds' ? Number.MIN_VALUE : 1} max={field.name === 'function_code' ? 127 : undefined} step={'integer' in field ? 1 : 'any'} onChange={event => {
            setForm(previous => ({ ...previous, [field.name]: event.target.value }));
            setReplaceConfirmed(false);
          }} /> : <textarea id={`diagnostics-control-${field.name}`} name={field.name} rows={field.name === 'candidate_id' || field.name === 'value_unit' ? 1 : 3} maxLength={4000} required={'required' in field} value={form[field.name]} onChange={event => {
            setForm(previous => ({ ...previous, [field.name]: event.target.value }));
            setReplaceConfirmed(false);
          }} />}
        </label>)}
        <button type="submit" className="button primary" disabled={mustAdopt}>{pending ? 'Speichert …' : saved ? `Neue Revision speichern (Basis ${saved.revision}) und bewerten` : 'Entwurf anlegen und bewerten'}</button>
      </fieldset>
    </form>
    <p className="muted">Bewerten speichert ausschließlich offline. Export lädt die aktuelle Serverrevision, nicht zwingend die dargestellte Basisrevision. Ungespeicherte Eingaben sind nicht enthalten. Es gibt keinen Schreib- oder Ausführen-Knopf.</p>
  </section>;
}
