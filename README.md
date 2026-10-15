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

Issue #30 ergänzt die isolierte Katalogreferenz für das Register-Prüfwerkzeug:
199 unveränderte Zuordnungen als validierte Paketressource, unveränderlicher
Prozesssnapshot und Auswahl von 1–3 engen Leseblöcken.
Vertrag und Grenzen: [Modbus/Katalog](docs/MODBUS.md#diagnoseauswahl-issue-30).

Issue #31 ergänzt ein getrenntes SQLite-Diagnosejournal mit unveränderlichen
Prüfplänen, dauerhaften Anfrage-Reservierungen, quittierungspflichtigen Stopps und
Schema-v2-Migration/Restore. Keine Geräte-I/O; Steuerrevisionen erhalten nur ihre
Tabelle. Interner Speichervertrag und Datenschutz:
[Datenmodell](docs/DATENMODELL.md#diagnosejournal-issue-31).

Issue #32 ergänzt `read_catalog()` über denselben strikten FC03-Telegrammpfad
wie Kernreads und den expliziten synthetischen Simulator-Katalogmodus
(`--catalog`). Issue #33 ergänzt den endlichen manuellen `ReadCheckRunner` mit
gemeinsamem Gerätebesitz, persistenten Stopps und gesperrter Recovery:
höchstens drei explizite Reads, 60 s Abstand einschließlich Speicherung,
600 s Laufzeit; keine zusätzlichen Kernmessungen. Issue #35 bindet Diagnose-API,
Recovery und Lifespan sicher an. Issue #36 ergänzt die Bedienung im Dashboard:
Katalog/Details, manuelle Prüfläufe und nicht ausführbare Steuerentwürfe.
Keine zusätzliche Live-Abnahme.
Issue #37 belegt die automatisierte Sicherheits-/Verbraucherabnahme einschließlich
echter Zweitprozesssperren, gegateter Stop-/Reservierungs-/Joinrennen,
unveränderter Backupquellen und nicht ausführbarer Steuerrevisionen.
Vollständige Matrixzuordnung und tatsächlich ausgeführte Prüfungen:
[Ergebnisse](reports/RESULTS.md#15102026--issue-37-automatisierte-diagnose-gesamtabnahme).
Die Browser-/Persistenzabnahme #38 ist mit echten Wartezeiten, bereinigten
Screenshots, Download-/SQLite-Abgleich und hartem Exception-Stopp belegt:
[Ergebnisse und Oberflächenbelege](reports/RESULTS.md#15102026--issue-38-reale-offline-browserabnahme).
Issue #39 belegt das installierte Wheel außerhalb des Checkouts (199 Einträge,
identische Ressourcenbytes) und die tatsächlich bediente gebaute StaticFiles-UI.
Containerlauf lokal ungeprüft: Docker nicht verfügbar.
[Paketabnahme und Grenzen](reports/RESULTS.md#15102026--issue-39-wheel-und-gebaute-laufzeitoberfläche).

Epic #29 bündelt die abgeschlossenen Pakete #30–#39; Umsetzung und getrennte
Offline-Abnahmen sind in der [Abschlussmatrix](reports/RESULTS.md#15102026--issue-29-epicabschluss)
den jeweiligen Pull Requests zugeordnet. Die Container-, Unraid-, Live- und
Steuerungsgrenzen bleiben ausdrücklich bestehen.


Issue #34 ergänzt rein offline bewertete Steuerentwürfe mit atomaren,
unveränderlichen SQLite-Revisionen und privater Exportprojektion. Auch vollständig
ausgefüllte Pläne bleiben nicht ausführbar; Sensorblocker und ungeklärter
autonomer START-/SOLL-Rückfall bleiben sichtbar.
[Vertrag](docs/DATENMODELL.md#steuerentwürfe-und-revisionen-issue-34).

Die Diagnose-API unter `/api/diagnostics` liefert bereinigtes Inventar, endliche
Prüfpläne und private JSON-Belege sowie revisionierte Offline-Steuerentwürfe.
GETs lösen keine Geräteanfrage aus; Start verlangt ausdrücklich
`other_readers_stopped:true` und sendet ebenfalls nichts. Nur ein zulässiger,
expliziter `/read` führt genau einen FC03-Versuch aus. Monitoring startet nach
Diagnoseende oder Quittierung nicht automatisch erneut.
[HTTP-Vertrag und Vertrauensgrenze](docs/DATENMODELL.md#diagnose-http-api-issue-35).

Im Dashboard zwischen **Übersicht** und **Diagnose** wechseln. Kopf und
Erfassungsstatus bleiben sichtbar; der Bereichswechsel erhält geladene Belege
und Formulareingaben. Die Diagnose bietet 50er-Katalogseiten, Suche nach Name,
Dezimaloffset oder Hexcode und getrennte START-/SOLL-Kandidaten ohne Leseauswahl.
Ein Prüfplan zeigt vor dem Start die tatsächlich aufgelösten Serverblöcke.
Nur „Nächste Anfrage lesen“ sendet nach der serverseitigen Wartefrist eine
einzelne Anfrage; jede Antwort benötigt eine ausdrückliche Bewertung.
Countdown, Refresh und JSON-Export starten nichts. Fehlerquittierung und
Diagnoseende setzen das Monitoring nicht fort.

Steuerpläne speichern ausschließlich Offline-Entwürfe mit Revisionsprüfung.
Bei einem Konflikt bleiben Eingaben erhalten; der neue Serverstand muss
ausdrücklich übernommen werden. „Formal bereit zur fachlichen Prüfung“ ist
keine Freigabe. Auch vollständige Exporte bleiben `execution_enabled:false`.
JSON-Belege und Betreiberfreitexte sind privat, nicht für öffentliche Issues.

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
Standardstart ohne aktivierte Erfassung führt keine Gerätezugriffe aus und startet
keinen Simulator. Ein konfigurierter aktivierter Sammler startet erst nach
erfolgreicher Diagnose-Recovery und Besitzprüfung.
Den Simulator lokal mit `uv run python -m backend.modbus_simulator` starten
(Standardbindung `127.0.0.1:1502`); Faults sind per `--fault` wählbar.

## Docker und Unraid

Für Unraid steht [compose.unraid.yaml](compose.unraid.yaml) als eigenständiger
Stack mit **`ghcr.io/lum1nat0r/sommerauer-monitor:0.2.1`** bereit, ohne lokalen
Build. Einrichtung von `.env`, persistentem Datenpfad und Start:
[Unraid-Anleitung](docs/UNRAID.md#unraid-veröffentlichtes-image-verwenden).
Der Container läuft standardmäßig als UID 99/GID 100, bindet Port 8000,
persistiert in `/data` und startet ohne Hostadresse oder aktivierte Erfassung.
Beim Zugriff über eine HTTPS-Domain hinter einem Reverse-Proxy die private
Containervariable `PUBLIC_ORIGIN` setzen; direkte Zugriffe bleiben möglich.
Die Korrektur benötigt ein entsprechend neu gebautes Image, nicht nur eine
Variable im bisherigen Image. [Proxy-Konfiguration](docs/UNRAID.md#domain-und-https-reverse-proxy).

Die bisherige `compose.yaml` bleibt für lokale Builds:
`cp .env.example .env`, beschreibbaren `DATA_PATH` setzen und
`docker compose up --build -d` ausführen. `/api/version` meldet Buildversion
und Revision. Pull Requests prüfen einen `linux/amd64`-Image-Build ohne Push.
Der Release-Git-Tag für Version 0.2.1 heißt **`v0.2.1`**; der Workflow veröffentlicht
nach seinen Offline-Prüfungen das Image mit Tag **`0.2.1`**
([Strategie und Sperren](docs/UNRAID.md#github-image-build-und-veröffentlichungsgrenze)).
Bis zur erfolgreichen Veröffentlichung, öffentlicher GHCR-Freigabe und anonymem
Pull ist dessen Verfügbarkeit nicht belegt. Lokale Docker-Prüfungen belegen
keine Installation auf Unraid oder Gerätefunktion.

Lizenz: eigener App-Code unter [MIT](LICENSE), vom Betreiber am 15.10.2026 bestätigt.

## Dokumentation

| Dokument | Inhalt |
|---|---|
| [Architektur](docs/ARCHITEKTUR.md) | Bausteine, Zuständigkeiten und Konfiguration |
| [Modbus](docs/MODBUS.md) | Offsets, Decoder, Prüfstatus und bekannte Grenzen |
| [Registerkatalog](backend/resources/register_catalog.json) | Alle 199 dokumentierten Projektzuordnungen; kein aktives Pollingprofil |
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
