# Entscheidungen und offene Punkte

Stand 19.10.2026; Herkunft jeweils angegeben.

Nachtrag 20.10.2026 (Betreiberauftrag): separates deploybares Werkzeug für einen
begrenzten START-/SOLL-Test (`9040`/`9020`) entwickeln. Gewünscht sind echte Tests
nach Deployment. Die Schreibkodierung wurde im bereitgestellten rekonstruierten
Export erneut statisch geprüft; Geräteversionsabgleich, konkrete Werte und
Gerätefreigabe stehen noch aus. Die Monitoring-App bleibt lesend. Rückstellung
durch den Testclient ist aktive Gegenänderung und keine nachgewiesene automatische
Gerätefunktion.

| Entscheidung | Stand/Herkunft |
|---|---|
| Version 1 = Modbus-Logging + eigenes Dashboard | Nutzerauftrag |
| Alle Minutenwerte dauerhaft | Explizite Nutzerantwort |
| Unbegrenztes Polling bei reinen Verbindungsfehlern im bestehenden Intervall; harte Fehlerstopps bleiben | Expliziter Betreiberauftrag vom 19.10.2026; ersetzt die frühere begrenzte Wiederverbindung |
| Weitere Werte nach schrittweiser Prüfung | Nutzerantwort; kein automatischer Vollscan |
| Unraid 7.3.2; Home Assistant und MQTT vorhanden | Nutzerangabe |
| Zugriff Heimnetz/Tailscale; kein Tailscale-Aufbau im Auftrag | Nutzerantwort |
| START/SOLL später, keine Manipulation echter Messwerte | Explizite Nutzerantwort |
| Externes/späteres Prognosemodell | Nutzerantwort |
| Öffentliches Repo `sommerauer-monitor` und umsetzbare Issues | Expliziter Folgeauftrag |
| Python/FastAPI + SQLite + React/TypeScript in einem Container | Architekturvorschlag im positiv aufgenommenen Plan; bei Umsetzung konkretisieren |
| 60 s für Kernblöcke; Zusatzwerte langsamer | Technischer Entwurf, Lastvorgaben einhalten |
| Kein Retry-Backoff oder Fünf-Versuche-Limit; 60 s Kern/300 s Zusatz, endliche Prüfläufe und Read-to-clear-Schutz unverändert | Betreiberauftrag vom 19.10.2026; [Fehlervertrag](FEHLERVERHALTEN.md) |

| Projektgrundlage | Entscheidung / Herkunft |
|---|---|
| Python-Laufzeit CPython 3.12.9; Abhängigkeiten in `uv.lock` | Konservative unterstützte Laufzeit, eingefrorener reproduzierbarer Satz |
| Node.js 26.x und npm 12.x; Frontend-Abhängigkeiten in `package-lock.json` | Verbindliche Entwicklungs- und CI-Laufzeiten |
| Erststart ohne Host, Erfassung standardmäßig deaktiviert; Host in API-Ausgabe redigiert | Offline-sichere Projektkonfiguration; keine Gerätezugriffe implementiert |
| CI nur mit synthetischen/in-process Tests und Frontend-Build | GitHub Actions workflow `.github/workflows/ci.yml`; keine Anlagenzugriffe/Secrets |
| Image-Build/Registry: PR-Build ohne Push, kein `main`-Image, Release nur aus `vX.Y.Z` nach Offline-Prüfungen | Arbeitsentscheidung für Issue #14; Release selbst bleibt bis Lizenz-/Abnahmefreigabe aus |
| Lizenz für eigenen App-Code: MIT, siehe `LICENSE`; Herstellerdateien und Abhängigkeiten nicht umlizenziert | Explizite Betreiberbestätigung am 15.10.2026 |

Noch offen: Wahl einer Modbus-Bibliothek vs. kleinem
eigenem Lesetransport, Zugriffsschutz der lokalen Verwaltungsfunktionen,
Unraid-Poolpfad/UID/GID, geprüfte Einheiten und Grenzen der Zusatzregister.
Die Foundation-Abhängigkeiten sind in `pyproject.toml` und `package.json` exakt
fixiert; konkrete Modbus-Abhängigkeit folgt erst im Transport-Issue.

Später offen: digitale FP-2-Anbindung, Kollektordaten, Modellgüte, X Minuten bis
Rückfall, Temperatur-/Versorgungsgrenzen, geeigneter autonomer Rückfallmechanismus.
Diese Punkte blockieren Version 1 nicht.

Nicht unterstellt: laufender Brenner aus Betriebszähler, thermische kW aus interner
Leistung, Solarertrag aus zwei Puffertemperaturen, unabhängige temporäre START-Vorgabe,
Herstellerfreigabe der selbst gewählten Pollinggrenzen.
