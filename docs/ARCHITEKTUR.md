# Architektur und Modulgrenzen

Ein deploybarer Container: Python/FastAPI liefert API und gebautes React/TypeScript-
Frontend. Node wird nur zum Bauen benötigt. SQLite auf lokalem persistentem Volume.

```mermaid
flowchart LR
  R[FC03-Leseclient] --> V[Decoder und Qualitätsprüfung]
  S[Ein Scheduler] --> R
  V --> DB[(SQLite)]
  DB --> API[FastAPI]
  API --> UI[Browser-Dashboard]
  DB -. später .-> MQTT[MQTT / Home Assistant]
  F[Externe Prognose] -. später .-> E[Offline-Entscheidung]
  DB -.-> E
```

## Komponenten

- Registerprofil: versionierte, freigegebene Gruppen; öffentliche Vollreferenz ist
  keine ausführbare Konfiguration. Das implementierte Erstprofil `core` enthält
  ausschließlich die drei bestätigten Blöcke in `backend/registers.py`.
- Transport: `backend/modbus.py` erzeugt ausschließlich FC03-Anfragen zu den exakten
  `core`-Blöcken, immer Unit 255, höchstens zwei Register und mit 3-s-Gesamtdeadline.
  Keine Wiederholungen. MBAP/PDU, Protokoll-ID, Länge, Transaktion, Unit, Funktion
  und Byteanzahl werden geprüft; Fehler enthalten empfangene Bytezahl.
- Decoder: reine Funktionen, Signalherkunft und Gültigkeit. Kein I/O und keine
  stillschweigende Skalierung unbekannter Einträge.
- Sammler (`backend/collector.py`): zentraler sequenzieller Kernprofil-Leser mit
  mindestens 60 s ab Abschluss der vorherigen Verarbeitung desselben Blocks,
  hochauflösend monoton gemessen, ohne zusätzliche Pause zwischen verschiedenen
  Blöcken. Testläufe begrenzen Dauer und/oder Anfragezahl; Pause, Stop und Shutdown
  sperren neue Reads.
  Ein OS-Dateilock im Datenverzeichnis verhindert konkurrierende Prozesse mit
  gemeinsamem Deployment-Volume. Die FastAPI-Lifespan startet ihn nur bei
  `COLLECTOR_ENABLED=true`; HTTP-Aufrufe starten keine Reads.
- Repository (`backend/storage.py`): versioniertes SQLite-Schema, atomare und
  idempotente Erfassungszyklen, Ereignis-/Zustands-/Konfigurationsspeicherung,
  begrenzte Chronologieabfragen, Online-Backup/Restore und Speicherfehler als
  `StorageError`. Anwendungsstart öffnet `/data/monitor.sqlite3` und prüft Migrationen.
- API/UI: `backend/main.py` stellt aus SQLite aktuelle Werte, seitenweise Historie,
  paginierte Ereignisse und gestreamten Original-CSV-Export bereit. Lesezugriffe
  sind Modbus-unabhängig. Mutierende Browser-Requests verlangen Same-Origin-Header;
  die API-Konfiguration kann nur die Anzeigezeitzone ändern. Modbus-Endpunkt und
  Datenpfad bleiben private Deployment-Konfiguration.
  Der Container liefert das gebaute Frontend über `StaticFiles`, `/api/version`
  gibt App-Version und Buildrevision aus. `Dockerfile` baut UI/Python getrennt;
  Runtime läuft nicht-root, schreibt persistent nach `/data` und startet per
  SIGTERM kontrolliert herunter.
- Ausgabeadapter später: MQTT unabhängig von der Verfügbarkeit des Brokers;
  Prognose und Steuerung bleiben getrennte Module und Datentypen.

## Konfiguration und Lebenszyklus

Die lokale Schnittstelle ist in `backend/config.py` umgesetzt; `.env.example` enthält
nur sichere Standardwerte. Unterstützte Variablen: `MODBUS_HOST` (optional),
`MODBUS_PORT`, `MODBUS_UNIT_ID`, `REGISTER_PROFILE`, `COLLECTOR_ENABLED`,
`COLLECTOR_MAX_REQUESTS`, `DATA_DIR` und `DISPLAY_TIMEZONE`. `COLLECTOR_ENABLED` ist
standardmäßig `false`; bei aktivierter Erfassung ohne Host startet die Anwendung mit
Konfigurationsfehler. `COLLECTOR_MAX_REQUESTS` begrenzt die Gesamtzahl der Reads und
deaktiviert automatische Wiederaufnahmen bei Transportfehlern für diesen endlichen
Lauf. Ohne Wert bleibt der reguläre Sammlerbetrieb unverändert. `/api/config` gibt nur
`host_configured` statt des Hostwerts zurück und veröffentlicht keinen privaten Datenpfad.

`uv.lock` sperrt Python-Abhängigkeiten; `package-lock.json` sperrt Frontendpakete.
Entwicklungsbasis: CPython 3.12.9, Node.js 22.14.0 und npm 10.9.2. Python 3.12
wird als konservative, von den benötigten Bibliotheken unterstützte Laufzeitreihe
verwendet; Node 22 ist die LTS-Reihe für den React/Vite-Build. CI und Lockdateien
fixieren reproduzierbare Eingaben. Änderungen dieser Versionen erfolgen bewusst
und zusammen mit aktualisierten Locks.

Der FC03-Transport ist eine synchrone Socket-Implementierung ohne Bibliotheks-Retry.
Der Offline-Simulator (`python -m backend.modbus_simulator`) bindet ausschließlich an
Loopback und bietet deterministische Antworten/Fehler. Der Sammler verbindet nur die
exakten Blöcke des `core`-Profils mit Decoder und SQLite. App-Start ohne
`COLLECTOR_ENABLED=true` öffnet nur die lokale Datenbank; bei aktivierter Erfassung
startet genau ein prozessweiter Sammler. API-/Browser-Refreshes lesen keine Modbus-Daten.

SQLite liegt in `DATA_DIR/monitor.sqlite3` (Standard `/data`) auf lokalem persistentem
Speicher. WAL, `synchronous=FULL`, versionierte Migration und SQLite-Online-Backup
werden durch `backend/storage.py` umgesetzt. Restore prüft Integrität und startet einen
gesicherten Sammlerzustand pausiert. Die Anwendung gibt den Datenpfad nicht über
`/api/config` aus. Netzwerkdateisysteme wie SMB/NFS sind für die aktive WAL-DB nicht
vorgesehen.

Shutdown: neue Anfragen sperren, laufende Anfrage höchstens bis Deadline beenden,
Speichertransaktionen abschließen, Zustand sichern, Verbindung schließen. Mehrere
Browser dürfen keine zusätzlichen Sammler starten. Das Deployment muss auch
konkurrierende Container für dieselbe Anlage verhindern bzw. erkennen; kein alleiniger
prozesslokaler Mutex als hinreichende Lösung behaupten.

Testbarkeit: Clock, Transport und Speichergrenzen injizierbar; Tests können Minuten
simulieren, ohne in Echtzeit zu warten. Änderungen an Laufzeiten erfolgen zusammen
mit aktualisierten Python-/npm-Locks und CI-Versionen.
