export type CollectorStatus = {
  state: string; reason: string | null; reconnect_attempts: number;
  reconnect_attempt_limit: number; next_action_at: string | null; next_action: string | null;
};
export type Config = { collector_enabled: boolean; host_configured: boolean; display_timezone: string };
export type Signal = {
  signal_id: string; value: number | null; unit: string; observed_at: string;
  age_seconds: number; quality: string; fresh: boolean;
  error_code?: string | null; error_message?: string | null; block_offset?: number; register_count?: number;
};
export type SignalDefinition = {
  signal_id: string; label: string; unit: string; kind: string; live_confirmed: boolean;
  verification_status: string; module_status: string; read_to_clear: boolean;
  description: string; interval_seconds: number;
};
export type ControlCandidate = { code: string; name: string; description: string; kind: string };
export type Point = {
  observed_at: string; value: number | null; quality: string; unit?: string;
  error_code?: string | null; error_message?: string | null;
};
export type EventItem = {
  event_id: string; occurred_at: string; kind: string; severity: string; message: string;
  details?: Record<string, unknown> | null;
};
export type Period = '1h' | '24h' | 'week' | 'month' | 'custom';
export type DashboardView = 'overview' | 'analysis' | 'values' | 'settings';
export type ChartSeries = {
  id: string; label: string; unit: string; kind: string; intervalSeconds: number; points: Point[];
};

export const kindLabels: Record<string, string> = {
  measurement: 'Messwert', derived: 'Abgeleiteter Wert / Regelgröße', counter: 'Zähler',
  status: 'Status / Kennung', setting: 'Einstellung', raw: 'Herstellerrohwert',
  device_time: 'Steuerungsdatum / -zeit', control_candidate: 'Steuerungskandidat',
};
export const stateLabels: Record<string, string> = {
  unconfigured: 'Ersteinrichtung – noch nicht konfiguriert', paused: 'Pausiert',
  running: 'Erfassung läuft', completed: 'Erfassung abgeschlossen',
  reconnect_wait: 'Verbindungsfehler – Wiederaufnahme geplant',
  stopped_transport: 'Gestoppt – Verbindungsfehler', stopped_protocol: 'Gestoppt – Protokollfehler',
  stopped_data: 'Gestoppt – Datenfehler', stopped_storage: 'Gestoppt – Speicherfehler',
};
export const periods: { id: Period; label: string }[] = [
  { id: '1h', label: '1 Stunde' }, { id: '24h', label: '24 Stunden' },
  { id: 'week', label: 'Woche' }, { id: 'month', label: 'Monat' }, { id: 'custom', label: 'Freier Zeitraum' },
];
function localParts(date: Date, timeZone: string) {
  const parts = new Intl.DateTimeFormat('en-CA', {
    timeZone, year: 'numeric', month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit', second: '2-digit', hourCycle: 'h23',
  }).formatToParts(date);
  return Object.fromEntries(parts.map(({ type, value }) => [type, Number(value)])) as Record<string, number>;
}
export function localInputToUtc(value: string, timeZone: string, shiftAcrossGap = false): Date | null {
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
export function shiftLocal(date: Date, timeZone: string, unit: 'day' | 'week' | 'month', amount: number) {
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
export function formatDate(value: string | Date, timeZone: string, options: Intl.DateTimeFormatOptions = {}) {
  try {
    return new Intl.DateTimeFormat('de-AT', {
      timeZone, dateStyle: 'medium', timeStyle: 'short', ...options,
    }).format(new Date(value));
  } catch { return 'Unbekannt'; }
}
export function ageLabel(seconds: number) {
  if (!Number.isFinite(seconds) || seconds < 0) return 'Alter unbekannt';
  if (seconds < 60) return `vor ${Math.floor(seconds)} s`;
  if (seconds < 3600) return `vor ${Math.floor(seconds / 60)} min`;
  return `vor ${Math.floor(seconds / 3600)} h ${Math.floor((seconds % 3600) / 60)} min`;
}
export function safeErrorCode(value: unknown): string | undefined {
  return typeof value === 'string' && /^[a-z][a-z0-9_]{0,79}$/.test(value) ? value : undefined;
}
export function blockLabel(offset: unknown, count?: unknown): string | undefined {
  if (typeof offset !== 'number' || !Number.isInteger(offset) || offset < 0 || offset > 65535) return undefined;
  const registers = typeof count === 'number' && Number.isInteger(count) && count > 0 && count <= 125
    ? ` · ${count} Register` : '';
  return `Blockoffset ${offset}${registers}`;
}
export async function requestJson<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, init);
  if (!response.ok) throw new Error(`HTTP ${response.status}`);
  return response.json() as Promise<T>;
}

export type BoilerState = 'off' | 'running' | 'embers' | 'ignition' | 'unknown';
export const boilerStateLabels: Record<BoilerState, string> = {
  off: 'Aus', running: 'Ein · Regelbetrieb', embers: 'Ein · Gluterhaltung',
  ignition: 'Ein · Zündung', unknown: 'Unbekannt',
};
export function decodeBoilerState(raw: number): { state: BoilerState; minimumRuntime: boolean } {
  if (![0, 2, 3, 4, 0x8002, 0x8003, 0x8004].includes(raw)) return { state: 'unknown', minimumRuntime: false };
  const base = raw & 0x7fff;
  return { state: base === 0 ? 'off' : base === 2 ? 'running' : base === 3 ? 'embers' : 'ignition', minimumRuntime: (raw & 0x8000) !== 0 };
}

export type BoilerSourceReason = 'not_selected' | 'no_observation' | 'unavailable' | 'invalid_quality'
  | 'missing_value' | 'invalid_value' | 'unit_mismatch' | 'invalid_encoding' | 'invalid_time'
  | 'invalid_age' | 'stale' | 'api_loading' | 'api_unavailable';
export type BoilerDisplay = {
  evidence:
    | { kind: 'status'; signal: Signal; ageSeconds: number; state: Exclude<BoilerState, 'unknown'>; minimumRuntime: boolean }
    | { kind: 'power'; signal: Signal; ageSeconds: number; indication: 'active' | 'ambiguous'; value: number }
    | { kind: 'none' };
  statusReason: BoilerSourceReason | null;
  powerReason: BoilerSourceReason | null;
};

export function selectBoilerDisplay({ selectedIds, signals, apiStatus, elapsedSeconds }: {
  selectedIds: ReadonlySet<string>;
  signals: ReadonlyMap<string, Signal>;
  apiStatus: 'loading' | 'ok' | 'degraded' | 'error';
  elapsedSeconds: number;
}): BoilerDisplay {
  if (apiStatus !== 'ok') {
    const reason = apiStatus === 'loading' ? 'api_loading' : 'api_unavailable';
    return { evidence: { kind: 'none' }, statusReason: reason, powerReason: reason };
  }
  function sourceReason(id: string, unit: string): BoilerSourceReason | null {
    if (!selectedIds.has(id)) return 'not_selected';
    const signal = signals.get(id);
    if (!signal) return 'no_observation';
    if (signal.quality === 'unavailable') return 'unavailable';
    if (signal.quality !== 'ok') return 'invalid_quality';
    if (signal.value === null) return 'missing_value';
    if (!Number.isFinite(signal.value)) return 'invalid_value';
    if (signal.unit !== unit) return 'unit_mismatch';
    if (!Number.isFinite(Date.parse(signal.observed_at))) return 'invalid_time';
    if (!Number.isFinite(signal.age_seconds) || signal.age_seconds < 0 || !Number.isFinite(elapsedSeconds)) return 'invalid_age';
    if (signal.fresh !== true || signal.age_seconds + Math.max(0, elapsedSeconds) > 600) return 'stale';
    return null;
  }
  const status = signals.get('modbus.1001');
  const power = signals.get('modbus.1003');
  let statusReason = sourceReason('modbus.1001', 'Rohwert');
  let powerReason = sourceReason('modbus.1003', '%');
  const decoded = decodeBoilerState(status?.value ?? Number.NaN);
  if (statusReason === null && decoded.state === 'unknown') statusReason = 'invalid_encoding';
  if (powerReason === null && power!.value! < 0) powerReason = 'invalid_value';
  if (statusReason === null && decoded.state !== 'unknown') {
    return { evidence: { kind: 'status', signal: status!, state: decoded.state, minimumRuntime: decoded.minimumRuntime,
      ageSeconds: status!.age_seconds + Math.max(0, elapsedSeconds) }, statusReason, powerReason };
  }
  if (powerReason === null) {
    return { evidence: { kind: 'power', signal: power!, value: power!.value!,
      indication: power!.value! > 0 ? 'active' : 'ambiguous',
      ageSeconds: power!.age_seconds + Math.max(0, elapsedSeconds) }, statusReason, powerReason };
  }
  return { evidence: { kind: 'none' }, statusReason, powerReason };
}
export type StatusInterval = { start: number; end: number; state: BoilerState; reason: string };
function pointState(point: Point): BoilerState {
  return point.quality === 'ok' && point.unit === 'Rohwert' && point.value !== null
    ? decodeBoilerState(point.value).state : 'unknown';
}
export function statusIntervals(points: Point[], start: number, end: number): StatusInterval[] {
  if (!(end > start)) return [];
  const intervals: StatusInterval[] = [];
  let cursor = start;
  for (let i = 1; i < points.length; i += 1) {
    const left = points[i - 1];
    const right = points[i];
    const a = Date.parse(left.observed_at);
    const b = Date.parse(right.observed_at);
    if (!Number.isFinite(a) || !Number.isFinite(b) || b <= a || b <= start || a >= end) continue;
    const intervalStart = Math.max(start, a, cursor);
    const intervalEnd = Math.min(end, b);
    if (intervalStart >= intervalEnd) continue;
    if (cursor < intervalStart) intervals.push({ start: cursor, end: intervalStart, state: 'unknown', reason: 'Keine Statusbeobachtung' });
    const state = pointState(left);
    const nextState = pointState(right);
    const known = state !== 'unknown' && state === nextState && b - a <= 600_000;
    intervals.push({ start: intervalStart, end: intervalEnd, state: known ? state : 'unknown',
      reason: known ? boilerStateLabels[state] : state !== 'unknown' && nextState !== 'unknown' && state !== nextState
        ? 'Wechselbereich unbestimmt' : 'Aufzeichnungslücke oder ungültiger Status' });
    cursor = intervalEnd;
  }
  if (cursor < end) intervals.push({ start: cursor, end, state: 'unknown', reason: 'Keine Statusbeobachtung' });
  return intervals;
}

export const signalGroups = ['Kessel & Verbrennung', 'Puffer', 'Heizkreise', 'Außen & Wetter', 'Elektronik & Steuerung', 'Inaktive Module'];
export function signalGroup(definition: SignalDefinition): string {
  const id = definition.signal_id;
  const code = id.startsWith('modbus.') ? id.slice(7).toUpperCase() : '';
  if (definition.module_status === 'inactive') return 'Inaktive Module';
  if (['8280', '1020', '1021', '1022', '1023'].includes(code)) return 'Außen & Wetter';
  if (definition.kind === 'device_time' || ['1009', '100A'].includes(code)) return 'Elektronik & Steuerung';
  if (id.startsWith('buffer.') || /^(90|91|95)[0-9A-F]{2}$/.test(code)) return 'Puffer';
  if (/^(80|85)[0-9A-F]{2}$/.test(code) || ['82E0', '82E1'].includes(code)) return 'Heizkreise';
  return 'Kessel & Verbrennung';
}
export const chartPresets = [
  { id: 'buffer', label: 'Puffer & Kessel', sources: ['buffer.top_temperature', 'buffer.bottom_temperature', 'boiler.temperature'] },
  { id: 'stratification', label: 'Pufferschichtung', sources: ['buffer.top_temperature', 'buffer.bottom_temperature'] },
  { id: 'power', label: 'Leistungsregelung', sources: ['modbus.1003', 'modbus.1008'] },
  { id: 'heating1', label: 'Heizkreis 1', sources: ['modbus.8020', 'modbus.8040'] },
  { id: 'heating2', label: 'Heizkreis 2', sources: ['modbus.8021', 'modbus.8041'] },
  { id: 'single', label: 'Einzelwert', sources: [] },
];
export function availablePresets(selectedIds: Iterable<string>) {
  const ids = new Set(selectedIds);
  return chartPresets.filter((preset) => preset.id === 'single' ? ids.size > 0
    : preset.id === 'stratification' ? preset.sources.every((id) => ids.has(id))
      : preset.sources.some((id) => ids.has(id)));
}
export function bufferDifference(top: Point[], bottom: Point[]): Point[] {
  const topByTime = new Map<number, Point>();
  const bottomByTime = new Map<number, Point>();
  for (const point of top) if (Number.isFinite(Date.parse(point.observed_at))) topByTime.set(Date.parse(point.observed_at), point);
  for (const point of bottom) if (Number.isFinite(Date.parse(point.observed_at))) bottomByTime.set(Date.parse(point.observed_at), point);
  const times = [...new Set([...topByTime.keys(), ...bottomByTime.keys()])].sort((a, b) => a - b);
  return times.map((time) => {
    const a = topByTime.get(time);
    const b = bottomByTime.get(time);
    const valid = a?.quality === 'ok' && b?.quality === 'ok' && a.unit === '°C' && b.unit === '°C'
      && a.value !== null && b.value !== null && Number.isFinite(a.value) && Number.isFinite(b.value);
    return { observed_at: new Date(time).toISOString(), value: valid ? a.value! - b.value! : null,
      quality: valid ? 'ok' : 'unavailable', unit: 'K' };
  });
}
export type ChartSegment = { unit: string; points: Point[] };
export function continuousSegments(points: Point[], intervalSeconds: number): ChartSegment[] {
  const segments: ChartSegment[] = [];
  let current: ChartSegment | undefined;
  let previous = NaN;
  for (const point of points) {
    const timestamp = Date.parse(point.observed_at);
    if (point.quality !== 'ok' || point.value === null || !Number.isFinite(point.value) || !Number.isFinite(timestamp)) {
      current = undefined; previous = NaN; continue;
    }
    const unit = point.unit ?? 'Einheit unbekannt';
    if (!current || current.unit !== unit || timestamp < previous || timestamp - previous > 3 * intervalSeconds * 1000) {
      current = { unit, points: [] };
      segments.push(current);
    }
    current.points.push(point);
    previous = timestamp;
  }
  return segments;
}
export function isStepped(kind: string) {
  return ['status', 'setting', 'counter', 'device_time', 'raw'].includes(kind);
}
export function downsampleSegment(points: Point[], start: number, end: number, width: number): Point[] {
  const cells = Math.max(1, Math.min(800, Math.floor(width)));
  if (points.length <= 4 || !(end > start)) return points;
  const result: Point[] = [];
  let cell = NaN;
  let first = 0;
  let min = 0;
  let max = 0;
  const flush = (last: number) => {
    const indices = [...new Set([first, min, max, last])].sort((a, b) => a - b);
    for (const index of indices) result.push(points[index]);
  };
  for (let i = 0; i < points.length; i += 1) {
    const next = Math.max(0, Math.min(cells - 1, Math.floor((Date.parse(points[i].observed_at) - start) / (end - start) * cells)));
    if (next !== cell) {
      if (i > 0) flush(i - 1);
      cell = next; first = i; min = i; max = i;
    } else {
      if (points[i].value! < points[min].value!) min = i;
      if (points[i].value! > points[max].value!) max = i;
    }
  }
  flush(points.length - 1);
  return result;
}
export function nearestPoint(points: Point[], time: number, intervalSeconds: number): Point | undefined {
  let low = 0;
  let high = points.length;
  while (low < high) {
    const mid = (low + high) >>> 1;
    if (Date.parse(points[mid].observed_at) <= time) low = mid + 1;
    else high = mid;
  }
  const before = points[low - 1];
  const after = points[low];
  const chosen = !before ? after : !after ? before
    : time - Date.parse(before.observed_at) <= Date.parse(after.observed_at) - time ? before : after;
  return chosen && Math.abs(Date.parse(chosen.observed_at) - time) <= intervalSeconds * 500 ? chosen : undefined;
}

export async function loadHistory(signalId: string, start: number, end: number, signal: AbortSignal,
  onProgress?: (loaded: number, total: number) => void): Promise<Point[]> {
  const points: Point[] = [];
  let total: number | undefined;
  let previous = -Infinity;
  do {
    signal.throwIfAborted();
    const query = new URLSearchParams({ start: new Date(start).toISOString(), end: new Date(end).toISOString(), limit: '10000', offset: String(points.length) });
    const page = await requestJson<{ signal_id: string; total: number; offset: number; limit: number; items: Point[] }>(
      `/api/history/${encodeURIComponent(signalId)}?${query}`, { signal });
    signal.throwIfAborted();
    if (!Number.isSafeInteger(page.total) || page.total < 0 || (total !== undefined && page.total !== total)
      || page.signal_id !== signalId || page.offset !== points.length || page.limit !== 10000 || !Array.isArray(page.items)
      || page.items.length > 10000 || points.length + page.items.length > page.total
      || (page.items.length === 0 && points.length < page.total)) {
      throw new Error('Historienabruf unvollständig: widersprüchliche Pagination');
    }
    total ??= page.total;
    for (const item of page.items) {
      const timestamp = Date.parse(item.observed_at);
      if (!Number.isFinite(timestamp) || timestamp < start || timestamp >= end || timestamp < previous
        || (item.value !== null && (typeof item.value !== 'number' || !Number.isFinite(item.value)))
        || typeof item.quality !== 'string' || (item.unit !== undefined && typeof item.unit !== 'string')) {
        throw new Error('Historienabruf unvollständig: widersprüchliche Beobachtungen');
      }
      points.push({ observed_at: item.observed_at, value: item.value, quality: item.quality, unit: item.unit,
        error_code: item.error_code, error_message: item.error_message });
      previous = timestamp;
    }
    onProgress?.(points.length, total);
  } while (points.length < total);
  return points;
}
