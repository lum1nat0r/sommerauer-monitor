import test from 'node:test';
import assert from 'node:assert/strict';
import {
  availablePresets, bufferDifference, continuousSegments, implausiblePoints, decodeBoilerState, downsampleSegment,
  displayMeasurement, isFresh, isStepped, loadHistory, localInputToUtc, nearestPoint, selectBoilerDisplay, signalGroup, statusIntervals,
} from '../frontend/src/dashboard.ts';

const origin = Date.parse('2026-10-01T00:00:00Z');
const point = (seconds, value, unit = '°C', quality = 'ok') => ({
  observed_at: new Date(origin + seconds * 1000).toISOString(), value, unit, quality,
});
const definition = (signal_id, extra = {}) => ({
  signal_id, label: signal_id, unit: '°C', kind: 'measurement', live_confirmed: false,
  verification_status: 'source_only', module_status: 'unknown', read_to_clear: false,
  description: '', interval_seconds: 300, ...extra,
});

test('Anlagenbetriebsstunden sind reine Darstellung der Originalminuten', () => {
  for (const [minutes, hours] of [[90, 1.5], [1440, 24], [1, 1 / 60]]) {
    assert.deepEqual(displayMeasurement('boiler.operating_minutes', minutes, 'min'), { value: hours, unit: 'h' });
  }
  assert.deepEqual(displayMeasurement('boiler.operating_minutes', null, 'min'), { value: null, unit: 'h' });
  assert.deepEqual(displayMeasurement('stoker.operating_minutes', 90, 'min'), { value: 90, unit: 'min' });
  assert.deepEqual(displayMeasurement('boiler.operating_minutes', 90, 'Rohwert'), { value: 90, unit: 'Rohwert' });
});

test('Browser übernimmt Backend-Frischegrenzen ohne eigene Intervallkonstante', () => {
  for (const limit of [240, 1200]) {
    const signal = observation(powerId, 50, { age_seconds: limit - 10, fresh_until_age_seconds: limit });
    assert.equal(isFresh(signal, 9.999), true);
    assert.equal(isFresh(signal, 10), true);
    assert.equal(isFresh(signal, 10.001), false);
    assert.equal(isFresh({ ...signal, quality: 'invalid' }, 0), false);
    assert.equal(isFresh({ ...signal, value: null }, 0), false);
    assert.equal(isFresh({ ...signal, fresh: false }, 0), false);
    assert.equal(isFresh({ ...signal, fresh_until_age_seconds: undefined }, 0), false);
  }
});

test('nur die sieben belegten Statuswörter werden dekodiert', () => {
  assert.deepEqual(decodeBoilerState(0), { state: 'off', minimumRuntime: false });
  for (const [raw, state] of [[2, 'running'], [3, 'embers'], [4, 'ignition']]) {
    assert.deepEqual(decodeBoilerState(raw), { state, minimumRuntime: false });
    assert.deepEqual(decodeBoilerState(raw | 0x8000), { state, minimumRuntime: true });
  }
  for (const raw of [1, 5, 0x8000, 0xffff, -1, 2.5, NaN, Infinity]) {
    assert.deepEqual(decodeBoilerState(raw), { state: 'unknown', minimumRuntime: false });
  }
});

const statusId = 'modbus.1001';
const powerId = 'modbus.1003';
const observation = (signal_id, value, extra = {}) => ({
  signal_id, ...point(0, value, signal_id === statusId ? 'Rohwert' : '%'),
  age_seconds: 20, fresh: true, fresh_until_age_seconds: 600, ...extra,
});
const boilerDisplay = (signals, extra = {}) => selectBoilerDisplay({
  signals: new Map(signals.map((signal) => [signal.signal_id, signal])),
  selectedIds: new Set([statusId, powerId]), apiStatus: 'ok', elapsedSeconds: 10, ...extra,
});

test('gültiger ausgewählter Steuerungszustand hat Vorrang vor positiver Istregelgröße, auch Aus', () => {
  for (const [raw, state, minimumRuntime] of [
    [0, 'off', false], [2, 'running', false], [3, 'embers', false], [4, 'ignition', false],
    [0x8002, 'running', true], [0x8003, 'embers', true], [0x8004, 'ignition', true],
  ]) {
    const status = observation(statusId, raw);
    const result = boilerDisplay([status, observation(powerId, 75)]);
    assert.deepEqual(result.evidence, { kind: 'status', signal: status, state, minimumRuntime, ageSeconds: 30 });
    assert.equal(result.statusReason, null);
  }
});

test('Leistungsersatz trennt positiven indirekten Hinweis von mehrdeutiger Null ohne Ein-/Aus-Zustand', () => {
  for (const [value, indication] of [[42.5, 'active'], [0, 'ambiguous']]) {
    const signal = observation(powerId, value);
    const result = boilerDisplay([signal]);
    assert.deepEqual(result.evidence, { kind: 'power', signal, value, indication, ageSeconds: 30 });
    assert.equal(result.statusReason, 'no_observation');
    assert.equal(result.powerReason, null);
    assert.equal('state' in result.evidence, false);
    assert.equal('minimumRuntime' in result.evidence, false);
  }
});

test('unbrauchbare Statusquelle bleibt mit echtem Grund sichtbar, während die Istregelgröße separat nutzbar ist', () => {
  const cases = [
    [undefined, 'no_observation'],
    [{ quality: 'unavailable', value: null, error_code: 'not_provided' }, 'unavailable'],
    [{ quality: 'invalid', value: null, error_code: 'unknown_boiler_state' }, 'invalid_quality'],
    [{ quality: 'error' }, 'invalid_quality'],
    [{ quality: 'unknown' }, 'invalid_quality'],
    [{ value: null }, 'missing_value'],
    [{ value: NaN }, 'invalid_value'],
    [{ value: Infinity }, 'invalid_value'],
    [{ unit: '%' }, 'unit_mismatch'],
    [{ value: 1 }, 'invalid_encoding'],
    [{ value: 0x8000 }, 'invalid_encoding'],
    [{ value: 0xffff }, 'invalid_encoding'],
    [{ observed_at: 'not-a-time' }, 'invalid_time'],
    [{ age_seconds: NaN }, 'invalid_age'],
    [{ age_seconds: Infinity }, 'invalid_age'],
    [{ age_seconds: -1 }, 'invalid_age'],
    [{ age_seconds: 591 }, 'stale'],
    [{ fresh: false }, 'stale'],
  ];
  for (const [extra, reason] of cases) {
    const signals = [observation(powerId, 55)];
    if (extra) signals.push(observation(statusId, 2, extra));
    const result = boilerDisplay(signals);
    assert.equal(result.evidence.kind, 'power', reason);
    assert.equal(result.evidence.indication, 'active', reason);
    assert.equal(result.statusReason, reason);
  }
});

test('ungültige oder fehlende Leistungsbeobachtungen erzeugen keinen aktuellen Ersatzbefund', () => {
  const cases = [
    [undefined, 'no_observation'],
    [{ quality: 'unavailable', value: null }, 'unavailable'],
    [{ quality: 'invalid', value: null, error_code: 'decode_failed' }, 'invalid_quality'],
    [{ quality: 'error' }, 'invalid_quality'],
    [{ quality: 'unknown' }, 'invalid_quality'],
    [{ quality: '' }, 'invalid_quality'],
    [{ value: null }, 'missing_value'],
    [{ value: NaN }, 'invalid_value'],
    [{ value: Infinity }, 'invalid_value'],
    [{ value: -1 }, 'invalid_value'],
    [{ unit: 'Rohwert' }, 'unit_mismatch'],
    [{ unit: 'kW' }, 'unit_mismatch'],
    [{ unit: ' %' }, 'unit_mismatch'],
    [{ observed_at: '' }, 'invalid_time'],
    [{ age_seconds: NaN }, 'invalid_age'],
    [{ age_seconds: -1 }, 'invalid_age'],
    [{ age_seconds: 591 }, 'stale'],
    [{ fresh: false }, 'stale'],
  ];
  for (const [extra, reason] of cases) {
    const result = boilerDisplay(extra ? [observation(powerId, 70, extra)] : []);
    assert.deepEqual(result.evidence, { kind: 'none' }, reason);
    assert.equal(result.powerReason, reason);
    assert.equal(result.statusReason, 'no_observation');
  }
});

test('lokale Auswahl schlägt vorhandene Beobachtungen; abgewählte Quellen liefern keine Evidenz', () => {
  const signals = [observation(statusId, 0), observation(powerId, 80)];
  const powerOnly = boilerDisplay(signals, { selectedIds: new Set([powerId]) });
  assert.equal(powerOnly.evidence.kind, 'power');
  assert.equal(powerOnly.statusReason, 'not_selected');
  const neither = boilerDisplay(signals, { selectedIds: new Set() });
  assert.deepEqual(neither.evidence, { kind: 'none' });
  assert.equal(neither.statusReason, 'not_selected');
  assert.equal(neither.powerReason, 'not_selected');
  const noPower = boilerDisplay([observation(powerId, 80)], { selectedIds: new Set([statusId]) });
  assert.deepEqual(noPower.evidence, { kind: 'none' });
  assert.equal(noPower.powerReason, 'not_selected');
});

test('Browserzeit erhöht beide Quellenalter und überschreitet die Frischegrenze ohne neuen Empfang', () => {
  for (const id of [statusId, powerId]) {
    const signal = observation(id, 2, { age_seconds: 300 });
    const atBoundary = boilerDisplay([signal], { elapsedSeconds: 300 });
    assert.equal(atBoundary.evidence.kind, id === statusId ? 'status' : 'power');
    assert.equal(atBoundary.evidence.ageSeconds, 600);
    const expired = boilerDisplay([signal], { elapsedSeconds: 300.001 });
    assert.deepEqual(expired.evidence, { kind: 'none' });
    assert.equal(id === statusId ? expired.statusReason : expired.powerReason, 'stale');
    const unknownAge = boilerDisplay([signal], { elapsedSeconds: NaN });
    assert.deepEqual(unknownAge.evidence, { kind: 'none' });
    assert.equal(id === statusId ? unknownAge.statusReason : unknownAge.powerReason, 'invalid_age');
    const clockBackwards = boilerDisplay([signal], { elapsedSeconds: -100 });
    assert.equal(clockBackwards.evidence.ageSeconds, 300);
  }
});

test('neueste Fehlerbeobachtung ersetzt einen früheren Gutwert, auch für den Leistungsersatz', () => {
  const result = boilerDisplay([
    observation(statusId, 2), observation(powerId, 80),
    observation(statusId, null, { quality: 'invalid' }),
    observation(powerId, null, { quality: 'unavailable' }),
  ]);
  assert.deepEqual(result.evidence, { kind: 'none' });
  assert.equal(result.statusReason, 'invalid_quality');
  assert.equal(result.powerReason, 'unavailable');
});

test('API-Ausfall und initiales Laden sperren jeden aktuellen Befund mit und ohne Quellen', () => {
  for (const apiStatus of ['loading', 'error', 'degraded']) {
    for (const signals of [[], [observation(statusId, 2)], [observation(powerId, 80)],
      [observation(statusId, 0), observation(powerId, 80)]]) {
      for (const selectedIds of [new Set(), new Set([statusId, powerId])]) {
        const result = boilerDisplay(signals, { apiStatus, selectedIds });
        assert.deepEqual(result.evidence, { kind: 'none' });
        const reason = apiStatus === 'loading' ? 'api_loading' : 'api_unavailable';
        assert.equal(result.statusReason, reason);
        assert.equal(result.powerReason, reason);
      }
    }
  }
});

test('Statusband extrapoliert nicht und stellt Wechsel, Fehler und Abstände als unbekannt dar', () => {
  const points = [point(100, 2, 'Rohwert'), point(400, 0x8002, 'Rohwert'),
    point(700, 3, 'Rohwert'), point(1000, null, 'Rohwert', 'invalid'),
    point(1300, 3, 'Rohwert'), point(2200, 3, 'Rohwert'), point(2500, 3, 'Rohwert')];
  const bands = statusIntervals(points, origin, origin + 3000_000);
  assert.equal(bands[0].state, 'unknown');
  assert.equal(bands[0].end, origin + 100_000);
  assert.equal(bands[1].state, 'running');
  assert.equal(bands[2].state, 'unknown');
  assert.match(bands[2].reason, /Wechselbereich/);
  assert.equal(bands[3].state, 'unknown');
  assert.equal(bands[4].state, 'unknown');
  assert.equal(bands[5].state, 'unknown');
  assert.equal(bands[6].state, 'embers');
  assert.equal(bands.at(-1).state, 'unknown');
  assert.equal(bands.at(-1).end, origin + 3000_000);
  for (let i = 1; i < bands.length; i += 1) assert.equal(bands[i - 1].end, bands[i].start);
  assert.equal(bands.reduce((sum, band) => sum + band.end - band.start, 0), 3000_000);
});

test('Statusband kennt weder Rohwert-fremde Einheiten noch ungültige Statuswörter', () => {
  for (const points of [[point(0, 0), point(300, 0)], [point(0, 1, 'Rohwert'), point(300, 1, 'Rohwert')]]) {
    assert.ok(statusIntervals(points, origin, origin + 300_000).every((band) => band.state === 'unknown'));
  }
  assert.deepEqual(statusIntervals([], origin, origin + 600_000), [
    { start: origin, end: origin + 600_000, state: 'unknown', reason: 'Keine Statusbeobachtung' },
  ]);
});

test('Pufferschichtung bewahrt negative Differenzen und bildet nur exakt zeitgleiche Celsiuswerte', () => {
  const top = [point(0, 60), point(60, 30), point(120, 80), point(180, 50), point(240, 55, 'Rohwert')];
  const bottom = [point(0, 35), point(60, 35), point(121, 40), point(180, null, '°C', 'invalid'), point(240, 30)];
  const result = bufferDifference(top, bottom);
  assert.deepEqual(result.map(({ value }) => value), [25, -5, null, null, null, null]);
  assert.ok(result.every(({ unit }) => unit === 'K'));
  assert.ok(result.filter(({ value }) => value === null).every(({ quality }) => quality !== 'ok'));
});

test('Pufferschichtung nutzt die letzte Beobachtung je Zeitpunkt in API-Reihenfolge', () => {
  assert.equal(bufferDifference([point(0, 60), point(0, 65)], [point(0, 30), point(0, 35)])[0].value, 30);
  assert.equal(bufferDifference([point(0, 60), point(0, null, '°C', 'invalid')], [point(0, 35)])[0].value, null);
});

test('Gruppenregeln sind geordnet und unbekannte ausgewählte Kanäle bleiben enthalten', () => {
  assert.equal(signalGroup(definition('modbus.8280', { module_status: 'inactive' })), 'Inaktive Module');
  for (const code of ['8280', '1020', '1021', '1022', '1023']) assert.equal(signalGroup(definition(`modbus.${code}`)), 'Außen & Wetter');
  assert.equal(signalGroup(definition('modbus.100A')), 'Elektronik & Steuerung');
  assert.equal(signalGroup(definition('modbus.8020', { kind: 'device_time' })), 'Elektronik & Steuerung');
  for (const id of ['buffer.top_temperature', 'modbus.90A0', 'modbus.9100', 'modbus.950F']) assert.equal(signalGroup(definition(id)), 'Puffer');
  for (const code of ['8020', '82E0', '82E1', '8500']) assert.equal(signalGroup(definition(`modbus.${code}`)), 'Heizkreise');
  assert.equal(signalGroup(definition('unknown.selected')), 'Kessel & Verbrennung');
});

test('Presets bleiben an Auswahl gebunden, Schichtung braucht beide Fühler', () => {
  assert.deepEqual(availablePresets([]), []);
  assert.deepEqual(availablePresets(['buffer.top_temperature']).map(({ id }) => id), ['buffer', 'single']);
  assert.deepEqual(availablePresets(['buffer.top_temperature', 'buffer.bottom_temperature']).map(({ id }) => id), ['buffer', 'stratification', 'single']);
  assert.deepEqual(availablePresets(['modbus.1008', 'modbus.8040']).map(({ id }) => id), ['power', 'heating1', 'single']);
  assert.deepEqual(availablePresets(['modbus.1001']).map(({ id }) => id), ['single']);
});

test('Liniensegmente trennen Qualität, Einheitenwechsel und große Lücken ohne Nullersatz', () => {
  const points = [point(0, 1, 'Rohwert'), point(60, 2, 'Rohwert'), point(120, 3, '%'),
    point(180, null, '%', 'invalid'), point(240, 4, '%'), point(480, 5, '%'), point(540, 6, '%')];
  const segments = continuousSegments(points, 60);
  assert.deepEqual(segments.map(({ unit, points }) => [unit, points.map(({ value }) => value)]), [
    ['Rohwert', [1, 2]], ['%', [3]], ['%', [4]], ['%', [5, 6]],
  ]);
  assert.equal(continuousSegments([{ ...point(0, 4), unit: undefined }], 60)[0].unit, 'Einheit unbekannt');
  assert.equal(isStepped('measurement'), false);
  assert.equal(isStepped('derived'), false);
  for (const kind of ['counter', 'status', 'setting']) assert.equal(isStepped(kind), true);
});

test('Verdichtung erhält erste/letzte Punkte, Spitze, Tal und Originalreihenfolge je Zeitzelle', () => {
  const points = Array.from({ length: 10_000 }, (_, index) => point(index, index === 5432 ? 999 : index === 5433 ? -50 : 20));
  const reduced = downsampleSegment(points, origin, origin + 10_000_000, 10);
  assert.equal(reduced[0], points[0]);
  assert.equal(reduced.at(-1), points.at(-1));
  assert.ok(reduced.includes(points[5432]));
  assert.ok(reduced.includes(points[5433]));
  assert.ok(reduced.length <= 40);
  assert.ok(reduced.every((item, index) => index === 0 || Date.parse(reduced[index - 1].observed_at) < Date.parse(item.observed_at)));
  assert.ok(downsampleSegment(points, origin, origin + 10_000_000, 100_000).length <= 3200);
});

test('Verdichtung je Segment erhält Einzelpunkte und sämtliche Lückengrenzen', () => {
  const points = Array.from({ length: 1000 }, (_, index) => point(index * 60, 20));
  points[400] = point(400 * 60, null, '°C', 'invalid');
  points[402] = point(402 * 60, null, '°C', 'invalid');
  const segments = continuousSegments(points, 60);
  assert.equal(segments.length, 3);
  assert.equal(segments[1].points[0], points[401]);
  for (const segment of segments) {
    const reduced = downsampleSegment(segment.points, origin, origin + 60_000_000, 2);
    assert.equal(reduced[0], segment.points[0]);
    assert.equal(reduced.at(-1), segment.points.at(-1));
  }
});

test('Inspektion liefert Originalqualität/Einheit nur innerhalb halben Messintervalls', () => {
  const points = [point(0, 10), point(60, null, 'Rohwert', 'invalid'), point(600, 12)];
  assert.equal(nearestPoint(points, origin + 29_000, 60), points[0]);
  assert.equal(nearestPoint(points, origin + 61_000, 60), points[1]);
  assert.equal(nearestPoint(points, origin + 300_000, 60), undefined);
  assert.equal(nearestPoint(points, origin + 630_000, 60), points[2]);
  assert.equal(nearestPoint(points, origin + 630_001, 60), undefined);
});

test('Zeitzonenregeln erhalten die frühere Herbststunde und verweigern die Frühlingslücke', () => {
  assert.equal(localInputToUtc('2026-10-25T02:30', 'Europe/Vienna').toISOString(), '2026-10-25T00:30:00.000Z');
  assert.equal(localInputToUtc('2026-03-29T02:30', 'Europe/Vienna'), null);
});

test('vollständige 31-Tage-Pagination erhält späte Fehler und reduziert Metadaten pro Seite', async (t) => {
  const count = 44_640;
  const requests = [];
  t.mock.method(globalThis, 'fetch', async (input, init) => {
    const url = new URL(input, 'http://localhost');
    const offset = Number(url.searchParams.get('offset'));
    assert.equal(url.searchParams.get('limit'), '10000');
    assert.equal(url.searchParams.get('start'), new Date(origin).toISOString());
    assert.equal(url.searchParams.get('end'), new Date(origin + count * 60_000).toISOString());
    assert.ok(init.signal instanceof AbortSignal);
    requests.push(offset);
    const items = Array.from({ length: Math.min(10_000, count - offset) }, (_, index) => ({
      ...point((offset + index) * 60, offset + index === 30_000 ? null : 20, '°C', offset + index === 30_000 ? 'invalid' : 'ok'),
      raw_words: [20], provenance: 'not retained', error_code: offset + index === 30_000 ? 'invalid_temperature' : null,
    }));
    return new Response(JSON.stringify({ signal_id: 'boiler.temperature', total: count, offset, limit: 10000, items }));
  });
  const progress = [];
  const points = await loadHistory('boiler.temperature', origin, origin + count * 60_000, new AbortController().signal, (loaded, total) => progress.push([loaded, total]));
  assert.deepEqual(requests, [0, 10_000, 20_000, 30_000, 40_000]);
  assert.equal(points.length, count);
  assert.equal(points[0].observed_at, new Date(origin).toISOString());
  assert.equal(points.at(-1).observed_at, new Date(origin + (count - 1) * 60_000).toISOString());
  assert.equal(points[30_000].value, null);
  assert.equal(points[30_000].error_code, 'invalid_temperature');
  assert.equal('raw_words' in points[0], false);
  assert.equal('provenance' in points[0], false);
  assert.equal(continuousSegments(points, 60).length, 2);
  assert.deepEqual(progress.at(-1), [count, count]);
});

test('leere, sinkende, wachsende oder widersprüchliche Pagination ist kein fertiger Verlauf', async (t) => {
  for (const variation of ['empty', 'decreasing', 'increasing', 'offset', 'chronology']) {
    let page = 0;
    const mock = t.mock.method(globalThis, 'fetch', async () => {
      page += 1;
      const second = page > 1;
      return new Response(JSON.stringify({ signal_id: 'boiler.temperature', total: second && variation === 'decreasing' ? 1 : second && variation === 'increasing' ? 3 : 2,
        offset: second && variation !== 'offset' ? 1 : 0, limit: 10000,
        items: second && variation === 'empty' ? [] : [point(variation === 'chronology' ? (second ? 0 : 60) : (second ? 60 : 0), 20)] }));
    });
    await assert.rejects(loadHistory('boiler.temperature', origin, origin + 120_000, new AbortController().signal), /unvollständig/);
    mock.mock.restore();
  }
});

test('Abbruch verhindert weitere Seiten und die Übernahme einer verspäteten Antwort', async (t) => {
  const controller = new AbortController();
  let calls = 0;
  t.mock.method(globalThis, 'fetch', async () => {
    calls += 1;
    controller.abort();
    return new Response(JSON.stringify({ signal_id: 'boiler.temperature', total: 2, offset: 0, limit: 10000, items: [point(0, 20)] }));
  });
  await assert.rejects(loadHistory('boiler.temperature', origin, origin + 120_000, controller.signal), { name: 'AbortError' });
  assert.equal(calls, 1);
});

test('Unplausible Werte werden als Marker geliefert und nie in Linien verbunden', () => {
  const points = [point(0, 50), point(60, 110, '°C', 'invalid'), point(120, 51), point(180, null, '°C', 'invalid')];
  assert.deepEqual(implausiblePoints(points).map(({ value }) => value), [110]);
  assert.deepEqual(continuousSegments(points, 60).map(({ points }) => points.map(({ value }) => value)), [[50], [51]]);
});
