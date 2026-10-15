import { useCallback, useEffect, useMemo, useState } from 'react';
import { diagnosticError, requestJson } from './api';
import { ageLabel, formatDate } from './format';
import ControlPlans from './ControlPlans';
import ReadRuns from './ReadRuns';

type Evidence = {
  run_id: string; completed_at: string; source: 'device' | 'simulator'; target_changed: boolean;
  request: { raw_words: number[] | null; interpretation_status: string; error_class: string | null;
    decoded_signals: { signal_id: string; value: number; unit: string }[] };
};
type Entry = {
  register_id: string; csv_label: string; offset_zero_based: number; sl_code_hex: string;
  in_user_reported_imported_profile: boolean; evidence_status: string; meaning: string | null;
  unit: string | null; decoding: string | null; read_support: string; write_support: string;
  latest_diagnostic: Evidence | null;
};
type Candidate = { candidate_id: string; label: string; sl_code_hex: string; potential_offset: number;
  source: string; read_block: null; write_support: string; limitation: string };
type Catalog = { catalog_sha256: string; source: 'device' | 'simulator'; blockade: string | null;
  entries: Entry[]; control_candidates: Candidate[] };

export default function Diagnostics({ timeZone, onCollectorChange }: { timeZone: string; onCollectorChange: () => Promise<void> }) {
  const [catalog, setCatalog] = useState<Catalog | null>(null);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [filter, setFilter] = useState('all');
  const [page, setPage] = useState(0);
  const [selected, setSelected] = useState<string[]>([]);
  const [detailId, setDetailId] = useState<string | null>(null);
  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      setCatalog(await requestJson<Catalog>('/api/diagnostics/catalog'));
      setError('');
    } catch (failure) { setError(diagnosticError(failure)); }
    finally { setLoading(false); }
  }, []);
  useEffect(() => { void refresh(); }, [refresh]);
  const entries = useMemo(() => {
    const query = search.trim().toLowerCase().replace(/^0x/, '');
    return (catalog?.entries ?? []).filter((entry) =>
      (!query || entry.csv_label.toLowerCase().includes(query) || String(entry.offset_zero_based).includes(query) || entry.sl_code_hex.toLowerCase().includes(query)) &&
      (filter === 'all' || (filter === 'confirmed' && entry.read_support === 'confirmed_core') ||
        (filter === 'documented' && entry.read_support === 'documented_raw') || (filter === 'result' && entry.latest_diagnostic !== null)));
  }, [catalog, search, filter]);
  const maxPage = Math.max(0, Math.ceil(entries.length / 50) - 1);
  const currentPage = Math.min(page, maxPage);
  const entry = catalog?.entries.find((item) => item.register_id === detailId);
  const candidate = catalog?.control_candidates.find((item) => item.candidate_id === detailId);
  const latest = entry?.latest_diagnostic;
  return <div className="diagnostics">
    <section className="diagnostics-panel" aria-labelledby="diagnostics-title">
      <div className="section-heading"><h2 id="diagnostics-title">Registerdiagnose</h2><button className="button secondary" disabled={loading} onClick={() => void refresh()}>Katalog neu laden</button></div>
      <p>199 dokumentierte Projektzuordnungen, kein vollständiges Herstellerregisterverzeichnis. Kein Vollscan, keine automatische Profilaktivierung und keine Schreibfunktion.</p>
      <p className="muted">LAN/Tailscale und Same-Origin sind keine Benutzeridentität und keine Geräteänderungsfreigabe.</p>
      {loading && <p role="status">Katalog wird geladen.</p>}
      {error && <p className="alert danger" role="alert">{error} Bereits geladene Belege bleiben sichtbar und können veraltet sein.</p>}
      {catalog && <>
        <dl className="diagnostics-meta"><dt>Aktuelle Quelle</dt><dd>{catalog.source === 'simulator' ? 'Simulator, synthetisch' : 'Anlage-aktuell (Gerät)'}</dd><dt>Kataloghash</dt><dd><code>{catalog.catalog_sha256}</code></dd></dl>
        {catalog.blockade && <p className="alert danger" role="alert">Diagnose-/Sammlerblockade: <strong>{catalog.blockade}</strong>. Aktive Läufe oder nicht quittierte Fehler verhindern weitere Planung/Starts. Keine automatische Quittierung.</p>}
        <div className="diagnostics-fields">
          <label>Register suchen<input type="search" value={search} placeholder="Bezeichnung, Dezimaloffset oder Hexcode" onChange={(event) => { setSearch(event.target.value); setPage(0); }} /></label>
          <label>Registerfilter<select value={filter} onChange={(event) => { setFilter(event.target.value); setPage(0); }}><option value="all">Alle</option><option value="confirmed">Bestätigt</option><option value="documented">Nur dokumentiert</option><option value="result">Mit Ergebnis</option></select></label>
        </div>
        <p className="muted">{entries.length} Treffer · {selected.length} Register ausgewählt. Auswahl bleibt bei Suche und Seitenwechsel erhalten; der Server löst daraus 1–3 Blöcke auf.</p>
        <div className="diagnostics-table-wrap" tabIndex={0} role="region" aria-label="Registertabelle, horizontal scrollbar"><table>
          <caption>Dokumentierte Register, höchstens 50 Einträge je Seite</caption>
          <thead><tr><th scope="col">Leseauswahl</th><th scope="col">Bezeichnung / Details</th><th scope="col">Offset / Hex</th><th scope="col">Belegstatus</th><th scope="col">Letztes Ergebnis</th></tr></thead>
          <tbody>{entries.slice(currentPage * 50, currentPage * 50 + 50).map((item) => <tr key={item.register_id}>
            <td><input type="checkbox" aria-label={`${item.csv_label} für Prüfplan auswählen`} checked={selected.includes(item.register_id)} onChange={(event) => setSelected((values) => event.target.checked ? [...values, item.register_id] : values.filter((id) => id !== item.register_id))} /></td>
            <th scope="row"><button className="button secondary" onClick={() => setDetailId(item.register_id)}>{item.csv_label}</button></th>
            <td>{item.offset_zero_based} / <code>{item.sl_code_hex}</code></td>
            <td>{item.read_support === 'confirmed_core' ? 'Historisch live/Display bestätigt' : 'Nur dokumentiert'}</td>
            <td>{item.latest_diagnostic ? <>{formatDate(item.latest_diagnostic.completed_at, timeZone)}<br />{item.latest_diagnostic.source === 'simulator' ? 'Simulator, synthetisch' : 'Gerätebeleg'}{item.latest_diagnostic.target_changed && <strong> · Abweichendes Ziel</strong>}</> : 'Kein gespeicherter Diagnosebeleg'}</td>
          </tr>)}</tbody>
        </table></div>
        {entries.length === 0 && <p role="status">Keine Register für diese Suche/Filterkombination.</p>}
        <div className="diagnostics-actions" aria-label="Katalogseiten"><button className="button secondary" disabled={currentPage === 0} onClick={() => setPage(currentPage - 1)}>Vorherige Registerseite</button><span>Seite {currentPage + 1} / {maxPage + 1}</span><button className="button secondary" disabled={currentPage === maxPage} onClick={() => setPage(currentPage + 1)}>Nächste Registerseite</button><button className="button secondary" disabled={!selected.length} onClick={() => setSelected([])}>Auswahl leeren</button></div>
        <h3>Separate Steuerkandidaten, nicht im FC03-Katalog</h3>
        <div className="diagnostics-actions">{catalog.control_candidates.map((item) => <button className="button secondary" key={item.candidate_id} onClick={() => setDetailId(item.candidate_id)}>{item.label} ({item.sl_code_hex})</button>)}</div>
        {(entry || candidate) && <article className="diagnostics-evidence" aria-label="Katalogdetails">
          <h3>{entry?.csv_label ?? candidate?.label}</h3>
          <dl className="diagnostics-meta">
            <dt>ID</dt><dd>{detailId}</dd><dt>Offset / Hex</dt><dd>{entry ? `${entry.offset_zero_based} / ${entry.sl_code_hex}` : `${candidate?.potential_offset} (nur potenziell) / ${candidate?.sl_code_hex}`}</dd>
            {entry && <><dt>Importstatus</dt><dd>{entry.in_user_reported_imported_profile ? 'Laut Betreiber im importierten Profil' : 'Nicht im berichteten Importprofil'}</dd><dt>Belegstatus</dt><dd>{entry.evidence_status}</dd><dt>Bedeutung</dt><dd>{entry.meaning ?? 'Interpretation ungeklärt'}</dd><dt>Einheit</dt><dd>{entry.unit ?? 'Einheit ungeklärt'}</dd><dt>Decoder</dt><dd>{entry.decoding ?? 'Decoder ungeklärt'}</dd><dt>read_support</dt><dd>{entry.read_support}</dd></>}
            {candidate && <><dt>Quelle</dt><dd>{candidate.source}</dd><dt>Leseblock</dt><dd>read_block=null, keine FC03-Auswahl</dd></>}
            <dt>write_support</dt><dd>unknown: Schreibfähigkeit unbekannt. „Soll“ ist kein Schreibnachweis.</dd>
          </dl>
          {candidate && <p className="alert">{candidate.limitation} Potenzielle Offsets sind keine freigegebenen Schreibadressen.</p>}
          {entry && (latest ? <div><h3>Neuester gespeicherter Diagnosebeleg</h3><p>{formatDate(latest.completed_at, timeZone)} · {ageLabel((Date.now() - Date.parse(latest.completed_at)) / 1000)} · <strong>{latest.source === 'simulator' ? 'Simulator, synthetisch' : 'Gerätebeleg'}</strong></p>{latest.target_changed && <p className="alert">Beleg stammt von abweichender Zielkonfiguration.</p>}<p>Gespeicherte Rohworte: {latest.request.raw_words?.map((word) => `${word} (0x${word.toString(16).toUpperCase().padStart(4, '0')})`).join(', ') ?? 'Keine Antwortworte'}</p>{latest.request.error_class && <p className="alert danger">{latest.request.error_class}</p>}{latest.request.interpretation_status === 'confirmed_core' ? <div className="diagnostics-interpretation"><h3>Gelieferte Kerninterpretation, kein neues Monitoringsignal</h3>{latest.request.decoded_signals.map((signal) => <p key={signal.signal_id}>{signal.signal_id}: {signal.value} {signal.unit}</p>)}</div> : <p>raw_only: Rohbeleg ohne Physikannahme, Einheit ungeklärt. Kein dekodierter Messwert.</p>}<p className="muted">Lauf {latest.run_id}. Alter Beleg, kein frisch abgefragter Livewert; Prüfstatus und Profil bleiben unverändert.</p></div> : <p>Noch kein gespeicherter Diagnosebeleg.</p>)}
        </article>}
      </>}
    </section>
    <ReadRuns registerIds={selected} timeZone={timeZone} onCollectorChange={onCollectorChange} onEvidenceChange={refresh} />
    <ControlPlans candidateId={detailId} timeZone={timeZone} />
  </div>;
}
