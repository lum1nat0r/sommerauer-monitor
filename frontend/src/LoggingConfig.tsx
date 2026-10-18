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
    <p className="logging-intro">Importieren und wählen Sie die bekannten Register für die Aufzeichnung. Hochgeladene Einträge mit passendem Decoder und Lesezuordnung sind im Entwurf vorgewählt, auch beim erneuten Upload. Touch-Abgleich durch den Betreiber, Modulaktivität und fachliche Bedeutung sind getrennte Angaben: Lesbarkeit bestätigt keine aktive Messung oder physikalische Skalierung. Erst Speichern übernimmt die Auswahl an der nächsten sicheren Zyklusgrenze.</p>
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
      <p id="csv-help">UTF-8, ohne Kopfzeile, mit Semikolon: <code>Name;dezimaler Offset;interner Hexcode</code>, zum Beispiel <code>Kessel_Ist;4102;1006</code>. Maximal 1 MiB. Interpretierbare hochgeladene Einträge mit passender Lesezuordnung werden vorgewählt; unbekannte oder unvollständige Zuordnungen bleiben gesperrt.</p>
      <p className="alert" id="read-clear-help">Neun Protokollregister sind Read-to-clear: 12F0, 85E0, 85E1, 8BF0, 8BF1, 8E0F, 8E1F, 95E0 und 95E1. Jede Auslesung leert dort die aufgesammelten Modul-Ausgangsbits; wiederholte oder konkurrierende Auslesungen können Werte verlieren. Auch diese Einträge werden beim Upload vorgewählt. Vor dem Speichern prüfen und gegebenenfalls abwählen.</p>
      {dirty && <p className="alert">Ein Entwurf ist bereits vorhanden. Ein weiterer Import erstellt die Importfelder erneut auf Basis der gespeicherten Konfiguration und wählt passende hochgeladene Einträge erneut vor. Ungespeicherte Einheit/Beschreibung für übernommene Einträge bleiben erhalten. Speichern Sie zuerst, wenn ungespeicherte Importfelder erhalten bleiben sollen.</p>}
      <label htmlFor="logging-csv">CSV-Datei als Entwurf einlesen<input id="logging-csv" type="file" accept=".csv,text/csv,text/plain" aria-describedby="csv-help" disabled={busy || revision === null || conflict} onChange={(event) => { const file = event.target.files?.[0]; event.target.value = ''; if (file) void importFile(file); }} /></label>
    </section>
    <section aria-labelledby="logging-draft-title">
      <div className="section-heading"><div><h2 id="logging-draft-title">Gemeinsamer Entwurf</h2><p className="muted">Basisrevision {revision ?? '—'} · {dirty ? 'Ungespeicherte Änderungen' : 'Keine ungespeicherten Änderungen'} · {draft.length} Register</p></div></div>
      <p id="logging-metadata-help">Einheit und Beschreibung sind reine Betreiber-Metadaten. Sie ändern weder Decoder noch Umrechnung oder Einheiten gespeicherter Messungen. Historische Daten bleiben unverändert. Die Mehrwortzähler Betrieb 7010/7011 und Stoker 7012/7013 werden jeweils nur vollständig und gemeinsam geschaltet.</p>
      <div className="logging-table-wrap" role="region" aria-label="Registerkonfiguration, horizontal scrollbar" tabIndex={0}>
        <table className="logging-table" aria-describedby="logging-metadata-help"><caption>Neue und geänderte Importzeilen zuerst; Auswahl und Metadaten werden gemeinsam gespeichert.</caption>
          <thead><tr><th scope="col">Import / Änderung</th><th scope="col">Hexcode</th><th scope="col">Offset (dezimal)</th><th scope="col">Aufzeichnen</th><th scope="col">Einheit (Metadaten)</th><th scope="col">Beschreibung (Metadaten)</th><th scope="col">Lesezuordnung / Signal</th></tr></thead>
          <tbody>{rows.map((entry) => {
            const group = entry.signal_id ? draft.filter((item) => item.signal_id === entry.signal_id) : [entry];
            const eligible = groupEligible(entry, group);
            const fields = Array.isArray(entry.changed_fields) ? entry.changed_fields : [];
            return <tr key={entry.code} className={`logging-row-${entry.change || 'unchanged'}`}>
              <th scope="row"><span className={fields.includes('name') ? 'import-field-changed' : ''}>{entry.name || 'Ohne Importname'}</span><span className="logging-change">{entry.change === 'new' ? 'Neu' : entry.change === 'changed' ? 'Geändert' : 'Unverändert'}</span>{fields.length > 0 && <small>Geänderte Felder: {fields.map((field) => fieldLabels[field] || field).join(', ')}</small>}</th>
              <td><code className={fields.includes('code') ? 'import-field-changed' : ''}>{entry.code}</code></td><td><span className={fields.includes('offset') ? 'import-field-changed' : ''}>{entry.offset ?? '—'}</span></td>
              <td><label className="logging-check"><input type="checkbox" checked={Boolean(entry.record)} disabled={busy || !eligible} aria-describedby={`eligibility-${entry.code}${entry.read_to_clear ? ` risk-${entry.code}` : ''}`} onChange={(event) => toggle(entry, event.target.checked)} />{entry.code} aufzeichnen</label>{entry.read_to_clear && <p className="read-clear-warning" id={`risk-${entry.code}`}>Read-to-clear: Lesen leert die Modul-Ausgangsbits. Aktivieren beeinflusst auch andere Leser.</p>}</td>
              <td><label className="visually-hidden" htmlFor={`unit-${entry.code}`}>Betreibereinheit für {entry.code}</label><input id={`unit-${entry.code}`} type="text" maxLength={40} value={entry.unit ?? ''} disabled={busy} onChange={(event) => update(entry.code, 'unit', event.target.value)} /></td>
              <td><label className="visually-hidden" htmlFor={`description-${entry.code}`}>Betreiberbeschreibung für {entry.code}</label><textarea id={`description-${entry.code}`} rows={2} maxLength={2000} value={entry.description ?? ''} disabled={busy} onChange={(event) => update(entry.code, 'description', event.target.value)} /></td>
              <td id={`eligibility-${entry.code}`}><strong>{entry.label || entry.name}</strong><span className={eligible ? 'logging-eligible' : 'logging-blocked'}>{eligible ? 'Bekannte Lesezuordnung – auswählbar' : entry.blocked_reason || 'Unbekannte oder unvollständige Mehrwortzuordnung; Aufzeichnung gesperrt.'}</span><small>{entry.kind ? kindLabels[entry.kind] || entry.kind : 'Kategorie nicht angegeben'} · {entry.verification_status === 'operator_touch_confirmed' ? 'Touch-Abgleich: Betreiberbestätigung' : entry.verification_status === 'source_only' ? 'Quellenbelegt · Touch-Abgleich offen' : 'Touch-Abgleich nicht angegeben'}</small><small>{entry.module_status === 'inactive' ? 'Modul / eigenständiger Kanal laut Betreiber inaktiv' : entry.module_status === 'active' ? 'Anlagenkanal laut Betreiber aktiv' : 'Modulaktivität nicht bestätigt'}</small><small>{entry.signal_id || 'Kein zugeordneter Decoder'}{entry.decoder && <> · Decoder: {entry.decoder}</>}</small>{entry.information && <small>{entry.information}</small>}</td>
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
