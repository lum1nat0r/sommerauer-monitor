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

Geprüft wurden nur die vorhandene öffentliche Registerreferenz und der statische
Registerkatalog (heute `docs/register_catalog.json`). Diese weisen 4098/1 (`Fehler_Min`), 4099/1
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

## 15.10.2026 – Domainaktionen hinter einem Reverse-Proxy

Betreiberbefund: Aktionen funktionieren beim IP-Zugriff, nicht über die eigene
Domain. Die reale Proxy-Konfiguration wurde nicht eingesehen; der TLS-/Host-
Unterschied ist lokal als passende Fehlerursache reproduziert, kein Befund
aus einem Zugriff auf das Deployment.

Vorher: In-process-Anfrage mit synthetischer HTTPS-Browser-Origin und interner
HTTP-Request-Adresse ergibt HTTP 403 `Same-origin request required`.
Korrektur: optionale private `PUBLIC_ORIGIN`, strikt als HTTP(S)-Origin ohne
Zugangsdaten, Pfad, Query, Fragment oder Wildcard validiert. Diese Freigabe
ergänzt den direkten Originzugriff; Schutzheader bleiben Pflicht. Compose-
Varianten, `.env.example` und Unraid-Template enthalten die Einstellung.
Keine neue CORS-Freigabe und kein ungeprüftes Vertrauen in Forwarded-Header.

Tatsächlich ausgeführte Offline-Prüfungen auf CPython 3.12.9:

- Gesamtes `pytest`: **727 bestanden**, eine bekannte
  Starlette-/AnyIO-DeprecationWarning. Regressionen prüfen erfolgreiche
  persistente Konfigurationsänderung über Proxy-Origin und Direktzugriff,
  Fremd-Origin/Scheme-/Port-/Suffix-Verwechslungen, fehlende Schutzheader,
  manipulierte Forwarded-Header, fehlende Freigabe und ungültige Konfiguration.
- `ruff check .`: **All checks passed!**
- Echter Uvicorn-Loopbackserver mit `--no-proxy-headers`, temporärem `DATA_DIR`,
  leerem Modbus-Ziel und deaktiviertem Collector: HTTPS-Browser-Origin bei
  internem HTTP-Host speichert die Anzeigezeitzone mit HTTP **200**; direkte
  Request-Origin ebenfalls **200**. Fremde Origin trotz gefälschter
  Forwarded-Header und fehlender Custom-Header jeweils **403**.
  Anschließendes GET bestätigt gespeichertes UTC, `host_configured:false`,
  `collector_enabled:false` und Collector `unconfigured`; die freigegebene
  Domain erscheint nicht in der API-Konfiguration.
- Beide Compose-Dateien als YAML sowie das Unraid-Template als XML geparst:
  gültig, `PUBLIC_ORIGIN` wird als optionale Containervariable weitergereicht.

Prüfungen in separater temporärer Pythonumgebung; der erste Versuch, die
bestehende Umgebung auf die vorgeschriebene Pythonversion umzustellen,
scheiterte an einem gesperrten Windows-Scripts-Verzeichnis. Anschließend die
lokalen Abhängigkeiten mit `uv sync --locked` wiederhergestellt; Python 3.12.13
und Imports von FastAPI/Uvicorn erfolgreich geprüft. Keine private
Deploymentkonfiguration verändert.

Grenzen: kein Zugriff auf die reale Domain, kein Browser-, Container-,
Unraid- oder Heizungsnachweis und keine Geräteanfrage für diese Korrektur.
Kein Tag/Release erstellt. Ein Image mit der Korrektur und die private
Originvariable müssen vor dem Einsatz auf Unraid bereitgestellt werden;
der bestehende Image-Tag wird nicht stillschweigend ersetzt.

## 15.10.2026 – Releasevorbereitung v0.2.1

Nutzerauftrag: Release mit dem aktuellen Stand v0.2.1. Basis ist `7cc1b40`
mit der zusammengeführten Reverse-Proxy-Origin-Korrektur aus PR #52.
Auf Branch `release/0.2.1` sind Paket-/Lockversionen, FastAPI-Metadaten,
Docker-/Compose-Vorgaben, Unraid-Template und Deploymentdokumentation auf
0.2.1 angehoben. Keine zusätzliche Funktionsänderung; historische Belege und
die VS-Code-Konfigurationsschemaversion bleiben unverändert.

Tatsächlich ausgeführte Offline-Prüfungen:

- `uv sync --locked` und `uv run ruff check .`: erfolgreich.
- `uv run pytest`: **727 bestanden**, eine Starlette-/AnyIO-DeprecationWarning;
  Testlauf auf CPython 3.12.13.
- `npm run build`: TypeScript und Vite erfolgreich.
- `uv build --wheel --python 3.12.9`: Wheel
  `sommerauer_monitor-0.2.1-py3-none-any.whl` erstellt.
- Separater In-process-Laufzeit-Smoke mit leerem Gerätehost, deaktivierter
  Erfassung und temporärem Datenverzeichnis: `/api/health` HTTP 200,
  Paketversion, OpenAPI und `/api/version` jeweils 0.2.1;
  Collectorstatus `unconfigured`. Keine Geräteanfragen.

Die Repositoryvorgaben untersagen dem Assistenten Merge und Tag-/Release-Erstellung.
Nach Betreiber-Merge des Release-PRs muss `v0.2.1` auf dem Main-Commit erstellt
und gepusht werden; erst dieser Tag startet die geprüfte GHCR-Pipeline für
`ghcr.io/lum1nat0r/sommerauer-monitor:0.2.1`.
Kein Image veröffentlicht oder dessen Abrufbarkeit behauptet. Kein neuer
Container-, Unraid-, Browser- oder Live-Nachweis; keine Deploymentänderung.

## 16.10.2026 – Diagnosefunktion zurückgebaut

Nutzerauftrag: Diagnose aus der Anwendung entfernen. Nach Hinweis auf das
verbindliche Verbot einer Historienumschreibung hat der Betreiber ausdrücklich
den Rückbau per Commit mit erhaltener Historie gewählt. Branch:
`remove/diagnostics`; Ausgangspunkt `8fd03f6`.

Diagnoseoberfläche, Diagnose-API, manuelle Katalog-Prüfläufe, Offline-Steuerpläne,
zugehörige Konfiguration, Tests und Abnahmebilder sind entfernt. Das bestätigte
Kernmonitoring bleibt erhalten; der Registerkatalog liegt wieder ausschließlich
als statische Referenz unter `docs/register_catalog.json`. Reverse-Proxy-Korrektur
mit `PUBLIC_ORIGIN` und Versions-/Deploymentkonfiguration 0.2.1 bleiben erhalten.
Alte Commits, Branches und Tags werden nicht umgeschrieben oder gelöscht.

Bestehende Datenbanken mit Schema 1 oder 2 bleiben verwendbar; Schema 2 wird
nicht heruntergestuft. Dort vorhandene zusätzliche Tabellen und Datensätze
bleiben unangetastet, ohne Diagnosefunktion in der Anwendung. Neue Datenbanken
enthalten nur Monitoringtabellen. Private Datenbanken wurden nicht geöffnet,
geändert oder gelöscht.

Tatsächlich ausgeführte Offline-Prüfungen:

- Isolierte CPython-3.12.9-Umgebung mit `uv sync --locked --python 3.12.9`;
  vorhandene Pythonumgebung nicht verändert.
- Gesamtes `python -m pytest -q`: **93 bestanden**, eine bekannte
  Starlette-/AnyIO-DeprecationWarning. Die Schema-1-/2-Regression prüft erhaltene
  Minutenwerte, weiteres Schreiben, Backup/Restore, pausierten Restorezustand
  und unveränderte Quelldaten einschließlich zusätzlicher alter Tabellen.
  Ein erster Lauf fand zwölf Proxytestfehler durch den mit der Diagnose
  entfernten Headerhelfer; der lokale Testhelfer ist wiederhergestellt.
- `python -m ruff check .`: **All checks passed!**
- `npm run build`: TypeScript und Vite erfolgreich, **28 Module**.
  `npm ci --ignore-scripts` scheiterte zuvor an einer gesperrten Windows-Binärdatei;
  `npm install --ignore-scripts --package-lock=false` stellte die Abhängigkeiten
  wieder her, mit Aufräumwarnungen zu gesperrten alten Binärdateien.
- Laufender Loopback-Simulator mit echtem FC03-Client und endlichem Sammler:
  **drei Kernanfragen**, **vier gespeicherte synthetische Beobachtungen**,
  Endzustand `completed`. Separater temporärer Datenpfad, keine Wiederaufnahme.
- Echter Uvicorn-Loopbackserver und gebaute Oberfläche: Gesundheit `ok`,
  Kernwerte 42/47/38 °C und 6079 Anlagen-Betriebsminuten sowie vier CSV-Zeilen.
  Diagnosepfade liefern **404** und fehlen in OpenAPI. Konfiguration über
  freigegebene synthetische Proxy-Origin **200**, Fremd-Origin **403**.
- Gebautes Dashboard in lokalem Chrome tatsächlich bedient und per Screenshot
  gesichtet: keine Diagnose-/Steuerplanbedienung, vier Messwertkarten,
  „Erfassung abgeschlossen“, Signalwechsel auf Puffer oben und Zeitraumwechsel
  auf eine Stunde. Bei 390 px kein horizontaler Überlauf; keine Browserfehler.
  Der Standard-Browserstart scheiterte zunächst; expliziter lokaler Chrome
  funktionierte. Eigene Browseransicht und Smokeserver anschließend beendet;
  temporäres Smokeskript entfernt.

Keine Live-Heizungsabfrage, kein Container-/Unraid-Lauf, kein Deployment und
kein neues Image/Release. Bereits veröffentlichte Images enthalten den Rückbau
nicht automatisch; vor einem Deployment ist ein neuer Build erforderlich.

## 18.10.2026 – Individuelle Modbus-Aufzeichnung (#55)

Quelle für den Importvertrag: öffentliches Betreiberbeispiel im Kommentar zu
Issue #55 (`Name;dezimaler Offset;interner Hexcode`, ohne Kopfzeile).
Kein privater Originalexport und keine Anlage unabhängig geprüft. Alle neuen
Prüfdaten, Namen und Betreibertexte waren synthetisch.

Implementiert: separate navigierbare Konfigurationsseite mit CSV-Entwurf,
farblich/textlich markiertem inkrementellem Abgleich, Aufzeichnungsauswahl und
Betreiber-Metadaten. Codebasierte Identität, Erhalt fehlender Zeilen und Texte,
Ablehnung mehrdeutiger Codes/Offsets, atomare revisionsgeschützte Speicherung,
No-op bei identischem Inhalt. Schema 1/2 wird additiv auf 3 erweitert, ohne
alte Tabellen oder Beobachtungen zu löschen. Nur vorhandene bestätigte Decoder
sind aktivierbar; CSV-Zeilen erzeugen weder Decoder noch Gerätefreigaben.

Der Sammler verwendet einen festen Snapshot pro Kerndurchlauf, überspringt
abgewählte Blöcke und speichert bei gemeinsam gelesenen Wörtern nur ausgewählte
Signale. 7010/7011 bleiben ein gemeinsam geschalteter Mehrwortzähler. Pause,
harte Stopps, Anfrage-/Wiederaufnahmebudget und Mindestabstände bleiben wirksam.
Mit Teilprofil kein automatischer Budgetreset ohne drei vollständige Kernzyklen.
Betreiber-Einheiten ändern weder Rohwerte noch Decoder-Einheiten.

Tatsächlich ausgeführte Offline-Prüfungen:

- CPython **3.12.9**, `uv` **0.12.2**, Node **26.12.0**, npm **12.2.1**.
  Abhängigkeiten mit `uv sync --locked --python 3.12.9` und `npm ci` installiert.
  Das zunächst installierte `uv` 0.13.1 wurde vor der Abnahme auf 0.12.2 korrigiert.
- `uv run pytest -q`: abschließend **148 bestanden**, eine bekannte
  Starlette-/AnyIO-DeprecationWarning. Schutzfälle für echte pausierte/gestoppte/
  wiederaufnehmende Collectorinstanzen ergänzt; einen bisherigen Test auf exakte
  Tabellennamen statt Nutzerverhalten entfernt.
  Abgedeckt: Import/Delta/Reihenfolge, Metadaten, Mehrwortfreigabe, Manipulation,
  echte konkurrierende CAS-Saves, SQLite-Fehler/Rollback, Schema-1-/2-Erhalt,
  Neustart, sichere Zyklusgrenze, leere Auswahl und unverändertes Retrybudget.
- `uv run ruff check .`: **All checks passed!**
- `npm run build`: TypeScript und Vite erfolgreich, **29 Module**.
- `uv build --wheel --python 3.12.9`: Wheel erfolgreich erstellt.
- Gitleaks über Backend, Frontendquellen, Tests und Dokumentation:
  **keine gefundenen Geheimnisse**; Betreiber-/Netzwerkdaten manuell ausgeschlossen.
- Gebaute Oberfläche durch echten Uvicorn-Loopbackserver ausgeliefert und im
  Chromium-Browser bedient: Upload → Tabelle bearbeiten → Speichern → bewusstes
  Fortsetzen → endlicher Simulatorlauf. Vor Upload bestand ein synthetischer
  vollständiger Kernzyklus; danach nur Kessel und Puffer oben ausgewählt.
  Insgesamt **fünf FC03-Anfragen** an den Loopback-Simulator, keine Wiederaufnahme,
  Endzustand `completed`. SQLite-Integrität **ok**.

| Signal | Beobachtungen vor Auswahländerung | Nach endlichem Folgezyklus |
|---|---:|---:|
| `boiler.temperature` | 1 | 2 |
| `buffer.top_temperature` | 1 | 2 |
| `buffer.bottom_temperature` | 1 | 1 |
| `boiler.operating_minutes` | 1 | 1 |

Die tatsächlichen Anfrageblöcke waren 4102/1, 28688/2, 36864/2, danach
4102/1 und 36864/2. Historische Zähler-/Puffer-unten-Werte blieben erhalten.
Trotz synthetischer Betreibereinheit „Testgrad“ blieben Kesselmessungen 42 °C.

Weitere tatsächliche Browserprüfungen:

- Upload ohne Speichern ließ Revision 0, Pausenzustand und Historie unverändert.
  Unbestätigte Zeilen waren sichtbar gesperrt; beide Zählercheckboxen schalteten
  gemeinsam. Neuladen erhielt Auswahl, Einheit und Beschreibung.
- Folgeimport ergänzte genau einen Eintrag und änderte einen Namen; fehlende
  Zeilen und Betreibertexte blieben erhalten. Neue/geänderte Zeilen standen mit
  Markierung oben. Umsortierter identischer Import hatte keine Änderungsmarker
  und erhöhte beim Speichern die Revision nicht.
- Widersprüchliche doppelte CSV-Zeile und ungültige UTF-8-Datei verständlich
  abgewiesen. Ein temporärer SQLite-Trigger erzwang einen realen Savefehler:
  HTTP 503, alte gespeicherte/aktive Revision und Historie unverändert.
  Trigger anschließend entfernt.
- App-Prozess beendet und auf demselben synthetischen Datenverzeichnis neu
  gestartet: gespeicherte Konfiguration geladen, `completed` erhalten, keine
  weitere Anfrage. Parallele Speicherung während Browserentwurf führte zu
  sichtbarem Versionskonflikt; lokaler Entwurf blieb bis zum Verwerfen erhalten.
- Desktop und 390-px-Ansicht per Screenshot gesichtet. Ein anfangs beobachteter
  mobiler Seitenüberlauf durch absolut positionierte Tabellenlabels wurde mit
  relativ positioniertem Scrollcontainer korrigiert. Final Seitenbreite 390 px;
  breite Tabelle nur innerhalb ihres eigenen Scrollcontainers. Keine JS-Fehler.

Der erste Versuch über Vites Entwicklungsproxy wurde korrekt vom Origin-Schutz
mit HTTP 403 abgewiesen; die Abnahme erfolgte danach mit der gebauten Oberfläche
direkt aus derselben App-Origin. Keine pauschale Origin-/Proxyfreigabe ergänzt.
Prüfprozesse, Browseransicht und Wegwerfskripte anschließend beendet/entfernt;
synthetische SQLite-Belege bleiben lokal im ignorierten Datenverzeichnis.

Grenzen: kein Heizungszugriff, keine Schreibbefehle, kein neuer Decoder,
kein Container-/Unraid-Lauf und kein Deployment oder Image-Release.
Vor Deployment konsistent sichern und einen neuen Build verwenden;
alte App-Versionen können die auf Schema 3 migrierte Datenbank nicht öffnen.
