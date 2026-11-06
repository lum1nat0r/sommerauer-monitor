import { useState } from 'react';
import type { FormEvent } from 'react';
import { requestJson } from './dashboard';
import type { PelletDelivery, PelletStatus } from './dashboard';

const headers = { 'Content-Type': 'application/json', 'X-Requested-With': 'SommerauerMonitor' };
const number = (value: number) => value.toLocaleString('de-AT', { maximumFractionDigits: 2 });

export default function PelletDeliveries({ pellets, onChanged }: { pellets: PelletStatus; onChanged: () => Promise<void> }) {
  const [notice, setNotice] = useState('');
  const [busy, setBusy] = useState(false);
  const [editing, setEditing] = useState<PelletDelivery | null>(null);

  async function send(url: string, init: RequestInit, success: string) {
    if (busy) return false;
    setBusy(true);
    setNotice('');
    try {
      await requestJson(url, { ...init, headers });
      await onChanged();
      setNotice(success);
      return true;
    } catch (error) {
      setNotice(error instanceof Error && error.message === 'HTTP 409'
        ? 'Für diesen Betriebsstundenstand gibt es bereits eine Lieferung.'
        : 'Speichern fehlgeschlagen. Bitte Eingaben prüfen.');
      return false;
    } finally {
      setBusy(false);
    }
  }

  async function addDelivery(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const data = new FormData(form);
    const price = data.get('price_eur_per_tonne');
    const saved = await send(editing ? `/api/pellets/deliveries/${encodeURIComponent(editing.delivery_id)}` : '/api/pellets/deliveries', {
      method: editing ? 'PUT' : 'POST',
      body: JSON.stringify({
        delivered_on: data.get('delivered_on'),
        operating_hours: Number(data.get('operating_hours')),
        tonnes: Number(data.get('tonnes')),
        supplier: data.get('supplier') || null,
        price_eur_per_tonne: price ? Number(price) : null,
      }),
    }, 'Lieferung gespeichert.');
    if (saved) { form.reset(); setEditing(null); }
  }

  async function saveCapacity(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const capacity = Number(new FormData(event.currentTarget).get('capacity_tonnes'));
    await send('/api/pellets/tank', { method: 'PUT', body: JSON.stringify({ capacity_tonnes: capacity }) }, 'Tankkapazität gespeichert.');
  }

  async function remove(id: string, label: string) {
    if (!window.confirm(`Lieferung vom ${label} löschen?`)) return;
    const deleted = await send(`/api/pellets/deliveries/${encodeURIComponent(id)}`, { method: 'DELETE' }, 'Lieferung gelöscht.');
    if (deleted && editing?.delivery_id === id) setEditing(null);
  }

  return <section className="settings-panel" aria-labelledby="pellets-title">
    <h2 id="pellets-title" className="visually-hidden">Pelletlieferungen</h2>
    <p className="muted">Verbrauch und Füllstand sind Schätzungen aus diesen Eingaben und dem Anlagen-Betriebszähler, keine Messung. Jede Lieferung gilt als Befüllung bis randvoll.</p>
    <form key={pellets.tank_capacity_tonnes} onSubmit={(event) => void saveCapacity(event)}>
      <label>Tankkapazität (t)<input name="capacity_tonnes" type="number" min="0" step="any" required defaultValue={pellets.tank_capacity_tonnes ?? ''} /></label>
      <button className="button secondary" type="submit" disabled={busy}>Kapazität speichern</button>
    </form>
    <h3>{editing ? `Lieferung vom ${editing.delivered_on.split('-').reverse().join('.')} bearbeiten` : 'Neue Lieferung'}</h3>
    <form key={editing?.delivery_id ?? 'new'} onSubmit={(event) => void addDelivery(event)}>
      <label>Datum<input name="delivered_on" type="date" required autoFocus={editing !== null} defaultValue={editing?.delivered_on} /></label>
      <label>Betriebsstunden (h)<input name="operating_hours" type="number" min="0" step="any" required defaultValue={editing?.operating_hours} placeholder={pellets.operating_hours === null ? undefined : `aktuell ${Math.round(pellets.operating_hours)}`} /></label>
      <label>Menge (t)<input name="tonnes" type="number" min="0" step="any" required defaultValue={editing?.tonnes} /></label>
      <label>Lieferant (optional)<input name="supplier" type="text" maxLength={100} defaultValue={editing?.supplier ?? undefined} /></label>
      <label>Preis in €/t (optional)<input name="price_eur_per_tonne" type="number" min="0" step="any" defaultValue={editing?.price_eur_per_tonne ?? undefined} /></label>
      <button className="button primary" type="submit" disabled={busy}>{editing ? 'Änderungen speichern' : 'Lieferung speichern'}</button>
      {editing && <button className="button secondary" type="button" disabled={busy} onClick={() => setEditing(null)}>Abbrechen</button>}
    </form>
    {notice && <p className="notice" role="status">{notice}</p>}
    {pellets.deliveries.length > 0 && <div className="logging-table-wrap" role="region" aria-label="Lieferungen, horizontal scrollbar" tabIndex={0}><table className="logging-table">
      <thead><tr><th scope="col">Datum</th><th scope="col">Betriebsstunden</th><th scope="col">Menge</th><th scope="col">Lieferant</th><th scope="col">€/t</th><th scope="col"><span className="visually-hidden">Aktion</span></th></tr></thead>
      <tbody>{pellets.deliveries.map((item) => {
        const date = item.delivered_on.split('-').reverse().join('.');
        return <tr key={item.delivery_id}><td>{date}</td><td>{number(item.operating_hours)} h</td><td>{number(item.tonnes)} t</td><td>{item.supplier ?? '—'}</td><td>{item.price_eur_per_tonne === null ? '—' : number(item.price_eur_per_tonne)}</td>
          <td><button type="button" className="button secondary" disabled={busy} onClick={() => { setNotice(''); setEditing(item); }}>Bearbeiten</button> <button type="button" className="button secondary" disabled={busy} onClick={() => void remove(item.delivery_id, date)}>Löschen</button></td></tr>;
      })}</tbody>
    </table></div>}
  </section>;
}
