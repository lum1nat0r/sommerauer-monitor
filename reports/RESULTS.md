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

## 14.10.2026 – Issue #5: SQLite-Historie, Ereignisse, Migrationen und Sicherung

`backend/storage.py` implementiert das SQLite-Schema v1 für Profile/Signale,
Leseanfragen, Beobachtungen, Ereignisse, Konfigurationsversionen und Sammlerzustand.
Messzyklen schreiben Anfrage und Beobachtungen atomar; Anfrage-IDs verhindern
Duplikate bei Wiederholung. Beobachtungen enthalten Rohworte, Qualität, UTC-Zeit,
Quelle sowie Profil-/Decoder-Version. Es gibt keine automatische Messwertlöschung.
Chronologische Verlaufsabfragen unterstützen Zeitgrenzen und höchstens 10.000 Punkte.

Schema-Migrationen prüfen `PRAGMA user_version`; neuere, unbekannte Schemata stoppen
den Start. SQLite-Online-Backup erstellt konsistente Sicherungen trotz WAL; Restore
prüft die Integrität und setzt einen gespeicherten Sammlerzustand auf `paused`.
Speicherbedarf berücksichtigt DB-, WAL- und SHM-Datei. Speicher-/SQL-Fehler werden
als `StorageError` gemeldet. FastAPI initialisiert beim Start `/data/monitor.sqlite3`;
es wird weiterhin kein Sammler gestartet und kein Modbus-Zugriff ausgeführt.

Tatsächlich geprüft:

- `uv run pytest` – 40 bestanden; ein vorhandenes Starlette/AnyIO-DeprecationWarning.
- `uv run ruff check .` – bestanden.
- Tests prüfen atomare Rücknahme bei fehlerhaftem Beobachtungsdatensatz,
  Wiederholungs-Deduplizierung, Migration/Neustart, DB-Schreibfehler (synthetisch
  durch SQLite-Abbruchtrigger), chronologische/halb-offene Zeitfilter, 10.050
  synthetische Messungen mit 10.000-Punkte-Grenze sowie Backup/Restore inklusive
  Integritätsprüfung und pausiertem Sammlerzustand.
- API-Smoke via `uv run python -c` und FastAPI TestClient: `/api/health` gab HTTP 200
  und `{"status":"ok"}` zurück; `monitor.sqlite3` wurde beim Start angelegt.

Grenzen: kein integrierter Sammler, keine Live-Daten/API-Verlaufsroute, kein realer
vollgelaufener Datenträger und kein Unraid-/Docker-/Hardwaretest. DB-Speicherfehler
werden als `StorageError` nach oben gemeldet; der Sammler-Stopp folgt mit dessen Issue.
Keine Modbus-Kommunikation. Issue und Kommentare nicht verändert; Änderungen bleiben
uncommitted, kein Commit/PR erstellt.

## 14.10.2026 – Issue #6: Zentraler Sammler und begrenzter Laufmodus

`backend/collector.py` verbindet den bestehenden FC03-Client, `core`-Decoder und
SQLite-Speicherung in einem sequenziellen Sammler. Je Block werden mindestens 60 s
zwischen Starts eingehalten; nach Request-Ende folgen mindestens 10 s Pause. Der
optionale Testlauf stoppt anhand von Höchstdauer und/oder Anfragebudget. Ein OS-
Dateilock im gemeinsamen Datenverzeichnis lehnt konkurrierende Prozesse ab.
Pause, Stop, geordneter Thread-Shutdown und Speicherfehler verhindern Folge-Reads.
Die FastAPI-Lifespan startet den Sammler ausschließlich bei explizitem
`COLLECTOR_ENABLED=true`; Browser-/HTTP-Refreshes rufen ihn nicht auf. Ausgeführt
werden nur die bestätigten `core`-Blöcke; unbestätigte Zusatzgruppen bleiben
inaktiv. Wiederverbindungen, Verwaltungsendpunkte und UI-Steuerung bleiben Issue #7/#8.

Tatsächlich geprüft:

- `uv run pytest tests/test_collector.py tests/test_app.py` – 13 bestanden.
- `uv run pytest` – 48 bestanden; ein Starlette/AnyIO-DeprecationWarning.
- `uv run ruff check .` – bestanden.
- Offline-Smoke: Collector gegen `ModbusSimulator` auf Loopback gestartet; eine
  synthetische Kesseltemperatur wurde empfangen, dekodiert und in SQLite gespeichert.
- FastAPI-Lifespan-Smoke mit aktiviertem Sammler und ausschließlich Loopback-Simulator:
  Sammler las headless ein Register; zwei `/api/health`-Abrufe erzeugten keine Zusatzreads.
- Neue synthetische Tests prüfen Anfragebudget, persistierte Beobachtung, 10-s-
  Requestabstand, 60-s-Blockintervall trotz 12-s-Requestdauer, Zeitlimit,
  Zählerrückgang, Pause/Shutdown, konkurrierende Besitzer und Stopp bei Speicherfehler.

Grenzen: keine Geräteanfragen, keine Live-/Unraid-/Docker-Verifikation. Das Lock
gilt für Prozesse, die dasselbe lokale Deployment-Datenverzeichnis verwenden;
unterschiedliche Datenverzeichnisse können keine gemeinsame Anlagenbesitzschaft
garantieren. Zusatzgruppen sind mangels bestätigter Decoder/Transportfreigabe nicht
aktiviert. API-Pause/Start und Dashboard folgen Issue #8/#9; Wiederverbindung Issue #7.
Änderungen bleiben uncommitted; kein Commit/PR erstellt.

## 15.10.2026 – Issue #7: Persistente Fehlerzustände und begrenzte Wiederaufnahme

Der Sammler speichert Zustand, Fehlerkategorie, Konfigurations-Fingerprint,
Wiederaufnahmebudget, Kernzyklusfortschritt, nächsten Block und vorab reservierte
Anfragen in der bestehenden SQLite-Zustandszeile. Reine Verbindungsfehler pausieren
den regulären Zeitplan und planen höchstens fünf Reads desselben bestätigten
Kernblocks mit Abständen von 1/2/5/10/15 Minuten. Budget und Anfrage werden vor
dem Socketzugriff persistiert; drei vollständige erfolgreiche Kernzyklen setzen
das Wiederaufnahmebudget zurück. Teilantworten, Protokoll-, Daten- und
Speicherfehler stoppen ohne Folge-Read. Harte Stopps und Nutzerpausen bleiben nach
Neustart bestehen. Ein abweichender Ziel-/Profil-Fingerprint führt nicht zu
automatischer Wiederaufnahme. Laufzeit-Wartefristen nutzen monotone Zeit; ein
Neustart setzt die volle Rest-Wartefrist konservativ neu an.

`GET /api/collector/status` stellt Zustand, Fehlerkategorie, Versuche, nächste
Aktion und Retry-Zeit bereit. Transportdetails und Konfigurations-Fingerprints
werden in der Antwort nicht offengelegt. Das Dashboard zeigt diese Statuswerte.
Manuelle Freigabe ist als `acknowledge_and_start`-Sammlermethode vorhanden; ein
zustandsändernder HTTP-Endpunkt bleibt wegen des noch offenen Zugriffsschutzes
außerhalb dieses Issues.

Tatsächlich geprüft:

- `uv run pytest -q` – 58 bestanden; ein vorhandenes Starlette/AnyIO-DeprecationWarning.
- `uv run ruff check .` – bestanden.
- `npm run build` – TypeScript-Prüfung und Vite-Produktionsbuild bestanden.
- Loopback-HTTP-Smoke über Vite-Proxy: `/api/collector/status` lieferte HTTP 200
  und den Zustand `unconfigured`; Frontend-Einstiegsseite lieferte HTTP 200.
- Synthetische Tests prüfen den gleichen Retry-Block, Uhrsprung ohne verkürzte
  monotone Wartezeit, genau fünf Wiederaufnahmeversuche, Protokoll-/Teilantwortstopp,
  Crashreservierung, Zielwechsel, pausierten Neustart und Reset nach drei
  vollständigen Kernzyklen.
- Ein zusätzlicher API-Test prüft den unlesbaren Zustandsspeicher; die Statusantwort
  bleibt nutzbar und enthält keine lokalen Speicherdetails.

Grenzen: kein Gerätezugriff, Live-/Unraid-/Docker-Test oder GitHub-Actions-Lauf.
Chromium konnte in dieser Umgebung nicht gestartet werden (`Shared browser daemon
unavailable`); UI wurde daher nicht visuell im Browser geprüft. Die Ausgabe von
Vite/HTTP wurde geprüft. Kein Schreibadapter, keine Verwaltungs-HTTP-Route und
keine Hardwareänderungen.

## 15.10.2026 – Issue #8: Lesende API, App-Konfiguration und Sammleraktionen

`backend/main.py` bietet aktuelle Signalwerte mit Einheit, UTC-Messzeit, Alter,
Qualität und Frischeflag; Historien werden nach Signal und halb-offenem,
zeitzonenpflichtigem Zeitfenster paginiert. Ereignisse besitzen `limit`/`offset`.
CSV läuft als Stream aus allen Originalbeobachtungen mit Zeitstempel, Qualität,
Rohworten und Decoderherkunft; keine API-Aggregation oder stilles Downsampling.
`/api/health` meldet Datenbankstatus getrennt vom Collectorstatus. Die API-Konfiguration
erlaubt nur die validierte Anzeigezeitzone; Host, Port, Unit, Profil und Datenpfad
bleiben Deployment-Konfiguration und werden nicht in Antworten ausgegeben.

Pause, Fortsetzen und quittiertes Starten sind POST-Routen ohne Geräteschreibweg.
Alle Mutationen verlangen eine exakt passende Origin-Quelle, nicht-cross-site
Fetch-Metadaten und einen benutzerdefinierten Header; fremde Browserformulare
werden abgewiesen. Konfigurationsänderungen werden versioniert und als Ereignis
protokolliert. OpenAPI/Swagger stammen aus den FastAPI-Routenschemas.

Tatsächlich geprüft:

- `uv run pytest tests/test_app.py tests/test_storage.py` – 20 bestanden,
  ein vorhandenes Starlette/AnyIO-DeprecationWarning.
- `uv run pytest` – 62 bestanden, ein vorhandenes Starlette/AnyIO-DeprecationWarning.
- `uv run ruff check .` – bestanden.
- `npm run build` – TypeScript-Prüfung und Vite-Produktionsbuild bestanden.
- Uvicorn auf Loopback gestartet: `/api/health`, `/api/config`,
  `/api/collector/status` und `/openapi.json` tatsächlich per HTTP geprüft;
  OpenAPI lieferte HTTP 200, Datenbank war gesund und Collector blieb `unconfigured`.
- Synthetische API-Prüfungen belegen aktuelle Signale/Einheiten/Qualität,
  Historienzeitstempel und Rohworte, CSV-Originalzeilen, Schutz fehlender
  Origin-Metadaten, protokollierte Zeitzonenänderung und abgewiesene naive/
  umgekehrte Zeitbereiche. Ein DST-Fallback-Test unterscheidet beide UTC-Zeitpunkte
  der wiederholten lokalen Stunde.

Grenzen: kein Modbus-Zugriff, keine Live-/Unraid-/Docker-Prüfung und keine visuelle
UI-Prüfung. Der Schreibzugriff auf Konfiguration umfasst absichtlich nur
`display_timezone`; Ziel-/Verbindungsparameter bleiben Deployment-Konfiguration.
Commit: `a1af16d` (`Implement local API for #8`). Pull Request:
https://github.com/lum1nat0r/sommerauer-monitor/pull/20 (Basis `main`, nach dem Merge von #7). GitHub Actions waren bei Übergabe noch ausstehend; ein früherer Lauf hatte beide Jobs bestanden.
