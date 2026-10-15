import { StrictMode, useEffect, useState } from 'react';
import { createRoot } from 'react-dom/client';
import './style.css';

type CollectorStatus = {
  state: string;
  reason: string | null;
  reconnect_attempts: number;
  reconnect_attempt_limit: number;
  next_action_at: string | null;
  next_action: string | null;
};

type Overview = {
  apiAvailable: boolean;
  collectorEnabled: boolean;
  hostConfigured: boolean;
  collector: CollectorStatus;
};

function App() {
  const [overview, setOverview] = useState<Overview | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    Promise.all([
      fetch('/api/health').then((response) => {
        if (!response.ok) throw new Error('API health request failed');
        return response.json() as Promise<{ status: string }>;
      }),
      fetch('/api/config').then((response) => {
        if (!response.ok) throw new Error('Configuration request failed');
        return response.json() as Promise<{
          collector_enabled: boolean;
          host_configured: boolean;
        }>;
      }),
      fetch('/api/collector/status').then((response) => {
        if (!response.ok) throw new Error('Collector status request failed');
        return response.json() as Promise<CollectorStatus>;
      }),
    ])
      .then(([health, config, collector]) => {
        setOverview({
          apiAvailable: health.status === 'ok',
          collectorEnabled: config.collector_enabled,
          hostConfigured: config.host_configured,
          collector,
        });
      })
      .catch(() => setFailed(true));
  }, []);

  const apiStatus = overview
    ? overview.apiAvailable
      ? 'erreichbar'
      : 'nicht erreichbar'
    : failed
      ? 'nicht erreichbar'
      : 'wird geprüft';
  const hostStatus = overview?.hostConfigured ? 'konfiguriert' : 'nicht konfiguriert';
  const collector = overview?.collector;

  return (
    <main>
      <h1>Sommerauer Monitor</h1>
      <p>API: {apiStatus}</p>
      <p>Modbus-Ziel: {hostStatus}</p>
      <section aria-labelledby="collector-heading">
        <h2 id="collector-heading">Datenerfassung</h2>
        <p>Zustand: {collector?.state ?? (failed ? 'nicht verfügbar' : 'wird geprüft')}</p>
        <p>Fehlergrund: {collector?.reason ?? 'Keiner gespeichert'}</p>
        <p>
          Wiederaufnahmeversuche: {collector?.reconnect_attempts ?? 0} /{' '}
          {collector?.reconnect_attempt_limit ?? 5}
        </p>
        <p>Nächste Aktion: {collector?.next_action ?? 'Status wird geladen'}</p>
        <p>
          Nächster Versuch:{' '}
          {collector?.next_action_at
            ? new Date(collector.next_action_at).toLocaleString()
            : 'nicht geplant'}
        </p>
      </section>
    </main>
  );
}


createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
