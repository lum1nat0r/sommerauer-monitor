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
  kind?: string;
  live_confirmed?: boolean;
  label?: string | null;
  verification_status?: string;
  module_status?: string;
  read_to_clear?: boolean;
  decoder?: string;
  information?: string;
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
const MAX_TRANSFER_BYTES = 4 * 1024 * 1024 - 1024;
const fieldLabels: Record<string, string> = { name: 'Importname', offset: 'Offset', code: 'Hexcode', unit: 'Einheit', description: 'Beschreibung', record: 'Aufzeichnen' };
const counterCodes: Record<string, string[]> = {
  'boiler.operating_minutes': ['7010', '7011'],
  'stoker.operating_minutes': ['7012', '7013'],
};
const kindLabels: Record<string, string> = {
  measurement: 'Messwert', derived: 'Abgeleiteter Wert / Regelgröße', counter: 'Zähler',
  status: 'Status / Kennung', setting: 'Einstellung', raw: 'Herstellerrohwert', device_time: 'Steuerungsdatum / -zeit',
};
function groupEligible(entry: Entry, group: Entry[]) {
  return entry.eligible && group.every((item) => item.eligible)
    && (counterCodes[entry.signal_id || ''] || []).every((code) => group.some((item) => item.code === code));
}

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
    if (!groupEligible(entry, group)) return;
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
        return old ? { ...entry, unit: old.unit, description: old.description } : entry;
      });
      setDraft(merged);
      setDirty(true);
      setNotice('CSV als Entwurf übernommen. Interpretierbare Einträge mit passender Lesezuordnung sind vorgewählt. Bisherige Metadaten bleiben erhalten. Aktiv wird die Auswahl erst mit „Entwurf speichern“.');
    } catch (failure) { setError(failure instanceof Error ? failure.message : 'CSV konnte nicht importiert werden.'); }
    finally { setBusy(false); }
  };

  const exportFile = async () => {
    setBusy(true); setError(''); setNotice('');
    try {
      const response = await fetch('/api/logging-config/export');
      if (!response.ok) {
        const body = await response.json().catch(() => null);
        throw new Error(typeof body?.detail === 'string' ? body.detail : `Export fehlgeschlagen (HTTP ${response.status}).`);
      }
      const url = URL.createObjectURL(await response.blob());
      const link = document.createElement('a');
      link.href = url; link.download = 'sommerauer-aufzeichnung.json';
      document.body.append(link);
      link.click(); link.remove();
      window.setTimeout(() => URL.revokeObjectURL(url), 1000);
      setNotice('Gespeicherte Konfiguration heruntergeladen. Ungespeicherter Entwurf und eine gegebenenfalls ältere aktive Auswahl sind nicht enthalten.');
    } catch (failure) { setError(failure instanceof Error ? failure.message : 'JSON-Export fehlgeschlagen.'); }
    finally { setBusy(false); }
  };

  const importJsonFile = async (file: File) => {
    if (revision === null) return;
    if (dirty && !window.confirm('Lokalen ungespeicherten Entwurf durch die JSON-Dateiauswahl ersetzen? Alle bisherigen Entwurfsänderungen werden verworfen. Die gespeicherte Konfiguration bleibt unverändert.')) return;
    setBusy(true); setError(''); setNotice('');
    try {
      if (file.size > MAX_TRANSFER_BYTES) throw new Error('Die JSON-Datei ist zu groß (maximal 4 MiB abzüglich 1 KiB Anfragehülle).');
      let configuration: unknown;
      try { configuration = JSON.parse(new TextDecoder('utf-8', { fatal: true }).decode(await file.arrayBuffer())); }
      catch { throw new Error('Die Datei muss gültiges UTF-8-JSON enthalten.'); }
      const preview = await request('/api/logging-config/import-preview', {
        method: 'POST', headers: jsonHeaders, body: JSON.stringify({ revision, configuration }),
      });
      setDraft(preview.entries);
      setDirty(true);
      setNotice('JSON-Auswahl und Betreiber-Metadaten als Entwurf übernommen. Nur im Ziel vorhandene Register bleiben erhalten, sind aber abgewählt. Prüfen und „Entwurf speichern“ wählen; bisher wurde nichts gespeichert oder an der Erfassung geändert.');
    } catch (failure) { setError(`${failure instanceof Error ? failure.message : 'JSON konnte nicht importiert werden.'} Der bisherige Entwurf bleibt erhalten.`); }
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
        method: 'PUT', headers: jsonHeaders, body: JSON.stringify({
          revision,
          entries: draft.map(({ code, offset, name, record, unit, description }) => ({ code, offset, name, record, unit, description })),
        }),
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
    <header className="topbar"><div><p className="eyebrow">MODBUS-KONFIGURATION</p><h1>Modbus <span>Aufzeichnung</span></h1></div></header>
    <p className="logging-intro">Register auswählen oder eine CSV-/JSON-Datei importieren. Änderungen werden erst mit „Entwurf speichern“ übernommen.</p>
    <section className="logging-status" aria-labelledby="logging-status-title">
      <h2 id="logging-status-title">Aufzeichnungsstatus</h2>
      {saved ? <><dl>
        <div><dt>Ausgewählt</dt><dd>{saved.entries.filter((entry) => entry.record).length} Register</dd></div>
        <div><dt>Übernahme</dt><dd>{saved.apply_status}</dd></div>
        <div><dt>Revision</dt><dd>{saved.revision}</dd></div>
      </dl>
        {saved.active_revision !== saved.revision && <p className="alert">Übernahme noch nicht bestätigt. Aktiv: {saved.active_entries.filter((entry) => entry.record).length} Register · Revision {saved.active_revision ?? 'noch keine'}.</p>}
      </> : <p>Konfiguration wird geladen …</p>}
    </section>
    {pollError && <p className="alert danger" role="alert">Status möglicherweise veraltet: {pollError}</p>}
    {error && <p className="alert danger" role="alert">{error}</p>}
    {notice && <p className="logging-notice" role="status">{notice}</p>}
    {conflict && <p className="alert" role="alert">Die gespeicherte Revision wurde zwischenzeitlich geändert. Ihr Entwurf auf Basis von Revision {revision} bleibt erhalten. Zum Übernehmen der aktuellen Wahrheit „Entwurf verwerfen und neu laden“ verwenden.</p>}
    <div className="logging-tools">
      <details className="logging-import">
        <summary>Aufzeichnung übertragen · JSON</summary>
        <p>Gespeicherte Auswahl inklusive Namen, Einheiten und Beschreibungen auf eine andere Instanz übertragen. Ungespeicherte Änderungen sind nicht enthalten.</p>
        <p className="muted">Keine Verbindungseinstellungen, Freigaben oder Erfassungszustände. Zielinstanz benötigt passende Register und einen kompatiblen Build. Eigene Namen und Beschreibungen vor Weitergabe prüfen.</p>
        <button type="button" className="button secondary" disabled={busy || saved === null} onClick={() => void exportFile()}>Aufzeichnung herunterladen</button>
        <h3>JSON importieren</h3>
        <p id="json-help">Ersetzt Auswahl und Metadaten im Entwurf, einschließlich Abwahlen. Nur im Ziel vorhandene Register werden abgewählt. Erst Speichern übernimmt den Entwurf; die Erfassung wird nicht gestartet.</p>
        {dirty && <p className="alert">Der Import ersetzt Ihre ungespeicherten Änderungen nach Bestätigung.</p>}
        <label htmlFor="logging-json">{dirty ? 'JSON-Datei wählen und Entwurfsersetzung bestätigen' : 'JSON-Datei als Entwurf prüfen'}<input id="logging-json" type="file" accept=".json,application/json" aria-describedby="json-help" disabled={busy || revision === null || conflict} onChange={(event) => { const file = event.target.files?.[0]; event.target.value = ''; if (file) void importJsonFile(file); }} /></label>
      </details>
      <details className="logging-import">
        <summary>Register hinzufügen · CSV</summary>
        <p id="csv-help">Ergänzt die gespeicherte Konfiguration und wählt bekannte Importzeilen im Entwurf vor. Unbekannte oder unvollständige Zuordnungen bleiben gesperrt. Ändert nur den Monitor, nicht die Gerätetabelle.</p>
        <p className="muted">Ohne Kopfzeile, UTF-8, maximal 1 MiB: <code>Name;dezimaler Offset;Hexcode</code>, etwa <code>Kessel_Ist;4102;1006</code>.</p>
        <p className="alert">Protokollregister werden ebenfalls vorgewählt. Lesen leert deren Modul-Ausgangsbits; vor dem Speichern die markierten Zeilen prüfen.</p>
        {dirty && <p className="alert">Ein weiterer CSV-Import setzt die Importfelder auf Basis der gespeicherten Konfiguration neu. Ungespeicherte Einheiten und Beschreibungen übernommener Einträge bleiben erhalten.</p>}
        <label htmlFor="logging-csv">CSV-Datei als Entwurf einlesen<input id="logging-csv" type="file" accept=".csv,text/csv,text/plain" aria-describedby="csv-help" disabled={busy || revision === null || conflict} onChange={(event) => { const file = event.target.files?.[0]; event.target.value = ''; if (file) void importFile(file); }} /></label>
      </details>
    </div>
    <section aria-labelledby="logging-draft-title">
      <div className="section-heading"><div><h2 id="logging-draft-title">Registerauswahl</h2><p className="muted">{draft.filter((entry) => entry.record).length} von {draft.length} Registern ausgewählt · {dirty ? 'Ungespeicherte Änderungen' : 'Keine ungespeicherten Änderungen'}</p></div></div>
      <details className="signal-metadata">
        <summary>Hinweise zur Bearbeitung</summary>
        <p id="logging-metadata-help">Einheit und Beschreibung sind eigene Metadaten, keine Decoder-Einstellungen. Gespeicherte Messwerte bleiben unverändert. Mehrwortzähler werden gemeinsam geschaltet. Neue und geänderte Importzeilen stehen zuerst. Basisrevision: {revision ?? '—'}.</p>
      </details>
      {draft.some((entry) => entry.record && entry.read_to_clear) && <p className="alert">Protokollregister ausgewählt: Jede Auslesung leert deren Modul-Ausgangsbits. Andere Leser können dadurch Informationen verlieren. Betroffene Zeilen sind markiert.</p>}
      <div className="logging-actions"><button type="button" className="button primary" disabled={busy || !dirty || revision === null || conflict} onClick={() => void save()}>{busy ? 'Bitte warten …' : 'Entwurf speichern'}</button><button type="button" className="button secondary" disabled={busy} onClick={() => void reload()}>Entwurf verwerfen und neu laden</button></div>
      <div className="logging-table-wrap" role="region" aria-label="Registerkonfiguration, horizontal scrollbar" tabIndex={0}>
        <table className="logging-table" aria-describedby="logging-metadata-help"><caption className="visually-hidden">Registerauswahl und bearbeitbare Metadaten</caption>
          <thead><tr><th scope="col">Register</th><th scope="col">Aufzeichnung</th><th scope="col">Signal / Details</th></tr></thead>
          <tbody>{rows.map((entry) => {
            const group = entry.signal_id ? draft.filter((item) => item.signal_id === entry.signal_id) : [entry];
            const eligible = groupEligible(entry, group);
            const fields = Array.isArray(entry.changed_fields) ? entry.changed_fields : [];
            return <tr key={entry.code} className={`logging-row-${entry.change || 'unchanged'}`}>
              <th scope="row">
                <span className={fields.includes('name') ? 'import-field-changed' : ''}>{entry.name || 'Ohne Importname'}</span>
                <small><code className={fields.includes('code') ? 'import-field-changed' : ''}>{entry.code}</code> · Offset <span className={fields.includes('offset') ? 'import-field-changed' : ''}>{entry.offset ?? '—'}</span></small>
                {entry.change !== 'unchanged' && <span className="logging-change">{entry.change === 'new' ? 'Neu' : 'Geändert'}</span>}
                {fields.length > 0 && <small>Geändert: {fields.map((field) => fieldLabels[field] || field).join(', ')}</small>}
              </th>
              <td>
                <label className="logging-check"><input type="checkbox" checked={Boolean(entry.record)} disabled={busy || !eligible} aria-label={`${entry.code} aufzeichnen`} aria-describedby={`eligibility-${entry.code}${entry.read_to_clear ? ` risk-${entry.code}` : ''}`} onChange={(event) => toggle(entry, event.target.checked)} />Aufzeichnen</label>
                {entry.read_to_clear && <p className="read-clear-warning" id={`risk-${entry.code}`}>Protokollregister: Lesen leert Modul-Ausgangsbits, auch für andere Leser.</p>}
              </td>
              <td>
                <div id={`eligibility-${entry.code}`}><strong>{entry.label || entry.name}</strong>
                  {!eligible && <span className="logging-blocked">{entry.blocked_reason || 'Unbekannte oder unvollständige Mehrwortzuordnung; Aufzeichnung gesperrt.'}</span>}
                  {entry.module_status === 'inactive' && <small>Modul / eigenständiger Kanal laut Betreiber inaktiv</small>}
                </div>
                <details className="signal-metadata">
                  <summary>Metadaten und Zuordnung</summary>
                  <label htmlFor={`unit-${entry.code}`}>Eigene Einheit<input id={`unit-${entry.code}`} type="text" maxLength={40} value={entry.unit ?? ''} disabled={busy} onChange={(event) => update(entry.code, 'unit', event.target.value)} /></label>
                  <label htmlFor={`description-${entry.code}`}>Eigene Beschreibung<textarea id={`description-${entry.code}`} rows={2} maxLength={2000} value={entry.description ?? ''} disabled={busy} onChange={(event) => update(entry.code, 'description', event.target.value)} /></label>
                  <small>{entry.kind ? kindLabels[entry.kind] || entry.kind : 'Kategorie nicht angegeben'} · {entry.verification_status === 'operator_touch_confirmed' ? 'Touch-Abgleich: Betreiberbestätigung' : entry.verification_status === 'source_only' ? 'Quellenbelegt · Touch-Abgleich offen' : 'Touch-Abgleich nicht angegeben'}</small>
                  <small>{entry.module_status === 'inactive' ? 'Modul / eigenständiger Kanal laut Betreiber inaktiv' : entry.module_status === 'active' ? 'Anlagenkanal laut Betreiber aktiv' : 'Modulaktivität nicht bestätigt'}</small>
                  <small>{entry.signal_id || 'Kein zugeordneter Decoder'}{entry.decoder && <> · Decoder: {entry.decoder}</>}</small>
                  {entry.information && <small>{entry.information}</small>}
                </details>
              </td>
            </tr>;
          })}</tbody>
        </table>
        {revision !== null && !rows.length && <p>Keine Register vorhanden. Importieren Sie eine CSV-Datei.</p>}
      </div>
      <p className="muted">Speichern übernimmt die gesamte Auswahl an einer sicheren Zyklusgrenze. Die Erfassung läuft unabhängig davon weiter oder bleibt gestoppt.</p>
    </section>
  </main>;
}
