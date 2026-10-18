import { useEffect, useRef, useState } from 'react';

type Entry = {
  code: string;
  offset: number;
  name: string;
  record: boolean;
  unit: string;
  description: string;
  signal_id: string | null;
  eligible: boolean;
  blocked_reason: string | null;
  change: 'new' | 'changed' | 'unchanged';
  changed_fields: string[];
};
type Snapshot = {
  revision: number;
  entries: Entry[];
  active_revision: number | null;
  active_entries: Entry[];
  apply_status: string;
};
const MAX_CSV_BYTES = 1024 * 1024;
const fieldLabels: Record<string, string> = { name: 'Importname', offset: 'Offset', code: 'Hexcode', unit: 'Einheit', description: 'Beschreibung', record: 'Aufzeichnen' };

async function request(url: string, init?: RequestInit): Promise<Snapshot> {
  const response = await fetch(url, init);
  const body = await response.json().catch(() => null);
  if (!response.ok) throw new Error(typeof body?.detail === 'string' ? body.detail : `Anfrage fehlgeschlagen (HTTP ${response.status}).`);
  if (!body || !Number.isInteger(body.revision) || !Array.isArray(body.entries)) throw new Error('Die API lieferte keine gültige Konfiguration.');
  return { ...body, active_entries: Array.isArray(body.active_entries) ? body.active_entries : [], apply_status: body.apply_status || 'Status unbekannt' };
}
const jsonHeaders = { 'Content-Type': 'application/json', 'X-Requested-With': 'SommerauerMonitor' };

export default function LoggingConfig() {
  const [saved, setSaved] = useState<Snapshot | null>(null);
  const [draft, setDraft] = useState<Entry[]>([]);
  const [revision, setRevision] = useState<number | null>(null);
  const [dirty, setDirty] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [pollError, setPollError] = useState('');
  const [notice, setNotice] = useState('');
  const initialized = useRef(false);

  useEffect(() => {
    let disposed = false;
    let pending = false;
    const refresh = async () => {
      if (pending) return;
      pending = true;
      try {
        const result = await request('/api/logging-config');
        if (disposed) return;
        setSaved((previous) => !previous || result.revision >= previous.revision ? result : previous);
        setPollError('');
        if (!initialized.current) {
          initialized.current = true;
          setRevision(result.revision);
          setDraft(result.entries);
        }
      } catch (failure) {
        if (!disposed) setPollError(failure instanceof Error ? failure.message : 'Status konnte nicht geladen werden.');
      } finally { pending = false; }
    };
    void refresh();
    const timer = window.setInterval(() => void refresh(), 5000);
    return () => { disposed = true; window.clearInterval(timer); };
  }, []);

  const update = (code: string, field: 'unit' | 'description', value: string) => {
    setDraft((entries) => entries.map((entry) => entry.code === code ? { ...entry, [field]: value } : entry));
    setDirty(true);
    setNotice('');
  };
  const toggle = (entry: Entry, checked: boolean) => {
    const group = entry.signal_id ? draft.filter((item) => item.signal_id === entry.signal_id) : [entry];
    if (!group.every((item) => item.eligible)) return;
    const codes = new Set(group.map((item) => item.code));
    setDraft((entries) => entries.map((item) => codes.has(item.code) ? { ...item, record: checked } : item));
    setDirty(true);
    setNotice('');
  };

  const importFile = async (file: File) => {
    if (revision === null) return;
    setBusy(true); setError(''); setNotice('');
    try {
      if (file.size > MAX_CSV_BYTES) throw new Error('Die CSV-Datei ist zu groß (maximal 1 MiB).');
      let csvText: string;
      try { csvText = new TextDecoder('utf-8', { fatal: true }).decode(await file.arrayBuffer()); }
      catch { throw new Error('Die CSV-Datei muss UTF-8-kodiert sein. Bitte vor dem Import entsprechend exportieren oder konvertieren.'); }
      const preview = await request('/api/logging-config/preview', {
        method: 'POST', headers: jsonHeaders, body: JSON.stringify({ csv_text: csvText, revision }),
      });
      const previous = new Map(draft.map((entry) => [entry.code, entry]));
      const merged = preview.entries.map((entry) => {
        const old = previous.get(entry.code);
        return old ? { ...entry, unit: old.unit, description: old.description, record: entry.eligible && old.offset === entry.offset ? old.record : false } : entry;
      });
      const previewCodes = new Set(preview.entries.map((entry) => entry.code));
      merged.push(...draft.filter((entry) => !previewCodes.has(entry.code)));
      const counterChanged = merged.some((entry) => entry.signal_id === 'boiler.operating_minutes' && entry.offset !== previous.get(entry.code)?.offset);
      setDraft(counterChanged ? merged.map((entry) => entry.signal_id === 'boiler.operating_minutes' ? { ...entry, record: false } : entry) : merged);
      setDirty(true);
      setNotice('CSV als Entwurf übernommen. Importfelder entsprechen der neuen Vorschau auf Basis der gespeicherten Konfiguration; bisherige Metadaten bleiben erhalten. Gespeichert wird erst mit „Entwurf speichern“.');
    } catch (failure) { setError(failure instanceof Error ? failure.message : 'CSV konnte nicht importiert werden.'); }
    finally { setBusy(false); }
  };

  const reload = async () => {
    setBusy(true); setError(''); setNotice('');
    try {
      const result = await request('/api/logging-config');
      setSaved(result); setDraft(result.entries); setRevision(result.revision); setDirty(false);
      initialized.current = true;
      setPollError(''); setNotice('Gespeicherte Konfiguration neu geladen; der bisherige Entwurf wurde verworfen.');
    } catch (failure) { setError(failure instanceof Error ? failure.message : 'Neuladen fehlgeschlagen. Der Entwurf bleibt erhalten.'); }
    finally { setBusy(false); }
  };
  const save = async () => {
    setBusy(true); setError(''); setNotice('');
    try {
      const result = await request('/api/logging-config', {
        method: 'PUT', headers: jsonHeaders, body: JSON.stringify({ revision, entries: draft }),
      });
      setSaved(result); setDraft(result.entries); setRevision(result.revision); setDirty(false);
      setNotice('Konfiguration gespeichert. Die Übernahme erfolgt an einer sicheren Zyklusgrenze; die Erfassung wurde weder gestartet noch pausiert.');
    } catch (failure) { setError(`${failure instanceof Error ? failure.message : 'Speichern fehlgeschlagen.'} Der Entwurf bleibt erhalten. Bei einem Versionskonflikt bitte ausdrücklich verwerfen und neu laden.`); }
    finally { setBusy(false); }
  };

  const rank = { new: 0, changed: 1, unchanged: 2 };
  const rows = [...draft].sort((a, b) => (rank[a.change] ?? 2) - (rank[b.change] ?? 2) || a.code.localeCompare(b.code));
  const conflict = saved !== null && revision !== null && saved.revision !== revision;
  return <main className="dashboard logging-page">
    <header className="topbar"><div><p className="eyebrow">OFFLINE-KONFIGURATION</p><h1>Modbus <span>Aufzeichnung</span></h1></div></header>
    <p className="logging-intro">Importieren und wählen Sie Register für die Aufzeichnung. Nur das bestätigte Kernprofil ist freigegeben. Es werden keine Geräteaktionen ausgelöst und keine zusätzlichen Decoder eingerichtet.</p>
    <section className="logging-status" aria-labelledby="logging-status-title">
      <h2 id="logging-status-title">Gespeichert und tatsächlich aktiv</h2>
      {saved ? <><dl><div><dt>Gespeicherte Revision</dt><dd>{saved.revision}</dd></div><div><dt>Aktive Revision</dt><dd>{saved.active_revision ?? 'Keine aktive Revision'}</dd></div><div><dt>Übernahmestatus</dt><dd>{saved.apply_status}</dd></div></dl>
        {([{ label: 'Gespeicherte Auswahl', entries: saved.entries }, { label: 'Aktive Auswahl', entries: saved.active_entries }]).map(({ label, entries }) => <p key={label}><strong>{label}:</strong> {entries.filter((entry) => entry.record).map((entry) => `${entry.name || entry.code} (${entry.code})`).join(', ') || 'Keine Register ausgewählt'}</p>)}
        {saved.active_revision !== saved.revision && <p className="alert">Die gespeicherte Revision ist noch nicht als aktiv bestätigt. Maßgeblich sind aktive Revision und Übernahmestatus.</p>}</> : <p>Konfiguration wird geladen …</p>}
      <p className="muted">Statusaktualisierung alle 5 Sekunden; Ihr Entwurf wird dabei nicht überschrieben.</p>
    </section>
    {pollError && <p className="alert danger" role="alert">Status möglicherweise veraltet: {pollError}</p>}
    {error && <p className="alert danger" role="alert">{error}</p>}
    {notice && <p className="logging-notice" role="status">{notice}</p>}
    {conflict && <p className="alert" role="alert">Die gespeicherte Revision wurde zwischenzeitlich geändert. Ihr Entwurf auf Basis von Revision {revision} bleibt erhalten. Zum Übernehmen der aktuellen Wahrheit „Entwurf verwerfen und neu laden“ verwenden.</p>}
    <section className="logging-import" aria-labelledby="logging-import-title">
      <h2 id="logging-import-title">CSV importieren</h2>
      <p id="csv-help">UTF-8, ohne Kopfzeile, mit Semikolon: <code>Name;dezimaler Offset;interner Hexcode</code>, zum Beispiel <code>Kessel_Ist;4102;1006</code>. Maximal 1 MiB. Neue Register und fachlich relevante Offsetänderungen werden nicht automatisch aufgezeichnet.</p>
      {dirty && <p className="alert">Ein Entwurf ist bereits vorhanden. Ein weiterer Import erstellt die Importfelder erneut auf Basis der gespeicherten Konfiguration. Ungespeicherte Einheit/Beschreibung bleiben erhalten, die Auswahl nur bei unverändertem Offset und gültiger Freigabe. Speichern Sie den Entwurf zuerst, wenn dessen Importfelder die Grundlage des nächsten Imports sein sollen.</p>}
      <label htmlFor="logging-csv">CSV-Datei als Entwurf einlesen<input id="logging-csv" type="file" accept=".csv,text/csv,text/plain" aria-describedby="csv-help" disabled={busy || revision === null || conflict} onChange={(event) => { const file = event.target.files?.[0]; event.target.value = ''; if (file) void importFile(file); }} /></label>
    </section>
    <section aria-labelledby="logging-draft-title">
      <div className="section-heading"><div><h2 id="logging-draft-title">Gemeinsamer Entwurf</h2><p className="muted">Basisrevision {revision ?? '—'} · {dirty ? 'Ungespeicherte Änderungen' : 'Keine ungespeicherten Änderungen'} · {draft.length} Register</p></div></div>
      <p id="logging-metadata-help">Einheit und Beschreibung sind reine Betreiber-Metadaten. Sie ändern weder Decoder noch Umrechnung oder Einheiten gespeicherter Messungen. Historische Daten bleiben unverändert. Der Mehrwortzähler 7010/7011 wird nur vollständig und gemeinsam geschaltet.</p>
      <div className="logging-table-wrap" role="region" aria-label="Registerkonfiguration, horizontal scrollbar" tabIndex={0}>
        <table className="logging-table" aria-describedby="logging-metadata-help"><caption>Neue und geänderte Importzeilen zuerst; Auswahl und Metadaten werden gemeinsam gespeichert.</caption>
          <thead><tr><th scope="col">Import / Änderung</th><th scope="col">Hexcode</th><th scope="col">Offset (dezimal)</th><th scope="col">Aufzeichnen</th><th scope="col">Einheit (Metadaten)</th><th scope="col">Beschreibung (Metadaten)</th><th scope="col">Freigabe / Signal</th></tr></thead>
          <tbody>{rows.map((entry) => {
            const group = entry.signal_id ? draft.filter((item) => item.signal_id === entry.signal_id) : [entry];
            const eligible = entry.eligible && group.every((item) => item.eligible) && (entry.signal_id !== 'boiler.operating_minutes' || ['7010', '7011'].every((code) => group.some((item) => item.code === code)));
            const fields = Array.isArray(entry.changed_fields) ? entry.changed_fields : [];
            return <tr key={entry.code} className={`logging-row-${entry.change || 'unchanged'}`}>
              <th scope="row"><span className={fields.includes('name') ? 'import-field-changed' : ''}>{entry.name || 'Ohne Importname'}</span><span className="logging-change">{entry.change === 'new' ? 'Neu' : entry.change === 'changed' ? 'Geändert' : 'Unverändert'}</span>{fields.length > 0 && <small>Geänderte Felder: {fields.map((field) => fieldLabels[field] || field).join(', ')}</small>}</th>
              <td><code className={fields.includes('code') ? 'import-field-changed' : ''}>{entry.code}</code></td><td><span className={fields.includes('offset') ? 'import-field-changed' : ''}>{entry.offset ?? '—'}</span></td>
              <td><label className="logging-check"><input type="checkbox" checked={Boolean(entry.record)} disabled={busy || !eligible} aria-describedby={`eligibility-${entry.code}`} onChange={(event) => toggle(entry, event.target.checked)} />{entry.code} aufzeichnen</label></td>
              <td><label className="visually-hidden" htmlFor={`unit-${entry.code}`}>Betreibereinheit für {entry.code}</label><input id={`unit-${entry.code}`} type="text" maxLength={40} value={entry.unit ?? ''} disabled={busy} onChange={(event) => update(entry.code, 'unit', event.target.value)} /></td>
              <td><label className="visually-hidden" htmlFor={`description-${entry.code}`}>Betreiberbeschreibung für {entry.code}</label><textarea id={`description-${entry.code}`} rows={2} maxLength={2000} value={entry.description ?? ''} disabled={busy} onChange={(event) => update(entry.code, 'description', event.target.value)} /></td>
              <td id={`eligibility-${entry.code}`}><span className={eligible ? 'logging-eligible' : 'logging-blocked'}>{eligible ? 'Bestätigtes Kernprofil' : entry.blocked_reason || 'Ungeprüft oder Mehrwortzuordnung unvollständig; Aufzeichnung gesperrt.'}</span><small>{entry.signal_id || 'Kein bestätigter Decoder'}</small></td>
            </tr>;
          })}</tbody>
        </table>
        {revision !== null && !rows.length && <p>Keine Register vorhanden. Importieren Sie eine CSV-Datei.</p>}
      </div>
      <div className="logging-actions"><button type="button" className="button primary" disabled={busy || !dirty || revision === null || conflict} onClick={() => void save()}>{busy ? 'Bitte warten …' : 'Entwurf speichern'}</button><button type="button" className="button secondary" disabled={busy} onClick={() => void reload()}>Entwurf verwerfen und neu laden</button></div>
      <p className="muted">Speichern überträgt die gesamte Auswahl atomar. Es startet, quittiert oder pausiert die Erfassung nicht.</p>
    </section>
  </main>;
}
