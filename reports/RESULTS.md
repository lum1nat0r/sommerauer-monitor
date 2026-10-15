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
zwischen Starts eingehalten. Der optionale Testlauf stoppt anhand von Höchstdauer
und/oder Anfragebudget. Ein OS-Dateilock im gemeinsamen Datenverzeichnis lehnt
konkurrierende Prozesse ab.
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

## 15.10.2026 – Issue #9: Dashboard mit Live-Übersicht, Verläufen und Fehleranzeige

`frontend/src/main.tsx` zeigt die vier bestätigten Kernsignale mit Einheit,
Messzeit, Datenalter und Frischequalität. Getrennte App-/Datenbank- und
Sammlerzustände enthalten Ersteinrichtung, Pause, Wiederaufnahme und harte
Fehlerstopps. Pause/Fortsetzen/Quittieren und Anzeigezeitzone verwenden die
geschützten Issue-#8-Endpunkte; Zieladresse und Heizungsparameter sind nicht
einstellbar. Verläufe bieten 1 h, 24 h, Woche, Monat und freien Zeitraum,
Signalwahl und CSV-Download. Das Diagramm zeichnet keine Verbindung über
erkannte Lücken von mehr als drei Minuten; Ereignisse und lokale Auswahl von
Signal/Zeitraum ergänzen die Ansicht. CSS passt sich schmalen Displays an und
enthält sichtbare Tastaturfokusse.

Tatsächlich geprüft:

- `uv run pytest -q` – 62 bestanden; ein vorhandenes Starlette/AnyIO-
  DeprecationWarning.
- `uv run ruff check .` – bestanden.
- `npm run build` – TypeScript-Prüfung und Vite-Produktionsbuild bestanden.
- Vite im Chromium-Browser mit ausschließlich synthetischen API-Fixtures:
  Ersteinrichtung, laufende Erfassung, veraltete Werte, Wiederaufnahmefehler,
  leerer Verlauf, erkannte Messlücke, Fehlerquittierung und Pause/Fortsetzen
  sichtbar bzw. bedienbar. Die drei Sammleraktionen sendeten jeweils genau den
  erwarteten POST-Endpunkt.
- Europe/Vienna-Fallback am 25.10.2026 mit freiem Zeitraum geprüft:
  02:30/02:45 Ortszeit wurden deterministisch auf 00:30/00:45 UTC abgebildet.
  Der Verlauf zeigt für eine synthetische sechstminütige Lücke keinen Linienzug
  und kennzeichnet die Lücke zugänglich.
- Bei 375 px Viewportbreite: vier Signal-Karten zweispaltig; Dokumentbreite
  blieb 375 px ohne horizontales Überlaufen. Tastatur-Space aktivierte
  „Freier Zeitraum“; Fokusindikatoren sind definiert. Ungültige gespeicherte
  Signal-/Zeitraumwerte fallen auf sichere Defaults zurück. Die nicht existente
  Ortszeit 29.03.2026 02:30 (Europe/Vienna) wird als ungültiger Zeitraum zurückgewiesen.

Die Browser-Fixtures sind synthetisch und belegen keine echte Messung,
Anlagenverträglichkeit oder Live-API-/Deployment-Funktion.

Grenzen: keine Gerätezugriffe; Zusatzregister bleiben inaktiv. Ein Browser-/
Gerätetest mit realen Messdaten und Deployment ist nicht Teil dieser Offline-
Implementierung. Keine unabhängige Geräte-/Herstellerprüfung.

## 15.10.2026 – Issue #11: Zusatzregister ohne Primärbelege ungeklärt

Geprüft wurden nur die vorhandene öffentliche Registerreferenz und der Katalog
am **damaligen** Ort `config/register_catalog.json` (seit #30 unverändert unter
[`backend/resources/register_catalog.json`](../backend/resources/register_catalog.json)).
Diese weisen 4098/1 (`Fehler_Min`), 4099/1
(`Leistung_Ist`), 4104/1 (`Leistung_Soll`), 33408/1 (`Aussen_Ist`) und optional
4354/1 (`Abgas_Sensor`) als statisch, ungefragt und ohne festgelegte Einheit
oder Decoder aus. Für 4098/2 sind dies zwei Einzelregister; daraus wird kein
Block-Decoder abgeleitet. Private Primärbelege oder aktuelle Benutzer-/Display-
Abgleiche lagen für diese Arbeit nicht vor. Damit bleiben Vorzeichen,
Skalierung, Fehlerwerte, gültige Bereiche und fachliche Bedeutung ungeklärt.

Alle Kandidaten bleiben außerhalb des aktiven `core`-Profils und sind keine
Messwerte. Der bestätigte Kernzeitplan ändert sich nicht; Zusatzintervalle
wurden nicht festgelegt. Es gab keine Geräteanfrage, keinen Scan, Schreibtest,
Import oder Zugriff auf private Rohdaten. Ein Live-Test bleibt offen, bis
Primärbelege und ein privater endlicher Ziel-/Laufplan vorliegen und andere
Leser ausgeschlossen sind.

Tatsächlich geprüft:

- `uv run pytest tests/test_registers.py` – 12 bestanden.
- `uv run ruff check .` – bestanden.

Grenzen: Keine Geräteantwort, kein Benutzer-/Displayabgleich und keine
unabhängige Herstellerprüfung. Offline-Decoder oder aktive Pollingfreigaben für
die Zusatzkandidaten wurden mangels belegter Semantik bewusst nicht ergänzt.

## 15.10.2026 – Issue #10: Docker-Paket und Unraid-Template

Ergänzt wurden ein mehrstufiges `Dockerfile` (Node-Frontendbuild, Python-
Runtime), `compose.yaml`, `unraid-template.xml` und Build-Context-Ausschlüsse.
Das Image bindet das Vite-Frontend in FastAPI ein, läuft standardmäßig mit UID
99/GID 100, enthält `/api/version` und prüft API-/SQLite-Erreichbarkeit per
Healthcheck. Compose begrenzt es auf `linux/amd64`, Bridge-Netzwerk,
read-only Root-Dateisystem, Capability-Drop, Init-Prozess und geordneten
SIGTERM-Shutdown. Persistenter Zustand bleibt unter `/data`; Collector und
Modbus sind standardmäßig deaktiviert. Das Unraid-Template bleibt auf ein noch
nicht veröffentlichtes Image verwiesen; kein Release-Tag wird behauptet.

Tatsächlich geprüft:

- `uv run --locked pytest -q` – 63 bestanden; ein vorhandenes
  Starlette/AnyIO-DeprecationWarning.
- `uv run --locked ruff check .` – bestanden.
- `npm run build` – TypeScript-Prüfung und Vite-Produktionsbuild bestanden.
- Lokaler FastAPI-Smoke mit dem gebauten `dist`: UI-Einstieg, JavaScript-Bundle,
  `/api/health` und `/api/version` lieferten HTTP 200; Version/Revision und
  Datenbankstatus geprüft. Keine Containerverifikation.
- `docker compose config --quiet` – Compose-Konfiguration gültig.
- `uv run --locked python -c "import xml.etree.ElementTree as ET; ET.parse('unraid-template.xml')"`
  – Template-XML wohlgeformt.
- Loopback-Simulator gestartet und über `ModbusTcpClient` Offset 4102 abgefragt:
  synthetische Antwort `RegisterRead(offset=4102, words=(42,), unit_id=255, function_code=3)`.
- `docker compose build --progress=plain` scheiterte vor Buildstart: Docker-CLI
  konnte keine Verbindung zum Docker-Engine-Pipe
  `//./pipe/dockerDesktopLinuxEngine` öffnen.

Grenzen und offene Abnahme: Die lokale Docker-Engine war nicht verfügbar. Daher
wurden Image-Build, Nicht-root-Prozess im Container, Volume-Schreibrechte,
Containerersatz/Persistenz, Healthcheck, Container-Shutdown, harte Stopps im
Container und Start ohne Hostkonfiguration nicht verifiziert. `docker compose
config` und synthetische Python-Tests ersetzen diese Containerprüfungen nicht.
Keine Unraid-7.3.2-Installation, keine Gerätezugriffe und kein Release-Tag.

## 15.10.2026 – Podman-Nachprüfung zu Issue #10

Nach Verfügbarkeit des lokalen Podman-5.8.1-Engines wurde das Image auf
`linux/amd64` gebaut. `podman compose --env-file .podman-smoke.env up -d --build`
baute den Stack und startete ihn; `/api/health` und die UI waren erreichbar.
Die Compose-Healthcheck-Argumente wurden dafür auf das Modul
`backend.healthcheck` umgestellt. Manueller Healthcheck lieferte `healthy`.

Tatsächlich geprüft:

- Compose-Container mit UID 99/GID 100: UI-HTML, JS-Bundle, Health, Konfiguration
  und Sammlerstatus erreichbar. Ohne Hostkonfiguration: `host_configured=false`,
  `collector_enabled=false`, Zustand `unconfigured`.
- Persistenter Compose-Bind-Mount: SQLite wurde beschreibbar angelegt und blieb
  über Containerersatz erhalten; zuvor gespeicherte Anzeigezeitzone `UTC` blieb
  erhalten.
- Geteilter Loopback-Netzwerk-Namespace mit ausschließlich dem Projektsimulator:
  Collector speicherte synthetisch `boiler.temperature=42`.
- Simulator-Fault `exception`: Collector ging zu `stopped_protocol`, blieb nach
  Containerersatz gestoppt; Wiederaufnahmezähler blieb 0.
- Geordnetes Stoppen der Collector-Container endete mit Exitcode 0. Der Compose-
  Healthcheck meldete nach Neustart `healthy`.
- `uv run --locked pytest -q` – 63 bestanden; ein vorhandenes
  Starlette/AnyIO-DeprecationWarning. `uv run --locked ruff check .` – bestanden.
- `npm audit` meldete eine hohe Vite-Schwachstelle in der gepinnten Version 6.2.2;
  verfügbarer Fix laut Audit: 6.4.4. Vite ist Build-/Entwicklungsabhängigkeit und
  wird nicht in die Runtime-Stufe kopiert; die Sperrdateien blieben unverändert.

Grenzen: Podman-/Container-Smokes sind keine Unraid-7.3.2-Prüfung. Keine
Gerätezugriffe. Eine tatsächliche Release-Veröffentlichung erfolgte nicht.

## 15.10.2026 – Issue #12: Offline-Ende-zu-Ende- und Wiederherstellungsabnahme

Die reproduzierbare Offline-Abnahme verbindet Loopback-Modbus-Simulator,
FC03-Collector, SQLite, API/CSV und Container-Dashboard. `tests/test_end_to_end.py`
prüft alle drei Kernblöcke Ende-zu-Ende mit virtueller Zeit, Signalen und
unveränderten CSV-/SQLite-Originalwerten; eine Volume-Ersetzung liefert eine
leere Historie statt erfundener Werte. Der Datenfluss verwendet ausschließlich
synthetische Simulator-/Testdaten. Keine Heizungs- oder sonstigen Netzlesezugriffe.

Abnahmestand: App `0.1.0`; Containerziel `linux/amd64`, API-Revision `unknown`.
Podman 5.8.1 auf WSL2 baute das Image. Der Image-Build verwendet Node 22.14.0
und CPython 3.12.9; Hostprüfungen liefen mit Node 26.7.0/npm 12.0.2,
uv 0.12.2 und CPython 3.12.13.

Tatsächlich geprüft:

- `uv run --locked pytest -q` – 65 bestanden; ein vorhandenes
  Starlette/AnyIO-DeprecationWarning. `uv run --locked ruff check .` bestanden.
- `npm run build` – TypeScript-Prüfung und Vite-Produktionsbuild bestanden.
  `docker compose config --quiet` und `podman build --platform linux/amd64`
  bestanden.
- Podman-Container als UID 99/GID 100 mit echtem Loopback-Simulator gestartet.
  Die Datenbank enthielt die sechs erfolgreichen FC03-Abfragen der drei
  bestätigten Blöcke (4102/1, 28688/2, 36864/2; Unit 255) und synthetisch
  dekodierte Werte 42, 6079, 47 und 38. Tatsächliche Abstände zwischen Requests
  waren mindestens 10 s, derselbe Block mindestens 60 s. `/api/health`,
  `/api/signals/current`, CSV und die Browseroberfläche lieferten HTTP 200;
  CSV enthielt vier Originalbeobachtungen.
- Der Container-Simulator wurde auf Modbus-Exception umgestellt. Die siebte
  Anfrage endete als `ProtocolError`/`stopped_protocol`; nach Containerneustart
  blieb Status und Budget `stopped_protocol`/0, ohne achte Anfrage. Datenbank
  und Historie blieben erhalten.
- SQLite-Online-Backup vor dem Fehlerstopp: Integritätsprüfung `ok`; Restore
  enthielt dieselben acht Beobachtungen (IDs, Signale, Zeitstempel, Werte,
  Rohworte), setzte den Collector auf `paused`.
- Chromium prüfte das laufende Container-Dashboard mit Simulatorwerten sowie
  eine separate synthetische Fixture mit veraltetem Wert, ungültiger Qualität
  und 6-Minuten-Lücke: Alter/Zeitstempel und Status sichtbar, zwei Punkte als
  eine Messlücke gekennzeichnet, keine verbindende Diagrammlinie; CSV enthielt
  drei Fixture-Zeilen. Keine Browser-JavaScript-Fehler.
- Bestehende Offline-Tests decken zusätzlich Verbindungsausfall/Flattern,
  fünf Wiederaufnahmeversuche, Crashreservierung/Neustart, Teilantworten,
  harte Fehlerstopps, Migration/Neustart, synthetischen Speicherfehler,
  10.050 Messungen, Backup/Restore und die wiederholte lokale Stunde beim
  Sommerzeitwechsel ab. Der Modbus-Client besitzt keinen Schreibaufruf.

Grenzen: Keine echte Geräteantwort, Displayprüfung, Unraid-7.3.2-Installation
oder Live-Verträglichkeitszusage. Volle Datenträger wurden nicht real erzeugt;
Speicherausfall ist per SQLite-Fehler injiziert. Ein verlorenes Datenvolume
ist nicht wiederherstellbar, sofern kein externes Backup existiert; der
Ersatzvolume-Test belegt nur den leeren, nicht vortäuschenden Neustart. Der
Podman-OCI-Build meldete, dass OCI-Images `HEALTHCHECK` nicht unterstützen;
die API-Healthroute wurde geprüft, nicht ein Container-Healthcheck. Keine
GitHub-Actions- oder Hardwareprüfung.

## 15.10.2026 – Endliche Full-Stack-Laufgrenze vorbereiten

`COLLECTOR_MAX_REQUESTS` begrenzt den App-Sammler über die lokale
Deployment-Konfiguration. Ein App-Lauf mit diesem Budget stoppt bei
Transportfehlern ohne automatische Wiederaufnahme; unbeschränkter Betrieb
behält das bestehende Wiederaufnahmeverhalten. Der pytest-Fixture deaktiviert
den Collector explizit, damit eine private `.env` mit aktivierter Erfassung
keine echten Gerätezugriffe aus Standardtests auslöst.

Tatsächlich geprüft:

- `uv run pytest` – 68 bestanden; ein vorhandenes Starlette/AnyIO-
  DeprecationWarning. `uv run ruff check .` bestanden.
- App, Collector, SQLite und Vite-Dashboard lokal mit Loopback-Simulator
  gestartet; Budget 1 führte zu Collectorstatus `completed`, einer
  SQLite/API-Beobachtung mit synthetischem Wert 42 sowie HTTP 200 für
  Dashboard und Healthroute.

Grenzen: Dieser Lauf war ausschließlich Simulatorbetrieb; es gab für diesen
Smoke keinen visuellen Dashboardabgleich. Kein Heizungszugriff, keine
Geräteantwort oder Displayprüfung. Der separate Live-Zyklus ist unten dokumentiert.

## 15.10.2026 – Begrenzter Full-Stack-Live-Zyklus

Nach Betreiberbestätigung, dass andere Modbus-Leser beendet waren, lief die App
mit dem ausschließlich lokal konfigurierten Ziel und einem temporären
Prozesslimit von drei Anfragen. Das Profil blieb `core`: FC03, Unit 255,
4102/1, 28688/2 und 36864/2. Die private Zieladresse und Rohmesswerte werden
hier nicht abgelegt.

Tatsächlich geprüft:

- Genau drei erfolgreiche Anfragen, je eine pro bestätigtem Block; keine
  Wiederaufnahmeversuche. SQLite enthält vier erfolgreiche Beobachtungen
  (je ein Kernsignal), API meldet Datenbank gesund und alle vier Werte bei
  der Abfrage mit Qualität `ok`.
- Vite-Proxy und Dashboard lieferten HTTP 200. Chromium zeigte die vier
  gespeicherten Kernwerte und den Zustand „Erfassung abgeschlossen“; nach
  Überschreiten der 120-s-Frischegrenze markierte die UI die Werte korrekt
  als veraltet. Ein Neustart zur Dashboardprüfung erzeugte keine weitere
  Anfrage; gespeichertes Budget blieb 3/3.
- App und Dashboard-Devserver wurden beendet. Der Prozesslimitwert war ein
  Start-Override; `.env` wurde nicht verändert.
- Nach der UI-/Endzustandskorrektur: `uv run pytest` – 69 bestanden, ein
  bestehendes Starlette/AnyIO-DeprecationWarning; `uv run ruff check .` und
  `npm run build` bestanden.

Grenzen: kein Displayabgleich, keine längere Betriebs-/Verträglichkeitsprüfung
und kein Unraid-Test. Der Browser zeigte die gespeicherten Messwerte; daraus
folgt keine unabhängige Bestätigung durch das Heizungsdisplay oder den Hersteller.

## 15.10.2026 – GHCR-Image-Workflow vorbereitet (Teilumfang #14)

Der neue Workflow baut bei Pull Requests ohne Push und veröffentlicht ein Image
nur für einen passenden Versionstag nach Lizenz-, `main`-Commit- und
Issue-#13-Prüfung sowie erneutem Offline-Test/Container-Smoke. Noch kein Tag,
kein GHCR-Push und kein Unraid-Deployment; die Lizenzentscheidung bleibt offen.
Node und npm im Docker-Build wurden an die vorhandene Node-26-/npm-12-Vorgabe
angepasst.

Tatsächlich geprüft:

- `actionlint` 1.7.12 für beide Workflowdateien und `bash -n` für das
  Smoke-Skript: ohne Befund.
- `uv run --locked pytest -q`: 69 bestanden, ein bestehendes
  Starlette/AnyIO-DeprecationWarning; `uv run --locked ruff check .` und
  `npm run build`: bestanden.
- `podman build --platform linux/amd64` mit Buildversion `pr-local` und
  synthetischer Revision `offline-smoke`: erfolgreich. Das endgültige Image
  verwendete Node 26.7.0/npm 12.0.2 für den Frontend-Build.
- Das tatsächliche Image lief nicht-root, mit schreibgeschütztem Root und
  temporärem Datenvolume ohne Modbus-Ziel/aktivierte Erfassung. Der aus dem
  Workflow aufgerufene Smokecheck prüfte `/api/health` (`ok`), `/api/version`
  (`pr-local`/`offline-smoke`) und Collectorstatus `unconfigured` erfolgreich.
- PR #27: GitHub Actions `pull-request-build` baute und startete das Image
  erfolgreich (38 s); die Python- und Frontend-Jobs der Offline-CI bestanden
  ebenfalls. Der Release-Job wurde beim PR erwartungsgemäß übersprungen.

Grenzen: Podman-OCI-Build meldete erneut, dass der Dockerfile-`HEALTHCHECK`
im OCI-Format nicht übernommen wird; die API-Healthroute wurde geprüft.
`npm ci` meldete eine bekannte High-Severity-Dependency-Warnung und für
`esbuild` unter npm 12 ein blockiertes Installationsskript; der Frontend-Build
war erfolgreich. Kein Release-Tag oder Registry-Push, kein Release-Job-Lauf und
kein Hardware-/Unraid-Test. GitHub-Rulesets für Branch/Tags sind noch nicht
konfiguriert; dies bleibt Voraussetzung vor dem ersten Release.

## 15.10.2026 – Issue #13: Abnahmeprüfung und gestufte Live-Läufe

Abnahmestand: App 0.1.0, Commit `64521b5`, Kernprofil/Decoder Version 1.
Die Abhängigkeit #12 ist geschlossen; deren Offline-/Containerbelege sind oben
dokumentiert und wurden nicht als neue Geräteprüfung ausgegeben.

### Bereits vorhandener Erstlauf

Die private SQLite-Datei des oben dokumentierten Full-Stack-Live-Zyklus wurde
erneut ausschließlich lokal ausgewertet, ohne Geräteanfrage:
FC03/Unit 255, genau 4102/1, 28688/2 und 36864/2, alle erfolgreich,
vier Beobachtungen mit Qualität `ok`, Profil-/Decoderversion 1.
Anfragebeginn 10:18:35.785 bis 10:18:35.910 UTC; gespeicherte
Anfragedauern 78, 19 und 35 ms. Endzustand `completed`, Budget 3/3,
Wiederaufnahmezähler 0, Stopgrund `Finite collection limit reached`.
Ein Wiederholungsintervall ist aus diesem Einzelzyklus nicht ableitbar.
Der ursprüngliche Plan vor Ausführung ist in der früheren `NEXT_STEPS.md`
nachvollziehbar ([Änderung in PR #26](https://github.com/lum1nat0r/sommerauer-monitor/pull/26/files)):
höchstens drei serielle Kernanfragen ohne Retry, feste 3-s-Deadline,
andere Leser vorher beendet, sofortiger Fehlerstopp. Eine separate damalige
private Laufplandatei wurde nicht eingesehen.

### Voraussetzungen und Offline-Vorbereitung der neuen Läufe

Betreiberangabe im Abnahmedialog: Alle anderen Modbus-Leser sind beendet,
Displayzugang besteht; der Monitor ist noch nicht auf Unraid installiert.
Lokal waren weder Python-/Node-Monitorprozesse noch laufende Podman-Container
vorhanden. Das schließt entfernte Leser nicht technisch aus; hierfür gilt die
Betreiberangabe.

Vor dem neuen Kurzlauf wurden 15 und 90 Anfragen mit dem tatsächlichen
FC03-Transport gegen den Loopback-Simulator und virtueller Schedulerzeit
ausgeführt: 20 bzw. 120 synthetische Beobachtungen, `completed`,
Wiederaufnahmezähler 0, SQLite-Integrität `ok`. Eine simulierte
Modbus-Exception stoppte nach genau einer Anfrage in `stopped_protocol`.
Wiederherstellung des jeweiligen Endzustands erzeugte keine weitere Anfrage.
Der erste Durchgang scheiterte ausschließlich beim Entfernen einer noch
geöffneten temporären SQLite-Datei unter Windows; nach explizitem Schließen
der Prüfverbindung war der gesamte Offline-Durchgang erfolgreich.
Dies sind Simulatorbelege, keine echten Laufzeiten oder Gerätefehler.

### Aktueller Displayabgleich

Die erste neue Kernmessung um 12:03:32 UTC / 14:03:32 Europe/Vienna wurde
dem Betreiber privat zum gezielten Displayvergleich genannt. Er bestätigte
die Übereinstimmung aller vier Kernwerte einschließlich Anlagen-Betriebszähler.
Das ist eine Betreiberbeobachtung, keine unabhängige Foto-/Displayprüfung
durch den Assistenten. Messwerte und Display-Rohbelege bleiben privat.

### Erster kurzer Live-Lauf: Timingabnahme nicht bestanden

Vorheriger Plan in `NEXT_STEPS.md`, konkrete Ziel-/Laufdaten privat.
Höchstens 300 s / 15 Anfragen, FC03/Unit 255, drei Kernblöcke,
mindestens 60 s je Block, 3-s-Transportdeadline, null Wiederaufnahmen.
Tatsächlich 15 erfolgreiche Anfragen in 240,687 s, 20 Beobachtungen `ok`,
SQLite-Integrität `ok`, Stopgrund Anfragebudget (`completed`, 15/15).
Am Transportaufruf wurden 59,984–60,047 s je wiederholtem Block gemessen;
damit war die Timingabnahme nicht bestanden. Kein Geräte-/Protokoll-/Datenfehler;
kein weiterer Lauf wurde automatisch gestartet.

Die ursprüngliche Windows-Uhr `time.monotonic` verwendet hier `GetTickCount64`
mit 15,625 ms Auflösung; die genannten Werte sind deshalb kein hochauflösender
Paketmitschnitt. Unabhängig davon reproduzierte ein neuer deterministischer
Regressionstest die fehlerhafte Referenz vor der persistenten Reservierung:
0,5 s variable Reservierungsdauer verkürzten den tatsächlichen Abstand
im injizierten Client auf 59,5 s (Test vor Korrektur fehlgeschlagen).

Korrektur: `time.perf_counter` als hochauflösende monotone Scheduleruhr
(hier `QueryPerformanceCounter`, Auflösung 100 ns); 60-s-Mindestabstand
konservativ ab Abschluss der vorherigen Blockverarbeitung statt ab Beginn
der Reservierung. Damit kommen Transport-/Verarbeitungslaufzeiten zum
Mindestintervall hinzu. Kein neuer Zusatzregister-, Retry- oder Schreibpfad.

Nach Korrektur: `uv run --locked pytest -q` – 70 bestanden, ein vorhandenes
Starlette/AnyIO-DeprecationWarning; `uv run --locked ruff check .` bestanden.
Der tatsächliche Loopback-Transport wurde mit 15/90 Anfragen und simulierter
Exception erneut erfolgreich ausgeführt; virtuelle Schedulerzeit, kein Live-Nachweis.
Ein neuer, separat geplanter Kurzlauf ersetzt nicht die Belege des ersten Laufs.

### Korrigierter kurzer Live-Lauf: bestanden

Neuer privater Plan und neue SQLite-Datei unter
`data/issue13-abnahme/short-fixed/`; vorheriger Lauf unverändert erhalten.
Dieselben drei Kernblöcke, FC03/Unit 255, 3-s-Deadline, 300-s-Limit,
eigenes Budget 15, keine Wiederaufnahme. Basis `64521b5` mit oben beschriebener
Timingkorrektur.

Tatsächlich 15/15 erfolgreiche Anfragen in 240,661 s (5 vollständige Kernzyklen),
20 Beobachtungen `ok`, SQLite-Integrität `ok`. Hochauflösend gemessene Abstände
am Transportaufruf desselben Blocks 60,040320–60,291638 s.
Antwortdauer 11,609–268,209 ms, Mittelwert 49,045 ms.
Stopgrund Anfragebudget, Endzustand `completed`, Wiederaufnahmezähler 0.
Wiederherstellung dieses gespeicherten Endzustands blieb `completed` und erzeugte
keine zusätzliche Transportanfrage; kein Neustart- oder Persistenzbeleg auf Unraid.

Erst nach dieser Auswertung wurde der separate 1800-s-/90-Anfragen-Plan in
`NEXT_STEPS.md` und privat festgehalten. Kein automatisches Verlängern des
kurzen Laufs und kein Übergang in unbeschränkte Erfassung.

### Längerer endlicher Live-Lauf: bestanden

Vor Beginn separat dokumentiert: höchstens 1800 s / 90 Anfragen,
privater Plan unter `data/issue13-abnahme/long/`, gleiche Zielkonfiguration
und Timingkorrektur wie im bestandenen Kurzlauf. Ein synchroner aktiver
Transport, FC03/Unit 255, nur 4102/1, 28688/2 und 36864/2, maximal zwei
Register, 3-s-Deadline; keine Wiederaufnahme und keine künstlichen Störungen.

Tatsächlich 90/90 erfolgreiche Anfragen, exakt 30 je Kernblock, von
12:14:59 bis 12:44:00 UTC; Laufdauer 1741,599 s.
120 Beobachtungen `ok`, SQLite-Integrität `ok`.
Hochauflösende Abstände am Transportaufruf desselben Blocks
60,024734–60,124170 s; Antwortdauer 11,346–97,432 ms,
Mittelwert 25,114 ms. Stopgrund Anfragebudget, `completed`, Budget 90/90,
Wiederaufnahmezähler 0. Wiederherstellung des gespeicherten Endzustands
erzeugte keine weitere Anfrage. Insgesamt 120 neue Live-Anfragen in
beiden Kurzläufen und diesem längeren Lauf; der frühere Erstzyklus
umfasste separat drei Anfragen.

Nach den Läufen meldete der Betreiber, keine neuen Störanzeigen oder
Anlagenauffälligkeiten bemerkt zu haben. Das ist eine Betreiberbeobachtung,
keine unabhängige Heizungsfunktionsprüfung oder Verträglichkeitszusage.
Nicht geprüft: andere Betriebsphasen über Tage/Wochen, Zusatzregister,
Sensor-Kalibrierung und die tatsächliche Installation auf Unraid.

### Persistenz, API und Dashboard nach Ende der Erfassung

- Lokales SQLite-Online-Backup und Restore des korrigierten Kurzlaufs:
  alle 20 Originalbeobachtungen einschließlich IDs, Zeiten, Werte und
  Rohworte identisch, Integrität `ok`, wiederhergestellter Zustand `paused`.
  Keine Geräteanfrage; Windows-Nachweis, kein Unraid-Test.
- Tatsächlichen Uvicorn-Prozess mit Langlauf-DB und
  `COLLECTOR_ENABLED=false` gestartet: Health/Datenbank `ok`, vier aktuelle
  Kernsignale mit gespeicherter Qualität `ok`; alle 120 CSV-Zeilen stimmten
  in ID, Signal, Zeit, Wert und Qualität mit SQLite überein. Rohwerte wurden
  dafür lokal verglichen, nicht veröffentlicht.
- Dabei wurde ein zweiter Abnahmefehler sichtbar: Die deaktivierte API
  behandelte gespeichertes `completed` fälschlich als `stopped_storage`.
  Den vorhandenen endlichen App-Test um Neustart mit deaktiviertem Sammler
  erweitert; vor Korrektur schlug dieser mit genau dem falschen Status fehl.
  Korrektur in `backend/main.py`: `completed` ist auch als gespeicherter
  Endzustand gültig. Kein neuer Steuer-/Gerätepfad.
- Erneut gestarteter tatsächlicher API-Prozess: `completed`, kein Fehlergrund,
  gesunde DB und identische 120 CSV-Beobachtungen. Anfragezahl blieb nach
  Prozessneustarts, API-Abfragen und Browserprüfung unverändert 90.
- Das tatsächliche Vite-/API-Dashboard wurde mit lokalem Chrome visuell geprüft:
  „Erfassung abgeschlossen“, kein fälschlicher Speicherstopp, vier gespeicherte
  Kernwerte als veraltet markiert, Verlauf mit 30 Originalbeobachtungen.
  Keine Browser-JavaScript-Fehler. Der automatische Browserstart war zunächst
  nicht verfügbar; expliziter Start des vorhandenen Chrome funktionierte.
  Kein Container-/Unraid-Dashboardnachweis aus diesem Lauf.
- Abschließend `uv run --locked pytest -q`: 70 bestanden, ein bekanntes
  Starlette/AnyIO-DeprecationWarning; `uv run --locked ruff check .` bestanden.
  Keine erneute Frontend-Build- oder GitHub-Actions-Prüfung für diese Aussage.
  Prüfprozesse beendet; temporäres Laufwerkzeug entfernt, private Laufpläne,
  Messungen und Auswertungen erhalten. `.env` unverändert.

### Finale Kriterien und Abnahmegrenze zu #13

| Issue-Kriterium | Ergebnis / Beleg |
|---|---|
| Neue Verbindung tatsächlich belegt | Erfüllt: ursprünglicher Erstzyklus und neue endliche FC03-Läufe am ausschließlich privat konfigurierten Ziel. |
| Jeder Lauf mit Plan, tatsächlicher Anzahl, Timing und Stopgrund | Erfüllt: historischer Erstplan in früherer `NEXT_STEPS.md`; neue Pläne vor Ausführung, tatsächliche Auswertungen oben und Rohbelege privat. Die erste Timingabnahme bleibt ausdrücklich fehlgeschlagen dokumentiert. |
| Kein Dauerbetriebsversprechen aus Einzelread | Erfüllt: gestufte Auswertung; Betriebsplan erst nach längerem Lauf erstellt, weder Dauerbetrieb aktiviert noch langfristige Störungsfreiheit behauptet. |
| Keine Schreibbefehle, Suche oder Wiederholung nach hartem Fehler | Erfüllt: nur die drei FC03-Kernblöcke, keine echten harten Fehler, null Live-Wiederaufnahmen; Exception-Stopp ausschließlich im Loopback-Simulator geprüft. |
| Private Rohbelege bleiben privat, Zusammenfassung nachvollziehbar | Erfüllt: Daten unter ignoriertem `data/issue13-abnahme/`, öffentlich nur bereinigte Methodik, Anfrage-/Timing-/Qualitätsauswertung und Betreiberbeobachtungen. |
| Unraid nur bei tatsächlicher Durchführung als bestanden markieren | Nachweisgrenze eingehalten: nicht installiert, nicht geprüft, nicht als bestanden markiert. |

**Abgenommen ist die gestufte lokale Kernregister-Leseinbetriebnahme.**
Der Betreiber bestätigt Displayübereinstimmung und keine bemerkten neuen
Anlagenauffälligkeiten; Geräteantworten, synthetische Nachweise und
Betreiberbeobachtungen bleiben getrennt. Der nachgelagerte
[Betriebsplan](../docs/INBETRIEBNAHME.md#betriebsplan-nach-der-begrenzten-abnahme)
beschreibt die nächste Betreiberinstallation, ohne sie zu aktivieren.
Unraid-Mount/Neustart/Containerersatz/externes Backup und Restore sowie
tatsächlicher Dauerbetrieb bleiben offen. Keine neue Lizenz-/Releasefreigabe
und keine Aktivierung zusätzlicher Gerätefunktionen.

## 15.10.2026 – MIT-Lizenz vom Betreiber bestätigt

Der Betreiber hat MIT für eigenen App-Code ausdrücklich akzeptiert.
`LICENSE` enthält den MIT-Lizenztext; README, Entscheidungen und Release-
Checklisten führen die Lizenzentscheidung nicht mehr als offen.
Herstellerdateien, rekonstruierter Herstellercode und Rechte an Abhängigkeiten
sind davon nicht erfasst. Kein Release-Tag, Registry-Push oder Deployment ausgelöst.

## 15.10.2026 – Unraid-Compose für das erste Release 0.1.0

Nutzerauftrag: eigenständige Compose-Datei für Unraid mit öffentlichem
Repository-Image vorbereiten; dieser Stand soll später den ersten Versionstag
erhalten. `compose.unraid.yaml` referenziert fest
`ghcr.io/lum1nat0r/sommerauer-monitor:0.1.0`, ohne Build-Schritt.
Der vorhandene Veröffentlichungsworkflow verlangt dafür den Git-Tag `v0.1.0`.
Die lokale Build-Datei `compose.yaml` bleibt unverändert.

Offline tatsächlich geprüft:

- Docker Compose 5.1.3 löst die Konfiguration erfolgreich auf; ohne `DATA_PATH`
  scheitert sie mit dem vorgesehenen Konfigurationsfehler. Der Bind-Mount legt
  fehlende Hostverzeichnisse nicht automatisch an. Leeres Modbus-Ziel und
  `COLLECTOR_ENABLED=false` bleiben die Erststartwerte.
- Aktuellen Projektstand mit Podman für Linux/amd64 lokal gebaut und den Stack
  über dessen Docker-Compose-Provider gestartet. Ein temporärer Override ersetzte
  ausschließlich die GHCR-Imagereferenz durch das lokale Prüfimage; eigener
  Linux-Datenpfad und Loopback-Webport, keine private Projekt-`.env`.
- `/api/health`: App/SQLite `ok`; `/api/version`: `0.1.0` mit Prüf-Revision
  `unraid-compose-smoke`; `/api/collector/status`: `unconfigured`.
  Dashboard-HTML wurde mit HTTP 200 ausgeliefert, keine neue visuelle UI-Abnahme.
- Tatsächlicher Benutzer `99:100`, schreibgeschütztes Root-Dateisystem und
  beschreibbarer `/data`-Bind-Mount geprüft. Der in Compose definierte Healthcheck
  wurde erfolgreich ausgeführt. Podmans OCI-Build übernimmt den Dockerfile-
  Healthcheck nicht; die Compose-Definition wurde im gestarteten Stack verwendet.
- Container über Compose ersetzt: zuvor geschriebener synthetischer
  Persistenzmarker blieb erhalten, SQLite-Integrität davor/danach `ok`,
  API weiterhin gesund und Erfassung weiterhin `unconfigured`.
- Prüfcontainer, Prüfnetzwerk, lokaler Prüfimage-Tag, temporäre Konfiguration
  und ausschließlich das selbst angelegte Linux-Prüfverzeichnis entfernt.
  Bestehende Messdaten und private Konfiguration unverändert.

Grenzen: Docker-Desktop-Engine hier nicht verfügbar; Laufzeitnachweis daher über
Podman/Linux, nicht auf Unraid. Kein Gerätezugriff, Registry-Push oder Git-Tag.
Öffentliche GHCR-Sichtbarkeit und anonymer Pull müssen nach dem erfolgreichen
Release geprüft werden; Unraid-Mount-/Betriebsabnahme bleibt beim Betreiber.
Einrichtung und Start sind in `docs/UNRAID.md` dokumentiert.

## 15.10.2026 – Issue #30: Katalogreferenz und isolierte Diagnoseauswahl

Die bisherige JSON-Quelle wurde nach `backend/resources/register_catalog.json`
verschoben, nicht kopiert. Alle 199 Einträge, Belegfelder, Top-Level-Metadaten
und `known_read_blocks` bleiben erhalten. Vor und nach der Verschiebung:
SHA-256 `a4f8b8c47ca99d496e8c2778286611a180c53f915a16438d41b794ff6ac43c09`
über die Dateibytes. Kein neuer privater Originalquellenbefund.

`backend/catalog.py` liefert lazy geladene, tief unveränderliche Prozesssnapshots,
validiert den Katalog vollständig und sperrt defekte Ressourcen ausschließlich
für Diagnosen mit `catalog_unavailable`. Nur Katalog-IDs werden auf 1–3 sortierte,
deduplizierte Blöcke aufgelöst; exakte Kernblock-Erweiterung, unbekannte Worte
einzeln. Die 194 Rohregister erhalten weder Semantik noch Pollingfreigabe.
START/SOLL bleiben getrennte Kandidaten ohne Leseblock/Schreibfähigkeit.

Tatsächlich offline geprüft mit CPython 3.12.9 und uv 0.12.2:

- `uv sync --locked --python 3.12.9` in einer isolierten temporären Umgebung.
  Der erste Versuch mit der vorhandenen `.venv` scheiterte an einer Windows-
  Zugriffssperre; keine fremden Prozesse beendet.
- `uv run pytest tests/test_registers.py`: **59 bestanden**. Enthält beschädigte/
  fehlende Ressourcen, Kernabdeckung, Bool-/Bereichs-/Hex-/Wortanzahlfehler,
  tiefe Unveränderlichkeit, Erfolg-/Fehlercache, fremdes Arbeitsverzeichnis,
  alle Einzelwort-Auswahlen, enge Blockgrenzen und Socket-Sentinel.
  Ein anfänglicher Escape-Fehler im neuen Subprozess-Test wurde korrigiert.
- `uv run pytest`: **117 bestanden**, ein Starlette/AnyIO-DeprecationWarning.
- `uv run ruff check .`: bestanden.
- Separater Python-Lauf außerhalb des Projektarbeitsordners: unveränderten
  Dateihash geprüft; 4098/4099/33408 ergeben drei Einzelblöcke, doppelte
  Zählerauswahl nur 28688/2. Leere Auswahl, 4103, Steuer-ID und vier Blöcke
  abgewiesen. Import ohne Ressourcenladen; nach Laden/mehrfacher Planung genau
  ein Ressourcenabruf und **null Socketzugriffe**. Fehlende Ressource liefert
  `catalog_unavailable`, Kerndecoder verarbeitet weiterhin 65 °C.
- Tatsächlicher Uvicorn-Prozess auf explizitem Loopback mit leerem Host,
  deaktiviertem Collector und temporärer Datenbank: trotz zuvor ausgelöstem
  `catalog_unavailable` startet die App. `/api/health` meldet App/DB `ok`,
  `/api/collector/status` meldet `unconfigured`. Prozess und temporäre Daten
  danach entfernt. Die erste zu breite Ressourceninjektion störte auch
  `tzdata`; nach Beschränkung auf das Backend war der Start erfolgreich.

Grenzen: ausschließlich Offline-Bibliotheksabnahme; keine Anlagenzugriffe,
neue HTTP-Routen, UI, Schreibausführung, Aktivierung oder neue Messungen.
Hatch-Paketdefinition und Backend-COPY erfassen den neuen Ressourcenort ohne
zusätzliche Konfiguration; ein gebautes Wheel außerhalb des Checkouts wurde
hier nicht geprüft und bleibt Teil von #39. Als Nächstes #31, danach #32/#33;
keine Folgepakete aus diesem Befund als implementiert ableiten.

## 15.10.2026 – Issue #31: Diagnosejournal, Reservierungen und Schema 2

`backend/storage.py` ergänzt die drei getrennten Tabellen `diagnostic_runs`,
`diagnostic_requests` und `control_plans` sowie den volumenweiten aktiven
UNIQUE-Index. Migration 0→1→2 und 1→2 läuft atomar; Minutenhistorie,
Signal-/Profildefinitionen und Kernsammler bleiben fachlich unverändert.
Die elf Diagnoseoperationen speichern private unveränderliche Pläne,
verbrauchte Reservierungen, tatsächliche Rohantworten und separate Bewertungen.
Harte Stopps/Unterbrechungen verlangen eine ausdrückliche Ursachenquittierung;
terminale IDs werden nicht reaktiviert. Keine Steuerrevisionsoperationen (#34).

Tatsächlich ausschließlich offline ausgeführt, CPython 3.12.9 / uv 0.12.2:

- `uv sync --locked` erfolgreich, verwendete jedoch die vorhandene Python-Version
  3.12.13. Umstellung der vorhandenen `.venv` auf 3.12.9 scheiterte an einer
  Windows-Zugriffssperre; keine fremden Prozesse beendet. Alle folgenden
  Prüfungen deshalb mit `uv run --isolated --python 3.12.9 --locked`.
- `pytest tests/test_storage.py`: **51 bestanden**, ausschließlich `tmp_path`-
  Datenbanken. Vollständige historische Zeilen vor/nach v1-Migration verglichen,
  atomarer Rollback bei Fehler in frischer und v1-Datenbank nachgewiesen.
- Zwei unabhängige Store-Verbindungen konkurrierten um Starts und denselben
  Schritt: höchstens ein aktiver Lauf, genau eine erfolgreiche Reservierung,
  genau eine Budgeterhöhung. Neustart/Recovery erhält verbrauchte Versuche.
- Alle Bewertungsvarianten einschließlich letztem Schritt, getrennte Bewertung,
  unveränderte Pläne/Rohworte, `[110]` bei synthetischem Decoderfehler und null
  zusätzliche Kernbeobachtungen geprüft. Interpretation unbestätigter Rohblöcke
  abgewiesen. SQL-Triggerfehler auf beiden Diagnosetabellen lassen keine halbe
  Reservierung, Antwort oder Bewertung zurück.
- Stop/Ablauf und gleichzeitiger Fehlerabschluss schwächen harte Fehler nicht ab;
  verspäteter Fehler nach bereits quittierter Unterbrechung verlangt neue
  Quittierung. UTC-Normalisierung, Pagination und terminale IDs geprüft.
- v1-/v2-Backuphash nach Restore unverändert; vollständige historische Zeilen,
  Diagnosepläne, Antworten, Bewertungen und mehrere synthetische Steuerrevisionen
  erhalten. Aktive Ziel-Läufe werden `interrupted`, Budget bleibt verbraucht.
  Schema 0/zu neue Backups und vorhandenes Restoreziel abgewiesen.
- Gesamtsuite mit explizit leerem `MODBUS_HOST` und
  `COLLECTOR_ENABLED=false`: **159 bestanden**, eine bestehende
  Starlette/AnyIO-DeprecationWarning. Ein vorheriger Lauf hatte zwei fehlgeschlagene
  Konfigurationstests wegen einer geerbten Host-Umgebungsvariable; keine
  Teständerung zur Unterdrückung, private Konfiguration unverändert.
- `ruff check .`: bestanden. `uv build --python 3.12.9` in temporäres Verzeichnis:
  Source-Distribution und Wheel erfolgreich; Buildartefakte anschließend entfernt.
- Separater echter SQLite-Verbraucherlauf außerhalb von pytest: Plan erstellen,
  Versuch reservieren, Rohwort 42 speichern, Bewertung `continue` bis `completed`,
  Backup/Restore; Endzustand, Budget 1/1 und Rohwort erhalten,
  **0 Kernbeobachtungen**. Temporäre Daten anschließend entfernt.

Sicherheitsentscheidung: Restore verlangt ein neues Offline-Ziel statt bestehende
Volumes zu überschreiben; Betriebsvolumen erst bei kontrolliert beendeten Lesern
tauschen. Speicher-Dicts bleiben privat, keine HTTP-/Downloadprojektion hinzugefügt.
Settings-Fingerprint, monotone Fristen, Gerätebesitz und Kernmonitoring-Umschaltung
bleiben #33, Transport #32, bereinigte öffentliche Projektion #35.
Keine Geräteverbindung, Scans, Schreibtelegramme oder neuen Live-Belege.

## 15.10.2026 – Issue #32: Gemeinsamer FC03-Pfad und Katalogsimulator

`backend/modbus.py` verwendet einen gemeinsamen privaten Telegrammpfad für
exakte Kernprofilreads und vor Socketzugriff katalogvalidierte Diagnoseblöcke.
Einzelne dokumentierte Worte sind zulässig, fremde Zweierblöcke und Lücken
nicht. Kernreads bleiben bei defektem Katalog nutzbar. Unveränderte Rohworte,
Fehlerklassen und tatsächliche empfangene Bytezahlen; keine Interpretation,
Wiederholung oder automatische Folgeanfrage.

Der Loopback-Simulator bleibt standardmäßig auf die drei Kernblöcke begrenzt.
Nur `catalog=True`/`--catalog` aktiviert synthetische Katalogantworten. Alle
bisherigen Faults gelten für beide Pfade; `received_requests` ist eine
threadsichere, schreibgeschützte und zeitlich stabile Momentaufnahme.

Tatsächlich ausschließlich offline ausgeführt, uv 0.12.2:

- `uv sync --locked` erfolgreich. System-`python` meldet 3.14.7; sämtliche
  Verhaltensprüfungen und der Smoke liefen deshalb ausdrücklich über
  `uv run --isolated --python 3.12.9 --locked` mit CPython 3.12.9.
- `pytest tests/test_modbus.py tests/test_registers.py`: **150 bestanden**.
  Beide Pfade mit sämtlichen Faults und exakten Bytezahlen, keine Retries;
  ungültige Typen/Bool-/Bereichswerte, Lücken und Fremdblöcke vor Socket
  per Sentinel und unveränderter Anfrageliste abgewiesen.
- Alle dokumentierten Einzelworte im expliziten Loopback-Katalogmodus
  geprüft; alle fünf Kernworte unverändert. Kerndecoder liefert für `(4,319)`
  genau 6079 Minuten. Unbekannte Rohworte bleiben ohne Interpretation.
- Gegatete konkurrierende Kern-/Katalogaufrufe beider Reihenfolgen öffnen
  nie parallele Sockets. Ein wartender Aufruf verbraucht sein eigenes
  Gesamtbudget ohne zweiten Socket. Deterministische In-process-Zeitprüfung
  mit langsamen Fragmenten erhält ein gemeinsames 0,35-s-Budget einschließlich
  Lock, Verbindung und Senden; kein Neustart je Fragment.
- Separater echter Loopback-Verbraucherlauf außerhalb von pytest, dynamischer
  Port, drei explizite Aufrufe 4098/1, 4099/1, 33408/1:
  Rohworte exakt `(0,)`, `(173,)`, `(65526,)`; Snapshot exakt
  `((255,3,4098,1),(255,3,4099,1),(255,3,33408,1))`.
  Anschließender expliziter Zählerread liefert unverändert `(4,319)`.
- Gesamtsuite mit explizit leerem `MODBUS_HOST` und deaktiviertem Collector:
  **236 bestanden**, eine bestehende Starlette/AnyIO-DeprecationWarning.
- `ruff check .`: bestanden. `uv build --python 3.12.9`: Source-Distribution
  und Wheel erfolgreich; erzeugte Buildartefakte anschließend entfernt.

Kein Frontend geändert; kein Browser-/Unraid-/Live-Nachweis und kein
installierter Wheel-Laufzeitnachweis behauptet. Keine privaten Ziele,
Gerätekommunikation oder Schreibtelegramme. Bestehende Caller behalten
ihre Imports und APIs; keine Symbolverschiebung oder Kompatibilitätsaliase.
Die LSP-Referenzabfrage am vorhandenen Ruff-Server lief in einen Timeout;
die im Issue vorgegebene exakte Symbolsuche erfasste Backend, Tests und Scripts.
Runner mit Besitz, Budget, Zielbindung, Fristen und Reviews bleibt #33;
API/UI und spätere Gesamtintegration bleiben getrennte Arbeitspakete.

## 15.10.2026 – Issue #33: Exklusive manuelle Prüfläufe und sichere Recovery

`ReadCheckRunner` implementiert den endlichen manuellen Diagnosevertrag:
unveränderliche Ziel-/Quell-/Katalogbindung, gemeinsamer Modus-RLock,
Collector-Stop/Join vor Übernahme derselben OS-Sperre, dauerhafte Reservierung
vor jedem Socket und Betreiberbewertung vor Fortschaltung. Start selbst liest
nichts. Feste Grenzen: höchstens drei geplante Anfragen, 3 s Gesamtdeadline,
60 s vor erster Anfrage und ab abgeschlossener Speicherung, 600 s Laufzeit.
Watchdog und Shutdown senden niemals Geräteanfragen; Monitoring bleibt angehalten.

`DeviceLock`/`DeviceOwnershipError` liegen ausschließlich in
`backend/device_lock.py`; alle bisherigen Nutzer sind migriert, keine alten
Aliase/Re-Exports. Der ungesperrte Direktleser wurde nach Prüfung seiner leeren
Repository-Aufrufermenge entfernt. LSP-Referenzen waren am Ruff-Server erneut
nicht verfügbar (Timeout); die exakte Symbolsuche wurde verwendet.

`DIAGNOSTICS_SOURCE` ist standardmäßig `device`; `simulator` verlangt exakt
`127.0.0.1`. Host/Port kommen nur aus Settings, private Plansnapshots/Fingerprints
bleiben im Speicher. Nur exakte Kernblöcke erhalten Interpretation; unbekannte
Rohworte bleiben unverändert und ohne Einheit. Zählerbelege werden über Läufe
hinweg nur bei identischem Zielfingerprint auf plausiblen Fortschritt geprüft.
Diagnose erzeugt keine zusätzlichen Kernbeobachtungen.

Tatsächlich ausschließlich offline geprüft, uv 0.12.2, CPython 3.12.9 über
`uv run --isolated --python 3.12.9 --locked`; private `.env` nicht als Testziel
verwendet. Für die Gesamtsuite Host explizit leer, Collector deaktiviert und
Diagnosequelle `device` gesetzt:

- Erste gezielte Runner-/Collector-Abnahme: **119 bestanden**; danach zusätzliche
  echte Übergabe-/Prozessabbruch- und Shutdown-Fälle ergänzt.
- Abschließende vollständige `pytest`-Suite: **342 bestanden**, eine bestehende
  Starlette/AnyIO-DeprecationWarning; keine unterdrückten Fehler.
- Exakte 59,999-/60-s-Grenzen, Verzögerungen von Antwort/Reservierung/Speicherung,
  unverbrauchbare Doppelaktionen, parallele Browseraufrufe und fehlende Reviews.
- Echter konkurrierender Zweitprozess auf isoliertem Datenvolumen ohne
  Clientzugriff; gegateter realer Collector-Worker gibt Besitz erst nach letzter
  Antwort/Join frei. Join-Timeout hält den Besitz; ein Fehler der letzten
  Kernantwort sperrt den Diagnosestart.
- Echter Kindprozess beendet sich unmittelbar nach Runner-Reservierung vor
  Antwortabschluss. Neue gesperrte Recovery erhält Versuch 1/3, setzt
  `interrupted` und macht die alte ID nicht erneut ausführbar.
- Transport-/Teilantwort-/Protokoll-/Decoder-/Speicherfehler stoppen ohne
  Folgeanfrage. Decoderfehler erhalten Rohworte; Ausfall auch der
  Fehlerpersistierung erhält aktive Markierung und Reservierung für Recovery.
  Gleichzeitiger Stop/Fristablauf schwächt harte Fehler nicht ab.
- Stop und `close()` während gegateter Antwort erhalten das Ergebnis; Besitz
  bleibt bis Verarbeitungsschluss exklusiv. `close()` beendet alle eigenen
  Watchdogs. Autonomer Ablauf ohne Browseraktion beendet den Lauf.
- Persistente Diagnosefehler sperren Collector-Start, direktes Run, Resume und
  Acknowledge ohne Kernbudgetänderung. Konservative erste 60 s auch in
  Collector-Recovery, unveränderter Kernzeitplan ohne Diagnosehistorie.
- `ruff check .`: bestanden. Finales Source-/Wheel-Build mit `uv build
  --python 3.12.9`: bestanden. `npm run build` mit Node 26.7.0/npm 12.0.2:
  TypeScript und Vite erfolgreich; kein Frontend geändert.

Separater tatsächlicher Loopback-Verbraucherlauf außerhalb von pytest:
temporäre SQLite-Datenbank, dynamischer lokaler Port, echter Katalogsimulator,
keine injizierte Uhr und kein injizierter Transport. Start sendete nichts;
vorzeitiger expliziter Read lieferte `read_not_due`. Drei jeweils explizit
aufgerufene und bewertete Schritte mit echten 60-s-Wartezeiten ergaben exakt
FC03/255 auf 4098/1, 4099/1, 33408/1 und gespeicherte Rohworte `[0]`, `[173]`,
`[65526]`. Gemessene Verbraucherschritte einschließlich Antwort/Speicherung:
60,050 / 60,051 / 60,068 s; Gesamtlauf 180,224 s. Endzustand `completed`,
Budget 3/3, **0 Kernbeobachtungen**. Keine automatische Folgeanfrage.
Temporäre Daten, Verbraucherskript und eigene Buildartefakte anschließend entfernt.

Plattformgrenze: OS-Besitz einschließlich echtem Zweitprozess unter Windows
(`msvcrt`) geprüft; Linux-`fcntl`-Zweig erhalten, lokal nicht ausgeführt.
Keine Live-/Unraid-/Browserabnahme, keine privaten Originalbelege unabhängig
neu geprüft, keine Geräte- oder Schreibkommunikation. HTTP/Lifespan und die
Betreiberangabe zum Ausschluss fremder Leser bleiben ausdrücklich #35,
Diagnoseoberfläche #36; Steuerplanbewertung folgt getrennt mit #34.

## 15.10.2026 – Issue #34: Formale Offline-Steuerentwürfe und Revisionen

`backend/control_plans.py` ergänzt den exakten 20-Felder-Entwurf, konkrete
fehlende Voraussetzungen und formale Bewertung. Vollständige Betreibertexte
ergeben ausschließlich `ready_for_review`, keinen unabhängigen Quellenbeleg und
keine Gerätefreigabe. Sensorblocker sowie START-/SOLL-Rückfalllücke bleiben
unabhängig von Vollständigkeit und Revision erhalten. Keine Schreibkodierung,
Temperaturgrenze, FC06-Fähigkeit oder Gerätefunktion abgeleitet.

Save/Get/List verwenden die vorhandene Schema-2-Tabelle. Neue Revisionen werden
unter `BEGIN IMMEDIATE` nur angehängt; konkurrierende Updates mit derselben
erwarteten Revision ergeben genau einen Erfolg und einen `revision_conflict`.
Alte Vor-/Versuchs-/Rückstellwerte bleiben erhalten. Die gemeinsame private
Exportprojektion enthält Revision, Entwurf, Betreiber-Quellenstatus, Bewertung
und immer `execution_enabled:false`. API und UI bleiben #35/#36.

Tatsächlich ausschließlich synthetisch/offline geprüft, CPython 3.12.9 über
`uv run --isolated --python 3.12.9 --locked`, uv 0.12.2:

- `pytest tests/test_storage.py tests/test_control_plans.py`: **164 bestanden**.
  Null-/Leerzustände, Textlänge 4000/4001, numerische Grenzen, unbekannte IDs und
  Zusatzfelder, konkrete fehlende Quellen-/Rückstellangaben, vollständige Pläne,
  Sensorblocker über Revision/Export, SQLite-Wiederöffnen, neueste Listen,
  konkurrierende Updates und injizierter Insertfehler mit vollständigem Rollback.
- Gesamtsuite mit explizit leerem `MODBUS_HOST`, deaktiviertem Collector und
  Diagnosequelle `device`: zunächst **455 bestanden**, nach Entfernen eines
  redundanten Sensorfalls final **454 bestanden**; jeweils eine bestehende
  Starlette/AnyIO-DeprecationWarning. Beide geänderten Testdateien enthalten.
- `ruff check .`: bestanden.
- `uv build --python 3.12.9`: Source-Distribution und Wheel gebaut.
- `npm ci` erfolgreich; npm meldete ein blockiertes esbuild-Installationsskript.
  `npm run build` mit Node 26.7.0/npm 12.0.2 dennoch erfolgreich
  (TypeScript und Vite). Kein Frontend geändert.

Separater Verbraucherlauf außerhalb pytest: temporäre SQLite, ausschließlich
synthetischer START-Entwurf, Socketkonstruktor explizit gesperrt. Anlage als
`draft`, vollständige Revision 2 als `ready_for_review`, veraltetes Update
abgewiesen. Nach Wiederöffnen alte Revision unverändert, aktuelle Revision
und Liste identisch; JSON-Rundlauf erhält Quellenstatus, Rückfallblocker und
`execution_enabled:false`. Temporäres Verbraucherskript und eigene
Python-Buildartefakte anschließend entfernt.

System-`python` ist 3.14.7, die lokale Standard-uv-Umgebung 3.12.13; deshalb alle
Verhaltensprüfungen explizit isoliert unter der geforderten 3.12.9 ausgeführt.
Private `.env` nicht als Testziel verwendet. Keine Geräteverbindung,
Live-/Browser-/Unraid-Abnahme, neuen Primärbelege oder Schreibfreigaben.

## 15.10.2026 – Issue #35: Diagnose-API und sichere Lifespan

Alle 15 Diagnose-/Steuerentwurfsrouten sind vor dem Frontend-Mount erreichbar.
Explizite OpenAPI-Projektionen erhalten Pläne, Quellenstatus und unveränderte
Rohbelege, aber keine privaten Zielsnapshots, Pfade oder Fingerprintwerte.
Plananlage liefert 201; gewöhnliche Aktionen/GETs 200. Strikte Bodies,
bereinigte deutsche Fachfehler und bestehender CSRF-Schutz sind angebunden.
Private JSON-Downloads verwenden `Cache-Control: private, no-store`.

Lifespan-Recovery erfolgt vor möglichem Collectorstart unter gemeinsamer
OS-Sperre. Fremder Besitz und Recoveryfehler verhindern Geräteaktionen, nicht
lesende APIs; fremder Zustand bleibt erhalten. Collectoraktionen teilen
`runner.mode_lock`; Stop setzt sein Event ohne äußeren Lock vor dem Warten.
Shutdown beendet zuerst Runner/Watchdogs und danach den eigenen Collector.
Keine automatische Monitoring-Fortsetzung nach Diagnoseende oder Quittierung.

Tatsächlich ausschließlich offline geprüft, CPython 3.12.9 über
`uv run --isolated --python 3.12.9 --locked`, uv 0.12.2:

- Geforderte Suite `pytest tests/test_diagnostics_api.py tests/test_app.py
  tests/test_read_checks.py tests/test_storage.py`: **376 bestanden**.
- Vollständige `pytest`-Suite: **649 bestanden**. Jeweils eine bestehende
  Starlette/AnyIO-DeprecationWarning, keine unterdrückten Fehler.
- HTTP-Nachweise: 59,999/60-s-Grenze, Mindestabstand einschließlich Speicherung,
  Reservierung über Frist ohne Socket, Doppel-/Altreads und parallele Browser,
  abgebrochener HTTP-Verbraucher mit sicherem Reload, manuelle Bewertungen,
  Stop/Ablauf während Read ohne Herabstufung harter Fehler.
- Sichere 201/404/422/409/503/403-Verträge, CSRF sämtlicher neuer Mutationen,
  Ziel-/Katalogwechsel, Rohbelege trotz Decoderfehler und Speicherstopps.
  Ein defekter Diagnosekatalog sperrt den tatsächlich gestarteten synthetischen
  Kernsammler nicht. Diagnose erzeugt keine zusätzlichen Minutenbeobachtungen.
- Echter fremder OS-Besitzer in separatem Windows-Prozess: lesende API bleibt
  erreichbar, aktive Reservierung und fremder Collectorzustand unverändert.
  Recovery erhält Budget/Antworten und setzt `interrupted`; Quittierung
  reaktiviert weder alte ID noch Monitoring. Shutdown gibt Gerätebesitz frei.
- Konkurrierende Revisionsupdates erzeugen genau eine neue Revision; alte
  Werte bleiben erhalten. Vollständige Entwürfe bleiben `ready_for_review`,
  Exporte `execution_enabled:false`. Gespeicherte Entwürfe werden beim GET
  auch bei inzwischen defektem Katalog nicht erneut validiert oder bewertet.
- `ruff check .`: bestanden. Source-Distribution und Wheel mit
  `uv build --python 3.12.9` in temporäres Ausgabeverzeichnis gebaut.
- `uv sync --locked` und `npm ci`: erfolgreich. npm meldete wie bisher ein
  blockiertes esbuild-Installationsskript; `npm run build` mit Node
  26.7.0/npm 12.0.2 war dennoch erfolgreich (TypeScript und Vite).

Erster Prüfdurchlauf: zwei redundante neue Testfälle enthielten eine falsche
Leertextannahme zum bestehenden Steuerentwurfsvertrag; sie wurden entfernt,
nicht neu festgeschrieben. Ein bestehender Settings-Test wurde durch geerbtes
`COLLECTOR_ENABLED=true` beeinflusst. Abschließende Suiten verwenden deshalb
explizit leeren Host, deaktivierten Collector, Quelle `device` und feste
synthetische Port-/Unit-/Profilwerte. Eine zusätzliche Regression belegte vor
der Korrektur die unerwünschte Katalog-Neuvalidierung gespeicherter Entwürfe;
nach Umstellung auf die gespeicherte Antwortprojektion besteht sie.

Separater Verbraucherlauf außerhalb pytest: echter Uvicorn-HTTP-Server und
echter Loopback-Katalogsimulator auf dynamischen lokalen Ports, temporäre
SQLite, explizite Settings ohne `.env`; ausschließlich die Uhr war virtuell.
Planung, Start, GET, Review und Export erzeugten keine Zusatzanfrage. Genau
vier explizite FC03/255-Anfragen: 4098/1, 4099/1, 33408/1 und 28688/2.
Gespeicherte Rohworte `[0]`, `[173]`, `[65526]` und `[4,319]`; letzter Block
dekodiert zu 6079 synthetischen Betriebsminuten. 0 Minutenbeobachtungen.
Steuerrevision 2 und veraltetes Update 409 belegt, Export nicht ausführbar;
gespeicherter Sensorentwurf bleibt nach simuliertem Katalogausfall abrufbar.
Server und Watchdogs kontrolliert beendet, Wegwerfskript und temporäre
Python-Buildartefakte entfernt. Keine reale 60-s-Zeitmessung aus diesem Lauf
ableiten; die separate echte Zeitabnahme von #33 bleibt davon unberührt.

LSP-Referenzen sind am verfügbaren Ruff-Server nicht unterstützt (Timeout;
Capabilities ohne Referenzprovider). Kein Frontend geändert und keine
Browser-/Linux-/Live-/Unraid-Abnahme in diesem Paket. Keine private `.env` als
Testziel, keine neuen Gerätebelege, unabhängigen Primärquellenprüfungen,
Schreibbefehle, Releases oder Deployments. Diagnoseoberfläche bleibt #36.

## 15.10.2026 – Issue #36: Diagnosebedienung im vorhandenen Dashboard

Umgesetzt: Bereichswahl ohne Router, vollständiger Katalog mit 50er-Seiten,
Such-/Belegfiltern und Details, getrennte nicht lesbare START-/SOLL-Kandidaten,
manuelle Prüfläufe einschließlich Historie/Review/Stopp/Quittierung sowie
vollständige Offline-Steuerentwürfe mit Revisionen und JSON-Export.
Gemeinsame Fetch-/Datumshelfer sind aus der Übersicht migriert; bestehende
Fehlermeldungen behalten `HTTP <Status>`. Keine zusätzlichen Bibliotheken,
Backendpfade, Gerätefunktionen oder automatische Diagnoseaktionen.

Tatsächlich ausgeführt, ausschließlich offline:

- CPython **3.12.9** in separater uv-Projektumgebung, uv **0.12.2**,
  Node **26.7.0**, npm **12.0.2**; bestehende Locks verwendet.
  Die vorhandene Standardumgebung bleibt auf 3.12.13 und wurde abschließend
  mit `uv sync --locked` wieder vollständig synchronisiert.
- `pytest`: **649 bestanden**, eine bestehende Starlette/AnyIO-
  DeprecationWarning. `ruff check .`: bestanden.
- `npm ci`: erfolgreich, wie bisher Hinweis auf blockiertes
  esbuild-Installationsskript. Finales `npm run build`: TypeScript und
  Vite-Produktion erfolgreich, 33 Module.
- Eigene Chrome-Bedienung gegen echten Vite-Devserver, echte Uvicorn-API und
  echten Loopback-Katalogsimulator, temporäres DATA_DIR, Collector deaktiviert,
  Quelle ausdrücklich `simulator`. Private `.env` unverändert; Umgebungswerte
  überschrieben das Ziel ausschließlich auf Loopback.
- Erster Browser-POST reproduzierte HTTP 403 im bisherigen Vite-Stringproxy:
  dessen `changeOrigin:true` änderte den Hostheader. Mit explizitem
  `changeOrigin:false` funktionieren reale Browsermutationen unter dem
  unveränderten Same-Origin-/`X-Requested-With`-Vertrag.

Katalog-/Darstellungsprüfung:

- Seiten tatsächlich bedient: **50 / 50 / 50 / 49** Einträge.
  `Aussen_Ist`, `33408` und `8280` treffen denselben Eintrag;
  Filter ergeben fünf bestätigte bzw. 194 dokumentierte Register und
  zunächst leere Ergebnisansicht. START/SOLL zeigen `read_block=null`,
  unbekannte Schreibfähigkeit und nur potenzielle Offsets, ohne Lesecheckbox.
- 33408 bleibt „Einheit ungeklärt“, `documented_raw`, `static_only_unqueried`,
  auch nach erfolgreicher Antwort. 65526 bleibt 65526/0xFFF6, kein −10-°C-Wert.
  Synthetische Kennzeichnung, Alter und Rohbelege bleiben nach Refresh,
  Bereichswechsel und API-Neustart sichtbar. Neustart mit geändertem
  Loopback-Zielport zeigt Zielabweichung, ohne die historische Simulatorquelle
  umzudeuten; dabei keine Geräteanfrage.
- Desktop **1360 px** und **390 px** mit echten Screenshots geprüft.
  Bei 390 px gemessene Dokumentbreite 375 px einschließlich Platz für die
  Browser-Scrollbar, kein Seitenüberlauf; Katalogtabelle scrollt innerhalb
  ihres Bereichs. Details und Formular stehen darunter. Kopf/Status und
  bestehende Übersicht/Verlauf bleiben nutzbar, Bereichswechsel erhält Eingaben.

Echter manueller Dreischrittlauf:

- Auswahl 4098/4099/33408 liefert ausschließlich 4098/1, 4099/1, 33408/1.
  Vor Planung/Start und nach Start ohne Read null Simulatoranfragen.
  Erststart ohne Leserbestätigung gesperrt; erster Leseknopf vor Fälligkeit
  gesperrt. Countdown sendet selbst keinen Request.
- Genau drei bewusste Reads mit Rohworten **[0]**, **[173]**, **[65526]**;
  Budget 1/3 → 2/3 → 3/3, jeweils `awaiting_review` vor „Geprüft, weiter“.
  Endzustand `completed`, keine automatische Monitoringfortsetzung.
  Gespeicherte UTC-Zeitstempel ergeben folgende tatsächliche Abstände:

| Abstand | Sekunden |
|---|---:|
| Start bis erste Anfrage | 66,763494 |
| Erste Antwortspeicherung bis zweite Anfrage | 86,567921 |
| Zweite Antwortspeicherung bis dritte Anfrage | 79,128046 |

- Refresh zwischen Schritten/nach Abschluss, GET-Export und Neustart erzeugen
  keine zusätzliche Simulatoranfrage. Heruntergeladener JSON-Laufbeleg und
  gespeicherter Export haben denselben Antwortzeitstempel. Keine privaten
  Ziel-/Pfad-/Fingerprintfelder im Export.
- Zusätzliche Kernwortauswahl 28688/28689/36865 wird vor Start exakt zu
  28688/2 und 36864/2 dedupliziert. Dieser Lauf wurde nach kurzem sichtbarem
  Countdown sicher abgebrochen: `cancelled`, null Reads.
- Geöffneter Lauf ohne Read wurde durch eigenen API-Prozessabbruch unterbrochen;
  Recovery im selben DATA_DIR zeigt `interrupted`, Budget 0, Quittierung
  startet weder alte ID noch Monitoring.
- Separater echter Simulatorlauf mit Fault `exception`: genau ein expliziter
  FC03-Versuch, `stopped_protocol`, `protocol_error`, neun empfangene Bytes,
  keine Ersatzrohworte und keine Folgeanfrage. Quittierung erhält den terminalen
  Zustand. Insgesamt über alle eigenen Läufe **vier FC03/255-Anfragen**.
- SQLite-Integrität `ok`, **null Kernbeobachtungen**, beide quittierten
  Fehlerzustände und abgeschlossener/abgebrochener Lauf dauerhaft gespeichert.

Formular-/Fehlerprüfung:

- START-Entwurf nur mit ID/Zweck als Revision 1 gespeichert: fehlende Quellen,
  Rückstellwert und übrige Nullfelder vollständig sichtbar. Alle 20 Felder
  synthetisch ausgefüllt, Revision 2 gespeichert und nach API-Neustart geladen;
  weitere Revision 3 erhalten. Nur `ready_for_review`, niemals ausführbar.
- Zweite unabhängige Browsersitzung speichert veraltete Basisrevision:
  sichtbarer `revision_conflict`; Eingabe bleibt erhalten, Serverrevision
  separat sichtbar und nur ausdrücklich übernehmbar. Vier gespeicherte
  Revisionen insgesamt einschließlich separatem Sensorentwurf.
- Echter heruntergeladener START-JSON-Export: Revision 3,
  `execution_enabled:false`, Betreiberquelle nicht unabhängig verifiziert,
  keine fehlenden Felder, sämtliche fünf Blocker einschließlich ungeklärtem
  autonomen Rückfall. Separater Kesselsensorentwurf behält
  `sensor_value_must_not_be_overridden`.
- `ApiError` mit echter HTTP-404-Antwort im Browser geprüft:
  Klasse/Status/Detail vorhanden, `message === "HTTP 404"`.
  Gemeinsame Formatierung liefert dieselbe Wiener/UTC-Zeit und Altersangabe.
- **Zusätzlich synthetische Browserantworten, keine realen DB-/Netzausfälle:**
  503 `storage_unavailable` und abgebrochener GET zeigen Fehler, behalten aber
  die drei gespeicherten Rohbelege. Anzeige von `expired`, `stopped_transport`,
  `stopped_data`, `stopped_storage` anhand abgeänderter GET-Zustände geprüft:
  kein weiterer Read, Fehler verlangen Quittierung, Ablauf nicht.
- Für den `read_not_due`-Bedienfehler wurde ausschließlich die vom Browser
  empfangene GET-Warteanzeige synthetisch auf null gesetzt; Serveruhr und
  Produktionsgrenzen blieben unverändert. Der bewusste vorzeitige Read erhält
  echten HTTP 409, deutsche Fachmeldung, keine Warteschlange/Retry und keine
  zusätzliche Simulatoranfrage. Gespeicherte Antworten bleiben erhalten.

Nachweise sind eigene Offline-Bedienprüfungen, keine unabhängigen
Primärquellen-, Geräte-, Langzeit-, Unraid- oder Live-Nachweise.
Keine neue Browser-Testabhängigkeit oder Source-only-Abnahme eingeführt.
Die zusätzlichen automatisierten Verbraucherprüfungen #37 und reproduzierbare
Screenshot-/Request-/Persistenzabnahme #38 bleiben getrennte Pflichtpakete;
Paket-/Wheel-Abnahme #39 ebenfalls offen. Eigene API samt Lifespan beendet,
Simulator/Devserver beendet, synthetische Downloads und temporäre
Prüfumgebung entfernt. Keine Schreibfunktion, Freigabe, Veröffentlichung
oder Deployment aktiviert.

## 15.10.2026 – Issue #37: automatisierte Diagnose-Gesamtabnahme

Ausschließlich synthetische Daten, isolierte temporäre Datenverzeichnisse,
explizite Loopbackziele oder injizierte Clients; keine private Anlagenkonfiguration,
keine Anlagenzugriffe und keine Schreibtelegramme. Vorhandene Komponentenprüfungen
werden wiederverwendet statt durch eine zweite Testarchitektur ersetzt.

Ergänzungen: echte konkurrierende Diagnosebesitzer in einem Zweitprozess,
gegatete Reservierungs-/Antwort-/Collector-Speicherrennen, Daten- und
Speicherfehler jeweils am ersten und zweiten Versuch, parallele HTTP-Starts,
negative Steuerplananlagen/-revisionen und unveränderliche Sensor-/Rückfallblocker.
Keine Produktionsänderung oder Sicherheitsausnahme erforderlich.

Verbindliche Umgebung: **CPython 3.12.9**, **uv 0.12.2**, **Node 26.7.0**,
**npm 12.0.2**. `uv sync --locked --python 3.12.9` in separater temporärer
Projektumgebung erfolgreich; das Umschalten der bestehenden `.venv` war wegen
gesperrter Windows-Dateien nicht möglich. Die bestehende Standardumgebung wurde
mit `uv sync --locked` wieder synchronisiert. `npm ci` erfolgreich; npm meldete
wie zuvor ein blockiertes esbuild-Installationsskript.

Die erste vollständige Suite meldete **1 failed, 643 passed, 1 warning in
82.50s**. Ursache war geerbtes `COLLECTOR_ENABLED=true` in einem
Runner-Settings-Test, nicht eine Geräteantwort. Die Tests isolieren jetzt alle
Deploymentvariablen nach bestehendem App-Testmuster. Der betroffene Test prüft
die Ablehnung ungültiger Simulatorziele statt eines bestimmten Fehlerwortlauts.

Final tatsächlich ausgeführt in dieser Python-3.12.9-Umgebung:

```sh
uv run pytest tests/test_read_checks.py tests/test_diagnostics_api.py tests/test_modbus.py tests/test_collector.py tests/test_storage.py tests/test_registers.py tests/test_app.py tests/test_end_to_end.py
uv run pytest tests/test_control_plans.py
uv run ruff check .
npm run build
```

Ausgabe der Prüfungen:

```text
644 passed, 1 warning in 83.81s (0:01:23)
63 passed in 0.35s
All checks passed!
✓ 33 modules transformed.
✓ built in 905ms
```

Die Warnung stammt aus Starlette und betrifft das veraltete
`anyio.abc.BlockingPortal`-Alias; keine Unterdrückung eingeführt.
Im Sammelaufruf für Ruff/Steuerplantests/Build scheiterte zusätzlich die
PowerShell-Exitcode-Verkettung; die drei Werkzeuge liefen dennoch mit den
obigen Ergebnissen. Ruff wurde nach der Isolationskorrektur separat erfolgreich
ausgeführt. Es wurde keine fehlgeschlagene Fachprüfung verschwiegen.
Keine neue Browserabhängigkeit, keine Produktions-Testoption, keine Änderungen
an Kernprofil, Messwertsemantik, Budgets oder öffentlich sichtbaren Verträgen.

Zusätzlicher tatsächlicher Laufzeitnachweis außerhalb von pytest: unveränderter
Runner mit echter monotoner Uhr, SQLite und echtem Loopback-Katalogsimulator.
Start sendete nichts; drei ausdrücklich aufgerufene Reads nach jeweils gemessenen
**60,050 s** Wartezeit lieferten exakt
`((255,3,4098,1),(255,3,4099,1),(255,3,33408,1))`,
Rohworte **[0] / [173] / [65526]**, Zustand **completed**,
**null Kernbeobachtungen**. Lauf samt Simulator kontrolliert beendet.
Dies ist kein Browser-, Geräteverträglichkeits- oder Dauerbetriebsnachweis.

### Zuordnung der vollständigen Abnahmematrix

Testnamen beziehen sich auf `tests/`; die parametrierten Fälle gehören zum
jeweiligen Nachweis. `R` = `test_read_checks.py`, `A` =
`test_diagnostics_api.py`, `T` = `test_modbus.py`, `C` =
`test_collector.py`, `S` = `test_storage.py`.

| Matrixfall aus #37 | Konkreter Verhaltensnachweis |
|---|---|
| Drei Rohregister, Reihenfolge, unbekannte Einheit, keine Kernbeobachtungen | A: `test_loopback_complete_route_cycle_preserves_raw_evidence_and_minute_history`; zusätzlicher realer Loopbacklauf oben |
| Nur 28689, vollständiger Zählerblock und 6079 min | A: `test_loopback_complete_route_cycle_preserves_raw_evidence_and_minute_history` |
| Überlappende Kernwortauswahl ohne doppelte Blöcke | A: `test_selection_is_resolved_deduplicated_and_sorted_without_merging_raw_neighbors` |
| Unbekannte ID, 4103 und vier Blöcke vor Socket abgewiesen | A: `test_invalid_selection_is_rejected_before_any_device_effect` |
| Manipulierte HTTP-Transport-/Budgetfelder | A: `test_plan_rejects_transport_and_execution_injection_without_echoing_values` |
| Direkter Transport mit ungültigem Block; unveränderte Kerngrenze | T: `test_catalog_rejects_noncanonical_blocks_before_any_socket`, `test_core_boundary_remains_exact_before_any_socket` |
| Doppelstart/-read, zwei Verbraucher, alte Schritte, Refresh während Anfrage | A: `test_two_parallel_starts_do_not_reset_first_read_deadline_or_budget`, `test_two_parallel_http_reads_reserve_and_send_once`, `test_cancelled_http_consumer_and_reload_cannot_replay_reserved_read` |
| Start ohne Read; erste 59,999-/60-s-Schranke | R: `test_first_read_is_due_at_exactly_sixty_seconds_without_waiting`; A: `test_read_due_boundary_old_steps_and_reviews_never_replay` |
| Folgefrist ab abgeschlossener Antwortspeicherung | R: `test_interval_starts_after_response_and_storage_complete`; A: `test_next_interval_includes_transport_and_persistence_time` |
| Reservierung überschreitet Frist oder Stop/Zielwechsel vor Socket | R: `test_slow_reservation_over_deadline_consumes_budget_without_socket`, `test_reservation_race_consumes_attempt_without_read` |
| Pflichtbewertung und continue/finish/anomaly | R: `test_review_ends_run_without_changing_device_answer`; A: Loopback-Zyklustest und `test_operator_review_changes_state_not_raw_answer_or_network` |
| Fehler erster/zweiter Anfrage, kein Retry, Byteanzahl/Rohworte | R: `test_transport_failure_stops_without_retry_and_redacts_exception`, `test_core_data_error_preserves_raw_words_and_blocks_remaining_plan`, `test_storage_failure_retains_reservation_and_recovery_never_replays`; A: `test_transport_errors_keep_previous_answers_and_never_retry` |
| Fehlerpersistierung fällt aus; Reservierung und Recoveryblockade | R: `test_storage_errors_block_every_following_action`, `test_storage_failure_retains_reservation_and_recovery_never_replays` |
| Harter Fehler gegen gleichzeitigen Stop/Ablauf | R: `test_stop_sets_event_before_lock_and_preserves_inflight_result`, `test_deadline_during_response_keeps_hard_error_and_releases_owner`; S: `test_concurrent_operator_stop_and_error_finish_never_soften_failure` |
| Zählerprogression nur bei gleichem Fingerprint | R: `test_counter_progression_checks_previous_run_with_same_fingerprint`, `test_counter_evidence_of_another_target_is_not_compared` |
| Prozessabbruch, Neustart/Restore, alte ID bleibt gesperrt | R: `test_process_exit_after_runner_reservation_preserves_budget_for_locked_recovery`; A: `test_lifespan_recovery_after_reservation_preserves_budget_and_acknowledgement_starts_nothing`; S: v2-Restoretest unten |
| Collector-Join einschließlich letzter Antwort und Fehler | R: `test_real_collector_hands_ownership_to_runner_only_after_final_response` |
| Join-Timeout und konkurrierender echter Prozess | R: `test_collector_join_timeout_does_not_open_diagnostics`, `test_runner_rejects_actual_competing_process_without_overwriting_foreign_state`; C: `test_collector_rejects_actual_competing_process_without_client_access` |
| Keine Collectorinstanz, verwaister/unsauberer Kernzustand | R: `test_persisted_unclean_core_state_blocks_start_without_collector`, `test_clean_persisted_core_stop_permits_diagnosis_without_restart` |
| Stop/Ablauf bei laufender Anfrage bzw. ohne Browser | R: `test_stop_sets_event_before_lock_and_preserves_inflight_result`, `test_watchdog_expires_without_any_browser_action_or_read`; A: `test_deadline_without_browser_reads_ends_run_and_never_starts_monitoring` |
| Alle Collectorstartpfade ohne Budget-/Zustandsänderung blockiert | C: `test_diagnostic_blocker_survives_restart_without_collector_mutation`, `test_diagnostic_blocker_is_checked_under_os_ownership` |
| Kern-/Diagnosefehler nicht durch Neustart oder neue Aktion umgehen | R: `test_persisted_unclean_core_state_blocks_start_without_collector`; C: vorgenannte Blockadetests; A: Lifespan-Recoverytest |
| Ursachenquittierung startet weder alten Lauf noch Monitoring | A: `test_data_stop_keeps_invalid_core_raw_words_and_blocks_new_plan_until_acknowledged`, Lifespan-Recoverytest; C: `test_acknowledged_diagnostic_error_stays_terminal_until_explicit_collector_resume` |
| Collector-Erstfrist nach Diagnose auch in Recovery | C: `test_diagnostic_history_delays_first_read_in_normal_and_recovery_paths` |
| v1-Migration/Restore erhält Minutenzeilen und Backupquelle | S: `test_v1_upgrade_preserves_every_historical_column`, `test_failed_v1_migration_rolls_back_schema_and_history`, `test_v1_restore_migrates_only_copy_and_preserves_complete_history` |
| v2-Backup erhält Diagnosen und alle Steuerrevisionen | S: `test_v2_restore_preserves_plans_answers_all_control_revisions_and_blockers`; jetzt echte save/get/list-Steuerdokumente mit unterschiedlichen Vor-/Test-/Rückstellwerten statt SQL-Platzhalterdokumenten |
| Backupversion 0/zukünftig abgewiesen, Neuaufbau weiter möglich | S: `test_restore_rejects_unsupported_version_without_touching_backup`, `test_fresh_migration_failure_also_rolls_back_v1_tables`; frische Stores in allen Abnahmen |
| Origin-/Headerpflicht und gültiger Same-Origin-Auftrag | A: `test_every_new_mutation_enforces_csrf_before_any_effect`, `test_valid_same_origin_reaches_domain_validation_not_csrf` |
| Unvollständiger START und unbewiesene Betreibertexte | A: `test_control_complete_revision_cycle_is_offline_and_never_executable`, `test_operator_fallback_claims_and_blank_evidence_do_not_authorize_control` |
| Vollständiger synthetischer Steuerentwurf bleibt nicht ausführbar | A: `test_control_complete_revision_cycle_is_offline_and_never_executable` |
| Sensorblocker bleibt trotz Texten und Revisionen | A: `test_sensor_blocker_survives_operator_approval_and_revision` |
| Veraltete Steuerrevision überschreibt keine früheren Werte | A: `test_control_complete_revision_cycle_is_offline_and_never_executable`, `test_two_parallel_control_updates_commit_one_immutable_revision` |
| Ungültiger Steuerkandidat/Felder/FC/Dauer/Budget/Textlänge ohne Speicherung | A: `test_invalid_control_creation_leaves_no_saved_plan_or_device_effect`, `test_nested_control_draft_validation_is_strict_and_keeps_previous_revision`, `test_control_models_forbid_injected_execution_fields` |
| Ziel-/Quell-/Katalogwechsel invalidiert alten Plan | A: `test_changed_or_invalid_binding_is_rejected_before_socket`; R: `test_detected_binding_change_ends_active_run_even_if_target_is_restored` |
| Fehlender Host/falsche Unit/Simulator mit anderem Ziel | R: `test_missing_host_or_wrong_unit_blocks_before_socket`, `test_simulator_source_requires_exact_ipv4_loopback`; A: `test_invalid_deployment_target_also_blocks_plan_creation` |
| Defekter Katalog sperrt Diagnose, nicht Kernsammler | A: `test_broken_catalog_does_not_prevent_real_core_collector_cycle`; T: `test_broken_catalog_blocks_diagnostics_but_not_core_reads` |
| Private Speicher-/Transportfehler nicht in API/Download | A: `test_storage_errors_use_safe_503_without_exception_or_path`, `test_transport_errors_keep_previous_answers_and_never_retry`, Loopback-Zyklustest mit Exportprojektion |
| Alter Inventarbeleg mit anderer Zielbindung bleibt historisch sichtbar | A: `test_catalog_latest_response_marks_changed_target_without_disclosing_binding`, `test_latest_evidence_ignores_unread_plans_and_updates_both_core_words` |

Die Tabelle bezeichnet synthetische Verbraucherabnahmen, keine unabhängige
Prüfung privater Originalquellen. Die zusätzliche reproduzierbare
Browser-/Screenshotabnahme **#38** und Paket-/Wheel-Laufzeitabnahme **#39**
bleiben offen. Windows-Prozesssperren belegen nicht den Linux-/Unraid-Pfad.

## 15.10.2026 – Issue #38: reale Offline-Browserabnahme

**Eigene synthetische Offline-Abnahme, keine Geräte- oder Herstellerprüfung.**
Ausgangsstand: gemergtes #37, Commit `a62799c`. Keine private `.env` geändert
oder als Testziel übernommen, kein bestehender Anlagen-Collector verwendet,
keine echte Zieladresse und kein Schreibtelegramm. Keine Produktionsänderung nötig.

### Umgebung und reproduzierbarer Aufbau

- CPython **3.12.9**, uv **0.12.2**, Node **26.7.0**, npm **12.0.2**;
  Abhängigkeiten aus `uv.lock` und `package-lock.json`.
- Die bestehende `.venv` war unter Windows gesperrt. Der erste
  `uv sync --locked --python 3.12.9` scheiterte mit Zugriff verweigert.
  Anschließend derselbe gesperrte Satz über `UV_PROJECT_ENVIRONMENT` in einer
  separaten temporären Umgebung erfolgreich installiert. Keine Nutzerprozesse beendet.
  Die Standardumgebung anschließend mit `uv sync --locked` wieder synchronisiert.
- API ausschließlich mit Prozess-Overrides: `MODBUS_HOST=127.0.0.1`,
  `MODBUS_PORT=1502`, `MODBUS_UNIT_ID=255`, `REGISTER_PROFILE=core`,
  `COLLECTOR_ENABLED=false`, leeres `COLLECTOR_MAX_REQUESTS`,
  `DIAGNOSTICS_SOURCE=simulator` und eigenem temporären `DATA_DIR`.
  Dieser Datenpfad blieb bei sämtlichen API-Neustarts identisch.
- Uvicorn auf Loopback-Port 8000; `npm run dev -- --host 127.0.0.1`
  meldete tatsächlich `http://127.0.0.1:5173/`. Genau diese URL wurde bedient.
  Chromium **155.0.0.0**, Desktopviewport 1440 px und Mobilviewport 390 × 844 px.
- Der vorhandene `ModbusSimulator(catalog=True, port=1502)` lief als
  Loopback-Server in der temporären Prüfsitzung. Seine vorhandene
  `received_requests`-Momentaufnahme lieferte den Transportnachweis.
  Das ist dieselbe Serverimplementierung wie die CLI, keine neue Diagnose-/Log-API.
  Faultwechsel durch kontrolliertes Beenden und neue Instanz mit `fault="exception"`.
- Für kontrollierte spätere API-Neustarts wurde nur temporär ein Uvicorn-Wrapper
  mit `server.should_exit` über lokale Standardeingabe verwendet.
  Keine Zeitgrenze, Uhr, Produktionskonfiguration oder App-Route verändert.

### Tatsächlich bediente Oberfläche

Übersicht/Diagnose, Kopf und Erfassungsstatus bleiben erreichbar. Alle **199**
Register über vier Seiten mit **50/50/50/49** unterschiedlichen Auswahlen erreicht.
`Aussen_Ist`, `33408` und `8280` ergeben denselben Eintrag. Bestätigt-Filter
zeigt fünf Kernworte; ein absichtlich fehlender Suchbegriff zeigt null Treffer.
Unbekannte Interpretation bleibt „Einheit ungeklärt“, `write_support: unknown`.
START/SOLL getrennt geöffnet, ohne FC03-Auswahl oder bestätigten Stellweg.

Bei 390 px sind `innerWidth` und Dokumentbreite beide **390 px**; die
Katalogtabelle hat lokal **342 px** Platz bei **690 px** Scrollinhalt.
Detail/Formular stehen darunter; Buttons und Eingaben bleiben bedienbar.
Tab vom Suchfeld erreicht den Filter mit sichtbarem grünem **3-px-Fokusring**.
Die bestehende mobile Übersicht zeigt vier leere Kernkarten, keine Diagnosewerte
als Kernmessungen.

Bereinigte Screenshots der tatsächlich laufenden Oberfläche:

| Beleg | Screenshot |
|---|---|
| Desktopinventar und Suche | [Desktopinventar](issue38/desktop-inventar.png) |
| Mobiles Inventar, lokal scrollbare Tabelle | [390-px-Inventar](issue38/mobil-inventar.png) |
| Mobiles vollständiges synthetisches Formular | [390-px-Formular](issue38/mobil-formular.png) |
| Gespeichertes Rohwort, Alter und Bewertung | [390-px-Rohbeleg](issue38/mobil-rohbeleg.png) |
| Zweites/drittes Rohwort, keine physikalische Interpretation | [Desktopresultat](issue38/desktop-ergebnis.png) |
| Zweiter Tab, sichtbarer Revisionskonflikt | [Konflikt](issue38/desktop-konflikt.png) |
| Bewusster Stopp ohne Read | [Manueller Abbruch](issue38/desktop-abbruch.png) |
| Recovery nach tatsächlichem Prozessabbruch | [Unterbrechung](issue38/desktop-unterbrochen.png) |
| Harter Fehler mit deutscher Meldung | [390-px-Protokollstopp](issue38/mobil-protokollstopp.png) |
| Fehlerbeleg mit Byteanzahl und Fehlercode | [Protokollbeleg](issue38/desktop-protokollfehler.png) |
| Reale Gesamtfrist bei geschlossenen Browser-Tabs | [600-s-Watchdog](issue38/desktop-watchdog.png) |

### Dreierplan, echte Wartezeiten und Persistenz

Exakt `register:4098`, `register:4099`, `register:33408` gewählt.
Vor Start zeigt der gespeicherte Serverplan **4098/1, 4099/1, 33408/1**,
drei Anfragen, FC03/255, 3-s-Deadline, 60-s-Abstände und 600-s-Gesamtfrist.
Refresh vor Start erhält den Plan: null Requests. Start mit ausdrücklicher
Leserbestätigung öffnet nur den Prüfmodus: weiterhin null Requests.
Countdown und gesperrten Read vor Freigabe tatsächlich beobachtet.

| Gemessene UTC-Differenz aus SQLite | Sekunden |
|---|---:|
| Laufstart bis erste Reservierung | 63,400817 |
| Erster Antwortabschluss einschließlich Speicherung bis zweite Reservierung | 62,952306 |
| Zweiter Antwortabschluss einschließlich Speicherung bis dritte Reservierung | 61,155190 |

Transportmomentaufnahme exakt, keine weiteren Requests durch Mount, Refresh,
Bereichswechsel, GET, Export oder Neustart:

```text
(255, 3, 4098, 1)
(255, 3, 4099, 1)
(255, 3, 33408, 1)
```

Manuell ausgelöste Antworten **[0] / 0x0000**, **[173] / 0x00AD**,
**[65526] / 0xFFF6**, Budgets **1/3 → 2/3 → 3/3**. Jeweils `raw_only`,
„Simulator, synthetisch“, kein Außentemperaturwert. Vor der Bewertung fehlt
die nächste Readaktion; jede Antwort ausdrücklich mit „Geprüft, weiter“
bewertet. Zwischen Schritten und nach Abschluss Seite aktualisiert.
Letzte Bewertung ergibt `completed`; Monitoring bleibt deaktiviert.

Echte Browserdownloads `diagnostic-run.json` und `control-plan.json` erzeugt.
Jede Schritt-ID, jedes Rohwort, jeder UTC-Beginn/-Abschluss und jede Bewertung
des Laufdownloads wurden feldweise mit `diagnostic_requests` verglichen.
Steuerdownload stimmt vollständig mit der gespeicherten Revision überein.
Öffentliche Planprojektion enthält Alias `Simulator`, keinen Host, Datenpfad
oder Ziel-Fingerprint. **Null Zeilen in `observations`**, keine neuen Pollingsignale.
SQLite-Integritätsprüfung: **ok**.

Zusätzlich zuerst einen harten API-Prozessabbruch bei bereits abgeschlossenem
Lauf geprüft; danach kontrollierter Lifespan-Shutdown mit Exitcode **0**
und Neustart mit demselben Volume/Overrides. Abgeschlossener Export unverändert,
Budget **3/3**, Steuerrevision **3** wieder ladbar, null zusätzliche Requests.
Alter und synthetische Herkunft bleiben sichtbar, kein neuer Live-Prüfstatus.

### Steuerentwurf und Sicherheitszustände

START-Revision **1** nur mit Kandidat/Zweck angelegt: Quellen, Rückstellwert
und übrige Voraussetzungen konkret als fehlend sichtbar. Alle **20** Felder
anschließend mit ausdrücklich synthetischen Betreiberangaben ausgefüllt,
einschließlich Vor-/Test-/Rückstellwert, Dauer/Anfragebudget, Stop-/Prüf-/
Rückstellschritten und Ausfallverhalten. Revision **2** formal
`ready_for_review`, danach weitere Revision **3** gespeichert.
Frühere Revisionen **1/2/3** bleiben in SQLite erhalten.

Zweiter Tab übernimmt Revision 2, während erster Tab Revision 3 speichert:
veralteter Speicherversuch zeigt echten HTTP-409-`revision_conflict` statt
Überschreiben; Konflikteingabe bleibt vollständig erhalten.
Wiederladen verlangt ausdrückliche Übernahme des Serverstands.
UI/Download stets `execution_enabled:false`, Betreiberquelle nicht unabhängig
verifiziert, autonome START-/SOLL-Rückfalllücke auch bei vollständigen Feldern
sichtbar. Keine aktivierbare Schreibaktion oder vermeintliche Gerätefreigabe.

Zusätzlicher manueller Lauf ohne Read bewusst beendet: `cancelled`, **0/1**.
Weiterer geöffneter Lauf ohne Read durch tatsächliches Beenden des eigenen
API-Prozesses unterbrochen: nach Neustart sichtbar `interrupted`, **0/1**,
Ursachenquittierung startet nichts. Beide ohne zusätzliche Simulatoranfrage.

Weiterer Lauf ausschließlich geöffnet, beide eigenen Browser-Tabs geschlossen
und **601 reale Sekunden ab beobachtetem Start** ohne Read abgewartet:
Watchdog beendet ihn selbstständig mit `expired`, **0/1**, danach echte UI
wieder geöffnet und deutsche Ablaufmeldung gesehen. Keine Uhrinjektion,
keine vorgezogene Deadline, kein Browserpolling und null Simulatoranfragen.
Die gespeicherten UTC-Zeiten liegen 599,989267 s auseinander; dies ist die
Wanduhrdifferenz, nicht die monotone Fristmessung.
Laufende Anfrage/Stopprennen bleiben durch die zusätzlich erneut ausgeführte
automatisierte Matrix belegt; dafür keinen weiteren Browserread erzeugt.

**Zusätzlich injizierte Browserantwort, kein realer DB-Ausfall:** Ein GET des
aktuellen Laufs erhielt temporär HTTP 503 mit `detail.code=storage_unavailable`.
Die deutsche Meldung nennt den Code; der bereits gespeicherte Rohbeleg bleibt
sichtbar. Die temporäre Interception wurde anschließend entfernt.
Lade-/Leerzustände und während Mutationen gesperrte Buttons tatsächlich gesehen;
zu frühe Folgeklicks wurden vom Browser als deaktiviert abgewiesen und nicht
als zusätzliche Geräteversuche ausgeführt.

### Separater echter Exception-Lauf

Neuer Lauf, eigener Simulator im Exception-Modus auf demselben Loopback-Port.
Nach realer erster 60-s-Schranke genau einmal manuell gelesen:
**HTTP 200** mit terminalem Laufdokument **`stopped_protocol`**,
Fehlerklasse **`protocol_error`**, **9 empfangene Bytes**, keine Rohersatzwerte,
Budget **1/1**. UI: „Protokollfehler: sofort gestoppt, keine Wiederholung.
Antwort und Ursache klären und quittieren.“

Simulator exakt **`(255, 3, 4098, 1)`**, SQLite
`state=stopped_protocol`, `requests_reserved=1`, zunächst keine Quittierung.
Kontrollierter API-Shutdown/Neustart mit gleichem Volume erhält den Stopp,
null zusätzliche Requests; lesende Oberfläche verfügbar.

Explizite API-Konfliktprüfungen nach Neustart:

| Aktion | HTTP / `detail.code` |
|---|---|
| Dieselbe ID erneut starten | 409 / `diagnostic_stop_unacknowledged` |
| Dieselbe ID erneut lesen | 409 / `run_conflict` |
| Neuen Plan erstellen | 409 / `diagnostic_stop_unacknowledged` |
| Kernmonitoring fortsetzen | 409 / `diagnostic_stop_unacknowledged` |

Nichtleere Ursachenklärung über echte UI gespeichert: alte ID bleibt
`stopped_protocol`, weiterhin exakt ein Fehlerrequest, weder Collector noch neuer
Lauf gestartet. Faultsimulator vor weiterem Lauf separat kontrolliert beendet.
Insgesamt damit **vier** FC03-Anfragen: drei erfolgreich, eine Protokollexception.

### Tatsächlich ausgeführte automatisierte Prüfungen

In der isolierten CPython-3.12.9-Umgebung:

```text
python -m pytest tests/test_read_checks.py tests/test_diagnostics_api.py tests/test_control_plans.py
374 passed, 1 warning in 35.04s
python -m ruff check .
All checks passed!
npm run build
33 modules transformed; built in 1.06s
```

Die zusätzlich vorgeschriebene Gesamtsuite aus #29/#37 wurde ebenfalls ausgeführt:

```text
python -m pytest tests/test_read_checks.py tests/test_diagnostics_api.py tests/test_modbus.py tests/test_collector.py tests/test_storage.py tests/test_registers.py tests/test_app.py tests/test_end_to_end.py
644 passed, 1 warning in 82.06s
```

Erster Gesamtlauf: **2 failed, 642 passed, 1 warning in 83.87s**.
Die beiden bestehenden E2E-Tests entfernten `MODBUS_HOST`, ließen aber
`DIAGNOSTICS_SOURCE=simulator` geerbt und lasen mangels Isolation `.env` als
Settings-Fallback. Das führte zur Settings-Validierungsablehnung vor einer
Anlagenanfrage, nicht zu einem Gerätefehler. In `tests/test_end_to_end.py`
deshalb das vorhandene Fixturemuster aus `test_app.py` übernommen:
explizite isolierte Deploymentvariablen und `Settings(_env_file=None)`.
Beide E2E-Verhaltenstests unverändert; kein Fehler unterdrückt oder Erwartungswert
umgepinnt. Der obige grüne Gesamtlauf lief absichtlich erneut mit geerbter
Simulator-Umgebung. Ruff nach dieser Korrektur ebenfalls erfolgreich.

Starlette meldet wie zuvor das veraltete `anyio.abc.BlockingPortal`-Alias.
`npm ci` erfolgreich, aber bestehendes blockiertes esbuild-Installationsskript
und **eine hohe Vite-Sicherheitslücke** gemeldet. `npm audit --json` bestätigt
den installierten direkten Vite-Stand **6.2.2**, unter anderem Windows-
Dateizugriffslücken; angebotene Korrektur **6.4.4**. Kein automatisches Upgrade
oder `audit fix --force` im Abnahmeauftrag. Devserver nur auf Loopback;
Abhängigkeitskorrektur vor nicht vertrauenswürdiger Bereitstellung erforderlich.
Siehe [Vite-Advisory](https://github.com/advisories/GHSA-fx2h-pf6j-xcff).

Keine neuen permanenten Testfälle: bestehende Verhaltensmatrix wiederverwendet,
nur die dabei tatsächlich gebrochene E2E-Umgebungsisolation korrigiert.
Die zusätzliche Leistung dieses Issues ist echte Browser-/Zeit-/Transport-/
Download-/Persistenzabnahme, nicht ein Test- oder Quelltextabgleich als
Oberflächenersatz. Wheel/gebaute Auslieferungsoberfläche und Container bleiben
#39; Linux/Unraid, Langzeitbetrieb und Geräteverträglichkeit sind hier nicht
geprüft. Private Originalquellen nicht unabhängig eingesehen.

Abschluss: fünf persistierte Läufe (`completed`, `cancelled`, quittiertes
`interrupted`, quittiertes `stopped_protocol`, `expired`), insgesamt vier
verbrauchte Reservierungen, null Kernbeobachtungen, SQLite `ok`, Collector
`unconfigured` und deaktiviert. Eigene API mit Exitcode 0 und Simulator
kontrolliert beendet. Der eigene npm-/Vite-Prozessbaum musste unter Windows
nach erfolgloser normaler Beendigung gezielt beendet werden. Temporären
Wrapper und lokale synthetische Testdateien entfernt; nur bereinigte
Oberflächenscreenshots bleiben im Repository.

## 15.10.2026 – Issue #39: Wheel und gebaute Laufzeitoberfläche

Reine Offline-Paketabnahme auf Basis des zusammengeführten Stands von #37/#38.
Keine Geräteadresse konfiguriert, kein Simulator gestartet, kein Collector
aktiviert, keine Geräteanfrage. Keine privaten Originalquellen unabhängig
eingesehen. Benutzerangaben und historische Gerätebelege bleiben davon getrennt.
Voraussetzungen: [automatisierte Matrix #37](#15102026--issue-37-automatisierte-diagnose-gesamtabnahme),
[Browser-/Persistenz-/Fehlerbelege #38](#15102026--issue-38-reale-offline-browserabnahme).
Zugehörige abgeschlossene PRs: [#47](https://github.com/lum1nat0r/sommerauer-monitor/pull/47)
und [#48](https://github.com/lum1nat0r/sommerauer-monitor/pull/48).
Die früheren Einträge beschreiben ihren damaligen Stand, keine nachträglich
umdatierte Paketprüfung. Der dort historische Pfad `config/register_catalog.json`
bleibt erhalten; heute ausschließlich `backend/resources/register_catalog.json`.

### Wheel: tatsächliches Artefakt und isolierter Import

Verwendet: **CPython 3.12.9**, **uv 0.12.2**, **Node 26.7.0**, **npm 12.0.2**.
Der vorgefundene Projektinterpreter war 3.12.13; ein erster Wheelbuild damit
zählt nicht als verbindlicher Nachweis. Der Wechsel der bestehenden `.venv`
scheiterte unter Windows an „Zugriff verweigert“. Deshalb frische temporäre
Buildumgebung mit 3.12.9 außerhalb des Repositories angelegt und
`UV_PROJECT_ENVIRONMENT` explizit darauf gesetzt, keine fremden Prozesse beendet.

Tatsächlich erfolgreiche Befehlsfolge (temporäre Orte hier nur als Platzhalter):

```sh
uv venv --python 3.12.9 <buildenv>
uv sync --locked --python 3.12.9
uv build --wheel --python 3.12.9
uv venv --python 3.12.9 <runtime>
uv pip install --python <runtime-python> <ermitteltes-wheel>
uv export --locked --no-dev --no-emit-project --format requirements-txt --output-file <requirements>
uv pip sync --python <runtime-python> <requirements>
uv pip install --no-deps --python <runtime-python> <ermitteltes-wheel>
```

Wheel per Verzeichnisauflistung ermittelt, nicht aus Version/Dateinamen geraten:
**`sommerauer_monitor-0.1.0-py3-none-any.whl`**.
Die erste Installation löste Abhängigkeiten auf; anschließend ausdrücklich mit
dem Export aus `uv.lock` synchronisiert und das konkrete Wheel ohne Neuauflösung
installiert. Nach dieser Synchronisierung den Import erneut ausgeführt.
Frische Runtime, kein editable Projekt, CWD außerhalb des Repositories,
`PYTHONPATH`/`PYTHONHOME` entfernt, zusätzlich Python-Isolationsmodus `-I`:

```sh
<runtime-python> -I -c "from backend.catalog import load_catalog; print(len(load_catalog().entries))"
```

Erwartet **199**, tatsächlich stdout **`199`**. `backend.catalog.__file__`
verweist auf `runtime/Lib/site-packages/backend/catalog.py`, nicht den Checkout.
`backend` ist ein Namespacepaket (`backend.__file__` ist `None`); deshalb den
konkreten Modulpfad geprüft. Ressource per `importlib.resources` aus derselben
installierten Umgebung gelesen, SHA-256 mit Buildinput verglichen:

```text
a4f8b8c47ca99d496e8c2778286611a180c53f915a16438d41b794ff6ac43c09
```

Beide Hashes identisch. Alle 199 Zuordnungen unverändert; keine zweite
Katalogdatei oder Fallbackquelle angelegt. Das Backend-Wheel enthält nicht die
Frontend-Builddateien. Keine Paketkorrektur erforderlich.

### Gebaute Oberfläche: tatsächlich bedient, nicht Vite

`npm ci` erfolgreich; bestehende Warnung zum blockierten esbuild-Installationsskript.
`npm run build` inklusive TypeScript erfolgreich: **33 Module**, **982 ms**,
`index-B5MTvnbq.js` (242.295 Bytes), `index-C1PgQ3gu.css` (10.313 Bytes).
Vite 6.2.2 unverändert; der in #38 belegte Sicherheitsbefund bleibt offen,
kein Abhängigkeitsupgrade in dieser Paketabnahme.

Buildinhalt ohne Wheel in das Geschwisterverzeichnis `static` des installierten
Backendpakets kopiert, entsprechend dem vorhandenen Dockerfile-/StaticFiles-
Layout. Uvicorn mit dem frischen Runtime-Python und `-I` außerhalb des Checkouts
auf Loopback gestartet. Explizit `MODBUS_HOST=""`, `COLLECTOR_ENABLED=false`,
`DIAGNOSTICS_SOURCE=device`, eigenes temporäres `DATA_DIR`; dort keine `.env`.
Keine private Deploymentdatei oder vorhandene Datenbank verwendet.

Standard-Browserstart scheiterte am Browserdaemon; erfolgreich mit lokalem
Edge über dieselbe Browserautomation geprüft. Tatsächlich:

- Übersicht geöffnet, zu Diagnose und zurück gewechselt, Katalog neu geladen.
- Katalog-GET **200**, **199 Einträge**; `/api/config`:
  `host_configured:false`, `collector_enabled:false`, `diagnostics_source:device`.
  „Anlage-aktuell (Gerät)“ ist dabei Quellenmodus, kein Verbindungsnachweis.
- HTML, gebaute JS-/CSS-Dateien jeweils **200** vom Uvicorn-Server.
  Kein Vite-/Devserver verwendet.
- Nach **33408** gesucht: genau `Aussen_Ist`, Details `documented_raw`,
  Interpretation/Einheit ungeklärt, kein gespeicherter Diagnosebeleg.
- Register ausgewählt, synthetischen Zweck eingegeben, bewusst Planung geklickt:
  **409 `target_not_configured`**, deutsche Konfliktmeldung sichtbar.
  Kein Lauf erzeugt, keine Start-/Readaktion erreichbar; kein automatischer Retry.
  Der einzige App-POST in dieser Browsersitzung war dieser Planversuch.
- START und SOLL separat gewählt und jeweils „Neuen Entwurf vorbereiten“:
  Kandidatenfeld **`control:buffer.start`** bzw. **`control:buffer.target`**.
  `execution_enabled:false` und Quellen-/Freigabe-/Rückfallgrenzen sichtbar.
  Keine Entwürfe gespeichert; Persistenzbeweis bleibt der reale Nachweis aus #38.
- Reload und erneuter Diagnosewechsel: Katalog weiter erreichbar.

Bereinigte Screenshots der tatsächlich gebauten Oberfläche:
[Suche/Details und hostlose Blockade](issue39-hostlos.png),
[SOLL-Offlinevorbereitung](issue39-steuerentwurf.png).
Browserfremde Edge-Neutab-Netzwerkfehler sind keine App-/Gerätefehler;
ein fehlendes Favicon lieferte 404, ohne die Bedienung zu beeinträchtigen.

SQLite danach: Integrität **`ok`**, jeweils **0 Zeilen** in `observations`,
`diagnostic_runs`, `diagnostic_requests`, `control_plans`. Keine Minutenhistorie
verändert und keine Reservierung verbraucht.

### Containergrenze und zusätzliche Prüfungen

**Containerlauf lokal ungeprüft: Docker nicht verfügbar**.
`docker version` liefert CLI **29.4.1**, Kontext `desktop-linux`, aber keine
Verbindung zur Docker-Linux-Engine (Named Pipe nicht vorhanden, Exitcode 1).
Deshalb weder Containerbuild noch Containerstart/API-Abnahme behauptet.
Statischer Befund: Das bestehende Dockerfile kopiert `backend` einschließlich
Ressource in den Backendbuild und die Runtime sowie `dist` nach `static`;
das ist kein Containerlaufbeweis. Kein neues Containerkonzept erforderlich.

In der temporären, aus `uv.lock` aufgebauten CPython-3.12.9-Buildumgebung:

```text
python -m pytest
707 passed, 1 warning in 82.83s
python -m ruff check .
All checks passed!
```

Bekannte Starlette-/AnyIO-DeprecationWarning, kein Testfehler. Keine neuen
permanenten Tests oder Produktionscodeänderungen erforderlich: bestehende
Verhaltenssuite plus tatsächlicher Paket-/Browser-Smoke.
Aufruferprüfung in Backend/Tests/Dokumentation: ausschließlich Paketloader/
kanonische Ressource; alte `config/`-Nennung nur als historischer Ergebnisbeleg.
Kein wieder eingeführter Direktleser, Kompatibilitätsalias oder Registereditor.
Dokumentation aktualisiert, keine zweite normative Vertrags-/Katalogkopie.

Browser beendet; eigener hostloser Uvicorn-Prozess unter Windows per
`terminate()` beendet (Exitcode **1**, kein behaupteter geordneter Lifespan-Shutdown).
Temporäre Umgebungen, Buildkopie, Datenbank und Logs anschließend entfernt;
nur bereinigte Screenshots und dieser Bericht bleiben.
Kein Tag, Release, Image-/Registry-Push, Deployment oder Unraid-Zugriff.
Linux-/Unraid-Laufzeit, Langzeitbetrieb, zusätzliche Registerinterpretationen
und autonome START-/SOLL-Rückstellung bleiben ungeprüft. Neue Live-Lesearbeit
verlangt einen eigenen endlichen öffentlichen Alias-/privaten Zielplan;
echte Steueränderungen zusätzlich konkrete Betreiberfreigabe.

## 15.10.2026 – Issue #29: Epicabschluss

Ausgangsstand: `main` nach Merge von PR #49 (`93cc7a5`).
Alle Unterissues #30–#39 sind auf GitHub geschlossen und ihre PRs zusammengeführt.
Der Abschluss ergänzt nur Dokumentation, keinen zweiten Implementierungspfad.
Issue-Text und Kommentare werden nicht verändert; die Schließreferenz steht im
Abschluss-PR. Historische offene Checkboxen im Epic sind keine neue Aussage
über den inzwischen zusammengeführten Implementierungsstand.

| Paket / Epic-Anforderung | Zusammengeführter PR | Nachweis in diesem Bericht |
|---|---|---|
| #30: 199 Katalogeinträge, 194 Rohkandidaten, sichere Blockauswahl | [#40](https://github.com/lum1nat0r/sommerauer-monitor/pull/40) | Abschnitt #30: validierter Snapshot, negative Auswahlfälle |
| #31: Journal, dauerhafte Reservierung, Migration/Restore | [#41](https://github.com/lum1nat0r/sommerauer-monitor/pull/41) | Abschnitt #31; zusätzliche Restore-/Rennnachweise in #37 |
| #32: enger FC03-Pfad und synthetischer Katalogsimulator | [#42](https://github.com/lum1nat0r/sommerauer-monitor/pull/42) | Abschnitt #32: Auswahl- und Protokollgrenzen |
| #33: exklusiver Besitzer, manuelle endliche Reads, Stopps/Recovery | [#43](https://github.com/lum1nat0r/sommerauer-monitor/pull/43) | Abschnitte #33/#37: Zweitprozess, Stop-/Reservierungs-/Joinrennen |
| #34: reine Bewertung, unveränderliche Steuerrevisionen | [#44](https://github.com/lum1nat0r/sommerauer-monitor/pull/44) | Abschnitte #34/#37/#38: Konflikte, Export nicht ausführbar |
| #35: Lifespan/API, bereinigte Projektionen, CSRF, wirkungsfreie GETs | [#45](https://github.com/lum1nat0r/sommerauer-monitor/pull/45) | Abschnitte #35/#37: API-/Sicherheitsverträge |
| #36: Dashboard, Lese-/Bewertungsfolge und Steuerformulare | [#46](https://github.com/lum1nat0r/sommerauer-monitor/pull/46) | Abschnitte #36/#38: Bedienung, Fehler-/Lade-/Konfliktzustände |
| #37: vollständige automatisierte Abnahmematrix | [#47](https://github.com/lum1nat0r/sommerauer-monitor/pull/47) | Abschnitt #37 mit konkreter Testzuordnung; Gesamtsuite unten erneut ausgeführt |
| #38: reale Browser-/Persistenz-/Fehlerabnahme | [#48](https://github.com/lum1nat0r/sommerauer-monitor/pull/48) | Abschnitt #38: Screenshots, echte 60-s-Schranken, Downloads/SQLite, Neustart |
| #39: installiertes Wheel, gebaute Oberfläche, Containergrenze | [#49](https://github.com/lum1nat0r/sommerauer-monitor/pull/49) | Abschnitt #39: isolierter Import/Hash, StaticFiles-Browser, Dockergrenze |

**Beim Epicabschluss selbst ausgeführt:**

- CPython **3.12.9**, uv **0.12.2**, Node **26.7.0**, npm **12.0.2**.
- Frische temporäre Projektumgebung mit `uv sync --locked --python 3.12.9`.
  Die vorhandene `.venv` blieb unverändert.
- Gesamtes `pytest`: **707 passed, 1 warning in 88.07s**, einschließlich aller
  acht im Epic verlangten Testdateien und der 63 Steuerplantests.
  Bekannte Starlette-/AnyIO-DeprecationWarning, kein Testfehler.
- `ruff check .`: **All checks passed!**
- `uv build --wheel --python 3.12.9`: erfolgreich,
  `sommerauer_monitor-0.1.0-py3-none-any.whl`.
- `npm run build`: TypeScript erfolgreich, **33 Module**, **1,10 s**.
- Separater API-Laufzeit-Smoke mit explizit leerem `MODBUS_HOST`,
  `COLLECTOR_ENABLED=false`, temporärem `DATA_DIR`: `/api/config` **200**,
  `host_configured:false`, `collector_enabled:false`; Collector `unconfigured`,
  OpenAPI **200**. Katalog **199**; Auswahl 4098, 4099, 33408 ergibt exakt
  drei Einzelblöcke, kein zusammengefasster Nachbarblock.

Ein erster Smoke-Aufruf scheiterte wegen fehlendem FastAPI in der bestehenden
Umgebung. Ein weiterer Versuch mit Python-seitigem Settingsersatz isolierte
die App-Konfiguration nicht wirksam: die API meldete die vorhandene
Deploymentkonfiguration und den gespeicherten Zustand `completed`.
Dieser Versuch zählt nicht als Offline-Isolationsnachweis; Geräteverkehr wurde
dabei nicht mitgeschnitten und wird deshalb nicht ausgeschlossen oder als
Live-Nachweis gewertet. Danach wurde der oben genannte Smoke vor jedem
Backendimport über explizite Umgebungsvariablen isoliert und erfolgreich geprüft.
Keine Schreibfunktion aufgerufen, keine private Konfiguration geändert.

Die Browser-/Wheelinstallationsbelege aus #38/#39 sind bestehende Nachweise,
keine in diesem Abschluss wiederholten Sitzungen. Kein neuer Browser-,
Container- oder Unraid-Nachweis behauptet. Docker-Engine war bei #39 nicht
erreichbar; diese dokumentierte, im Epic erlaubte Containergrenze bleibt offen.
Bekannter Vite-Sicherheitsbefund, Linux-/Unraid-Deployment, Langzeitbetrieb,
neue Registerinterpretationen sowie Stellweg und autonomer Rückfall (#18)
bleiben außerhalb dieses Abschlusses. Keine Gerätefreigabe, kein Release,
kein Deployment und kein Dauerbetrieb aus dem Epicabschluss ableiten.

## 15.10.2026 – Version 0.2.0 vorbereitet

Nutzerauftrag: aktuellen `main`-Stand als Version 0.2.0 vorbereiten.
Ausgangspunkt: `b769952`, lokal und auf `origin/main` identisch, sauberer
Arbeitsbaum. Umsetzung auf `release/0.2.0`, keine Funktionsänderungen.
Python-/npm-Paket und Lockdateien, FastAPI-Metadaten, Docker-Buildvorgabe,
Compose-Dateien, Unraid-Template und öffentliche Deploymentanleitung auf
0.2.0 angehoben. Historische Abnahmeversionen und synthetische Testdaten
bleiben unverändert.

Tatsächlich ausgeführte Offline-Prüfungen:

- `uv sync --locked`: erfolgreich, installiertes Paket 0.2.0.
- `uv run ruff check .`: erfolgreich.
- `uv run pytest`: **707 bestanden**, eine DeprecationWarning aus
  Starlette/AnyIO; CPython **3.12.13**.
- `npm run build`: erfolgreich, 33 Module.
- `uv build --wheel --python 3.12.9`: erfolgreich,
  `sommerauer_monitor-0.2.0-py3-none-any.whl`.
- Separater In-process-Laufzeit-Smoke mit vor Backendimport explizit leerem
  `MODBUS_HOST`, deaktiviertem Collector, `DIAGNOSTICS_SOURCE=device` und
  temporärem Datenverzeichnis: installiertes Paket, OpenAPI und
  `/api/version` melden 0.2.0; `/api/health` HTTP 200,
  Collector `unconfigured`. Keine private Konfiguration geändert.

Repositoryvorgaben: kein Merge durch den Assistenten, kein neuer Tag und kein
GitHub-Release. Nach Betreiber-Merge ist `v0.2.0` auf dem zusammengeführten
Main-Commit der vorgesehene Auslöser für die vorhandene Image-Pipeline.
Kein neuer Container-, Unraid-, Browser- oder Live-Nachweis; keine Erfassung
oder Geräteänderung aktiviert. Der dokumentierte Vite-Sicherheitsbefund
bleibt unverändert.
