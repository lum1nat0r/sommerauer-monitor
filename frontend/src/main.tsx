import { StrictMode, useEffect, useState } from 'react';
import { createRoot } from 'react-dom/client';
import './style.css';

type Overview = {
  apiAvailable: boolean;
  collectorEnabled: boolean;
  hostConfigured: boolean;
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
    ])
      .then(([health, config]) => {
        setOverview({
          apiAvailable: health.status === 'ok',
          collectorEnabled: config.collector_enabled,
          hostConfigured: config.host_configured,
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
  const collectorStatus = overview?.collectorEnabled ? 'aktiviert' : 'deaktiviert';
  const hostStatus = overview?.hostConfigured ? 'konfiguriert' : 'nicht konfiguriert';

  return (
    <main>
      <h1>Sommerauer Monitor</h1>
      <p>API: {apiStatus}</p>
      <p>Erfassung: {collectorStatus}</p>
      <p>Modbus-Ziel: {hostStatus}</p>
      <p>
        Datenerfassung und Messwertspeicherung sind in dieser Projektphase noch nicht
        implementiert.
      </p>
    </main>
  );
}

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
