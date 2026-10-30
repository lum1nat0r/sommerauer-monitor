import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import type { FormEvent } from 'react';
import { createPortal } from 'react-dom';
import HistoryChart from './HistoryChart';
import {
  ageLabel, availablePresets, blockLabel, boilerStateLabels, bufferDifference, chartPresets,
  displayMeasurement, formatDate, isFresh, kindLabels, loadHistory, localInputToUtc,
  periods, requestJson, safeErrorCode, selectBoilerDisplay, shiftLocal, signalGroup, signalGroups, stateLabels,
} from './dashboard';
import type {
  BoilerSourceReason, ChartSeries, CollectorStatus, Config, ControlCandidate, DashboardView,
  EventItem, Period, Point, Signal, SignalDefinition,
} from './dashboard';

function savedValue(key: string, fallback = '') {
  try { return localStorage.getItem(key) ?? fallback; } catch { return fallback; }
}
function remember(key: string, value: string) {
  try { localStorage.setItem(key, value); } catch { /* Storage is optional. */ }
}

function EventDetails({ details }: { details: EventItem['details'] }) {
  if (!details || typeof details !== 'object' || Array.isArray(details)) return null;
  const id = typeof details.signal_id === 'string' && /^[a-zA-Z0-9_.-]{1,160}$/.test(details.signal_id)
    ? details.signal_id : undefined;
  const code = safeErrorCode(details.error_code);
  const block = blockLabel(details.block_offset, details.register_count);
  return id || code || block
    ? <p className="event-details">{[id && `Signal: ${id}`, code && `Fehlercode: ${code}`, block].filter(Boolean).join(' · ')}</p>
    : null;
}

function SignalMetadata({ definition }: { definition: SignalDefinition }) {
  return <details className="signal-metadata"><summary>Metadaten · {definition.signal_id}</summary>
    <p className="signal-tags"><span>{kindLabels[definition.kind] || definition.kind}</span>
      <span>{definition.verification_status === 'operator_touch_confirmed' ? 'Touch-Abgleich: Betreiberbestätigung' : 'Quellenbelegt · Touch-Abgleich offen'}</span>
      <span>{definition.module_status === 'inactive' ? 'Modul / eigenständiger Kanal laut Betreiber inaktiv' : definition.module_status === 'active' ? 'Anlagenkanal laut Betreiber aktiv' : 'Modulaktivität nicht bestätigt'}</span></p>
    <p>{definition.description}</p>
    <p className="muted">Der Touch-Abgleich bestätigt die notierte Anzeige / Lesbarkeit, nicht unabhängig Sensorik, physikalische Skalierung oder Aktorzustand.</p>
    <p className="muted">Abtastintervall: {definition.interval_seconds} s · Gespeicherte Beobachtungen behalten ihre Originaleinheit.</p>
    {definition.read_to_clear && <p className="alert warning">Read-to-clear: Jede Auslesung leert die aufgesammelten Modul-Ausgangsbits. Andere Leser können dadurch Werte verlieren.</p>}
  </details>;
}

function SignalProblem({ signal }: { signal: Signal }) {
  const code = safeErrorCode(signal.error_code);
  const invalid = signal.quality === 'invalid';
  const missingWeather = code === 'missing_weather';
  const message = typeof signal.error_message === 'string' && signal.error_message.trim()
    ? signal.error_message
    : missingWeather ? 'Für diesen Wettersensor liegen keine Wetterdaten vor.'
      : invalid ? 'Der gelieferte Messwert ist ungültig.'
        : signal.quality === 'unavailable' ? 'Für dieses Signal liegt aktuell kein Messwert vor.'
          : signal.quality === 'ok' ? 'Die aktuelle Beobachtung enthält keinen Messwert.'
            : 'Der Messwert kann wegen unbekannter Messqualität nicht angezeigt werden.';
  return <div className="signal-problem"><p>{message}</p>
    {invalid && <p><strong>Wert unplausibel – Ursache prüfen.</strong> Das Signal wird weiter regulär abgefragt und gespeichert.</p>}
    {missingWeather && !invalid && <p>Bei laufender Erfassung: erneute Abfrage im normalen Intervall.</p>}
    {code && <p className="signal-error-code">Fehlercode: {code}</p>}
  </div>;
}

const emptyPoints: Point[] = [];
const titles: Record<DashboardView, string> = {
  overview: 'Übersicht', analysis: 'Analyse', values: 'Alle Werte', settings: 'Einstellungen',
};
const boilerSourceReasons: Record<BoilerSourceReason, string> = {
  not_selected: 'lokal nicht zur Aufzeichnung ausgewählt',
  no_observation: 'noch keine Messung vorhanden',
  unavailable: 'Quelle nicht verfügbar / nicht bereitgestellt',
  invalid_quality: 'Beobachtung mit ungültiger oder unbekannter Qualität',
  missing_value: 'Beobachtung ohne Messwert',
  invalid_value: 'ungültiger Zahlenwert',
  unit_mismatch: 'gespeicherte Einheit passt nicht zur Quelle',
  invalid_encoding: 'unbekanntes Steuerungszustandswort',
  invalid_time: 'Beobachtungszeit ungültig',
  invalid_age: 'Datenalter nicht verlässlich bestimmbar',
  stale: 'Beobachtung veraltet',
  api_loading: 'API-Daten werden noch geprüft; kein aktueller Befund',
  api_unavailable: 'API oder Datenspeicher nicht verfügbar; kein aktueller Befund',
};
type Snapshot = {
  config: Config | null;
  collector: CollectorStatus | null;
  signals: Signal[];
  definitions: SignalDefinition[] | null;
  candidates: ControlCandidate[];
  recordedIds: string[];
  events: EventItem[];
  receivedAt: number;
};

export default function Dashboard({ view }: { view: DashboardView }) {
  const [snapshot, setSnapshot] = useState<Snapshot>({
    config: null, collector: null, signals: [], definitions: null,
    candidates: [], recordedIds: [], events: [], receivedAt: 0,
  });
  const [apiStatus, setApiStatus] = useState<'loading' | 'ok' | 'degraded' | 'error'>('loading');
  const [now, setNow] = useState(Date.now);
  const [period, setPeriod] = useState<Period>(() => {
    const saved = savedValue('dashboard-period');
    return periods.some(({ id }) => id === saved) ? saved as Period : '24h';
  });
  const [selectedSignal, setSelectedSignal] = useState(() => savedValue('dashboard-signal', 'boiler.temperature'));
  const [customStart, setCustomStart] = useState(() => savedValue('dashboard-custom-start'));
  const [customEnd, setCustomEnd] = useState(() => savedValue('dashboard-custom-end'));
  const [preset, setPreset] = useState('buffer');
  const [search, setSearch] = useState('');
  const [notice, setNotice] = useState('');
  const [busy, setBusy] = useState(false);
  const [timezoneDraft, setTimezoneDraft] = useState('Europe/Vienna');
  const [alertTarget, setAlertTarget] = useState<HTMLElement | null>(null);
  const [historyNow, setHistoryNow] = useState(Date.now);
  const [history, setHistory] = useState<Record<string, Point[]>>({});
  const [historyErrors, setHistoryErrors] = useState<Record<string, string>>({});
  const [progress, setProgress] = useState<Record<string, { loaded: number; total: number }>>({});
  const [historyLoading, setHistoryLoading] = useState(false);
  const [historyCancelled, setHistoryCancelled] = useState(false);
  const pollController = useRef<AbortController | null>(null);
  const actionController = useRef<AbortController | null>(null);
  const historyController = useRef<AbortController | null>(null);
  const historyBusy = useRef(false);
  const historyGeneration = useRef(0);
  const pollGeneration = useRef(0);
  const mounted = useRef(false);
  const currentTimezone = useRef('Europe/Vienna');
  const { config, collector, signals, definitions, candidates, recordedIds, events, receivedAt } = snapshot;
  const timeZone = config?.display_timezone || 'Europe/Vienna';

  const refresh = useCallback(async (replace = false) => {
    if (!mounted.current || (pollController.current && !replace)) return;
    pollController.current?.abort();
    const controller = new AbortController();
    pollController.current = controller;
    const generation = ++pollGeneration.current;
    const init = { signal: controller.signal };
    try {
      const [health, current, status, settings, eventResult, catalog, logging] = await Promise.all([
        requestJson<{ status: 'ok' | 'degraded' }>('/api/health', init),
        requestJson<{ signals: Signal[] }>('/api/signals/current', init),
        requestJson<CollectorStatus>('/api/collector/status', init),
        requestJson<Config>('/api/config', init),
        requestJson<{ items: EventItem[] }>('/api/events?limit=20', init),
        requestJson<{ signals: SignalDefinition[]; control_candidates: ControlCandidate[] }>('/api/signals', init),
        requestJson<{ entries: { record: boolean; signal_id: string | null }[] }>('/api/logging-config', init),
      ]);
      if (controller.signal.aborted || !mounted.current || generation !== pollGeneration.current) return;
      const previousTimezone = currentTimezone.current;
      setTimezoneDraft((existing) => existing === previousTimezone ? settings.display_timezone : existing);
      currentTimezone.current = settings.display_timezone;
      const received = Date.now();
      setSnapshot({ config: settings, collector: status, signals: current.signals,
        definitions: catalog.signals, candidates: catalog.control_candidates,
        recordedIds: [...new Set(logging.entries.filter((entry) => entry.record && entry.signal_id).map((entry) => entry.signal_id as string))],
        events: eventResult.items, receivedAt: received });
      setNow(received);
      setApiStatus(health.status);
    } catch {
      if (!controller.signal.aborted && mounted.current && generation === pollGeneration.current) {
        controller.abort();
        setApiStatus('error');
      }
    } finally {
      if (generation === pollGeneration.current) pollController.current = null;
    }
  }, []);

  useEffect(() => {
    mounted.current = true;
    setAlertTarget(document.getElementById('global-alerts'));
    void refresh();
    const poll = window.setInterval(() => void refresh(), 15_000);
    const clock = window.setInterval(() => setNow(Date.now()), 1_000);
    return () => {
      mounted.current = false;
      ++pollGeneration.current;
      pollController.current?.abort();
      pollController.current = null;
      actionController.current?.abort();
      window.clearInterval(poll);
      window.clearInterval(clock);
    };
  }, [refresh]);

  useEffect(() => remember('dashboard-period', period), [period]);
  useEffect(() => remember('dashboard-signal', selectedSignal), [selectedSignal]);
  useEffect(() => remember('dashboard-custom-start', customStart), [customStart]);
  useEffect(() => remember('dashboard-custom-end', customEnd), [customEnd]);

  const selectedIds = useMemo(() => new Set(recordedIds), [recordedIds]);
  const visibleDefinitions = useMemo(() => {
    if (!definitions) return [];
    const known = new Set(definitions.map((definition) => definition.signal_id));
    return [...definitions.filter((definition) => selectedIds.has(definition.signal_id)),
      ...recordedIds.filter((id) => !known.has(id)).map((id): SignalDefinition => ({
        signal_id: id, label: id, unit: '', kind: 'raw', live_confirmed: false,
        verification_status: 'unknown', module_status: 'unknown', read_to_clear: false,
        description: 'Kein Katalogeintrag verfügbar; der Wert bleibt Teil der gespeicherten Aufzeichnungsauswahl.', interval_seconds: 300,
      }))];
  }, [definitions, recordedIds, selectedIds]);
  const effectiveSignal = visibleDefinitions.some((definition) => definition.signal_id === selectedSignal)
    ? selectedSignal : visibleDefinitions[0]?.signal_id || '';
  useEffect(() => {
    if (definitions && effectiveSignal !== selectedSignal) setSelectedSignal(effectiveSignal);
  }, [definitions, effectiveSignal, selectedSignal]);
  const presets = availablePresets(selectedIds);
  const effectivePreset = view === 'overview' ? 'buffer'
    : presets.some((item) => item.id === preset) ? preset : presets[0]?.id || 'single';
  const activePreset = chartPresets.find((item) => item.id === effectivePreset);
  const sourceIds = useMemo(() => (effectivePreset === 'single' ? [effectiveSignal] : activePreset?.sources || [])
    .filter((id) => id && selectedIds.has(id)), [effectivePreset, effectiveSignal, activePreset, selectedIds]);
  const showStatusBand = effectivePreset === 'buffer' && selectedIds.has('modbus.1001');
  const requestKey = [...new Set([...sourceIds, ...(showStatusBand ? ['modbus.1001'] : [])])].join('|');
  const historyVisible = view === 'overview' || view === 'analysis';

  useEffect(() => {
    if (!historyVisible) return;
    setHistoryNow(Date.now());
    const timer = window.setInterval(() => {
      if (!historyBusy.current) setHistoryNow(Date.now());
    }, 60_000);
    return () => window.clearInterval(timer);
  }, [historyVisible]);

  const range = useMemo(() => {
    const end = new Date(historyNow);
    if (period === '1h') return { start: new Date(historyNow - 3_600_000), end };
    if (period === '24h') return { start: new Date(historyNow - 86_400_000), end };
    if (period === 'week') return { start: shiftLocal(end, timeZone, 'week', -1), end };
    if (period === 'month') return { start: shiftLocal(end, timeZone, 'month', -1), end };
    return { start: localInputToUtc(customStart, timeZone), end: localInputToUtc(customEnd, timeZone) };
  }, [period, historyNow, timeZone, customStart, customEnd]);
  const rangeValid = Boolean(range.start && range.end && range.start < range.end);
  const rangeStart = range.start?.getTime() ?? 0;
  const rangeEnd = range.end?.getTime() ?? 0;

  useEffect(() => {
    const generation = ++historyGeneration.current;
    const controller = new AbortController();
    historyController.current = controller;
    setHistory({});
    setHistoryErrors({});
    setProgress({});
    setHistoryCancelled(false);
    const ids = requestKey ? requestKey.split('|') : [];
    const active = historyVisible && rangeValid && ids.length > 0;
    historyBusy.current = active;
    setHistoryLoading(active);
    if (active) {
      let next = 0;
      const isCurrent = () => !controller.signal.aborted && generation === historyGeneration.current;
      const worker = async () => {
        while (next < ids.length && isCurrent()) {
          const id = ids[next++];
          try {
            const points = await loadHistory(id, rangeStart, rangeEnd, controller.signal, (loaded, total) => {
              if (isCurrent()) setProgress((previous) => ({ ...previous, [id]: { loaded, total } }));
            });
            if (isCurrent()) setHistory((previous) => ({ ...previous, [id]: points }));
          } catch (error) {
            if (isCurrent()) setHistoryErrors((previous) => ({ ...previous, [id]: error instanceof Error ? error.message : 'Abruf fehlgeschlagen.' }));
          }
        }
      };
      void Promise.all(Array.from({ length: Math.min(2, ids.length) }, () => worker())).finally(() => {
        if (isCurrent()) {
          historyBusy.current = false;
          setHistoryLoading(false);
        }
      });
    }
    return () => {
      controller.abort();
      if (generation === historyGeneration.current) historyBusy.current = false;
    };
  }, [historyVisible, requestKey, rangeValid, rangeStart, rangeEnd, view, effectivePreset, historyNow]);

  function cancelHistory() {
    historyController.current?.abort();
    ++historyGeneration.current;
    historyBusy.current = false;
    setHistoryLoading(false);
    setHistoryCancelled(true);
  }

  const ageOf = (signal: Signal) => signal.age_seconds + Math.max(0, now - receivedAt) / 1000;
  const fresh = (signal: Signal) => isFresh(signal, (now - receivedAt) / 1000);
  const signalById = useMemo(() => new Map(signals.map((signal) => [signal.signal_id, signal])), [signals]);
  const definitionById = useMemo(() => new Map(visibleDefinitions.map((definition) => [definition.signal_id, definition])), [visibleDefinitions]);
  const status = signalById.get('modbus.1001');
  const power = signalById.get('modbus.1003');
  const boiler = selectBoilerDisplay({ selectedIds, signals: signalById, apiStatus,
    elapsedSeconds: (now - receivedAt) / 1000 });
  const evidence = boiler.evidence;
  const boilerTitle = evidence.kind === 'status' ? boilerStateLabels[evidence.state]
    : evidence.kind === 'power' ? evidence.indication === 'active' ? 'Leistungsregelung aktiv' : 'Betriebszustand nicht eindeutig'
      : 'Betriebszustand unbekannt';
  const errorList = signalById.get('modbus.1002');
  const errorListCurrent = Boolean(selectedIds.has('modbus.1002') && errorList && apiStatus === 'ok'
    && errorList.quality === 'ok' && errorList.value !== null && errorList.unit === 'Rohwert'
    && fresh(errorList));

  const chartSeries = useMemo<ChartSeries[]>(() => effectivePreset === 'stratification'
    ? history['buffer.top_temperature'] && history['buffer.bottom_temperature'] ? [{
      id: 'buffer.difference', label: 'Pufferschichtung · oben minus unten', unit: 'K', kind: 'measurement',
      intervalSeconds: Math.max(definitionById.get('buffer.top_temperature')?.interval_seconds || 60,
        definitionById.get('buffer.bottom_temperature')?.interval_seconds || 60),
      points: bufferDifference(history['buffer.top_temperature'], history['buffer.bottom_temperature']),
    }] : []
    : sourceIds.filter((id) => history[id]).map((id) => {
      const definition = definitionById.get(id)!;
      return { id, label: definition.label, unit: definition.unit, kind: definition.kind,
        intervalSeconds: definition.interval_seconds || 300, points: history[id] };
    }), [history, effectivePreset, sourceIds, definitionById]);
  const lastSuccessfulAt = signals.filter((signal) => signal.value !== null && signal.quality === 'ok')
    .reduce<string | undefined>((latest, signal) => !latest || signal.observed_at > latest ? signal.observed_at : latest, undefined);

  async function runCollectorAction(action: 'pause' | 'resume' | 'acknowledge-and-start') {
    if (busy) return;
    setBusy(true);
    setNotice('');
    const controller = new AbortController();
    actionController.current = controller;
    try {
      const result = await requestJson<CollectorStatus>(`/api/collector/${action}`, {
        method: 'POST', headers: { 'X-Requested-With': 'SommerauerMonitor' }, signal: controller.signal,
      });
      if (controller.signal.aborted || !mounted.current) return;
      setSnapshot((previous) => ({ ...previous, collector: result }));
      setNotice(action === 'pause' ? 'Erfassung pausiert.' : action === 'resume' ? 'Erfassung fortgesetzt.' : 'Erfassung nach Freigabe gestartet.');
      await refresh(true);
    } catch (error) {
      if (!controller.signal.aborted && mounted.current) setNotice(error instanceof Error && error.message === 'HTTP 409'
        ? 'Aktion nicht möglich: Sammler nicht konfiguriert oder Fehlerursache noch nicht quittierbar.'
        : 'Aktion fehlgeschlagen. Prüfe API-Verfügbarkeit und Same-Origin-Zugriff.');
    } finally {
      if (!controller.signal.aborted && mounted.current) setBusy(false);
    }
  }

  async function saveTimezone(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (busy) return;
    setBusy(true);
    setNotice('');
    const controller = new AbortController();
    actionController.current = controller;
    try {
      await requestJson('/api/config', {
        method: 'PUT', headers: { 'Content-Type': 'application/json', 'X-Requested-With': 'SommerauerMonitor' },
        body: JSON.stringify({ display_timezone: timezoneDraft }), signal: controller.signal,
      });
      if (controller.signal.aborted || !mounted.current) return;
      await refresh(true);
      if (!controller.signal.aborted && mounted.current) setNotice('Anzeigezeitzone gespeichert.');
    } catch {
      if (!controller.signal.aborted && mounted.current) setNotice('Zeitzone konnte nicht gespeichert werden. Verwende eine unterstützte IANA-Zeitzone.');
    } finally {
      if (!controller.signal.aborted && mounted.current) setBusy(false);
    }
  }

  function selectForAnalysis(id: string) {
    setSelectedSignal(id);
    setPreset('single');
    window.location.hash = '#/analyse';
  }

  const globalAlerts = <>
    {apiStatus === 'error' && <div className="alert danger" role="alert">Die App-API ist nicht erreichbar. Aktueller Status nicht verfügbar; bereits geladene Werte können veraltet sein.</div>}
    {apiStatus === 'degraded' && <div className="alert danger" role="alert">Die App ist erreichbar, aber der Datenbankspeicher ist nicht verfügbar. Aktueller Status nicht verfügbar.</div>}
    {collector?.state.startsWith('stopped_') && <div className="alert danger" role="alert"><strong>{stateLabels[collector.state] || 'Erfassung gestoppt'}</strong><p>{collector.reason || 'Fehlerursache vor einer erneuten Freigabe prüfen.'}</p><a href="#/einstellungen">Erfassung und Ereignisse prüfen</a></div>}
  </>;

  const renderValue = (definition: SignalDefinition, compact = false) => {
    const signal = signalById.get(definition.signal_id);
    const hasProblem = Boolean(signal && (signal.quality !== 'ok' || signal.value === null));
    const current = signal && !hasProblem && fresh(signal);
    const displayed = signal && displayMeasurement(signal.signal_id, signal.value, signal.unit);
    const block = blockLabel(signal?.block_offset, signal?.register_count);
    return <article key={definition.signal_id} className={`${compact ? 'metric-card' : 'value-row'}${hasProblem ? signal?.quality === 'invalid' ? ' signal-invalid' : ' signal-unavailable' : signal && !current ? ' stale' : ''}${definition.module_status === 'inactive' ? ' inactive' : ''}`}>
      <div className="value-name"><h3>{definition.label}</h3>{definition.module_status === 'inactive' && <p className="muted">Inaktives Modul / eigenständiger Kanal</p>}</div>
      <p className="signal-value">{signal && !hasProblem && signal.value !== null
        ? <>{displayed!.value!.toLocaleString('de-AT', { maximumFractionDigits: 2 })}<span>{displayed!.unit}</span></>
        : signal && signal.quality === 'invalid' && signal.value !== null
          ? <>{signal.value.toLocaleString('de-AT', { maximumFractionDigits: 2 })}<span>{signal.unit}</span></>
          : <span aria-label="Kein gültiger Messwert">—</span>}</p>
      <div className="value-quality"><p className={`freshness ${current && apiStatus === 'ok' ? 'fresh' : 'old'}`}>
        {hasProblem ? signal?.quality === 'invalid' ? signal.value !== null ? 'Unplausibel' : 'Fehler' : signal?.quality === 'unavailable' ? 'Nicht verfügbar' : 'Kein gültiger Messwert'
          : signal ? apiStatus !== 'ok' ? 'Aktualität nicht bestätigt' : current ? 'Aktuell' : 'Veraltet' : 'Noch keine Messung'}
      </p>{signal && <p className="sample-time">Datenalter: {ageLabel(ageOf(signal))}<br />Beobachtung: {formatDate(signal.observed_at, timeZone)}<br />Qualität: {signal.quality}{block && <><br />{block}</>}</p>}</div>
      {signal && hasProblem && <SignalProblem signal={signal} />}
      {!compact && <><SignalMetadata definition={definition} /><button type="button" className="button secondary signal-history-button" onClick={() => selectForAnalysis(definition.signal_id)}>Im Verlauf auswählen</button></>}
    </article>;
  };

  const historyPanel = <section className="history-panel" aria-labelledby="history-title">
    <div className="section-heading"><div><p className="eyebrow">GESPEICHERTE ORIGINALBEOBACHTUNGEN</p><h2 id="history-title">{activePreset?.label || 'Verlauf'}</h2></div>
      {visibleDefinitions.length && rangeValid ? <a className="button secondary download" href={`/api/export.csv?${new URLSearchParams({ start: range.start!.toISOString(), end: range.end!.toISOString() })}`} download>Alle Originalbeobachtungen als CSV</a> : <button className="button secondary" disabled>CSV herunterladen</button>}
    </div>
    <div className="history-controls">
      {view === 'analysis' && <label>Vergleich<select value={effectivePreset} disabled={!visibleDefinitions.length} onChange={(event) => setPreset(event.target.value)}>
        {!presets.length && <option value="single">Keine Werte ausgewählt</option>}{presets.map((item) => <option key={item.id} value={item.id}>{item.label}</option>)}
      </select></label>}
      {view === 'analysis' && effectivePreset === 'single' && <label>Signal<select value={effectiveSignal} disabled={!visibleDefinitions.length} onChange={(event) => setSelectedSignal(event.target.value)}>
        {!visibleDefinitions.length && <option value="">Keine Werte zur Aufzeichnung ausgewählt</option>}
        {visibleDefinitions.map((definition) => <option key={definition.signal_id} value={definition.signal_id}>{definition.label} ({displayMeasurement(definition.signal_id, null, definition.unit).unit || 'ohne Einheit'}){definition.read_to_clear ? ' · Read-to-clear' : ''}</option>)}
      </select></label>}
      <fieldset disabled={!visibleDefinitions.length}><legend>Zeitraum</legend><div className="periods">{periods.map(({ id, label }) => <button type="button" key={id} aria-pressed={period === id} className={`period-button ${period === id ? 'selected' : ''}`} onClick={() => setPeriod(id)}>{label}</button>)}</div></fieldset>
    </div>
    {period === 'custom' && <div className="custom-range"><label>Beginn ({timeZone})<input type="datetime-local" value={customStart} onChange={(event) => setCustomStart(event.target.value)} /></label><label>Ende ({timeZone})<input type="datetime-local" value={customEnd} onChange={(event) => setCustomEnd(event.target.value)} /></label></div>}
    {!visibleDefinitions.length && <p className="empty-chart">{definitions === null ? 'Signaldefinitionen werden geladen …' : <>Keine Werte zur Aufzeichnung ausgewählt. <a href="#/modbus">Aufzeichnung konfigurieren</a>.</>}</p>}
    {visibleDefinitions.length > 0 && !rangeValid && <p className="alert warning" role="status">Bitte einen gültigen Zeitraum mit Ende nach Beginn wählen. Nicht existierende Ortszeiten bei der Sommerzeitumstellung sind ungültig.</p>}
    {rangeValid && visibleDefinitions.length > 0 && <>
      <p className="chart-caption">{formatDate(new Date(rangeStart), timeZone)} bis {formatDate(new Date(rangeEnd), timeZone)} · {timeZone} · Ende ausgeschlossen</p>
      {historyLoading && <div className="history-progress" role="status"><p>Verlauf wird vollständig geladen … {Object.entries(progress).map(([id, value]) => `${definitionById.get(id)?.label || id}: ${value.loaded.toLocaleString('de-AT')} / ${value.total.toLocaleString('de-AT')}`).join(' · ')}</p><button type="button" className="button secondary" onClick={cancelHistory}>Laden abbrechen</button></div>}
      {historyCancelled && <p className="alert warning" role="status">Laden abgebrochen. Bereits vollständig geladene Reihen bleiben sichtbar; fehlende Reihen sind nicht vollständig geladen.</p>}
      {Object.entries(historyErrors).map(([id, message]) => <p className="alert warning" role="status" key={id}><strong>{definitionById.get(id)?.label || id}: Verlauf unvollständig / nicht verfügbar.</strong> {message}</p>)}
      {sourceIds.length === 0 && <p className="empty-chart">Für diesen Vergleich sind keine zugehörigen Quellen ausgewählt. <a href="#/modbus">Aufzeichnung konfigurieren</a> oder <a href="#/analyse">anderen Vergleich wählen</a>.</p>}
      {effectivePreset === 'power' && <p className="muted">Interne Leistungsregelgrößen Ist / Soll in %, keine thermische Leistung in kW.</p>}
      {effectivePreset === 'stratification' && <p className="muted">Oben minus unten in K. Nur zeitgleiche gültige °C-Beobachtungen; keine Interpolation oder Vorwärtsfüllung.</p>}
      {effectivePreset === 'single' && definitionById.get(effectiveSignal) && <SignalMetadata definition={definitionById.get(effectiveSignal)!} />}
      {chartSeries.length > 0 || showStatusBand ? <HistoryChart start={rangeStart} end={rangeEnd} timeZone={timeZone} series={chartSeries}
        statusPoints={showStatusBand ? history['modbus.1001'] || emptyPoints : undefined} /> : !historyLoading && sourceIds.length > 0 && <p className="empty-chart">Keine vollständig geladene Messreihe verfügbar.</p>}
      {sourceIds.filter((id) => history[id]?.length === 0).map((id) => <p className="empty-chart" key={id}>{definitionById.get(id)?.label || id}: keine Beobachtungen im gewählten Zeitraum.</p>)}
      {effectivePreset === 'buffer' && !showStatusBand && <p className="muted">Kein Steuerungszustandsband: Statuskanal 1001 ist nicht zur Aufzeichnung ausgewählt. Der indirekte Leistungshinweis wird nicht als Zustandsverlauf ausgegeben. <a href="#/modbus">Statuskanal konfigurieren</a>.</p>}
      {effectivePreset === 'buffer' && <p className="source-note">Pufferanstiege lassen sich mit dem Pellet-Steuerungszustand vergleichen. Solarertrag und Wärmequelle sind ohne eigene Solarmessung nicht eindeutig nachgewiesen.</p>}
      <p className="muted">CSV exportiert alle gespeicherten Originalbeobachtungen des Zeitbereichs, unabhängig von Vergleich, Reihenumschaltung oder Darstellungsverdichtung.</p>
    </>}
  </section>;

  const matchingDefinitions = visibleDefinitions.filter((definition) => `${definition.label} ${definition.signal_id} ${definition.description}`.toLocaleLowerCase('de').includes(search.toLocaleLowerCase('de')));
  const canPause = collector?.state === 'running' || collector?.state === 'reconnect_wait';
  const canResume = collector?.state === 'paused';
  const canAcknowledge = collector?.state === 'completed' || collector?.state.startsWith('stopped_');

  return <main className="dashboard">
    {alertTarget ? createPortal(globalAlerts, alertTarget) : globalAlerts}
    <div className="section-heading"><div><p className="eyebrow">LOKALES MONITORING</p><h1 tabIndex={-1}>{titles[view]}</h1></div>
      <div className="connection-status"><span className={`app-status ${apiStatus}`}>API: {apiStatus === 'ok' ? 'erreichbar' : apiStatus === 'degraded' ? 'Datenbank gestört' : apiStatus === 'error' ? 'nicht erreichbar' : 'wird geprüft'}</span><span>Erfassung: {collector ? stateLabels[collector.state] || 'Unbekannter Zustand' : 'wird geprüft'}</span></div>
    </div>
    {notice && <p className="notice" role="status">{notice}</p>}
    {view === 'overview' && <>
      <section className={`boiler-status ${evidence.kind === 'status' ? evidence.state : 'unknown'}`} aria-labelledby="boiler-title">
        <p className="eyebrow">PELLETKESSEL · {evidence.kind === 'status' ? 'STEUERUNGSZUSTAND' : 'BETRIEBSANZEIGE'}</p><h2 id="boiler-title">{boilerTitle}</h2>
        {evidence.kind === 'status' && evidence.minimumRuntime && <p className="minimum-runtime">Mindestlaufzeit aktiv</p>}
        {evidence.kind === 'power' && <>
          <p className="alert warning indirect-evidence"><strong>Indirekter Betriebshinweis</strong> · Interne Istregelgröße: {evidence.value.toLocaleString('de-AT')} %. Kein bestätigter Steuerungs- oder Flammenzustand.</p>
          {evidence.indication === 'ambiguous' && <p>0 % kann Aus oder Gluterhaltung bedeuten; andere Zustände sind damit nicht ausgeschlossen.</p>}
        </>}
        {evidence.kind === 'none' && <p>Es liegt kein brauchbarer aktueller Steuerungszustand oder indirekter Betriebshinweis vor. Das bedeutet nicht „Heizung aus“.</p>}
        {evidence.kind !== 'none' && <p className="status-meta">Stand {formatDate(evidence.signal.observed_at, timeZone)} · {ageLabel(evidence.ageSeconds)} · Abfrage alle 5 Minuten</p>}
        {boiler.statusReason && <p className="source-note"><strong>Statusquelle modbus.1001:</strong> {boilerSourceReasons[boiler.statusReason]}. Keine aktuelle Ein-/Aus-Aussage aus dieser Quelle.</p>}
        {status && selectedIds.has('modbus.1001') && evidence.kind !== 'status' && <p className="status-meta">Letzte Statusbeobachtung: {formatDate(status.observed_at, timeZone)} · {ageLabel(ageOf(status))} · kein aktueller Zustandsnachweis</p>}
        {status && selectedIds.has('modbus.1001') && boiler.statusReason && (status.error_code || status.error_message || ['unavailable', 'invalid_quality', 'missing_value'].includes(boiler.statusReason)) && <SignalProblem signal={status} />}
        {evidence.kind === 'none' && boiler.powerReason && <p className="source-note"><strong>Optionale Istregelgröße modbus.1003:</strong> {boilerSourceReasons[boiler.powerReason]}.</p>}
        {evidence.kind === 'none' && power && selectedIds.has('modbus.1003') && boiler.powerReason && (power.error_code || power.error_message || ['unavailable', 'invalid_quality', 'missing_value'].includes(boiler.powerReason)) && <SignalProblem signal={power} />}
        {evidence.kind !== 'status' && <p><a href="#/modbus">Aufzeichnung prüfen</a></p>}
        <details className="signal-metadata">
          <summary>Quelle und Aktualisierung</summary>
          {evidence.kind !== 'none' && <p>Quelle: {evidence.signal.signal_id}</p>}
          <p>Softwarezustand der Steuerung, keine unabhängige Flammenrückmeldung. Ein eigener Displayabgleich steht noch aus.</p>
          <p>Die Frischegrenze kommt aus dem Backend und beträgt das Vierfache des jeweiligen Erfassungsintervalls. Keine sekundengenaue Liveanzeige.</p>
        </details>
      </section>
      {errorListCurrent && errorList && <p className={errorList.value! > 0 ? 'alert warning' : 'status-meta'}>{errorList.value === 0 ? 'Fehlerliste leer' : `Fehlerliste: ${errorList.value! > 0 ? `Fehlernummer ${errorList.value}` : `Rohwert ${errorList.value}`} · Stand ${formatDate(errorList.observed_at, timeZone)}`}</p>}
      <section className="metrics" aria-label="Ausgewählte Kessel- und Pufferwerte">{['boiler.temperature', 'buffer.top_temperature', 'buffer.bottom_temperature', 'boiler.operating_minutes'].map((id) => definitionById.get(id)).filter((definition): definition is SignalDefinition => Boolean(definition)).map((definition) => renderValue(definition, true))}</section>
      {historyPanel}
    </>}
    {view === 'analysis' && historyPanel}
    {view === 'values' && <>
      <p className="muted">Nur gespeicherte Aufzeichnungsauswahl; Suche und Diagrammwahl ändern keine Auswahl. Frühere Gutwerte ersetzen keine aktuelle Fehlerbeobachtung.</p>
      <label className="value-search">Werte suchen<input type="search" value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Name, Signal-ID oder Beschreibung" /></label>
      {definitions === null ? <p>Signaldefinitionen werden geladen …</p> : !visibleDefinitions.length ? <p className="empty-chart">Keine Werte zur Aufzeichnung ausgewählt. <a href="#/modbus">Aufzeichnung konfigurieren</a>.</p> : !matchingDefinitions.length ? <p>Keine Werte für diese Suche.</p> : signalGroups.map((group) => {
        const items = matchingDefinitions.filter((definition) => signalGroup(definition) === group);
        return items.length > 0 && <section className="value-group" key={group}><h2>{group} <span className="muted">({items.length})</span></h2><div className="value-list">{items.map((definition) => renderValue(definition))}</div></section>;
      })}
    </>}
    {view === 'settings' && <>
      <section className="collector-panel" aria-labelledby="collector-title"><div className="collector-copy"><p className="eyebrow">ERFASSUNG · KEINE HEIZUNGSBEDIENUNG</p><h2 id="collector-title">{collector ? stateLabels[collector.state] || 'Unbekannter Zustand' : 'Status wird geladen'}</h2>
        <p>{collector?.reason || (collector?.state === 'unconfigured' ? 'Die Installation ist noch nicht für die Erfassung eingerichtet.' : collector?.state === 'completed' ? 'Der endliche Erfassungslauf ist beendet. Dies ist keine Aussage zum Heizungszustand.' : 'Keine aktive Fehlermeldung.')}</p>
        <p className="status-meta">Letzte erfolgreiche Messung: <strong>{lastSuccessfulAt ? formatDate(lastSuccessfulAt, timeZone) : 'Noch keine erfolgreiche Messung'}</strong>{collector?.state === 'reconnect_wait' && collector.next_action_at && <> · Nächster Versuch: <strong>{formatDate(collector.next_action_at, timeZone)}</strong></>}</p>
        {collector?.state === 'reconnect_wait' && <p>Die Abfragen werden ohne Versuchslimit im regulären Intervall fortgesetzt.</p>}
      </div><div className="collector-actions">
        {canPause && <button className="button secondary" disabled={busy} onClick={() => void runCollectorAction('pause')}>Erfassung pausieren</button>}
        {canResume && <button className="button primary" disabled={busy} onClick={() => void runCollectorAction('resume')}>Erfassung fortsetzen</button>}
        {canAcknowledge && <button className="button primary" disabled={busy} onClick={() => void runCollectorAction('acknowledge-and-start')}>{collector?.state === 'completed' ? 'Erfassung geprüft – erneut starten' : 'Fehlerursache geprüft – Erfassung quittieren und starten'}</button>}
      </div></section>
      <section className="settings-panel" aria-labelledby="timezone-title"><h2 id="timezone-title">Anzeigezeitzone</h2><form onSubmit={(event) => void saveTimezone(event)}><label>Zeitzone<select value={timezoneDraft} onChange={(event) => setTimezoneDraft(event.target.value)}>{[...new Set(['Europe/Vienna', 'Europe/Berlin', 'UTC', timeZone])].map((zone) => <option key={zone} value={zone}>{zone}</option>)}</select></label><button className="button secondary" type="submit" disabled={busy || timezoneDraft === timeZone}>Zeitzone speichern</button></form><p className="muted">Das ändert nur die Darstellung. Zieladresse und Heizungsparameter werden hier nicht geändert.</p></section>
      <section className="settings-panel"><h2>Modbus-Aufzeichnung</h2><p>Die gespeicherten Aufzeichnungseinträge bestimmen alle angezeigten Werte und Vergleiche. Eine Diagrammwahl aktiviert keine zusätzlichen Signale.</p><a className="button secondary" href="#/modbus">Aufzeichnung konfigurieren</a></section>
      <section className="events-panel" aria-labelledby="events-title"><h2 id="events-title">App- und Erfassungsereignisse</h2>{events.length ? <ol className="event-list">{events.map((item) => <li key={item.event_id}><span className={`severity ${['error', 'warning', 'info'].includes(item.severity) ? item.severity : 'info'}`} /><div><p>{item.message}</p><EventDetails details={item.details} /><small>{item.kind.replaceAll('_', ' ')} · {formatDate(item.occurred_at, timeZone)}</small></div></li>)}</ol> : <p className="muted">Noch keine Ereignisse gespeichert.</p>}</section>
      <section className="control-candidates" aria-labelledby="control-candidates-title"><p className="eyebrow">SCHREIBNUTZUNG NICHT FREIGEGEBEN</p><h2 id="control-candidates-title">START / SOLL</h2><p>Die Basisparameter sind lesend importierbar. Eine spätere Schreibnutzung ist weiterhin nur Kandidat. Keine Schreibfunktion, Geräteaktion oder automatische Rückstellung.</p>{candidates.length ? <dl>{candidates.map((candidate) => <div key={candidate.code}><dt>{candidate.name} <code>{candidate.code}</code></dt><dd>{candidate.description}<br /><span className="muted">Schreibkandidat · nicht zur Ausführung freigegeben</span></dd></div>)}</dl> : <p className="muted">Steuerungskandidaten werden mit den Signaldefinitionen geladen.</p>}</section>
      <footer><span>Web-App-Status, Erfassungszustand und Heizungszustand sind getrennt.</span><span>{config?.host_configured ? 'Modbus-Ziel konfiguriert' : 'Kein Modbus-Ziel konfiguriert'} · {config?.collector_enabled ? 'Sammler beim Start aktiviert' : 'Sammler beim Start deaktiviert'}</span></footer>
    </>}
  </main>;
}
