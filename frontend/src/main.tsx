import { StrictMode, useCallback, useEffect, useMemo, useState } from 'react';
import { createRoot } from 'react-dom/client';
import './style.css';
import { requestJson } from './api';
import { ageLabel, formatDate } from './format';
import Diagnostics from './Diagnostics';

type CollectorStatus = {
  state: string;
  reason: string | null;
  reconnect_attempts: number;
  reconnect_attempt_limit: number;
  next_action_at: string | null;
  next_action: string | null;
};
type Config = {
  collector_enabled: boolean;
  host_configured: boolean;
  display_timezone: string;
};
type Signal = {
  signal_id: string;
  value: number | null;
  unit: string;
  observed_at: string;
  age_seconds: number;
  quality: string;
  fresh: boolean;
};
type Point = { observed_at: string; value: number | null; quality: string };
type EventItem = {
  event_id: string;
  occurred_at: string;
  kind: string;
  severity: string;
  message: string;
};
type Period = '1h' | '24h' | 'week' | 'month' | 'custom';
type SignalId = Signal['signal_id'];

const signalInfo: Record<SignalId, { label: string; unit: string }> = {
  'boiler.temperature': { label: 'Kesseltemperatur', unit: '°C' },
  'buffer.top_temperature': { label: 'Puffer oben', unit: '°C' },
  'buffer.bottom_temperature': { label: 'Puffer unten', unit: '°C' },
  'boiler.operating_minutes': { label: 'Anlagen-Betriebszähler', unit: 'min' },
};
const signalIds = Object.keys(signalInfo) as SignalId[];
const stateLabels: Record<string, string> = {
  unconfigured: 'Ersteinrichtung – noch nicht konfiguriert',
  paused: 'Pausiert',
  running: 'Erfassung läuft',
  completed: 'Erfassung abgeschlossen',
  reconnect_wait: 'Verbindungsfehler – Wiederaufnahme geplant',
  stopped_transport: 'Gestoppt – Verbindungsfehler',
  stopped_protocol: 'Gestoppt – Protokollfehler',
  stopped_data: 'Gestoppt – Datenfehler',
  stopped_storage: 'Gestoppt – Speicherfehler',
};
const periods: { id: Period; label: string }[] = [
  { id: '1h', label: '1 Stunde' }, { id: '24h', label: '24 Stunden' },
  { id: 'week', label: 'Woche' }, { id: 'month', label: 'Monat' },
  { id: 'custom', label: 'Freier Zeitraum' },
];
const CHART_GAP_THRESHOLD_MS = 180_000;

function localParts(date: Date, timeZone: string) {
  const parts = new Intl.DateTimeFormat('en-CA', {
    timeZone, year: 'numeric', month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit', second: '2-digit', hourCycle: 'h23',
  }).formatToParts(date);
  return Object.fromEntries(parts.map(({ type, value }) => [type, Number(value)])) as Record<string, number>;
}

function localInputToUtc(value: string, timeZone: string, shiftAcrossGap = false): Date | null {
  const match = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})$/.exec(value);
  if (!match) return null;
  const [, y, mo, d, h, mi] = match.map(Number);
  const desired = Date.UTC(y, mo - 1, d, h, mi);
  let candidate = desired;
  for (let attempt = 0; attempt < 3; attempt += 1) {
    const actual = localParts(new Date(candidate), timeZone);
    const represented = Date.UTC(actual.year, actual.month - 1, actual.day, actual.hour, actual.minute, actual.second);
    candidate += desired - represented;
  }
  const candidates = [-3, -2, -1, 0, 1, 2, 3].map((hours) => candidate + hours * 3_600_000);
  const matching = candidates.filter((timestamp) => {
    const actual = localParts(new Date(timestamp), timeZone);
    return actual.year === y && actual.month === mo && actual.day === d && actual.hour === h && actual.minute === mi;
  });
  if (matching.length) return new Date(Math.min(...matching));
  if (!shiftAcrossGap) return null;
  const nextValid = candidates.map((timestamp) => {
    const actual = localParts(new Date(timestamp), timeZone);
    const represented = Date.UTC(actual.year, actual.month - 1, actual.day, actual.hour, actual.minute);
    return { timestamp, difference: represented - desired };
  }).filter(({ difference }) => difference > 0 && difference <= 3 * 3_600_000)
    .sort((left, right) => left.difference - right.difference)[0];
  return nextValid ? new Date(nextValid.timestamp) : null;
}


function shiftLocal(date: Date, timeZone: string, unit: 'day' | 'week' | 'month', amount: number) {
  const p = localParts(date, timeZone);
  let shifted: Date;
  if (unit === 'month') {
    const targetMonth = new Date(Date.UTC(p.year, p.month - 1 + amount, 1));
    const lastDay = new Date(Date.UTC(targetMonth.getUTCFullYear(), targetMonth.getUTCMonth() + 1, 0)).getUTCDate();
    shifted = new Date(Date.UTC(targetMonth.getUTCFullYear(), targetMonth.getUTCMonth(), Math.min(p.day, lastDay), p.hour, p.minute));
  } else {
    shifted = new Date(Date.UTC(p.year, p.month - 1, p.day + amount * (unit === 'week' ? 7 : 1), p.hour, p.minute));
  }
  const input = `${shifted.getUTCFullYear()}-${String(shifted.getUTCMonth() + 1).padStart(2, '0')}-${String(shifted.getUTCDate()).padStart(2, '0')}T${String(shifted.getUTCHours()).padStart(2, '0')}:${String(shifted.getUTCMinutes()).padStart(2, '0')}`;
  return localInputToUtc(input, timeZone, true);
}

function Chart({ points, unit, timeZone }: { points: Point[]; unit: string; timeZone: string }) {
  const valid = points.filter((point) => point.value !== null && point.quality === 'ok');
  if (valid.length === 0) return <p className="empty-chart">Für diesen Zeitraum liegen keine gültigen Messwerte vor.</p>;
  const values = valid.map((point) => point.value as number);
  const low = Math.min(...values);
  const high = Math.max(...values);
  const padding = high === low ? Math.max(Math.abs(high) * 0.03, 1) : (high - low) * 0.12;
  const minY = low - padding;
  const maxY = high + padding;
  const start = Date.parse(valid[0].observed_at);
  const end = Date.parse(valid[valid.length - 1].observed_at);
  const span = Math.max(end - start, 1);
  const x = (point: Point) => 48 + ((Date.parse(point.observed_at) - start) / span) * 704;
  const y = (point: Point) => 176 - (((point.value as number) - minY) / (maxY - minY)) * 148;
  const paths: string[] = [];
  let run: Point[] = [];
  for (const point of valid) {
    const previous = run[run.length - 1];
    if (previous && Date.parse(point.observed_at) - Date.parse(previous.observed_at) > CHART_GAP_THRESHOLD_MS) {
      if (run.length > 1) paths.push(run.map((item, i) => `${i ? 'L' : 'M'} ${x(item).toFixed(1)} ${y(item).toFixed(1)}`).join(' '));
      run = [];
    }
    run.push(point);
  }
  if (run.length > 1) paths.push(run.map((item, i) => `${i ? 'L' : 'M'} ${x(item).toFixed(1)} ${y(item).toFixed(1)}`).join(' '));
  const gaps = valid.slice(1).filter((point, i) => Date.parse(point.observed_at) - Date.parse(valid[i].observed_at) > CHART_GAP_THRESHOLD_MS).length;
  const yLabels = [minY, (minY + maxY) / 2, maxY];
  return <>
    <div className="chart-wrap" role="img" aria-label={`${valid.length} gültige Messpunkte in ${unit}; ${gaps} gekennzeichnete Messlücken`}>
      <svg className="chart" viewBox="0 0 800 210" preserveAspectRatio="none" aria-hidden="true">
        {yLabels.map((value, i) => {
          const yy = 176 - ((value - minY) / (maxY - minY)) * 148;
          return <g key={i}><line x1="48" x2="752" y1={yy} y2={yy} className="gridline" /><text x="40" y={yy + 4} textAnchor="end" className="axis-label">{value.toLocaleString('de-AT', { maximumFractionDigits: 1 })}</text></g>;
        })}
        {paths.map((path, index) => <path key={index} d={path} className="chart-line" />)}
        {valid.length === 1 && <circle cx={x(valid[0])} cy={y(valid[0])} r="4" className="chart-dot" />}
      </svg>
    </div>
    <div className="chart-caption"><span>{formatDate(valid[0].observed_at, timeZone)}</span><span>{valid.length} Werte · {gaps ? `${gaps} Messlücken` : 'keine erkannten Messlücken'}</span><span>{formatDate(valid[valid.length - 1].observed_at, timeZone)}</span></div>
  </>;
}

function App() {
  const [area, setArea] = useState<'overview' | 'diagnostics'>('overview');
  const [config, setConfig] = useState<Config | null>(null);
  const [collector, setCollector] = useState<CollectorStatus | null>(null);
  const [signals, setSignals] = useState<Signal[]>([]);
  const [events, setEvents] = useState<EventItem[]>([]);
  const [apiStatus, setApiStatus] = useState<'loading' | 'ok' | 'degraded' | 'error'>('loading');
  const [period, setPeriod] = useState<Period>(() => {
    const saved = localStorage.getItem('dashboard-period');
    return periods.some(({ id }) => id === saved) ? saved as Period : '24h';
  });
  const [selectedSignal, setSelectedSignal] = useState<SignalId>(() => {
    const saved = localStorage.getItem('dashboard-signal');
    return signalIds.includes(saved as SignalId) ? saved as SignalId : 'boiler.temperature';
  });
  const [customStart, setCustomStart] = useState('');
  const [customEnd, setCustomEnd] = useState('');
  const [history, setHistory] = useState<Point[]>([]);
  const [historyTotal, setHistoryTotal] = useState(0);
  const [historyError, setHistoryError] = useState('');
  const [notice, setNotice] = useState('');
  const [busy, setBusy] = useState(false);
  const [timezoneDraft, setTimezoneDraft] = useState('Europe/Vienna');
  const timeZone = config?.display_timezone || 'Europe/Vienna';

  const refresh = useCallback(async () => {
    try {
      const [health, current, status, settings, eventResult] = await Promise.all([
        requestJson<{ status: 'ok' | 'degraded' }>('/api/health'),
        requestJson<{ signals: Signal[] }>('/api/signals/current'),
        requestJson<CollectorStatus>('/api/collector/status'),
        requestJson<Config>('/api/config'),
        requestJson<{ items: EventItem[] }>('/api/events?limit=20'),
      ]);
      setApiStatus(health.status);
      setSignals(current.signals);
      setCollector(status);
      setConfig(settings);
      setTimezoneDraft((existing) => existing === (config?.display_timezone || 'Europe/Vienna') ? settings.display_timezone : existing);
      setEvents(eventResult.items);
    } catch {
      setApiStatus('error');
    }
  }, [config?.display_timezone]);

  useEffect(() => {
    void refresh();
    const timer = window.setInterval(() => void refresh(), 15_000);
    return () => window.clearInterval(timer);
  }, [refresh]);

  useEffect(() => {
    localStorage.setItem('dashboard-period', period);
    localStorage.setItem('dashboard-signal', selectedSignal);
  }, [period, selectedSignal]);

  const range = useMemo(() => {
    const now = new Date();
    if (period === '1h') return { start: new Date(now.getTime() - 3_600_000), end: now };
    if (period === '24h') return { start: new Date(now.getTime() - 86_400_000), end: now };
    if (period === 'week') return { start: shiftLocal(now, timeZone, 'week', -1), end: now };
    if (period === 'month') return { start: shiftLocal(now, timeZone, 'month', -1), end: now };
    return { start: localInputToUtc(customStart, timeZone), end: localInputToUtc(customEnd, timeZone) };
  }, [period, customStart, customEnd, timeZone]);

  const loadHistory = useCallback(async () => {
    if (!range.start || !range.end || range.start >= range.end) {
      setHistory([]);
      setHistoryTotal(0);
      setHistoryError(period === 'custom' ? 'Bitte einen gültigen Zeitraum mit Ende nach Beginn wählen.' : 'Zeitraum konnte nicht in die Anzeigezeitzone umgerechnet werden.');
      return;
    }
    const query = new URLSearchParams({ start: range.start.toISOString(), end: range.end.toISOString(), limit: '10000' });
    try {
      const result = await requestJson<{ total: number; items: Point[] }>(`/api/history/${encodeURIComponent(selectedSignal)}?${query}`);
      setHistory(result.items);
      setHistoryTotal(result.total);
      setHistoryError('');
    } catch {
      setHistoryError('Der Verlauf konnte nicht geladen werden. Die API bleibt unabhängig von der Erfassung verfügbar.');
    }
  }, [range, selectedSignal, period]);

  useEffect(() => {
    void loadHistory();
    const timer = window.setInterval(() => void loadHistory(), 60_000);
    return () => window.clearInterval(timer);
  }, [loadHistory]);

  const runCollectorAction = async (action: 'pause' | 'resume' | 'acknowledge-and-start') => {
    setBusy(true);
    setNotice('');
    try {
      const result = await requestJson<CollectorStatus>(`/api/collector/${action}`, {
        method: 'POST',
        headers: { 'X-Requested-With': 'SommerauerMonitor' },
      });
      setCollector(result);
      setNotice(action === 'pause' ? 'Erfassung pausiert.' : action === 'resume' ? 'Erfassung fortgesetzt.' : 'Fehler quittiert; Erfassung gestartet.');
      await refresh();
    } catch (error) {
      setNotice(error instanceof Error && error.message === 'HTTP 409'
        ? 'Aktion nicht möglich: Sammler nicht konfiguriert oder Fehlerursache noch nicht quittierbar.'
        : 'Aktion fehlgeschlagen. Prüfe API-Verfügbarkeit und Same-Origin-Zugriff.');
    } finally {
      setBusy(false);
    }
  };

  const saveTimezone = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setBusy(true);
    setNotice('');
    try {
      await requestJson('/api/config', {
        method: 'PUT', headers: { 'Content-Type': 'application/json', 'X-Requested-With': 'SommerauerMonitor' },
        body: JSON.stringify({ display_timezone: timezoneDraft }),
      });
      await refresh();
      setNotice('Anzeigezeitzone gespeichert.');
    } catch {
      setNotice('Zeitzone konnte nicht gespeichert werden. Verwende eine unterstützte IANA-Zeitzone.');
    } finally {
      setBusy(false);
    }
  };

  const selected = signals.find((signal) => signal.signal_id === selectedSignal);
  const lastSuccessfulAt = signals
    .filter((signal) => signal.value !== null && signal.quality === 'ok')
    .reduce<string | undefined>((latest, signal) => !latest || signal.observed_at > latest ? signal.observed_at : latest, undefined);
  const canPause = collector?.state === 'running' || collector?.state === 'reconnect_wait';
  const canResume = collector?.state === 'paused';
  const canAcknowledge = collector ? ['stopped_transport', 'stopped_protocol', 'stopped_data', 'stopped_storage'].includes(collector.state) : false;
  const csvQuery = range.start && range.end ? `?${new URLSearchParams({ start: range.start.toISOString(), end: range.end.toISOString() })}` : '';


  return <main className="dashboard">
    <header className="topbar">
      <div><p className="eyebrow">LOKALES MONITORING</p><h1>Sommerauer <span>Monitor</span></h1></div>
      <div className="app-status" aria-live="polite"><span className={`status-dot ${apiStatus}`} />API {apiStatus === 'ok' ? 'erreichbar' : apiStatus === 'degraded' ? 'Datenbank gestört' : apiStatus === 'error' ? 'nicht erreichbar' : 'wird geprüft'}</div>
    </header>

    {apiStatus === 'error' && <div className="alert danger" role="alert">Die App-API ist nicht erreichbar. Bereits geladene Werte können veraltet sein.</div>}
    {apiStatus === 'degraded' && <div className="alert danger" role="alert">Die App ist erreichbar, aber der Datenbankspeicher ist nicht verfügbar.</div>}

    <section className="collector-panel" aria-labelledby="collector-title">
      <div className="collector-copy"><p className="eyebrow">ERFASSUNGSSTATUS</p><h2 id="collector-title">{collector ? stateLabels[collector.state] || 'Unbekannter Zustand' : 'Status wird geladen'}</h2>
        <p>{collector?.reason || (collector?.state === 'unconfigured' ? 'Die Installation ist noch nicht für die Erfassung eingerichtet.' : collector?.state === 'completed' ? 'Der endliche Erfassungslauf ist beendet.' : 'Keine aktive Fehlermeldung.')}</p>
        <p className="status-meta">Letzte erfolgreiche Messung: <strong>{lastSuccessfulAt ? formatDate(lastSuccessfulAt, timeZone) : 'Noch keine erfolgreiche Messung'}</strong>
          {collector?.state === 'reconnect_wait' && collector.next_action_at && <> · Nächster Versuch: <strong>{formatDate(collector.next_action_at, timeZone)}</strong></>}</p>
        {collector?.state === 'reconnect_wait' && <p className="status-meta">Wiederaufnahmeversuche: {collector.reconnect_attempts} / {collector.reconnect_attempt_limit}. {collector.next_action}</p>}
      </div>
      <div className="collector-actions">
        {canPause && <button className="button secondary" disabled={busy} onClick={() => void runCollectorAction('pause')}>Pause</button>}
        {canResume && <button className="button primary" disabled={busy} onClick={() => void runCollectorAction('resume')}>Fortsetzen</button>}
        {canAcknowledge && <button className="button primary" disabled={busy} onClick={() => void runCollectorAction('acknowledge-and-start')}>Fehlerursache geprüft – quittieren und starten</button>}
      </div>
    </section>
    {notice && <p className="notice" role="status">{notice}</p>}
    <nav className="diagnostics-navigation" aria-label="Dashboard-Bereich">
      <button className={`button ${area === 'overview' ? 'primary' : 'secondary'}`} aria-pressed={area === 'overview'} onClick={() => setArea('overview')}>Übersicht</button>
      <button className={`button ${area === 'diagnostics' ? 'primary' : 'secondary'}`} aria-pressed={area === 'diagnostics'} onClick={() => setArea('diagnostics')}>Diagnose</button>
    </nav>
    <div hidden={area !== 'diagnostics'}><Diagnostics timeZone={timeZone} onCollectorChange={refresh} /></div>
    <div hidden={area !== 'overview'}>

    <section aria-labelledby="signals-title"><div className="section-heading"><div><p className="eyebrow">LETZTE BEKANNTE MESSWERTE</p><h2 id="signals-title">Anlagenübersicht</h2></div><p className="muted">Anzeigezeit: {timeZone}</p></div>
      <div className="signal-grid">
        {signalIds.map((id) => {
          const signal = signals.find((item) => item.signal_id === id);
          const fresh = signal?.fresh && signal.quality === 'ok';
          return <article className={`signal-card ${signal && !fresh ? 'stale' : ''}`} key={id}>
            <h3>{signalInfo[id].label}</h3>
            {signal?.value !== null && signal?.quality === 'ok' ? <p className="signal-value">{signal.value.toLocaleString('de-AT', { maximumFractionDigits: 1 })}<span>{signal.unit}</span></p> : <p className="signal-value unavailable">—</p>}
            <p className={`freshness ${signal ? fresh ? 'fresh' : 'old' : ''}`}>{signal ? fresh ? 'Aktuell' : signal.quality !== 'ok' ? `Ungültige Messqualität: ${signal.quality}` : 'Veraltet' : 'Noch keine Messung'}</p>
            {signal && <p className="sample-time">{formatDate(signal.observed_at, timeZone)}<br />Datenalter: {ageLabel(signal.age_seconds)}</p>}
          </article>;
        })}
      </div>
    </section>

    <section className="history-panel" aria-labelledby="history-title"><div className="section-heading"><div><p className="eyebrow">GESPEICHERTE ORIGINALMESSUNGEN</p><h2 id="history-title">Verlauf</h2></div>
      {range.start && range.end && <a className="button secondary download" href={`/api/export.csv${csvQuery}`} download>CSV herunterladen</a>}
    </div>
      <div className="history-controls">
        <label>Signal<select value={selectedSignal} onChange={(event) => setSelectedSignal(event.target.value as SignalId)}>{signalIds.map((id) => <option key={id} value={id}>{signalInfo[id].label} ({signalInfo[id].unit})</option>)}</select></label>
        <fieldset><legend>Zeitraum</legend><div className="periods">{periods.map(({ id, label }) => <button type="button" key={id} aria-pressed={period === id} className={`period-button ${period === id ? 'selected' : ''}`} onClick={() => setPeriod(id)}>{label}</button>)}</div></fieldset>
      </div>
      {period === 'custom' && <div className="custom-range"><label>Beginn ({timeZone})<input type="datetime-local" value={customStart} onChange={(event) => setCustomStart(event.target.value)} /></label><label>Ende ({timeZone})<input type="datetime-local" value={customEnd} onChange={(event) => setCustomEnd(event.target.value)} /></label></div>}
      <div className="chart-card"><div className="chart-title"><h3>{signalInfo[selectedSignal].label}</h3><span>{signalInfo[selectedSignal].unit}</span></div>
        {historyError ? <p className="alert" role="status">{historyError}</p> : <Chart points={history} unit={signalInfo[selectedSignal].unit} timeZone={timeZone} />}
        {historyTotal > history.length && <p className="muted">Darstellung auf 10.000 Messpunkte begrenzt; CSV enthält weiterhin alle Werte des Zeitraums.</p>}
        {selected && !selected.fresh && <p className="alert stale-note">Der letzte bekannte Wert ist veraltet. Der Verlauf zeigt keine künstlichen Messwerte.</p>}
      </div>
    </section>

    <div className="lower-grid">
      <section className="events-panel" aria-labelledby="events-title"><div className="section-heading"><div><p className="eyebrow">APP- UND ERFASSUNGSEREIGNISSE</p><h2 id="events-title">Ereignisse</h2></div></div>
        {events.length ? <ol className="event-list">{events.map((item) => <li key={item.event_id}><span className={`severity ${item.severity}`} />
          <div><p>{item.message}</p><small>{item.kind.replaceAll('_', ' ')} · {formatDate(item.occurred_at, timeZone)}</small></div></li>)}</ol> : <p className="muted">Noch keine Ereignisse gespeichert.</p>}
      </section>
      <section className="settings-panel" aria-labelledby="settings-title"><div className="section-heading"><div><p className="eyebrow">NUR LOKALE ANZEIGE</p><h2 id="settings-title">Einstellungen</h2></div></div>
        <form onSubmit={(event) => void saveTimezone(event)}><label>Anzeigezeitzone<select value={timezoneDraft} onChange={(event) => setTimezoneDraft(event.target.value)}><option value="Europe/Vienna">Europe/Vienna</option><option value="Europe/Berlin">Europe/Berlin</option><option value="UTC">UTC</option></select></label><button className="button secondary" type="submit" disabled={busy || timezoneDraft === timeZone}>Zeitzone speichern</button></form>
        <p className="muted">Das ändert nur die Darstellung. Zieladresse und Heizungsparameter werden hier nicht geändert.</p>
      </section>
    </div>
    </div>
    <footer><span>Web-App-Status und Erfassungszustand sind getrennt.</span><span>{config?.host_configured ? 'Modbus-Ziel konfiguriert' : 'Kein Modbus-Ziel konfiguriert'} · {config?.collector_enabled ? 'Sammler beim Start aktiviert' : 'Sammler beim Start deaktiviert'}</span></footer>
  </main>;
}

createRoot(document.getElementById('root')!).render(<StrictMode><App /></StrictMode>);
