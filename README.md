# Sommerauer Monitor

Geplante lokale Monitoring-App für eine Sommerauer-Pelletsheizung: Modbus-Datenlogging,
dauerhafte Minutenhistorie und Web-Dashboard auf Unraid.

**Stand 15.10.2026: Projektgrundlage, bestätigtes Kernprofil/Decoder, strikter FC03-Lesetransport,
Loopback-Simulator, SQLite-Speicherung, zentraler Sammler, begrenzte Wiederaufnahme,
lesende API, Dashboard und Offline-Ende-zu-Ende-Abnahme (#12) umgesetzt.**
Die gestufte lokale Kernregister-Abnahme (#13) ist mit endlichen FC03-Läufen
und vom Betreiber bestätigtem Displayabgleich belegt
([Ergebnisse](reports/RESULTS.md), [Betriebsplan](docs/INBETRIEBNAHME.md)).
Offen: tatsächliches Unraid-Deployment und Langzeitbetrieb. Kein Dauerbetrieb aktiviert.

## Hier mit der Arbeit beginnen

1. [AGENTS.md](AGENTS.md): Arbeitsrahmen und Grenze für Geräteänderungen.
2. [Plan](docs/PLAN.md) und [Entscheidungen](docs/ENTSCHEIDUNGEN.md).
3. [Roadmap mit Issues](docs/ROADMAP.md) und [nächste Schritte](NEXT_STEPS.md).
4. Für das gewählte Issue die dort verlinkten Fachunterlagen lesen.

Erste Version: Kesseltemperatur, Puffer oben/unten und Anlagen-Betriebszähler;
weitere Register nach Prüfung. Alle Minutenmessungen bleiben dauerhaft erhalten.
Bei reinen Verbindungsfehlern begrenzte Wiederverbindung, bei Protokoll-/Datenfehlern Stopp.
Messlücken und Datenalter bleiben sichtbar.

Vorgesehener Aufbau: Python/FastAPI, SQLite, React/TypeScript, ein Docker-Container.
Ein zentraler Sammler; Browser und später Home Assistant verwenden seine Daten.
Unraid 7.3.2, Zugang im Heimnetz/Tailscale. Deployment übernimmt der Betreiber.

## Lokale Entwicklung

Voraussetzungen (verbindlich): CPython 3.12.9, `uv` 0.12.2, Node.js 26.x und npm 12.x.
Python- und Frontend-Abhängigkeiten sind in `uv.lock` bzw. `package-lock.json`
festgehalten.

```sh
uv sync --locked
npm ci
uv run pytest
uv run ruff check .
npm run build
```

Die API startet lokal mit `uv run uvicorn backend.main:app --host 127.0.0.1 --port 8000`.
Für die UI in einem zweiten Terminal `npm run dev` ausführen; Vite liefert die Oberfläche
auf `http://127.0.0.1:5173` und leitet `/api` an die API weiter. Der Erststart hat keinen
Modbus-Host und `COLLECTOR_ENABLED=false`; die App führt keine Gerätezugriffe aus.

### Gesamttest in VS Code (nur Simulator)

Abhängigkeiten einmal mit `uv sync --locked` und `npm ci` installieren. In Run and
Debug `Sommerauer Monitor: Offline-Gesamttest` auswählen und starten. VS Code wartet,
bis der Loopback-Simulator auf `127.0.0.1:1502` bereit ist, startet dann API und
Vite-Dashboard und öffnet die von Vite gemeldete URL (standardmäßig `http://127.0.0.1:5173`;
falls belegt, den nächsten freien Port). Die Launch-Konfiguration erzwingt den Simulator
als Ziel, aktiviert den Sammler und speichert Testdaten getrennt unter
`data/vscode-simulator/`; dort sichtbare Werte sind synthetisch. Ports 1502 und 8000
müssen frei sein. Nach Debug-Stopp den weiterlaufenden Simulator im zugehörigen
Task-Terminal mit Ctrl+C beenden.
Lokale Einstellungen stehen in `.env`, niemals echte Hostnamen oder Zugangsdaten in
Beispiele, Logs oder CI übernehmen.

`/api/config` enthält weder Hostwert noch lokalen Datenpfad. Der Host wird nur als
gesetzt/nicht gesetzt ausgewiesen. Der enge FC03-Client und Offline-Simulator sind
unter `backend/modbus.py` und `backend/modbus_simulator.py` verfügbar; der
Anwendungsstart startet weder Sammler noch Simulator und führt keine Gerätezugriffe aus.
Den Simulator lokal mit `uv run python -m backend.modbus_simulator` starten
(Standardbindung `127.0.0.1:1502`); Faults sind per `--fault` wählbar.

## Docker und Unraid

Das lokale Containerpaket und die Anleitung stehen in [docs/UNRAID.md](docs/UNRAID.md).
Mit `cp .env.example .env` lokale Defaults anlegen, dort einen beschreibbaren
`DATA_PATH` setzen und mit `docker compose up --build -d` lokal bauen. Der Container
läuft als UID 99/GID 100, bindet Port 8000, persistiert ausschließlich in `/data`
und startet ohne Hostadresse oder aktivierte Erfassung. `/api/version` meldet
Buildversion und Revision. Pull Requests prüfen jetzt einen `linux/amd64`-Image-Build
ohne Push; ausschließlich freigegebene Versionstags können nach Offline-Prüfungen
ein GHCR-Image veröffentlichen ([Strategie und Sperren](docs/UNRAID.md#github-image-build-und-veröffentlichungsgrenze)).
Der Unraid-Template-Imageverweis ist weiterhin ein erwarteter Registrypfad,
kein veröffentlichtes Image; es gibt noch keinen Release-Tag. Lokale
Docker-Prüfungen belegen keine Installation auf Unraid oder Gerätefunktion.

Lizenz: eigener App-Code unter [MIT](LICENSE), vom Betreiber am 15.10.2026 bestätigt.

## Dokumentation

| Dokument | Inhalt |
|---|---|
| [Architektur](docs/ARCHITEKTUR.md) | Bausteine, Zuständigkeiten und Konfiguration |
| [Modbus](docs/MODBUS.md) | Offsets, Decoder, Prüfstatus und bekannte Grenzen |
| [Registerkatalog](config/register_catalog.json) | Alle 199 dokumentierten Projektzuordnungen; kein aktives Pollingprofil |
| [Datenmodell](docs/DATENMODELL.md) | Signalnamen, Historie, Qualität, Zeitstempel, API-Vertrag |
| [Fehlerverhalten](docs/FEHLERVERHALTEN.md) | Zustände, Wiederverbindungsbudget und harter Stopp |
| [Inbetriebnahme](docs/INBETRIEBNAHME.md) | Begrenzte Lesetests und Übergang zum Dauerbetrieb |
| [Unraid](docs/UNRAID.md) | Anforderungen an Container, Sicherung und Releases |
| [Ausbau](docs/AUSBAU.md) | MQTT, Solarthermie und externe Prognose |
| [START-Rückfall](docs/START_RUECKFALL.md) | Noch offener Rückfall und Grenze späterer Steuerung |
| [Quellen](docs/QUELLEN.md) | Herkunft, Prüfsummen und Nachweisgrenzen |

Private Netzwerkadresse, Zugangsdaten, echte Messprotokolle, Fotos, Firmwareexporte und
rekonstruierter Herstellercode gehören nicht in dieses Repository. Der Katalog ist
eine sachliche, bereinigte Dokumentation der projektspezifischen Zuordnung und kein
universeller Sommerauer-Registerplan. Beispiele unter `examples/` sind synthetisch.

## Lizenz

Eigener App-Code steht unter der [MIT-Lizenz](LICENSE).
Herstellerdateien und rekonstruierter Herstellercode sind davon nicht erfasst;
Abhängigkeiten behalten ihre jeweiligen Lizenzen.
