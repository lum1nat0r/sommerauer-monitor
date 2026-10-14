# Ergebnisse

## 14.10.2026 – Öffentliche Planungsübergabe

Plan, Architektur, Modbus-Faktenkatalog, Fehler-/Datenverträge, Inbetriebnahme,
Unraid-Anforderungen und spätere Erweiterungen dokumentiert. Nutzer beauftragte
Repository und Issues als Arbeitsgrundlage für spätere Agenten.

Keine App implementiert, kein Docker-Image gebaut, keine neuen Geräteanfragen,
keine Schreibbefehle oder Serveränderungen. Historische Live-Ergebnisse stammen
aus dem privaten Vorprojekt und sind in docs/QUELLEN.md als solche eingeordnet.

Lokale Übergabeprüfung: Katalog gegen private Faktenreferenz, relative Links,
JSON-Dateien und Ausschluss privater Artefakte. Noch keine App-Funktionstests.
Issue-Reihenfolge und aktuelle Links stehen in docs/ROADMAP.md.

## 14.10.2026 – Issue #2: Projektgrundlage und Offline-CI

Implementiert: Python/FastAPI und React/TypeScript-Projektstruktur, lokal geladene
Umgebungskonfiguration, standardmäßig deaktivierter Sammler, redigierte
Konfigurationsantwort, Python-/npm-Locks und GitHub Actions für ausschließlich
in-process API-Tests, statische Qualitätsprüfung und Frontend-Build. Die Anwendung
enthält noch keinen Modbus-Transport, Sammler, Datenbank oder Docker-Auslieferung.
MIT bleibt Vorschlag; keine Lizenzdatei angelegt. Issue und GitHub-Kommentare wurden
nicht verändert.

Tatsächlich geprüft:

- `uv lock`, `uv sync --locked`
- `uv run ruff check .` – bestanden.
- `uv run pytest` – 4 bestanden; ein DeprecationWarning aus Starlette/AnyIO.
- `npm install --package-lock-only`, `npm ci`, `npm run build` – Build bestanden.
- API via Uvicorn gestartet; `/api/health` lieferte `{"status":"ok"}`,
  `/api/config` meldete `host_configured=false` und `collector_enabled=false`.
- UI im Chromium-Browser auf Loopback geöffnet; API-Erreichbarkeit und die deaktivierte
  Erfassung ohne Hostkonfiguration sichtbar.
- Testfälle belegen Start ohne Host, Fehler bei aktivierter Erfassung ohne Host und
  dass die API-Antwort weder den gesetzten Hostwert noch den lokalen Datenpfad enthält.
- Suche nach IPv4-Adressen in Code, Konfiguration, CI und relevanter Dokumentation
  fand nur die dokumentierten Loopback-URLs für lokale Entwicklung.

Grenzen: Kein GitHub Actions-Lauf, Docker-Build, Unraid-/Hardwaretest oder
Gerätezugriff. Lokale Maschine stellte Node.js 26.7.0/npm 12.0.2 statt der für CI
festgelegten Node.js 22.14.0/npm 10.9.2 bereit; npm meldete Engine-Warnungen,
der lokale Build war dennoch erfolgreich. Der CI-Workflow pinnt die festgelegten
Versionen. Keine privaten Hostdaten oder Geräte-Secrets verwendet.

## 14.10.2026 – Issue #3: Geprüftes Kernprofil und reine Registerdecoder

Implementiert wurde `backend/registers.py` mit dem aktiven `core`-Profil für
4102/1, 28688/2 und 36864/2 sowie reinen signed16-, Temperatur- und
Betriebsminuten-Decodern. Resultate binden Rohworte, Offset, Quelle und
Profil-/Decoderversion. Ungültige Werte liefern typisierte Decode-Fehler;
Zusatzregister werden nicht interpretiert. Eine zeitbezogene Prüfung verwirft
Rückgänge und Zuwächse oberhalb der verstrichenen Minuten plus einer Minute
Quantisierungsreserve. Der Vollkatalog bleibt davon getrennt und alle Einträge
bleiben deaktiviert.

Tatsächlich geprüft:

- `uv run pytest` – 17 bestanden; ein Starlette/AnyIO-DeprecationWarning.
- `uv run ruff check .` – bestanden.
- Offline-Smoke über `uv run python -c`: signed16-Temperatur `-4`, Zählerübergang
  5759→5760 und Zeitplausibilität bestanden.

Kein Transport, Sammler, Datenbank, Live-Test oder Gerätezugriff gehört zu
diesem Issue; diese Teile bleiben offen.

## 14.10.2026 – Issue #4: Strikter FC03-Transport und Loopback-Simulator

`backend/modbus.py` implementiert einen eigenen synchronen TCP-Lesetransport ohne
Drittbibliothek und ohne Retries. Requests sind auf exakt die drei `core`-Blöcke,
FC03, Unit 255, höchstens zwei Register und maximal 3 Sekunden begrenzt. Antworten
werden als MBAP/PDU geprüft; Fehler tragen die Zahl empfangener Bytes. Timeout/
Verbindungsfehler ohne Bytes und unvollständige Teilantworten haben getrennte
Fehlerklassen. `backend/modbus_simulator.py` liefert deterministische synthetische
Antworten und Fehler und bindet ausschließlich an `127.0.0.1`; der App-Start
aktiviert weder Transport noch Simulator. Keine Gerätekommunikation.

Tatsächlich geprüft:

- `uv run pytest` – 31 bestanden; ein bestehendes Starlette/AnyIO-DeprecationWarning.
- `uv run ruff check .` – bestanden.
- Simulator-CLI auf `127.0.0.1:1502` gestartet und aus separatem Client-Aufruf
  tatsächlich abgefragt: Offset 4102 lieferte synthetisch
  `RegisterRead(offset=4102, words=(42,), unit_id=255, function_code=3)`.
- Neue synthetische Transporttests prüfen fragmentierte Antworten, Unit,
  Transaktion, Protokoll-ID, MBAP-Länge, Funktion, Byteanzahl, Modbus-Exception,
  Timeout ohne Antwortbytes, unvollständige Antwort, Profilgrenze und Loopbackbindung.

Grenzen: kein Sammler, kein automatischer Wiederaufnahme-Mechanismus und keine
Integration in den API-Lebenszyklus; kein Live-, Unraid- oder Hardwaretest.
Der Simulatorwert `42` ist ausschließlich synthetisch und kein Messwert.
Änderungen bleiben uncommitted; kein Commit/PR erstellt.
