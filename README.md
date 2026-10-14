# Sommerauer Monitor

Geplante lokale Monitoring-App für eine Sommerauer-Pelletsheizung: Modbus-Datenlogging,
dauerhafte Minutenhistorie und Web-Dashboard auf Unraid.

**Stand 14.10.2026: Projektgrundlage, offlinefähiger API/UI-Startpunkt sowie das
bestätigte Kernprofil mit reinen Decodern umgesetzt. Erfassung, Speicherung,
Modbus-Transport, Docker-Image und Geräteprüfung sind noch nicht implementiert.**

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

Voraussetzungen: CPython 3.12.9, `uv` 0.12.2, Node.js 22.14.0 und npm 10.9.2.
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
Lokale Einstellungen stehen in `.env`, niemals echte Hostnamen oder Zugangsdaten in
Beispiele, Logs oder CI übernehmen.

`/api/config` enthält weder Hostwert noch lokalen Datenpfad. Der Host wird nur als
gesetzt/nicht gesetzt ausgewiesen.
Ein aktivierter Sammler ohne `MODBUS_HOST` ist ungültige Konfiguration. Ein Sammler
oder Modbus-Transport ist in diesem Arbeitsschritt noch nicht implementiert.

Lizenz: noch nicht festgelegt. Vor einem Software-Release muss der Betreiber entscheiden;
der MIT-Vorschlag ist keine erteilte Lizenz.

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

Eine Lizenz ist noch nicht festgelegt. MIT ist der bisherige Vorschlag für eigenen
App-Code; vor dem ersten Software-Release entscheiden und dokumentieren.
Öffentliche Sichtbarkeit allein ist keine zusätzliche Lizenz für Herstellerdateien.
