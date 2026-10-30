# Ergebnisse

## 19.10.2026 – Releasevorbereitung v0.3.1

Betreiberauftrag: die abgenommene Polling-Änderung als v0.3.1 committen, pushen
und veröffentlichen. Ausgangspunkt `494f837` auf `main`, eigener Arbeitsbranch
`release/0.3.1`. Paket-/Lockversionen, FastAPI-Metadaten, Docker-/Compose-Vorgaben,
Unraid-Template und Deploymentdokumentation einheitlich auf 0.3.1 angehoben.
Funktionsnachweis: [fortlaufendes Polling](#19102026--fortlaufendes-polling-statt-fehlversuchslimit).

Ausgeführte Releaseprüfungen:

- `uv sync --locked`: erfolgreich, Paketversion 0.3.1 installiert.
- `uv run --locked pytest -q` mit deaktivierter Erfassung und leerem Ziel:
  419 bestanden; bekannte Starlette/AnyIO-DeprecationWarning.
- `uv run --locked ruff check .`: erfolgreich.
- `npm ci`, `npm run build`: erfolgreich.
- `node --test tests/dashboard.test.mjs`: 25 bestanden.
- Separater Laufzeit-Smoke mit temporärer SQLite-Datenbank, leerem Gerätehost
  und deaktiviertem Sammler: Health, Version, Collectorstatus und OpenAPI HTTP 200.
  Installiertes Paket, API und OpenAPI melden 0.3.1; Datenbank gesund,
  Collector `unconfigured`, keine Sammlerinstanz.

Veröffentlichungsnachweise einschließlich Container-Build/-Smoke und
öffentlichem Registry-Abruf werden im GitHub-Release festgehalten.
Keine lokale Containerlaufzeit vorhanden; der Image-Smoke läuft im bestehenden
Release-Workflow. Keine Gerätezugriffe, keine Änderung privater Konfiguration,
keine Aktivierung oder Aktualisierung der Betreiberinstanz.

## 18.10.2026 – Releasevorbereitung v0.3.0

Basis: `c8dba9c` auf `main`, einschließlich PR #59. Paket-/Lockversionen,
FastAPI-Metadaten, Docker-/Compose-Vorgaben, Unraid-Template und
Deploymentdokumentation sind auf 0.3.0 angehoben. Historische Belege bleiben
unverändert. Der Betreiber erlaubt für dieses Release ausdrücklich den Merge
des Versions-PRs nach erfolgreichen Prüfungen und die Veröffentlichung.

Tatsächlich ausgeführte Offline-Prüfungen:

- `uv sync --locked`, `uv run ruff check .`: erfolgreich.
- `uv run pytest`: 416 bestanden; eine bestehende
  Starlette/AnyIO-DeprecationWarning.
- `npm run build`: TypeScript-Prüfung und Produktionsbuild erfolgreich.
- Separater In-process-Laufzeit-Smoke mit temporärem Datenverzeichnis,
  ohne Gerätehost und mit deaktiviertem Sammler: `/api/health`,
  `/api/version` und `/api/collector/status` HTTP 200; Paketversion,
  OpenAPI und Versionsendpunkt 0.3.0, Zustand `unconfigured`, kein Sammler.

Veröffentlichungsnachweis folgt im GitHub-Release und dessen Container-Workflow.
Keine Gerätezugriffe, keine Unraid-Abnahme und keine Aktivierung der Erfassung.

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

## 18.10.2026 – Plattformübergreifender VS-Code-Heizungsstart

`.vscode/launch.json` ergänzt um **Heizung (API + Dashboard)** ohne Simulator-
Startaufgabe. Die API übernimmt das private Ziel aus Umgebung/`.env`, aktiviert
den Sammler mit höchstens drei Anfragen ohne Transport-Retry und separater
persistenter Ablage `data/vscode-heizung/`. Keine automatische Quittierung
gespeicherter Abschluss-/Fehlerzustände. Der Offline-Gesamttest bleibt erhalten.
Python verwendet den in VS Code ausgewählten Interpreter; Dashboardstart mit
`npm` unter Linux und `npm.cmd` unter Windows. Einrichtung in der README.

Tatsächlich geprüft, ausschließlich offline unter Linux:

- Launch-Datei als JSON geladen; API-Modul und Argumente daraus mit der
  Projekt-Pythonumgebung gestartet. Nur für den Smoke-Test synthetisches
  Loopback-Ziel und separates Wegwerf-Datenverzeichnis eingesetzt.
- Echter Uvicorn-Prozess und `npm run dev`: `/api/health` meldete App/SQLite
  `ok`; Dashboard über Vites `/api`-Proxy erreichbar.
- Genau drei erfolgreiche Simulator-Anfragen: FC03/Unit 255, 4102/1,
  28688/2 und 36864/2. Vier gespeicherte Kernsignal-Beobachtungen mit
  Qualität `ok`; SQLite-Integrität `ok`, Endzustand `completed`.
- Laufendes Vite-Dashboard in Chromium geöffnet und per Screenshot geprüft:
  API erreichbar, vier synthetische Werte und „Erfassung abgeschlossen“;
  keine Browserfehler. Kein Test zustandsändernder UI-Aktionen.
- API auf derselben synthetischen Datenbank neu gestartet: weiterhin
  `completed`, weiterhin genau drei Anfragen; kein neues Budget durch Neustart.
- Prüfprozesse und Browsertab beendet. Synthetische SQLite-Belege verbleiben
  ausschließlich im ignorierten lokalen Datenverzeichnis.

Grenzen: Keine private `.env` mit tatsächlichem Heizungsziel vorhanden;
keine Geräteverbindung, kein Dauerbetrieb und keine Heizungsänderung.
Windows und der Start über die tatsächlichen VS-Code-Debugadapter wurden
nicht ausgeführt; geprüft wurden die gestarteten Programme und deren Verhalten.

## 18.10.2026 – Quellengeprüfte V2-Registerauswahl

Nutzerauftrag nach Bereitstellung einer privaten 80er-CSV und der privaten
Vorprojekt-Unterlagen: zusätzliche Register jetzt bewusst auswählbar/aktivierbar
machen; START/SOLL getrennt vorbereiten, tatsächliche Ansteuerung und Alerting
später klären. Der Betreiber wurde auf neun Read-to-clear-Register hingewiesen
und verlangte ausdrücklich auch für die neuen Einträge auswählbare Checkboxen.
Dies wurde umgesetzt, ohne neue Zeilen automatisch einzuschalten.

Quellenarbeit: Lesezweige, tatsächlich verwendete Konversions-/Anzeigepfade
und die bisherigen Nachweise aus dem privaten Softwareexport wurden statisch
ausgewertet. Alle 80 bereitgestellten Code-/Offset-Zuordnungen sind damit
abgedeckt. Originalexporte, rekonstruierter Herstellercode, private Pfade und
Netzwerkdetails wurden nicht in das Repository übernommen. Nur fünf
Registerwörter bleiben live/Display-bestätigt; neue Decoder sind statisch
belegt und offline geprüft, nicht neu an der Anlage validiert.

Implementierung:

- Explizites Leseprofil mit unverändertem Kern und zusätzlich isolierten
  Zusatzregistern; Betriebs- und Stokerzähler jeweils als vollständiges Paar.
  Keine Suche, Adressbereiche mit Lücken oder beliebigen Registerzugriffe.
- Kanalbezogene Temperaturgrenzen, interne Leistungsregelgröße in Prozent,
  Versorgung in Zehntelvolt, Förder-/Pausentakte in Zehntelsekunden.
  Physikalisch ungeklärte Lambda-/Gebläsegrößen ausdrücklich als Hersteller-
  rohwerte. Raumwert 0 und Abgaswert 299 bleiben als mehrdeutige
  Initial-/Istwerte dokumentiert, statt unbelegt verworfen zu werden.
- Zusatzbeobachtungen mit Herkunft `extended/1/1`, bisherige Kerndaten weiterhin
  `core/1/1`. Dezimalwerte bleiben in SQLite erhalten; keine Historienänderung.
- Zentraler Zeitplan mit mindestens 60 s für Kern- und 300 s für Zusatzblöcke;
  nicht fällige Zusätze verdrängen keine fälligen Kernwerte.
  Frische-/Diagrammlückengrenzen berücksichtigen das jeweilige Intervall.
- Zusatz-Verbindungsfehler und ungewisse Zusatzanfragen stoppen ohne
  automatische Wiederholung, auch nach Neustart. Protokoll-/Teilantwortfehler
  bleiben `stopped_protocol`; Core-Recovery unverändert.
- Dynamischer Signalkatalog, Verlauf und Karten; Kategorien und Quellen-/
  Livebelegstatus sichtbar. Neun Read-to-clear-Hinweise unmittelbar an den
  aktivierbaren Checkboxen. Der Simulator bildet das Leeren der Akkumulatoren
  tatsächlich ab, statt nur feste Protokollwerte zu wiederholen.
- START/SOLL als getrennte, nicht ausführbare Kandidaten im Dashboard.
  Kein Schreibadapter/-endpunkt, kein Alerting und keine Gerätekonfiguration.

Tatsächlich ausgeführte Prüfungen:

- `uv run pytest -q`: abschließend **228 bestanden**, eine bekannte
  Starlette-/AnyIO-DeprecationWarning. Decodergrenzen, Rohwertsemantik,
  Paarzuordnung, Auswahl/Persistenz, historische Herkunft, Frische,
  60-/300-s-Zeitplan, Fehlerstopps und Neustartgrenzen abgedeckt.
- `uv run ruff check .`: **All checks passed!**
- `npm run build`: TypeScript und Vite erfolgreich.
- `uv build --wheel --python 3.12.9`: erfolgreich.
- Im ersten neuen Read-to-clear-Test war der synthetische Startakkumulator
  bereits null; die Fixture wurde auf ausdrücklich synthetische gesetzte Bits
  korrigiert. Danach tatsächliches Leeren, getrennte Kanäle und unabhängige
  Simulatorinstanzen erfolgreich geprüft.
- Gebaute App mit Uvicorn, Chromium und echtem Loopback-FC03-Simulator gestartet.
  Virtuelle Zeit beschleunigte ausschließlich Wartezeiten im Wegwerf-Smoke.
  Die tatsächlich bereitgestellte CSV wurde über die Browseroberfläche hochgeladen:
  80 Zeilen, keine deaktivierte Checkbox, neun Risikohinweise; vor Bearbeitung
  nur die bisherigen fünf Kernwörter ausgewählt, gespeicherte Revision unverändert.
- Stokerpaar gemeinsam ein-/ausgeschaltet, dann bewusst alle 80 Testzeilen
  ausgewählt und gespeichert. Sammler blieb bis zum bewussten Fortsetzen
  pausiert; Seitenneuladen erhielt die Auswahl.

| Nachweis im endlichen Loopback-Lauf | Ergebnis |
|---|---:|
| Registerwörter der geprüften Auswahl | 80 |
| Unterstützte Signale | 78 |
| Tatsächliche FC03-Anfragen einschließlich vorbereitendem Kernzyklus | 80 |
| Gespeicherte synthetische Beobachtungen einschließlich bestehender Historie | 82 |
| Beobachtungen mit bisheriger Herkunft `core/1/1` | 8 |
| Beobachtungen mit neuer Herkunft `extended/1/1` | 74 |

Endzustand `completed`, SQLite-Integrität `ok`. Beispielsweise wurde das
synthetische Versorgungswort 240 als 24 V und das Stokerpaar als 1560 Minuten
gespeichert; Kesselhistorie enthielt alten und neuen Punkt. Prozessneustart
erhielt alle 80 Auswahlen, Revision, Abschluss und Anfragezahl ohne weitere Reads.
Im Browser Zusatzsignal im Verlauf ausgewählt, physikalische Einheit und
Quellenstatus geprüft; Signalwahl blieb nach Neuladen erhalten.
START/SOLL waren sichtbar, ohne Eingaben oder Aktionsbuttons.
Desktop und 390-px-Ansicht per Screenshot geprüft: kein Seitenüberlauf,
keine JavaScript-Fehler.

Zusätzliche tatsächliche Loopback-Fehler-Smokes: Zusatz-Versorgung ohne
Antwortbytes, Read-to-clear ohne Antwortbytes und Read-to-clear mit falscher
Unit. Jeweils genau eine Anfrage, null Wiederaufnahmen; Zustände
`stopped_transport`, `stopped_transport`, `stopped_protocol`. Neuer Collector
auf demselben synthetischen Zustand führte keine weitere Anfrage aus.
Gitleaks über Quelltexte, Tests und Dokumentation ohne Fund.

Eigene Prüfprozesse/Browsertab beendet und Wegwerfskript entfernt;
synthetische SQLite-Belege bleiben lokal im ignorierten Datenverzeichnis.
Vorhandene Nutzeränderungen am VS-Code-Start und an der Übergabe bleiben
erhalten. Keine private `.env` oder echte Datenbank verändert.

Grenzen: keine neue Heizungsabfrage, keine Tabellenimporte, keine
Heizungsänderung, kein Container-/Unraid-Lauf und kein Image-Release.
Für die Nutzung ist ein neuer Build/Neustart der App erforderlich.
Eine spätere Geräteabnahme bleibt gezielt und endlich zu planen; die
Auswählbarkeit ersetzt keine Hersteller-Verträglichkeitszusage.

## 18.10.2026 – CSV-Vorauswahl interpretierbarer Einträge

Neue Betreiberanforderung: Beim CSV-Upload sind alle Einträge mit vorhandenem
Decoder und passender Lesezuordnung im Entwurf bereits für „Aufzeichnen“
ausgewählt. Das gilt ausdrücklich auch für hochgeladene, zuvor abgewählte
Bestandszeilen und die neun mit Warnung versehenen Read-to-clear-Werte.
Nicht hochgeladene gespeicherte Zeilen behalten ihre Auswahl; Betreibertexte
bleiben erhalten. Vollständige Zählerpaare werden gemeinsam vorgewählt,
unbekannte/falsche/unvollständige Zuordnungen bleiben abgewählt und gesperrt.

Backend-Vorschau und Browser verwenden dieselbe Vorauswahl; die bisherige
Frontend-Überschreibung auf `record=false` ist entfernt. Vorschau bleibt
ohne Speicherung oder Geräteabfrage. Erst „Entwurf speichern“ übernimmt die
Auswahl. Reimport kann zuvor gespeicherte Abwahlen im Entwurf wieder aufheben;
Bedienhinweise und Read-to-clear-Warnung erläutern dies ausdrücklich.

Tatsächlich geprüft:

- `uv run pytest -q`: **231 bestanden**, eine bekannte DeprecationWarning.
  Geänderte Reimportregeln, Metadatenerhalt, falsche/unbekannte Zuordnung,
  unvollständige und vollständige Zählerpaare sowie Draft/Persistenz geprüft.
- `uv run ruff check .`: erfolgreich.
- `npm run build`: TypeScript/Vite erfolgreich.
- Gebaute Oberfläche mit echtem Uvicorn und Chromium, ohne konfigurierten Host
  und ohne Sammler, gestartet. Tatsächliche private 80er-CSV hochgeladen:
  **80 Checkboxen ausgewählt, keine gesperrt**; gespeichert blieben vorher
  nur die fünf Kernwörter auf Revision 0. Upload allein änderte nichts.
- Im Browser Leistung abgewählt und gespeichert, danach dieselbe Datei erneut
  hochgeladen: im Entwurf wieder ausgewählt; gespeicherte Abwahl blieb bis
  zu einem weiteren Speichern unverändert auf Revision 1.
- Neue Bedien- und Read-to-clear-Hinweise per Screenshot geprüft;
  keine JavaScript-Fehler. Prüfprozess/Browsertab beendet, Wegwerfskript entfernt.

Keine Heizungsabfrage, keine Heizungsänderung, kein Deployment und kein Release.
Vorhandene lokale Nutzeränderungen bleiben erhalten.

## 18.10.2026 – Fehler einzelner Werte isolieren und an Kacheln anzeigen

Nutzerauftrag nach einem real beobachteten `stopped_data` wegen fehlender
gespeicherter Wetterdaten: übrige Werte weiter auslesen und die konkrete
Fehlerursache an der jeweiligen Anlagenkachel darstellen. Die vorherige
Untersuchung des laufenden Monitors war ausschließlich lesend. Für diese
Umsetzung wurde die laufende Heizungs-App weder neu gestartet noch quittiert;
es wurden keine neuen Heizungsanfragen ausgeführt.

Implementiert:

- Kanalweise Decoderergebnisse mit `quality`, `error_code`, `error_message`
  und nullable `value`. Strukturell falsche Blockdaten bleiben globale Fehler.
- Dokumentierte fehlende Wetterdaten ergeben `unavailable`/`missing_weather`,
  statt den gesamten Sammler anzuhalten. Reguläre spätere Abfragen dürfen
  wieder gültige Daten liefern; keine erfundenen Nullmessungen.
- Echte ungültige Einzelwerte und registerbezogene Modbus-Ausnahmen 2/3
  werden persistent in `blocked_signals` ausgesetzt; andere ausgewählte
  Signale laufen weiter. Gesunde Nachbarn im selben Pufferblock bleiben
  nutzbar. Nicht ausgewählte fehlerhafte Nachbarn werden nicht still ohne
  zugehörige Fehlerbeobachtung gesperrt.
- Wiederanlauf, normales Resume und CSV-Speichern löschen Sperren nicht.
  Explizite Quittierung nach Ursachenprüfung darf sie aufheben, ohne das
  Anfragebudget zurückzusetzen. Fehlende optionale Wetterdaten brauchen keine
  Quittierung. Vollständig gesperrte Auswahl wartet ohne Read-/Busy-Loop.
- Allgemeine Gerätefehler, Busy-/Gatewayfehler, ungültige/teilweise
  Modbus-Antworten und Speicherprobleme behalten globale Schutzstopps.
  Auch diese Fälle erhalten sichere Fehlerbeobachtungen soweit speicherbar.
- Schema 4 ergänzt zwei nullable Fehlerfelder an Beobachtungen. Migration
  1/2/3 additiv; bestehende Historie und Zusatz-Alttabellen bleiben erhalten.
  Current liefert deterministisch genau die neueste Beobachtung je Signal,
  auch bei identischen Zeitstempeln; Zugriff beginnt über die kleine
  Signaltabelle statt über alle dauerhaft erhaltenen Minutenbeobachtungen.
- Current-/History-API und CSV transportieren Fehlerfelder, Current auch
  Blockoffset/Registerzahl. Kacheln zeigen konkrete Ursache, Code, Zeitpunkt
  und Qualität; früher gute Werte werden bei aktuellem Fehler nicht als
  frisch angezeigt. Fehlerpunkte unterbrechen Diagrammlinien. Ereignisse
  zeigen nur kontrollierte Detailfelder, keine privaten Host-/Pfadfehler.

Tatsächlich ausgeführte Prüfungen:

- `uv run pytest -q`: abschließend **257 bestanden**, eine bekannte
  Starlette-/AnyIO-DeprecationWarning. Bestehende Decoder-/Collectorverträge
  migriert; Fehlerfortsetzung, Paarisolation, Quarantäne/Restore/Freigabe,
  fehlend→wieder verfügbar, harte Stopps, Migration/Backup und Fehlerexport
  geprüft. Im ersten Integrationslauf erwartete ein alter Recoverytest noch
  ausschließlich einen Gutwert; er prüft nun die neue Fehlerbeobachtung und
  den anschließenden Gutwert als zusammenhängenden Übergang.
- `uv run ruff check .`: **All checks passed!**
- `npm run build`: TypeScript und Vite erfolgreich.
- `uv build --wheel --python 3.12.9`: erfolgreich.
- Gebaute App mit Uvicorn und Chromium auf isoliertem Datenverzeichnis,
  echter Loopback-Modbus-Transport und ausschließlich synthetische Werte.
  Wartezeiten durch eine virtuelle Uhr beschleunigt, nicht durch Änderung
  der Produktionsintervalle.
- Im Browser kleine CSV importiert, Zähler abgewählt, Auswahl gespeichert
  und bewusst fortgesetzt. Vorbereitender gültiger Kernzyklus blieb in der
  Historie. Danach gleichzeitig: Wettertemperatur −50, Wetterstatus −1,
  Puffer oben 110 und validierte Modbus-Ausnahme 2 für einen Protokollblock;
  Kessel, Puffer unten und Versorgung lieferten weiter gültige Werte.

| Endlicher gemischter Loopback-Lauf | Ergebnis |
|---|---:|
| Tatsächliche FC03-Anfragen einschließlich Vorbereitung | 20 |
| Gespeicherte Beobachtungen | 22 |
| Gültige Beobachtungen | 16 |
| Nicht verfügbare Wetterbeobachtungen | 4 |
| Isolierte ungültige Beobachtungen | 2 |
| Ausgesetzte Signal-IDs | 2 |
| Auslesungen des abgelehnten Protokollblocks | 1 |

Endzustand `completed` durch das endliche Budget, SQLite-Integrität `ok`.
Puffer oben behielt seinen früheren gültigen Punkt und erhielt danach eine
ungültige Beobachtung mit `value=NULL`; Puffer unten wurde im gemeinsamen Block
weiter erfasst. Prozessneustart erhielt Fehlerkacheln, zwei Signalsperren,
Historie und Anfragezahl ohne neue Reads.

Browsernachweis: Wetterkachel mit „Kein gespeicherter Wetterzustand“,
`missing_weather` und Offset 4129; Pufferfehler mit konkretem Wertbereich;
abgelehnter Protokollblock mit `modbus_exception_2`; gesunde Nachbarkachel
weiter gültig. Fehler-/Warnfarben zusätzlich als Text, kein Fake-0 und kein
alter Ersatzwert. Anlagenübersicht, Verlauf und 390-px-Ansicht per Screenshot
gesichtet; kein horizontaler Seitenüberlauf, keine JavaScript-Fehler.

Zusätzliche tatsächliche Loopback-Smokes:

- Wetterstatusfolge gültig 2 → fehlend → gültig 3 über drei reguläre
  300-s-Abfragen: gespeicherte Qualitäten `ok` → `unavailable` → `ok`,
  kein gesperrtes Signal, keine künstliche Nullmessung.
- Falsche Unit: nach einer Anfrage `stopped_protocol`, Fehlercode
  `protocol_error` an der Beobachtung.
- Verbindungsabbruch ohne Antwortbytes im endlichen Lauf: nach einer Anfrage
  `stopped_transport`, Fehlercode `transport_error`.

Gitleaks über Backend, Frontend, Tests und Dokumentation ohne Fund.
Eigene Prüfprozesse und Browseransicht beendet, Wegwerfskript/-CSV entfernt;
synthetische SQLite-Belege verbleiben lokal im ignorierten Datenverzeichnis.
Vorhandene Nutzeränderungen bleiben erhalten. Keine echte Datenbank,
private `.env`, Heizungsparameter oder Modbus-Tabelle verändert.

Vor Einsatz konsistent sichern, App/Frontend mit neuem Stand starten und
einen bereits gespeicherten globalen Fehlerstopp nach Prüfung ausdrücklich
quittieren. Die Migration selbst quittiert nichts. Alte App-Versionen können
Schema 4 nicht öffnen. Kein Container-/Unraid- oder Live-Nachweis aus diesen
Prüfungen ableiten; keine Veröffentlichung, Commits oder Pushes ausgeführt.

## 18.10.2026 – Feldabgleich der 80 unterstützten Register

Die vorhandenen Betreiber-Notizen und die zuvor ausgewerteten Herstellerpfade
wurden in verständliche Anzeigenamen und fachliche Beschreibungen übernommen.
Die Ausgabe bleibt Teil von `/api/signals`, ohne neue Gruppenrouter oder
automatische Änderungen an Auswahl und Kachelsichtbarkeit. CSV-Importnamen bleiben
unabhängig von den Anzeigenamen, damit unveränderte Reimporte ihre Identität behalten.

- `verification_status`: Touch-Abgleich / Lesbarkeit laut Betreiber für 79 Wörter;
  für `10D1` fehlt die Bestätigung. Keine unabhängige physikalische Verifikation.
- `module_status`: NM/SP und eigenständige Puffer-2-Parameter als inaktiv markiert,
  getrennt vom Verifikationsstatus. Lesbare Zahlen sind dort keine aktiven
  Anlagenmessungen. `9000` und `9001` bleiben ausdrücklich die aktiven Fühler
  oben/unten desselben Puffers; IDs, Blockmapping und Beschreibungen unverändert.
- Präzisiert: Fehlerlisten-Minimum / 0 leer, identische Abgasquellen,
  Saugzug-Prozentanzeige ohne U/min-Normierung, einheitenlose Lambda-Ganzzahlen,
  Materialförderungs-Stoppschwelle, Teillast-/Zündtaktalias, Heizkreis-Vorlauf /
  Quellen-Ist / berechneter Vorlauf-Sollwert, Ausbaukonfiguration statt Pumpenstatus
  und PT100-Betriebsart statt Rohmesswert.
- `91E0/1` erhalten Prozentmetadaten für die belegten Anzeigestufen 10/50/90,
  ohne Energieinterpretation. Alle neuen Prozentmetadaten behalten die
  identische Rohwortdekodierung ohne zusätzliche Skalierung oder Statusgrenzen.
- Historische Beobachtungen behalten ihre gespeicherten Einheiten in API und CSV;
  unterschiedliche Einheiten im selben Zeitraum werden getrennt gezeichnet.
  Der historische Kern-Livenachweis und die Intervalle 60/300 s bleiben unverändert.

Verhaltenstests ergänzt für unverändertes aktives Puffer-Mapping,
Prozentmetadaten ohne Rohwortskalierung oder neue Grenzen, getrennte
Verifikations-/Modulzustände, historische Einheiten in API/Export und unveränderte
CSV-Importidentität. Anschließend tatsächlich geprüft: `uv run pytest -q`
mit 317 bestandenen Tests und einer bekannten DeprecationWarning;
`uv run ruff check .` erfolgreich; `npm run build` erfolgreich.
Gebaute App isoliert ohne Collector/Heizungsziel gestartet und in Chromium
geprüft: unveränderte Pufferbezeichnungen, Saugzug-Prozentdarstellung,
Touch-Betreiberbestätigung und weiterhin offener Status von 10D1.
Screenshot der Verlaufsauswahl gesichtet; keine JavaScript-Fehler.

Keine Heizungsabfrage, Neustart, Quittierung, Änderung einer echten Datenbank
oder privaten `.env`. Private Originaldateien und Quellen wurden nicht kopiert.
Keine Git-Aktionen, Commits oder Veröffentlichung.

## 18.10.2026 – Dashboard auf Aufzeichnungsauswahl begrenzen

Kacheln folgen ausschließlich der gespeicherten Aufzeichnungsauswahl.
Kernsignale, historische Werte und eine noch ausstehende alte aktive Auswahl
erzwingen keine zusätzlichen Kacheln mehr. Verlauf und Historie bleiben erhalten.
`npm run build` erfolgreich. Tatsächliche lokale Browseroberfläche geprüft:
40 ausgewählte Signale, 40 Kacheln, weiterhin 78 Verlaufseinträge.
Keine Änderung der Auswahl, kein Sammlerneustart und keine zusätzliche
Heizungsabfrage durch die Prüfung.

## 18.10.2026 – Diagrammauswahl auf Aufzeichnungsauswahl begrenzen

Verlaufsauswahl nutzt denselben Filter wie die Anlagenkacheln.
Eine gespeicherte, inzwischen ausgeschlossene Signalwahl wird korrigiert;
bei leerer Auswahl sind Auswahl und Export deaktiviert. Historie bleibt erhalten.
TypeScript-/Vite-Build und Diffprüfung erfolgreich. Der lokale Vite-Port war
bei der Abnahme nicht erreichbar; deshalb gebaute App isoliert ohne Collector
gestartet und im Browser geprüft: vier ausgewählte Signale, vier Diagrammoptionen,
unzulässige gemerkte Auswahl nach Neuladen auf verfügbares Signal korrigiert.
Keine Heizungsabfrage oder Änderung der tatsächlichen Aufzeichnungsauswahl.

## 18.10.2026 – Dashboard „Ruhige Energiezentrale“

### Umsetzung und Nachweisgrenzen

Die Übersicht zeigt den Software-Steuerungszustand des Pelletkessels getrennt
von API und Erfassung, ausgewählte Kessel-/Puffertemperaturen und einen
gemeinsamen Verlauf mit abgetastetem Statusband. Analyse, gruppierte Werte,
Einstellungen und der erhaltene Modbus-Editor nutzen einen gemeinsamen Rahmen
mit persistentem Hell-/Dunkelmodus. Der Editor bleibt beim Navigieren gemountet.
Die gespeicherte Auswahl (`logging.entries`) bleibt alleinige Anzeigegrundlage;
Suche, Vergleichswahl, Upgrade und Katalogabfrage ändern diese Auswahl nicht.

`1001`/4097 ist eine explizite reine FC03-Leserweiterung, ein Wort, 300-s-Intervall
und 600-s-Frische. Nur die sieben belegten unsigned Statuswörter werden akzeptiert;
Zusatzbit und Originalrohwort bleiben erhalten. Unbekannte Wörter ergeben
`invalid`/`unknown_boiler_state`, niemals „Aus“. Der Status ist quellenbelegt,
nicht live oder am Touch bestätigt. CSV `Betriebsstatus;4097;1001` konfiguriert
nur nach ausdrücklichem Speichern den Monitor, keine Gerätetabelle.
Kernprofil, Kernzyklen, Standardauswahl und Schutzstopps bleiben unverändert.
Keine Datenbankmigration, neue UI-Abhängigkeit oder Geräte-Schreibfunktion.

Historien werden vollständig mit festen Grenzen und höchstens zwei gleichzeitigen
Signalabrufen paginiert. Relative Zeitfenster wandern, freie Grenzen bleiben
fest und werden lokal wiederhergestellt. Teilfehler, Abbruch und widersprüchliche
Seiten bleiben sichtbar. Linien und Stufen respektieren Qualität, Einheiten und
Lücken; Min-/Max-Verdichtung verändert nur die Darstellung, nicht Inspektion oder
CSV. Pufferschichtung verwendet ausschließlich zeitgleiche gültige °C-Werte,
ohne Interpolation. Statuswechselbereiche und fehlende Beobachtungen bleiben
unbekannt; keine sekundengenaue Schaltkante, Flammenstunden oder Solarzuordnung.

### Automatisierte Prüfungen

- `uv run pytest -q`: **330 bestanden**. Eine bekannte Starlette-/AnyIO-
  DeprecationWarning zum `BlockingPortal`-Alias, keine Testfehler.
- `node --test tests/dashboard.test.mjs`: **15 bestanden**, ohne neue
  Testabhängigkeit, Import der seiteneffektfreien TypeScript-Helfer.
- `npm run build`: TypeScript und Vite erfolgreich, auch nach den letzten
  visuellen Korrekturen.
- `uv run ruff check .`: erfolgreich.
- Decodergrenzen einschließlich `0x8002/3/4` und Fehlerwörtern, explizite
  Preview-/Save-Auswahl, falscher Offset, endlicher Loopback-Statuslauf mit
  genau einer Anfrage und Current-/History-/CSV-Vertrag geprüft.
- Frontend-Verhalten: Zustandsband, negative/zeitversetzte Pufferschichtung,
  Gruppenpriorität, einheitentreue Segmente, einzelne Temperaturspitzen,
  Lückengrenzen, Originalpunktnähe, DST, vollständige 44.640-Punkt-Pagination,
  inkonsistente Seiten und Abbruch geprüft.
- Obsolete feste Umfangszahlen wurden aus den Profil-/Simulatortests entfernt,
  nicht auf neue Zahlen umgepinnt; Allowlist-/Offset-/Kernschutz bleibt erhalten.

### Tatsächliche Offline-App und Browser

Die echte FastAPI-App lief mit explizit isolierten Einstellungen:
`_env_file=None`, neues temporäres Datenverzeichnis, Sammler deaktiviert,
leerer Modbus-Host und leerer öffentlicher Origin. Seeds ausschließlich
synthetisch über `SQLiteStore.record_cycle` und explizite
`save_logging_config`-Auswahl. Keine echte Datenbank oder private `.env` als
Fixture. Vite für den UI-Smoke; zusätzlich gebautes Frontend im
wegwerfbaren Smokeprogramm unter demselben API-Origin bereitgestellt.
Zeit-/Race-/Fehlerfälle wurden ergänzend mit synthetischen Browserantworten
geprüft; Weiterleitungen ausschließlich an diese isolierte Loopback-API,
keine Geräteverbindung.

Tatsächlich bedient und beobachtet:

- Alle Routen, unbekannter Hash als Übersicht, genau ein sichtbares `main`,
  `aria-current` und Fokus auf der Inhaltsüberschrift nach Navigation.
  Lokaler Editorentwurf bleibt über Übersicht und Rückkehr erhalten.
- Status 0 → „Aus“, `0x8003` → „Ein · Gluterhaltung“ mit Mindestlaufzeit-
  Kennzeichen, fehlende Messung, ungültiger Status, Alter über 600 s und
  nicht verfügbare Statusquelle mit getrennten Aussagen. `completed` bleibt
  „Erfassung abgeschlossen“, keine Aussage zum Heizungszustand.
  Fehlerliste 0 als leer, positive Nummer als Warnhinweis.
- Statusband enthält unbestimmte Wechsel, Fehler und eine Lücke über 600 s.
  Mobile Zwischenlinien wurden entfernt, damit die Zustandsflächen nicht
  durch die einzelnen sehr schmalen 5-Minuten-Rechteckränder verdeckt werden.
  Beobachtungen selbst werden nicht reduziert.
- 31-Tage-Bereich mit **44.640 Minutenpunkten je Temperaturreihe** vollständig
  bis Offset 40.000 geladen. Inspektion zeigt Anfang und tatsächliches Ende,
  nicht nur die ersten 10.000 Punkte. Fehler auf späterer Seite trennt die
  Kurven in sechs Segmente für drei Reihen.
- Vorzeitig leere Seite: namentlicher unvollständiger Abruf, keine fertige
  Kurve dieser Reihe; andere Reihen sichtbar. Gemessene maximale Parallelität:
  zwei Historienabrufe. Ladeabbruch und verspätete Antwort nach Presetwechsel
  überschreiben die neue Auswahl nicht.
- Alle sechs Presets bedient; Heizkreis 1/2 und interne Leistungs-Ist/Soll-
  Vergleiche sichtbar. Historischer Wechsel `Rohwert` → `%` auf getrennten
  Flächen, ohne Umrechnung. Originalpunktinspektion mit Tastatur und mobiler
  Zeitauswahl; tatsächliche, auch voneinander abweichende Messzeiten sichtbar.
- Browserzeit um eine Minute fortgeschaltet: relativer Bereich wandert,
  freier Bereich bleibt fest. Herbstzeit `25.10.2026 02:30 Europe/Vienna`
  ergibt `00:30Z`; Frühlingslücke `29.03.2026 02:30` wird abgewiesen.
  Freie Start-/Endwerte nach Reload wiederhergestellt.
- API-Ausfall: kein aktuelles Ein/Aus; Datenalter steigt von neun auf zehn
  Minuten weiter. API- und synthetischer Speicherstopp auch im Editor sichtbar.
- 15 gespeicherte Signale → 15 eindeutige Wertezeilen, fachlich gruppiert.
  Wetterfehler `missing_weather` direkt sichtbar. Suche verändert nur die
  Ansicht. Bei leerer gespeicherter Auswahl keine erzwungenen Kacheln/Werte,
  Vergleich und Export deaktiviert, selbst bei abweichenden `active_entries`.
- Tatsächlicher HTTP-409-Konflikt gegen isolierte API: lokaler Editorentwurf
  bleibt erhalten. Zeitzonen-PUT erfolgreich, Collectoraktion ohne aktivierten
  Sammler erwartungsgemäß HTTP 409; beide behalten `X-Requested-With`.
  Der Vite-Fremdorigin wurde bei einer Mutation zuvor sicher mit HTTP 403
  abgewiesen; die Same-Origin-Abnahme erfolgte deshalb mit dem gebauten
  Frontend. Keine Sicherheitsprüfung gelockert.
- Screenshots bei 1440×1000, 390×844 und 320×740 gesichtet, beide Themes
  einschließlich Editor, Formulare und Warnungen. Kein Dokumentüberlauf;
  nur Registertabellenregion intern scrollbar. Systemthemewechsel ohne
  explizite Wahl, manueller Wechsel und Reload geprüft. Texttokens auf
  Flächen erfüllen rechnerisch mindestens 4,5:1 in beiden Paletten.
- Keine JavaScript-Ausnahme im regulären Lauf. Erwartete `ERR_ABORTED`-
  Netzwerkeinträge entstehen bei StrictMode-/Navigations-/Ladeabbrüchen.

### Während der CSV-Abnahme gefundener und behobener Altfehler

Der tatsächliche große Download brach zunächst vorzeitig ab. Servertrace:
Starlette setzt den synchronen Generator auf wechselnden Workerthreads fort;
die darin gehaltene SQLite-Verbindung hatte `check_same_thread=True`.
Der deterministische Regressionstest mit zwei getrennten, sequenziell
verwendeten Workerthreads scheiterte vor der Korrektur mit demselben Fehler.

Nur die eigene Exportverbindung erlaubt nun diesen sequenziellen Threadwechsel
und wird am Streamende geschlossen. Andere Speicheroperationen behalten ihre
bisherige Threadbindung. Kein Vollpuffer, keine Exportverdichtung und keine
Änderung der Daten. Regression anschließend bestanden.

Erneuter tatsächlicher Browserdownload: **16.245.786 Byte**, je **44.641**
Temperaturbeobachtungen im dafür um eine Minute erweiterten Prüfbereich,
285 Statusbeobachtungen und alle anderen ausgewählten Reihen. CSV eingelesen:
Originaleinheiten, Rohwörter und Fehlerzeilen mit leerem Wert und konkretem
Fehlercode erhalten; nicht auf Preset oder visuelle Punktzahl beschränkt.

### Offen ausschließlich an der Anlage

Keine Geräteanfrage, kein Mappingimport, Start/Stop, Neustart oder Quittieren
einer realen App. Die bekannte Gerätetabelle enthält `1001` nicht; ihr aktueller
Bereitstellungsnachweis fehlt. Deshalb keine echte Statusabnahme behauptet.
Nächster begrenzter Schritt und Stopps stehen in [NEXT_STEPS](../NEXT_STEPS.md):
erst Mappingnachweis und Ausschluss anderer Leser, dann eigener privater Plan
für maximal eine FC03-Anfrage an `Anlage-aktuell` mit Displayabgleich.
Eine Tabellenänderung ist dadurch nicht erlaubt. Keine automatische Aufnahme
in die reale Dauerauswahl, kein Unraid-/Dauerbetriebsnachweis.

Eigene Prüfserver und Browsertab beendet; wegwerfbares Smokeprogramm entfernt.
Keine Git-Aktionen, Commits, Pushes oder Pull Requests.

## 18.10.2026 – Themeicons, Aufzeichnungstransfer und ehrliche Betriebsanzeige

### Änderungen

- Der Themebutton enthält native SVG-Icons: Mond bietet Dunkelmodus an,
  Sonne Hellmodus. 44×44 px Bedienfläche, Tooltip, zugänglicher Name und
  `aria-pressed`; Persistenz und Systemtheme unverändert. Keine Iconbibliothek.
- `GET /api/logging-config/export` liefert die gespeicherte Konfiguration als
  `sommerauer-aufzeichnung.json`. Version 1, ausschließlich Eingabefelder
  `code`, `offset`, `name`, `record`, `unit`, `description`, einschließlich
  Abwahlen. Kein ungespeicherter Entwurf und keine ältere aktive Revision.
- `POST /api/logging-config/import-preview` übernimmt die Datei mit aktueller
  lokaler Revision in einen Entwurf. JSON ersetzt Auswahl/Betreibertexte;
  nur im Ziel vorhandene Register samt Metadaten bleiben erhalten, aber
  abgewählt. CSV bleibt ergänzend. Erst das bestehende PUT speichert atomar.
  Lokalen Entwurf nur nach ausdrücklicher Bestätigung ersetzen.
- Beide Instanzen benötigen einen kompatiblen Build. Fremde Formatversionen,
  Zusatz-/Freigabefelder, ungeeignete ausgewählte Register, Duplikate,
  fehlerhafte Zählerpaare und zu große Dateien werden abgelehnt. Keine
  Geräteadressen, privaten Pfade, Laufzeitfreigaben, Budgets oder Historien
  übertragen. Eigene Namen/Beschreibungen vor Weitergabe prüfen.
- Die Betriebsanzeige verwendet `1001` vorrangig, sofern ausgewählt, aktuell,
  gültig und in `Rohwert`. Ohne brauchbaren Status wird ausschließlich eine
  vorhandene ausgewählte aktuelle `1003`-Beobachtung in `%` verwendet:
  positive interne Istregelgröße → „Leistungsregelung aktiv“ als deutlich
  **indirekter Betriebshinweis**; 0 % → „Betriebszustand nicht eindeutig“.
  Keine bestätigte Ein-/Aus- oder Flammenaussage aus Leistungsregelung,
  Temperaturen, Abgas oder Anlagenzähler. Keine brauchbare Quelle →
  „Betriebszustand unbekannt“ mit konkretem Grund. Fehler einer Statusquelle
  bleiben auch beim Leistungsersatz sichtbar. Das Statusband bleibt `1001`
  vorbehalten; keine synthetische Zustandsgeschichte.

### Tatsächlich ausgeführte Prüfungen

- `uv run pytest -q`: **357 bestanden**, eine bekannte Starlette-/AnyIO-
  DeprecationWarning. Neue Fälle für JSON-Roundtrip, leere Auswahl,
  Format-/Feld-/Größenvalidierung, Revisionskonflikte und Same-Origin.
  Historie, harte Stopps, verbrauchte Budgets und Signalsperren bleiben bei
  Vorschau und Speichern erhalten.
- `node --test tests/dashboard.test.mjs`: **23 bestanden**. Quellenpriorität,
  mehrdeutige Null, Qualität/Einheit/Auswahl, fortlaufendes Alter,
  API-Ausfall und keine Rückkehr zu früheren Gutwerten geprüft.
- `npm run build`: TypeScript/Vite erfolgreich, abschließend auch nach
  Button-/Transferabständen. `uv run ruff check .`: erfolgreich.
- Zwei echte isolierte API-Instanzen mit neuem temporärem Datenverzeichnis,
  `_env_file=None`, leerem Modbus-Host und deaktiviertem Sammler gestartet.
  Ausschließlich synthetische Daten über die bestehende Speicherung gesät.
  Belegte Ports 8000/5173 nur lesend festgestellt und unangetastet gelassen;
  eigene API-/Frontendprozesse auf getrennten Loopbackports.
- Echter Download über den UI-Button, nativ per Chromium-Downloadevent bis
  `completed` beobachtet und Datei gelesen: 967 Byte, 9 Registereinträge,
  davon 7 ausgewählt. Eine vorher lokal ungespeicherte Beschreibung ist
  nicht enthalten; gespeicherte Beschreibung/Betreibereinheit unverändert.
- Datei in der zweiten laufenden Instanz per Upload übernommen:
  abgelehnte Entwurfsersetzung erzeugt keine Vorschauanfrage und erhält
  den lokalen Text. Bestätigte Vorschau übernimmt die Quelldaten, belässt
  die Datenbank unverändert und wählt das zielseitige Zusatzregister ab.
  Nach bewusstem Speichern und Reload alle Quell-Eingabefelder gleich,
  Zusatzregister erhalten/abgewählt; Collector weiterhin `completed`,
  vorhandene 61 Kesselbeobachtungen unverändert. Schutzheader vorhanden.
- Tatsächlicher konkurrierender Speichervorgang im isolierten Ziel:
  JSON-Vorschau erhält HTTP 409, der bisherige lokale Entwurf bleibt erhalten.
- Neun Browser-Statusfälle mit ergänzend synthetischen API-Antworten:
  echtes Aus vor positiver Regelgröße, Gluterhaltung mit Mindestlaufzeitbit,
  positiver indirekter Befund, 0 %, abgewählte/falsche Einheit/veraltete
  Istregelgröße, ungültiger Status bei brauchbarer Regelgröße und API-Ausfall.
  Keine automatische Auswahländerung, keine neue Geräteabfrage.
- Sonne/Mond-Wechsel, Tooltip, gedrückter Zustand und Reload-Persistenz in
  der laufenden Oberfläche geprüft. Screenshots der Betriebsanzeige und des
  Transfers bei Desktop und 320 px gesichtet, zusätzlich 390 px geprüft:
  kein Dokumentüberlauf, Themebutton 44 px. Hell/Dunkel auch im Editor.
  Abschließender regulärer Lauf ohne JavaScript-Fehler.

### Grenze und Übergabe

Die Bereitstellung von `1001` am Gerät ist weiterhin nicht nachgewiesen;
die Softwarequelle selbst ist belegt. Die indirekte Istregelgröße behebt
diesen Hardware-Nachweis nicht. 0 % kann insbesondere Gluterhaltung bedeuten,
nicht „Heizung aus“. Keine Mappingänderung oder automatische Aktivierung.

Keine reale App, private Konfiguration, Datenbank oder Produktionsauswahl
gelesen/verändert; keine Heizungsabfrage oder tatsächliche Erfassungsfreigabe.
Der Übertragungs-Smoke verwendete ausschließlich eigene Wegwerf-Instanzen,
keine Produktionsdatei. Bedienung und kompatibler Build sind in README und
Modbus-Dokumentation beschrieben. Eigene Prüfserver/Browsertabs beendet,
Smokeprogramm und synthetische Transferdatei entfernt. Keine Git-Aktionen.

## 18.10.2026 – Gerätetabellen-CSV mit Betriebsstatus vorbereitet

Auf ausdrücklichen Auftrag eine separate private Datei
`Modbus_P190317R_V3_Status.csv` vorbereitet. Basis: vorhandene vollständige
V1-Gerätetabelle, nicht die um Freitext ergänzte V2-Notizdatei.
Von 199 Zuordnungen 84 HK03–HK16-, 8 NM- und 36 SP-Zeilen entfernt;
HK01/HK02 und alle anderen Zeilen in ursprünglicher Reihenfolge erhalten.
Einzige neue Zuordnung: `Betriebsstatus;4097;1001`. Ergebnis 72 Einträge.
Keine privaten Originaldateien ins Repository übernommen.

Offline tatsächlich geprüft: drei Semikolonspalten, ASCII ohne BOM mit CRLF,
eindeutige Codes und Offsets, numerischer Hexcode gleich dezimalem Offset,
exakte Filterung und unveränderter Rest gegenüber der Vorlage, Kernregister
und Status vorhanden. Bestehender Monitor-CSV-Parser akzeptiert die Datei.
SHA256: `a8d3e38df6b6947dc4c9a73a0f41214569a7231986d915df70c729bfc19085fc`.

Kein Geräteimport/-zugriff oder aktiver Monitor-Auswahlwechsel. Tatsächliche
Importakzeptanz und Displayübereinstimmung nicht geprüft. Betreiber bestätigt
die bisher fehlende Zuordnung. Vor Import aktuelle Gerätetabelle als Rückweg
sichern, Leser pausieren und entfernte Kanäle im Monitor abwählen.
`1001` besitzt einen Schreibzweig; die Tabelle selbst kann keine reine
Lesefreigabe erzwingen. Sicherheits- und Abnahmegrenze in NEXT_STEPS ergänzt.

## 18.10.2026 – Decoder nach installiert gemeldeter Gerätetabelle

Betreiber meldet die neue CSV an der Heizung installiert. Die Lesepfade und
Parameterdefinitionen erneut in den privaten Originalquellen geprüft; keine
Originaltexte übernommen. Ergänzt: Betriebsart `1000` (Lesecodes
0/1/2/3/6/7/9/10), Kessel-Basis-Soll `1007` (60–90 °C), Puffer-SOLL
`9020` und START `9040` (10–90 °C). Grenzen einschließlich, Rohwörter erhalten;
ungültige Einstellungen und unbekannte Zustände werden Fehlerbeobachtungen.
Zusätzlich die CSV-Decoderlücken `1005` (30–100 % Maximalregelgröße),
`1012` (Software-Reinigung 0/1/2) und `1013` (gewichteter Intervallzähler in min)
geschlossen. Alle neuen Kanäle source-only, Intervall 300 s, nicht automatisch
ausgewählt oder als livebestätigt markiert. Keine Schreibfunktion.

Tatsächlich ausgeführt: 392 Python-Tests, 23 Node-Tests, TypeScript/Vite-Build
und Ruff erfolgreich. Eine bekannte Starlette-/AnyIO-DeprecationWarning.
Regressionen für zulässige und unzulässige Kodierungen/Parametergrenzen,
Originalrohwort-Erhalt, explizite Auswahl und endlichen Loopback-Collector
mit sieben Anfragen; Current, History und CSV geprüft. Überholte Ausschluss-
annahmen für nun lesbare START/SOLL-Offsets aus betroffenen Tests entfernt.

Die tatsächlich laufende API war zunächst `stopped_transport`, ohne neue
Kanäle in der gespeicherten Auswahl und ohne deren Beobachtungen.
Der Betreiber wählte den eigenen VS-Code-Neustart; danach lieferte die
laufende API die neuen Definitionen. Die vollständige reale CSV als reine
Vorschau gegen diese API geprüft: HTTP 200, alle 76 Zeilen zuordenbar.
Auch im tatsächlichen Vite-Editor die CSV als ungespeicherten Entwurf
hochgeladen, neue Decoderzuordnungen sichtbar geprüft und Screenshot gesichtet.
Kein PUT/Save und keine Quittierung: gespeicherte Revision 5 unverändert,
Collector weiter `stopped_transport`. Eigenen Prüftab danach geschlossen.

Keine direkte Modbus-Anfrage, kein zusätzlicher Anlagenclient, keine
Geräteschreibaktion, kein Eingriff in die laufende Prozessverwaltung durch
den Assistenten. Tatsächliche neue Anlagenwerte/Displayübereinstimmung bleiben
offen. Der Transportstopp ist nicht durch neue Decoder behoben oder
quittiert; seine Ursache vor einer begrenzten erneuten Lesesitzung klären.

## 18.10.2026 – Dashboardhinweise und Aufzeichnungsübersicht gekürzt

Die laufende Oberfläche zeigte beim automatischen Zeitcursor die älteste
Temperaturbeobachtung, während die Statushistorie erst später begann. Der
Text „Keine Messung an dieser Stelle“ war deshalb historisch richtig, aber
ohne bewusste Zeitwahl leicht als aktueller Gerätefehler misszuverstehen.
Keine Änderung an Messwerten, Decodern oder Lücken-/Frischegrenzen.

Zeitcursor und Einzelwerte erscheinen jetzt erst bei Maus-, Touch- oder
Tastaturinspektion. Fehlende Statusbeobachtungen benennen den gewählten
Zeitpunkt und die Suchnähe ±2,5 Minuten. Die aktuelle Kesselkarte bleibt davon
unabhängig. Im Normalfall nur Zustand, Beobachtungszeit und Abfrageintervall;
technische Hinweise in aufklappbaren Quellendetails. Konkrete Probleme und
indirekte Hinweise bleiben sichtbar. Den pauschalen Garantiehinweis bei
leerer Fehlerliste entfernt, ohne die Fehleranzeige abzuschalten.

Modbus-Konfiguration: doppelte vollständige gespeicherte/aktive Registerlisten
entfernt. Kompakter Status mit Anzahl, Übernahmestatus und Revision;
aktive Anzahl/Revision zusätzlich nur bei ausstehender Übernahme. Einleitung
gekürzt, irreführendes Offline-Etikett durch Modbus-Konfiguration ersetzt.
Import-/Exportfunktionen und Read-to-clear-Warnung unverändert.

In der laufenden Vite-Oberfläche mit laufender API geprüft: 76 ausgewählte
Register, Übernahme aktiv, Revision 6, kompakte Statuskarte statt Listen.
Browserprüfungen für anfänglich ausgeblendete Einzelwerte, historische
Statuslücke, gezielte Inspektion einer echten Statusbeobachtung, unabhängige
aktuelle Statuskarte und bedienbare Quellendetails. Mobile Anzeige bei 390 px
ohne horizontalen Seitenüberlauf und erfolgreiche Touch-Statusinspektion;
Screenshots der tatsächlichen Desktop-/Mobiloberfläche gesichtet.
Ausstehende Übernahme zusätzlich ausschließlich im eigenen Browsertab mit
synthetischer API-Antwort geprüft: gespeicherte und aktive Anzahl getrennt.
TypeScript/Vite-Build erfolgreich. Keine neue UI-Testsuite eingeführt.

Keine Konfiguration gespeichert, keine Erfassung gestartet/gestoppt/quittiert
und keine zusätzlichen Geräteanfragen durch den Assistenten. Die laufende
Erfassung des Betreibers bleibt unberührt. Keine Hardware-/Displayabnahme.

## 18.10.2026 – Modbus-Seite auf Registerauswahl fokussiert

CSV-Import und JSON-Transfer als zwei standardmäßig geschlossene Bereiche.
Anleitungen gekürzt, überholten ständigen Statuskanal-Einzelimporthinweis
entfernt. CSV-Ergänzung und JSON-Ersatz einschließlich Abwahlen bleiben
ausdrücklich unterschieden. Auswahl und Metadaten werden weiterhin nur
als Entwurf geändert, erst der bestehende Save übernimmt.

Registertabelle von sieben auf drei Spalten reduziert: Name mit Hexcode/
Offset, Aufzeichnung und Signal/Details. Eigene Einheiten/Beschreibungen sowie
Decoder-/Quellenangaben je Zeile aufklappbar. Unverändert-Plaketten entfernt,
neue/geänderte Felder weiterhin hervorgehoben. Sperrgründe, inaktive Module
und Read-to-clear-Warnungen bleiben sichtbar; ausgewählte Protokollregister
zusätzlich unmittelbar vor den Speicheraktionen angekündigt. Speicheraktionen
vor die Tabelle verschoben, allgemeine Bearbeitungshinweise eingeklappt.
Keine Request-, Import-, Auswahl-, Konflikt- oder Speicherlogik geändert.

Tatsächlich laufende API/Vite-App im Browser geprüft: 88 vorhandene und 76
ausgewählte Register. Lokale Beschreibungs-/Auswahländerung blieb über
Navigation erhalten. Metadateneditor aufklappbar, gesperrte Register weiter
deaktiviert, Protokollwarnungen erreichbar. JSON-Download HTTP 200;
CSV-Vorschau HTTP 200 und eigene ungespeicherte Beschreibung erhalten.
Eigener Prüftab ohne Speicherung verworfen und geschlossen.

Desktop-Screenshots sowie mobile Darstellung bei 390 und 320 px geprüft:
kein horizontaler Dokumentüberlauf, nur die Tabelle intern scrollbar.
TypeScript/Vite-Build erfolgreich. Keine neuen UI-Testabhängigkeiten.
Gespeicherte und aktive Revision 6 sowie 76 ausgewählte Register unverändert,
Collector weiterhin running. Kein PUT/Save, kein Start/Stopp/Quittieren,
keine zusätzlichen direkten Anlagenanfragen. Kein Hardware-/Displayabgleich.

## 18.10.2026 – Issue #56: Stunden, Zeitachse, Hover und Frische

Nur Offline-Umsetzung mit synthetischen Daten; keine Anlagenanfragen und keine
Änderung privater Konfiguration oder laufender Erfassung.

- Anlagen-Betriebszähler in Übersicht, Werteliste, Signalwahl, Diagramm,
  Inspektion und Hover in Dezimalstunden. Originalminuten, Signal-ID,
  API und CSV bleiben unverändert; andere Minutensignale werden nicht umgerechnet.
- Die bereits vorhandene feste Abfragezeitachse bleibt erhalten, einschließlich
  leerer Randbereiche, innerer Lücken, Einzelpunkten und leerer Zeiträume.
- Sichtbarer Hover zeigt ausschließlich nahe gültige Originalbeobachtungen mit
  Signalname, tatsächlicher Messzeit in der Anzeigezeitzone und Wert/Einheit.
- Current-API liefert `fresh_until_age_seconds = 4 * interval_seconds`.
  Browseralter und Betriebsanzeige verwenden dieselbe Backendgrenze; auf der
  Grenze noch frisch, erst darüber veraltet. Fehler/null bleiben nicht frisch.

Tatsächlich ausgeführt:

- `uv run pytest`: 416 bestanden; eine DeprecationWarning aus Starlette/AnyIO.
- `uv run ruff check .`: erfolgreich.
- `node --test tests/*.test.mjs`: 25 bestanden.
- `npm run build`: TypeScript und Vite erfolgreich.
- `git diff --check`: erfolgreich.
- API-Grenztests mit synthetischen Intervallen 7 und 91 Sekunden, jeweils
  1 ms vor, auf und nach der vierfachen Grenze; gültig, invalid, null und missing.
- Tatsächlicher Chromium-Browser mit synthetischen API-Antworten: Übersicht
  zeigt 90 Minuten als 1,5 h; alle fünf Zeitraumoptionen inklusive freier
  Grenzen 01.–02.10.2026 durchlaufen und ausgewiesene Abfragegrenzen geprüft.
- Isolierte tatsächliche Diagrammkomponente im Browser: Daten nur im mittleren
  Teil des Fensters, innere Lücke, einzelner Zähler-/Temperaturpunkt und leeres
  Fenster. Sichtbare Tooltips für 1,5 h, 24 h und 65 °C samt Europe/Vienna und
  tatsächlicher Messzeit; in der leeren Fläche kein Tooltip. Screenshots geprüft.
  Temporäre Prüfseite anschließend entfernt.

Keine Geräte-, Display-, Unraid- oder Dauerbetriebsabnahme. Der Browsernachweis
verwendet synthetische Quellen, keine privaten Messwerte.

## 19.10.2026 – Fortlaufendes Polling statt Fehlversuchslimit

**Betreiberauftrag:** Der Sammler soll bei Nichterreichbarkeit nicht nach einer
festen Zahl von Fehlversuchen dauerhaft stoppen, sondern im festgelegten
Intervall weiter auslesen.

**Umsetzung:** Gemeinsamer normaler Zeitplan auch nach Verbindungsfehlern;
kein Fünf-Versuche-Limit, keine 1/2/5/10/15-Minuten-Backoff-Stufen und keine
Drei-Kernzyklen-Resetlogik mehr. Kernblöcke mindestens 60 s, normale Zusatzblöcke
mindestens 300 s ab Abschluss. Fehlerhafte Zusatzabfragen verdrängen keine
fälligen Kernwerte. Erfolgreiche Antworten werden direkt wieder gespeichert;
Fehlerbeobachtungen bleiben mit `value=null` in der Historie.

Alte Transportstopps werden beim aktivierten Dienststart automatisch
fortgesetzt, sofern alter und neuer Lauf unbeschränkt sind und kein
Read-to-clear-Block betroffen ist. Nutzerpause, Zielwechsel, endliche
Laufgrenzen, `completed`, Signalsperren und harte Protokoll-/Daten-/Speicherstopps
bleiben wirksam. Ungewisse Read-to-clear-Auslesungen behalten ihren Schutzstopp.
Die API akzeptiert Diagnosezähler über fünf und liefert kein
`reconnect_attempt_limit` mehr. Das Dashboard zeigt Fortsetzung ohne Versuchslimit.

**Ausgeführte Offline-Prüfungen:**

- `uv run --locked pytest -q` mit deaktivierter Erfassung und leerem Ziel:
  419 bestanden; eine DeprecationWarning aus Starlette/AnyIO.
- `npm run build`: TypeScript und Vite erfolgreich.
- `node --test tests/dashboard.test.mjs`: 25 bestanden.
- `uv run --locked ruff check .`: erfolgreich.
- Regressionen: länger anhaltender Ausfall und Erholung, reguläre Kern-/Zusatz-
  intervalle, nicht verdrängte Kernwerte, Auswahlwechsel nach Fehler, Neustart
  aus alten Budgetsperren und unterbrochenen Anfragen, Pause/Fortsetzung sowie
  unveränderte endliche und harte Schutzgrenzen.
- Throwaway-Smoke mit echtem `ModbusTcpClient`, Loopback-Simulator
  `close_no_data`, SQLite und virtueller Schedulerzeit: erster Lauf genau
  21 fehlgeschlagene FC03-Anfragen, weiterhin `reconnect_wait`, Diagnosezähler 20.
  Zweiter Lauf 21 Fehler, anschließend drei erfolgreiche Anfragen nach Wechsel
  zu gültigen Simulatorantworten; danach ausdrücklich durch den Prüflauf gestoppt.
  Pro Kernblock exakt 60 s virtuelle Abstände, sieben Fehlerbeobachtungen und
  anschließend gültige Kesseltemperatur 42 °C als synthetischer Wert.
  SQLite-Integrität in beiden Läufen `ok`.
- Tatsächlich gebautes Dashboard mit isolierter laufender FastAPI auf Loopback
  in Chromium geöffnet. API-Zustand `reconnect_wait` mit 20 Folgeversuchen,
  nächster Termin und Hinweis „ohne Versuchslimit“ sichtbar; Screenshot geprüft.
  Keine fingierten Browserantworten; Daten stammen aus dem Loopback-Ausfalllauf.
  Prüftab und Prüfserver anschließend beendet.

**Grenzen:** Keine Anlagenanfrage, kein Unraid-Deployment, keine Langzeit- oder
Displayabnahme. `.env`, reale Daten und laufende Heizungs-App blieben unverändert.
Die neue Wiederaufnahme benötigt einen neuen App-/Image-Build und dessen Neustart;
bestehende veröffentlichte Images wurden nicht verändert.

## Unplausible Werte speichern statt sperren (30.10.2026)

**Auslöser (Benutzerangabe):** Produktive Instanz meldete Kerntemperatur 110 °C
(`invalid_temperature`); das Signal wurde bisher mit `value=NULL` dauerhaft gesperrt.

**Änderung:** Bereichsfehler speichern den dekodierten Wert mit Qualität `invalid`
(keine Schema-Migration), setzen keine Signalsperre mehr und werden im Diagramm als
Marker, an der Kachel als „Unplausibel" gekennzeichnet. Alte Wertfehler-Sperren
fallen beim Start weg; Modbus-Ausnahme-2/3-Sperren bleiben.

**Ausgeführte Offline-Prüfungen (synthetisch/in-process):** `pytest` 420 bestanden
(Python 3.14 statt Projekt-3.12, lokale Scratch-Umgebung), `node --test` 26 bestanden,
`npm run build` (tsc + vite) erfolgreich.

**Grenzen:** Kein Geräte- oder Unraid-Zugriff; die laufende App wurde nicht neu
gestartet. Wirkt erst nach neuem Build und Neustart.
