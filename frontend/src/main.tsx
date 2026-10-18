import { StrictMode, useEffect, useRef, useState } from 'react';
import { createRoot } from 'react-dom/client';
import Dashboard from './Dashboard';
import type { DashboardView } from './dashboard';
import LoggingConfig from './LoggingConfig';
import './style.css';

type Theme = 'light' | 'dark';
const links: { hash: string; label: string; view?: DashboardView }[] = [
  { hash: '#/', label: 'Übersicht', view: 'overview' },
  { hash: '#/analyse', label: 'Analyse', view: 'analysis' },
  { hash: '#/werte', label: 'Alle Werte', view: 'values' },
  { hash: '#/einstellungen', label: 'Einstellungen', view: 'settings' },
  { hash: '#/modbus', label: 'Modbus-Aufzeichnung' },
];
function savedTheme(): Theme | null {
  try {
    const saved = localStorage.getItem('dashboard-theme');
    return saved === 'light' || saved === 'dark' ? saved : null;
  } catch { return null; }
}
function Navigation() {
  const [hash, setHash] = useState(() => window.location.hash);
  const [explicitTheme, setExplicitTheme] = useState<Theme | null>(savedTheme);
  const [systemDark, setSystemDark] = useState(() => window.matchMedia('(prefers-color-scheme: dark)').matches);
  const theme = explicitTheme || (systemDark ? 'dark' : 'light');
  const route = links.find((link) => link.hash === hash) || links[0];
  const focusAfterNavigation = useRef(false);
  useEffect(() => {
    const navigate = () => { focusAfterNavigation.current = true; setHash(window.location.hash); };
    window.addEventListener('hashchange', navigate);
    const media = window.matchMedia('(prefers-color-scheme: dark)');
    const changed = () => setSystemDark(media.matches);
    media.addEventListener('change', changed);
    return () => { window.removeEventListener('hashchange', navigate); media.removeEventListener('change', changed); };
  }, []);
  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    document.documentElement.style.colorScheme = theme;
  }, [theme]);
  useEffect(() => {
    if (!focusAfterNavigation.current) return;
    focusAfterNavigation.current = false;
    const heading = document.querySelector<HTMLElement>('[data-active="true"] main h1');
    if (heading) { heading.tabIndex = -1; heading.focus(); }
  }, [hash]);
  const toggleTheme = () => {
    const next = theme === 'dark' ? 'light' : 'dark';
    setExplicitTheme(next);
    try { localStorage.setItem('dashboard-theme', next); } catch { /* Lokale Anzeige bleibt auch ohne Storage bedienbar. */ }
  };
  const modbus = route.hash === '#/modbus';
  return <>
    <header className="site-header">
      <div className="brand"><a href="#/">Sommerauer <span>Monitor</span></a><p>Lokale Energiezentrale</p></div>
      <button className="button secondary theme-toggle" aria-label="Dunkelmodus" aria-pressed={theme === 'dark'} title={theme === 'dark' ? 'Zum Hellmodus wechseln' : 'Zum Dunkelmodus wechseln'} onClick={toggleTheme}>
        <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
          {theme === 'dark' ? <>
            <circle cx="12" cy="12" r="4" />
            <path d="M12 2v2m0 16v2M2 12h2m16 0h2M4.93 4.93l1.42 1.42m11.3 11.3 1.42 1.42M4.93 19.07l1.42-1.42m11.3-11.3 1.42-1.42" />
          </> : <path d="M20.9 13.1A9 9 0 0 1 10.9 3.1 9 9 0 1 0 20.9 13.1Z" />}
        </svg>
      </button>
      <nav className="app-navigation" aria-label="Hauptnavigation">{links.map((link) => <a key={link.hash} href={link.hash} aria-current={route.hash === link.hash ? 'page' : undefined}>{link.label}</a>)}</nav>
    </header>
    <div id="global-alerts" className="global-alerts" />
    <div hidden={modbus} data-active={!modbus}><Dashboard view={route.view || 'settings'} /></div>
    <div hidden={!modbus} data-active={modbus}><LoggingConfig /></div>
  </>;
}
createRoot(document.getElementById('root')!).render(<StrictMode><Navigation /></StrictMode>);
