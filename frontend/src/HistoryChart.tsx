import { useEffect, useId, useMemo, useRef, useState } from 'react';
import type { KeyboardEvent, PointerEvent } from 'react';
import {
  boilerStateLabels, continuousSegments, implausiblePoints, decodeBoilerState, displayMeasurement, downsampleSegment,
  formatDate, isStepped, nearestPoint, statusIntervals,
} from './dashboard';
import type { BoilerState, ChartSeries, Point } from './dashboard';

export type HistoryChartProps = {
  start: number; end: number; timeZone: string; series: ChartSeries[]; statusPoints?: Point[];
};
const patterns = ['', '9 4', '3 4', '12 4 3 4', '6 3', '2 3'];
const numberFormat = new Intl.NumberFormat('de-AT', { maximumFractionDigits: 2 });
const valueFormat = new Intl.NumberFormat('de-AT', { maximumSignificantDigits: 21 });
const statusColors: Record<BoilerState, string> = {
  off: 'var(--muted)', running: 'var(--success)', embers: 'var(--warning)',
  ignition: 'var(--accent)', unknown: 'var(--border)',
};

export default function HistoryChart({ start, end, timeZone, series, statusPoints }: HistoryChartProps) {
  const container = useRef<HTMLDivElement>(null);
  const [width, setWidth] = useState(640);
  const [hidden, setHidden] = useState<Set<string>>(() => new Set());
  const [cursor, setCursor] = useState<number | null>(null);
  const [hover, setHover] = useState<{ x: number; y: number; scaleX: number; scaleY: number } | null>(null);
  const [announcement, setAnnouncement] = useState('');
  const id = useId().replace(/:/g, '');
  useEffect(() => {
    const element = container.current;
    if (!element) return;
    const resize = () => setWidth(Math.max(220, Math.floor(element.getBoundingClientRect().width)));
    resize();
    const observer = new ResizeObserver(resize);
    observer.observe(element);
    return () => observer.disconnect();
  }, []);
  const left = 66;
  const right = 16;
  const plotWidth = Math.max(1, width - left - right);
  const x = (time: number) => left + (time - start) / (end - start) * plotWidth;
  const prepared = useMemo(() => series.map((entry, index) => {
    const points = entry.id === 'boiler.operating_minutes'
      ? entry.points.map((point) => point.unit === 'min'
        ? { ...point, ...displayMeasurement(entry.id, point.value, point.unit) } : point)
      : entry.points;
    return {
      ...entry, points, unit: displayMeasurement(entry.id, null, entry.unit).unit ?? entry.unit,
      color: entry.id === 'boiler.temperature' ? 'var(--c1)'
        : entry.id === 'buffer.top_temperature' ? 'var(--c2)'
          : entry.id === 'buffer.bottom_temperature' ? 'var(--c3)' : `var(--c${index % 6 + 1})`,
      dash: patterns[index % patterns.length],
      implausible: implausiblePoints(points).filter((point) => {
        const time = Date.parse(point.observed_at);
        return time >= start && time < end;
      }),
      segments: continuousSegments(points, entry.intervalSeconds)
        .map((segment) => ({ ...segment, points: segment.points.filter((point) => {
          const time = Date.parse(point.observed_at);
          return time >= start && time < end;
        }) })).filter((segment) => segment.points.length > 0),
    };
  }), [series, start, end]);
  const panels = useMemo(() => {
    const units = new Map<string, typeof prepared>();
    for (const entry of prepared) {
      if (hidden.has(entry.id)) continue;
      const sourceUnits = new Set(entry.points.filter((point) => {
        const time = Date.parse(point.observed_at);
        return time >= start && time < end;
      }).map((point) => point.unit ?? 'Einheit unbekannt'));
      if (!sourceUnits.size) sourceUnits.add(entry.unit || 'Einheit unbekannt');
      for (const unit of sourceUnits) {
        const entries = units.get(unit) ?? [];
        entries.push(entry);
        units.set(unit, entries);
      }
    }
    return [...units].map(([unit, entries], panelIndex) => {
      let min = Infinity;
      let max = -Infinity;
      let reduced = false;
      const paths = entries.flatMap((entry) => entry.segments.filter((segment) => segment.unit === unit).map((segment) => {
        for (const point of segment.points) {
          min = Math.min(min, point.value!);
          max = Math.max(max, point.value!);
        }
        const points = entry.kind === 'status' ? segment.points : downsampleSegment(segment.points, start, end, plotWidth);
        reduced ||= points.length < segment.points.length;
        return { entry, points, sourcePoints: segment.points };
      }));
      const marks = entries.flatMap((entry) => entry.implausible
        .filter((point) => (point.unit ?? 'Einheit unbekannt') === unit).map((point) => ({ entry, point })));
      for (const { point } of marks) {
        min = Math.min(min, point.value!);
        max = Math.max(max, point.value!);
      }
      const empty = !Number.isFinite(min);
      if (empty) { min = 0; max = 1; }
      const padding = max === min ? Math.max(1, Math.abs(min) * 0.05) : (max - min) * 0.08;
      return { unit, entries, paths, marks, min: min - padding, max: max + padding, reduced, empty, top: panelIndex * 242 + 32 };
    });
  }, [prepared, hidden, plotWidth, start, end]);
  const bands = useMemo(() => statusPoints === undefined ? [] : statusIntervals(statusPoints, start, end), [statusPoints, start, end]);
  const timestamps = useMemo(() => {
    const times = new Set<number>();
    for (const entry of prepared) {
      if (hidden.has(entry.id)) continue;
      for (const point of entry.points) {
        const time = Date.parse(point.observed_at);
        if (time >= start && time < end) times.add(time);
      }
    }
    for (const point of statusPoints ?? []) {
      const time = Date.parse(point.observed_at);
      if (time >= start && time < end) times.add(time);
    }
    return [...times].sort((a, b) => a - b);
  }, [prepared, hidden, statusPoints, start, end]);
  const panelBottom = Math.max(1, panels.length) * 242;
  const bandTop = panelBottom + 18;
  const axisY = panelBottom + (statusPoints === undefined ? 8 : 66);
  const height = axisY + 58;
  const hoveredPoint = useMemo(() => {
    if (!hover || hover.x < left || hover.x > width - right) return undefined;
    const time = start + (hover.x - left) / plotWidth * (end - start);
    let nearest: { entry: (typeof prepared)[number]; point: Point; x: number; y: number } | undefined;
    let distance = 8;
    for (const panel of panels) {
      if (hover.y < panel.top || hover.y > panel.top + 180) continue;
      for (const { entry, sourcePoints } of panel.paths) {
        const point = nearestPoint(sourcePoints, time, Infinity);
        if (!point) continue;
        const px = left + (Date.parse(point.observed_at) - start) / (end - start) * plotWidth;
        const py = panel.top + 180 - (point.value! - panel.min) / (panel.max - panel.min) * 180;
        const pixels = Math.hypot((px - hover.x) * hover.scaleX, (py - hover.y) * hover.scaleY);
        if (pixels <= distance) {
          distance = pixels;
          nearest = { entry, point, x: px, y: py };
        }
      }
    }
    return nearest;
  }, [hover, panels, start, end, plotWidth, width]);
  const inspectionTime = cursor !== null && cursor >= start && cursor < end ? cursor : undefined;
  const visibleEntries = prepared.filter((entry) => !hidden.has(entry.id));
  const details = visibleEntries.map((entry) => ({ entry, point: inspectionTime === undefined ? undefined : nearestPoint(entry.points, inspectionTime, entry.intervalSeconds) }));
  const statusPoint = inspectionTime === undefined || statusPoints === undefined ? undefined : nearestPoint(statusPoints, inspectionTime, 300);
  const tickCount = width < 500 ? 2 : 4;
  const ticks = Array.from({ length: tickCount + 1 }, (_, index) => start + (end - start) * index / tickCount);
  const tickDate = new Intl.DateTimeFormat('de-AT', { timeZone, day: '2-digit', month: '2-digit' });
  const tickTime = new Intl.DateTimeFormat('de-AT', { timeZone, hour: '2-digit', minute: '2-digit', hourCycle: 'h23' });
  function inspectPointer(event: PointerEvent<SVGSVGElement>) {
    const bounds = event.currentTarget.getBoundingClientRect();
    const coordinate = (event.clientX - bounds.left) * width / bounds.width;
    const time = start + Math.max(0, Math.min(1, (coordinate - left) / plotWidth)) * (end - start);
    setCursor(Math.min(end - 1, time));
    setHover(event.pointerType === 'mouse' ? {
      x: coordinate, y: (event.clientY - bounds.top) * height / bounds.height,
      scaleX: bounds.width / width, scaleY: bounds.height / height,
    } : null);
  }
  function inspectKey(event: KeyboardEvent<HTMLDivElement>) {
    if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key) || !timestamps.length) return;
    event.preventDefault();
    setHover(null);
    let low = 0;
    let high = timestamps.length;
    const current = inspectionTime ?? timestamps[0];
    while (low < high) {
      const mid = (low + high) >>> 1;
      if (timestamps[mid] < current) low = mid + 1;
      else high = mid;
    }
    const index = event.key === 'Home' ? 0 : event.key === 'End' ? timestamps.length - 1
      : event.key === 'ArrowLeft' ? Math.max(0, low - 1)
        : Math.min(timestamps.length - 1, low + (inspectionTime !== undefined && timestamps[low] === current ? 1 : 0));
    const time = timestamps[index];
    setCursor(time);
    const summaries = visibleEntries.map((entry) => {
      const point = nearestPoint(entry.points, time, entry.intervalSeconds);
      return `${entry.label}: ${point ? `${point.value === null ? 'kein Wert' : valueFormat.format(point.value)} ${point.unit ?? 'Einheit unbekannt'}, Qualität ${point.quality}, Messzeit ${formatDate(point.observed_at, timeZone, { timeStyle: 'medium' })}` : 'Für diesen Zeitpunkt keine Beobachtung'}`;
    });
    if (statusPoints !== undefined) {
      const point = nearestPoint(statusPoints, time, 300);
      summaries.push(`Steuerungszustand: ${point ? `${point.value ?? 'kein Wert'} ${point.unit ?? 'Einheit unbekannt'}, Qualität ${point.quality}, Messzeit ${formatDate(point.observed_at, timeZone, { timeStyle: 'medium' })}` : 'Für diesen Zeitpunkt keine Statusaufzeichnung in der Nähe (±2,5 Minuten)'}`);
    }
    setAnnouncement(`${formatDate(new Date(time), timeZone, { timeStyle: 'medium' })}. ${summaries.join('. ')}`);
  }
  if (!(end > start)) return <p className="empty-chart">Kein gültiger Zeitraum ausgewählt.</p>;
  return <div className="history-chart" ref={container}>
    <fieldset className="chart-legend">
      <legend>Diagrammreihen ein- oder ausblenden</legend>
      {prepared.map((entry) => <label className="chart-legend-item" key={entry.id}>
        <input type="checkbox" checked={!hidden.has(entry.id)} onChange={() => setHidden((previous) => {
          const next = new Set(previous);
          if (next.has(entry.id)) next.delete(entry.id); else next.add(entry.id);
          return next;
        })} />
        <svg className="chart-swatch" width="32" height="16" aria-hidden="true"><line x1="1" y1="8" x2="31" y2="8" stroke={entry.color} strokeWidth="3" strokeDasharray={entry.dash} /></svg>
        {entry.label}
      </label>)}
      {!prepared.length && <span className="muted">Keine ausgewählte Messreihe.</span>}
    </fieldset>
    <div className="chart-inspector" role="group" tabIndex={0} onKeyDown={inspectKey}
      aria-label="Verlauf untersuchen" aria-describedby={`${id}-help`}>
      <svg className="chart-svg" width="100%" height={height} viewBox={`0 0 ${width} ${height}`}
        role="img" aria-labelledby={`${id}-title ${id}-description`} onPointerDown={inspectPointer}
        onPointerMove={(event) => { if (event.pointerType === 'mouse' || event.buttons > 0) inspectPointer(event); }}
        onPointerLeave={() => setHover(null)}
        style={{ display: 'block', touchAction: 'pan-y', fontFamily: 'inherit', fontSize: 14 }}>
        <title id={`${id}-title`}>Messwerte im gewählten Zeitraum</title>
        <desc id={`${id}-description`}>Getrennte Flächen je Anzeigeeinheit, gemeinsame Zeitachse. Lücken werden nicht überbrückt. Details unter dem Diagramm.</desc>
        <defs>
          <pattern id={`${id}-unknown`} width="8" height="8" patternUnits="userSpaceOnUse">
            <rect width="8" height="8" fill="var(--surface)" />
            <path d="M-2 2L2 -2M0 8L8 0M6 10L10 6" stroke="var(--border)" strokeWidth="2" />
          </pattern>
          {panels.map((panel, index) => <clipPath key={panel.unit} id={`${id}-clip-${index}`}><rect x={left} y={panel.top} width={plotWidth} height="180" /></clipPath>)}
        </defs>
        {panels.map((panel, panelIndex) => {
          const y = (value: number) => panel.top + 180 - (value - panel.min) / (panel.max - panel.min) * 180;
          return <g key={panel.unit}>
            <text className="chart-unit" x={left} y={panel.top - 12} fill="var(--fg)">{panel.unit}</text>
            {[0, 1, 2, 3, 4].map((index) => {
              const value = panel.min + (panel.max - panel.min) * index / 4;
              return <g key={index}>
                <line className="chart-grid" x1={left} x2={width - right} y1={y(value)} y2={y(value)} stroke="var(--border)" />
                <text className="chart-axis-label" x={left - 8} y={y(value) + 5} textAnchor="end" fill="var(--muted)">{numberFormat.format(value)}</text>
              </g>;
            })}
            {ticks.map((time) => <line key={time} x1={x(time)} x2={x(time)} y1={panel.top} y2={panel.top + 180} stroke="var(--border)" strokeDasharray="2 4" />)}
            <g clipPath={`url(#${id}-clip-${panelIndex})`}>
              {panel.paths.map(({ entry, points }, segmentIndex) => {
                let path = '';
                for (let i = 0; i < points.length; i += 1) {
                  const px = x(Date.parse(points[i].observed_at));
                  const py = y(points[i].value!);
                  path += i === 0 ? `M${px},${py}` : isStepped(entry.kind) ? `H${px}V${py}` : `L${px},${py}`;
                }
                return <g key={`${entry.id}-${segmentIndex}`}>
                  <path d={path} stroke={entry.color} strokeWidth="2" strokeDasharray={entry.dash} fill="none" />
                  {points.length === 1 && <circle cx={x(Date.parse(points[0].observed_at))} cy={y(points[0].value!)} r="3" fill={entry.color} />}
                </g>;
              })}
              {panel.marks.map(({ entry, point }) => {
                const mx = x(Date.parse(point.observed_at));
                const my = y(point.value!);
                return <path key={`${entry.id}-${point.observed_at}`} d={`M${mx - 4},${my - 4}L${mx + 4},${my + 4}M${mx - 4},${my + 4}L${mx + 4},${my - 4}`}
                  stroke="var(--error)" strokeWidth="2" fill="none"><title>{`${entry.label}: unplausibel ${point.value} ${point.unit ?? ''}`}</title></path>;
              })}
            </g>
            {panel.empty && <text x={left + plotWidth / 2} y={panel.top + 92} textAnchor="middle" fill="var(--muted)">Keine gültigen Messungen</text>}
          </g>;
        })}
        {!panels.length && <text x={left + plotWidth / 2} y="112" textAnchor="middle" fill="var(--muted)">Keine sichtbare Reihe</text>}
        {statusPoints !== undefined && <g>
          <text x={left} y={bandTop - 6} fill="var(--muted)">Steuerungszustand</text>
          {bands.map((band, index) => {
            const bandWidth = x(band.end) - x(band.start);
            const color = statusColors[band.state];
            return <g key={index}>
              <rect x={x(band.start)} y={bandTop} width={bandWidth} height="26"
                fill={band.state === 'unknown' ? `url(#${id}-unknown)` : color} fillOpacity={band.state === 'unknown' ? 1 : 0.25}>
                <title>{`${boilerStateLabels[band.state]} · ${band.reason} · ${formatDate(new Date(band.start), timeZone)} bis ${formatDate(new Date(band.end), timeZone)}`}</title></rect>
              {bandWidth > 115 && <text x={x(band.start) + bandWidth / 2} y={bandTop + 18} textAnchor="middle" fill="var(--fg)">{boilerStateLabels[band.state]}</text>}
            </g>;
          })}
        </g>}
        {inspectionTime !== undefined && <line className="chart-cursor" x1={x(inspectionTime)} x2={x(inspectionTime)} y1="20" y2={axisY} stroke="var(--fg)" strokeWidth="1.5" strokeDasharray="4 3" />}
        {hoveredPoint && <circle cx={hoveredPoint.x} cy={hoveredPoint.y} r="4" fill={hoveredPoint.entry.color} stroke="var(--surface)" strokeWidth="1.5" pointerEvents="none" />}
        {ticks.map((time, index) => <text key={time} className="chart-axis-label" x={x(time)} y={axisY + 20}
          textAnchor={index === 0 ? 'start' : index === ticks.length - 1 ? 'end' : 'middle'} fill="var(--muted)">
          <tspan x={x(time)}>{tickDate.format(time)}</tspan><tspan x={x(time)} dy="18">{tickTime.format(time)}</tspan>
        </text>)}
      </svg>
      {hoveredPoint && <div className="chart-tooltip" role="tooltip" style={{
        ...(hoveredPoint.x < width / 2 ? { left: `${hoveredPoint.x / width * 100}%` } : { right: `${(width - hoveredPoint.x) / width * 100}%` }),
        top: `${hoveredPoint.y / height * 100}%`,
        transform: hoveredPoint.y < 110 ? 'translateY(12px)' : 'translateY(calc(-100% - 12px))',
      }}>
        <strong>{hoveredPoint.entry.label}</strong>
        <span>{formatDate(hoveredPoint.point.observed_at, timeZone, { timeStyle: 'medium' })} ({timeZone})</span>
        <span>{valueFormat.format(hoveredPoint.point.value!)} {hoveredPoint.point.unit ?? 'Einheit unbekannt'}</span>
      </div>}
    </div>
    {statusPoints !== undefined && <p className="chart-status-note">Steuerungszustand alle 5 Minuten · Schraffiert: unbekannt oder Zustandswechsel zwischen zwei Abfragen.</p>}
    {statusPoints !== undefined && <div className="chart-status-legend" aria-label="Zustände im Statusband">
      {(Object.keys(boilerStateLabels) as BoilerState[]).map((state) => <span className="chart-status-key" key={state}>
        <svg width="22" height="16" aria-hidden="true"><rect x="1" y="1" width="20" height="14" fill={state === 'unknown' ? `url(#${id}-unknown)` : statusColors[state]} stroke="var(--border)" /></svg>
        {boilerStateLabels[state]}
      </span>)}
    </div>}
    {panels.some((panel) => panel.reduced) && <p className="chart-compression-note">Darstellung verdichtet · Inspektion und CSV enthalten die Originalbeobachtungen.</p>}
    <p className="chart-keyboard-help" id={`${id}-help`}>Messwerte zu einem Zeitpunkt: Diagramm berühren oder mit der Maus zeigen. Tastatur: Links/Rechts, Pos1/Ende.</p>
    {inspectionTime !== undefined && <>
    <p className="chart-inspection-time">Gewählter Zeitpunkt: {formatDate(new Date(inspectionTime), timeZone, { timeStyle: 'medium' })}</p>
    <dl className="chart-details">
      {details.map(({ entry, point }) => <div className="chart-detail-row" key={entry.id}>
        <dt>{entry.label}</dt>
        <dd>{point ? <><strong>{point.value === null ? 'Kein Wert' : valueFormat.format(point.value)} {point.unit ?? 'Einheit unbekannt'}</strong>
          {' · '}Qualität: {point.quality}{' · '}Messzeit: {formatDate(point.observed_at, timeZone, { timeStyle: 'medium' })}
          {point.error_code && ` · ${point.error_code}`}{point.error_message && ` · ${point.error_message}`}</> : 'Für diesen Zeitpunkt keine Beobachtung'}</dd>
      </div>)}
      {statusPoints !== undefined && <div className="chart-detail-row"><dt>Steuerungszustand</dt><dd>
        {statusPoint ? <>{boilerStateLabels[statusPoint.quality === 'ok' && statusPoint.unit === 'Rohwert' && statusPoint.value !== null ? decodeBoilerState(statusPoint.value).state : 'unknown']}
          {statusPoint.value !== null && ` · Originalwert: ${statusPoint.value} ${statusPoint.unit ?? 'Einheit unbekannt'}`}
          {statusPoint.quality === 'ok' && statusPoint.unit === 'Rohwert' && statusPoint.value !== null && decodeBoilerState(statusPoint.value).minimumRuntime && ' · Mindestlaufzeit-Kennzeichen'}
          {' · '}Qualität: {statusPoint.quality}{' · '}Messzeit: {formatDate(statusPoint.observed_at, timeZone, { timeStyle: 'medium' })}
          {statusPoint.error_code && ` · ${statusPoint.error_code}`}</> : 'Für diesen Zeitpunkt keine Statusaufzeichnung in der Nähe (±2,5 Minuten)'}
      </dd></div>}
    </dl>
    </>}
    <p className="visually-hidden" aria-live="polite" aria-atomic="true">{announcement}</p>
  </div>;
}
