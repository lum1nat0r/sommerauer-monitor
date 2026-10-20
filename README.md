# Sommerauer Monitor

Geplante lokale Monitoring-App für eine Sommerauer-Pelletsheizung: Modbus-Datenlogging,
dauerhafte Minutenhistorie und Web-Dashboard auf Unraid.

**Stand 15.10.2026: Projektgrundlage, bestätigtes Kernprofil/Decoder, strikter FC03-Lesetransport,
Loopback-Simulator, SQLite-Speicherung, zentraler Sammler, automatische Wiederaufnahme,
lesende API, Dashboard und Offline-Ende-zu-Ende-Abnahme (#12) umgesetzt.**
Die gestufte lokale Kernregister-Abnahme (#13) ist mit endlichen FC03-Läufen
und vom Betreiber bestätigtem Displayabgleich belegt
([Ergebnisse](reports/RESULTS.md), [Betriebsplan](docs/INBETRIEBNAHME.md)).
Offen: tatsächliches Unraid-Deployment und Langzeitbetrieb. Kein Dauerbetrieb aktiviert.

**Rückbau 16.10.2026:** Diagnosefunktion und Offline-Steuerentwürfe wurden
entfernt; die App dient dem Monitoring. Die Git-Historie bleibt erhalten.
Vorhandene Datenbanken und Minutenhistorien nicht löschen.

## Hier mit der Arbeit beginnen

1. [AGENTS.md](AGENTS.md): Arbeitsrahmen und Grenze für Geräteänderungen.
2. [Plan](docs/PLAN.md) und [Entscheidungen](docs/ENTSCHEIDUNGEN.md).
3. [Roadmap mit Issues](docs/ROADMAP.md) und [nächste Schritte](NEXT_STEPS.md).
4. Für das gewählte Issue die dort verlinkten Fachunterlagen lesen.

Erste Version: Kesseltemperatur, Puffer oben/unten und Anlagen-Betriebszähler;
weitere Register nach Prüfung. Alle Minutenmessungen bleiben dauerhaft erhalten.
Fehler einzelner Werte werden isoliert; übergreifende Protokoll-/Speicherfehler stoppen.
Reine Verbindungsfehler beenden den Dauerbetrieb nicht mehr: weiter im normalen
60-/300-s-Intervall, ohne Fehlversuchslimit oder steigende Wartezeiten.
Endliche Prüfläufe und ungewisse Read-to-clear-Auslesungen behalten ihre Stopps.
Messlücken und Datenalter bleiben sichtbar.

Vorgesehener Aufbau: Python/FastAPI, SQLite, React/TypeScript, ein Docker-Container.
Ein zentraler Sammler; Browser und später Home Assistant verwenden seine Daten.
Unraid 7.3.2, Zugang im Heimnetz/Tailscale. Deployment übernimmt der Betreiber.

## Lokale Entwicklung

Separates **START/SOLL-Testwerkzeug** mit eigenem CLI-Container, privatem Plan,
Rücklesen und aktiver Rückstellung: [Bedienung](docs/SCHREIBTEST.md).
`python -m write_test template` erzeugt lokal eine unvollständige Planvorlage,
ohne Gerätezugriff. Das statisch geprüfte Schreibprofil kann nur bestimmte
Temperaturen darstellen; tatsächliche Geräteversion vor Nutzung bestätigen.
Kein garantierter Rückfall bei Host-/Netzausfall.

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

### API und Dashboard mit der Heizung in VS Code

Unter Windows und Linux dieselbe `.vscode/launch.json` verwenden:

1. Abhängigkeiten wie oben mit `uv sync --locked` und `npm ci` installieren.
   VS-Code-Erweiterungen **Python** und **Python Debugger** installieren.
2. Über **Python: Select Interpreter** die Projektumgebung auswählen:
   Linux `.venv/bin/python`, Windows `.venv/Scripts/python.exe`. Die Launch-Datei
   übernimmt diesen Interpreter ohne fest eingebauten Betriebssystempfad.
   `npm` muss im PATH des VS-Code-Prozesses liegen; unter Windows wird
   ausdrücklich `npm.cmd` verwendet.
3. Eine private `.env` im Projektstamm anhand von `.env.example` anlegen.
   `MODBUS_HOST` ausschließlich auf die tatsächlich freigegebene Hausanlage
   setzen; Port 502, Unit 255 und Profil `core` gemäß bestätigter Konfiguration.
   Die Datei ist ignoriert und wird nicht über Git übertragen; auf jedem Rechner
   privat bereitstellen.
4. Andere Modbus-Leser beenden und den begrenzten Lauf gemäß
   [Inbetriebnahme](docs/INBETRIEBNAHME.md) dokumentieren.
   In **Run and Debug** **Sommerauer Monitor: Heizung (API + Dashboard)**
   auswählen und mit **F5** starten.

Dieser Start aktiviert den in der API integrierten Sammler, aber **keinen
Simulator**. Er überschreibt aus Sicherheitsgründen drei `.env`-Werte:
`COLLECTOR_ENABLED=true`, `COLLECTOR_MAX_REQUESTS=3` und
`DATA_DIR=${workspaceFolder}/data/vscode-heizung`. Zieladresse und übrige
Gerätekonfiguration kommen aus der privaten Umgebung/`.env`; keine eingebaute
Heizungsadresse. API auf `127.0.0.1:8000`, Dashboard über Vites gemeldete URL
(normalerweise `http://127.0.0.1:5173`). Port 8000 muss frei sein.

Ohne gespeicherte abweichende Aufzeichnungsauswahl werden die drei bestätigten
FC03-Blöcke einmal gelesen; danach zeigt die UI **Erfassung abgeschlossen**.
Bei endlichen Läufen gibt es keine Wiederholung nach Verbindungsfehlern.
API und Dashboard bleiben verfügbar; Debug-Stopp beendet beide Starts.
Heizungsdaten bleiben dauerhaft im separaten Verzeichnis erhalten, ohne sie
mit `data/vscode-simulator/` zu vermischen. Neustart quittiert weder Abschluss
noch Fehler und gibt kein neues Anfragebudget; zum Weiterarbeiten keine DB
löschen. Dies ist kein automatisch aktivierter Dauerbetrieb.

Die bestehende Auswahl **Offline-Gesamttest** bleibt unverändert verfügbar.

`/api/config` enthält weder Hostwert noch lokalen Datenpfad. Der Host wird nur als
gesetzt/nicht gesetzt ausgewiesen. Der enge FC03-Client und Offline-Simulator sind
unter `backend/modbus.py` und `backend/modbus_simulator.py` verfügbar; der
Anwendungsstart startet weder Sammler noch Simulator und führt keine Gerätezugriffe aus.
Den Simulator lokal mit `uv run python -m backend.modbus_simulator` starten
(Standardbindung `127.0.0.1:1502`); Faults sind per `--fault` wählbar.

### Dashboard: Übersicht, Analyse und alle Werte

Die Übersicht (`#/`) stellt die **Betriebsanzeige des Pelletkessels**
und ausgewählte Kessel-/Puffertemperaturen in den Mittelpunkt. API-Erreichbarkeit
und Erfassungszustand sind davon getrennt; „Erfassung abgeschlossen“ bedeutet
nicht „Heizung aus“. Eine aktuelle gültige Beobachtung des ausgewählten
Statuskanals `1001` hat Vorrang. Fehlt sie, verwendet die Anzeige eine
ausgewählte aktuelle Istregelgröße `1003` in `%` als **indirekten Betriebshinweis**:
über 0 % „Leistungsregelung aktiv“, bei 0 % „Betriebszustand nicht eindeutig“.
0 % kann auch Gluterhaltung bedeuten, kein bestätigtes „Aus“.
Ohne brauchbare Quelle erscheint „Betriebszustand unbekannt“ mit konkretem Grund.
Veraltete/ungültige Werte und API-Ausfälle ergeben keinen aktuellen Ersatzbefund.
Temperaturen, Abgas und Betriebszähler werden nicht zu Flammen-/Ein-Aus-Nachweisen
umgedeutet. Das Statusband bleibt ausschließlich echten Statusbeobachtungen vorbehalten.
Beide Quellen haben 300-s-Abtastintervall und 1200-s-Frischegrenze (vier Intervalle, Grenze inklusiv), keine
sekundengenaue Liveanzeige. Der Betreiber meldet die neue Gerätetabelle installiert;
ein eigener Messwert-/Displayabgleich von `1001` steht noch aus:
[Statuskanal und lokale CSV-Aufnahme](docs/MODBUS.md#kessel-steuerungszustand-nur-lesend-und-ausdrücklich-auswählen).

Die Statuskarte zeigt im Normalfall nur Zustand, Beobachtungszeit und
Abfrageintervall. Quellen-/Frischeinformationen sind unter **Quelle und
Aktualisierung** aufklappbar; konkrete Probleme und indirekte Betriebshinweise
bleiben direkt sichtbar.

Unter **Analyse** (`#/analyse`) stehen passende Vergleiche nur für gespeicherte
ausgewählte Quellen bereit: Puffer & Kessel, Pufferschichtung (oben minus unten
in K, nur zeitgleiche gültige °C-Werte), interne Leistungsregelung in %,
Heizkreis-Ist/Soll und Einzelwert. Kein Solarertrag, keine thermischen kW
oder Flammenstunden werden daraus abgeleitet.

Alle Reihen teilen feste Zeitgrenzen und die Anzeigezeitzone. Relative Fenster
wandern beim 60-s-Refresh; freie Grenzen einschließlich DST-Prüfung bleiben fest
und werden lokal gemerkt. Die Historie wird vollständig seitenweise geladen,
mit Fortschritt und **Laden abbrechen**, höchstens zwei Reihen gleichzeitig.
Fehlende Seiten oder Reihen werden benannt. Messfehler, große Lücken und
Einheitenwechsel werden nicht verbunden. Unterschiedliche gespeicherte Einheiten
bleiben auf getrennten Diagrammflächen; gespeicherte Werte werden nicht umgerechnet.
Das Statusband zeigt Zwischenräume verschiedener Zustände und fehlender
Beobachtungen als unbekannt, ohne erfundene Schaltzeit.

Die Legende schaltet nur die Darstellung um. Maus/Antippen oder fokussiertes
Diagramm mit Links/Rechts und Pos1/Ende untersuchen Originalbeobachtungen samt
Qualität und tatsächlicher Messzeit. Hover über vorhandenen gültigen Messpunkten
zeigt Signalname, Messzeit und Wert mit Einheit. Der Anlagen-Betriebszähler
`boiler.operating_minutes` erscheint ausschließlich zur Anzeige in Stunden:
90 min → 1,5 h, 1.440 min → 24 h, auch in Übersicht, Signalwahl und Tooltip.
API, Speicherung und CSV behalten die Originalminuten. Lange Kurven werden nur
visuell verdichtet; **CSV enthält weiterhin alle Originalbeobachtungen des
Zeitbereichs**, auch Fehler und nicht im Vergleich gezeigte Signale.
Einzelwerte und Zeitcursor erscheinen erst nach einer bewussten Zeitwahl,
nicht automatisch an der ältesten Beobachtung. Fehlende Statusbeobachtungen
beziehen sich ausschließlich auf diesen historischen Zeitpunkt (Suchnähe
±2,5 Minuten), nicht auf die aktuelle Statuskarte.

**Alle Werte** (`#/werte`) gruppiert jeden gespeicherten ausgewählten Wert einmal.
Suche nach Name, ID oder Beschreibung ändert keine Aufzeichnung. Metadaten
stehen in aufklappbaren Details; konkrete Wertfehler bleiben direkt sichtbar.
**Einstellungen** (`#/einstellungen`) bündelt Erfassung, Zeitzone und Ereignisse.
Die Modbus-Seite bleibt beim Navigieren gemountet; lokale Entwürfe bleiben erhalten.
Der Übernahmestatus zeigt Registeranzahl, Status und gespeicherte Revision
statt doppelter vollständiger Registerlisten. Bei ausstehender Übernahme
bleiben aktive Registeranzahl und aktive Revision zusätzlich sichtbar.
Import/Export sind einklappbar. Die Registertabelle zeigt kompakt Register
mit Hexcode/Offset, Aufzeichnungsauswahl und Signalzuordnung. Eigene Einheit,
Beschreibung und technische Quellenangaben stehen pro Zeile unter **Metadaten
und Zuordnung**. Unveränderte Zeilen erhalten keine Änderungsplakette;
Sperrgründe, inaktive Module und Read-to-clear-Risiken bleiben direkt sichtbar.
Die Speicheraktionen stehen vor der Tabelle; Hinweise zur Bearbeitung sind
aufklappbar. Diese Darstellung ändert weder Auswahl noch Import-/Speichervertrag.

Der gemeinsame **Sonne-/Mond-Button** gilt auch für den Editor und merkt die Wahl
lokal. Das Icon zeigt den angebotenen Wechsel: Mond zum Dunkelmodus, Sonne zum
Hellmodus; Tooltip und zugängliche Beschriftung bleiben vorhanden. Ohne gültige
explizite Auswahl gilt das Systemtheme. Storageausfälle verhindern die Bedienung
nicht; keine externen Fonts oder neue UI-Abhängigkeiten.


### Modbus-Werte auswählen

Die Navigation **Modbus-Aufzeichnung** öffnet eine separate Konfigurationsseite.
CSV hochladen, **Aufzeichnen**, Einheit und Beschreibung bearbeiten, dann
**Entwurf speichern**. Vorschau und Änderungen bleiben bis dahin unverbindlich.
Die Auswahl steuert die tatsächliche Erfassung, nicht nur die Anzeige.
Die explizit unterstützte V2-Auswahl und der separat ergänzte Statuskanal
`1001` sind bewusst aktivierbar. Die Betreiber-Notizen bestätigen für 79
V2-Register den Touch-Abgleich / die Lesbarkeit; für `10D1` und `1001` fehlt
diese Bestätigung. Das ist kein unabhängiger Sensor-, Skalierungs- oder
Aktornachweis. Der historische Live-Kernnachweis umfasst weiterhin fünf Register.
Verständliche Anzeigenamen und Beschreibungen werden über `/api/signals` geliefert,
getrennt von unveränderten CSV-Importnamen. Inaktive Netzmischer-/Speichermodule und
eigenständige Puffer-2-Parameter sind gekennzeichnet; `9000` / `9001` bleiben aktive
Fühler oben / unten desselben Puffers, mit unveränderten IDs und Decodergrenzen.
Neue Prozentmetadaten skalieren keine Rohworte; frühere Beobachtungen behalten ihre
Einheiten, gemischte Historien werden im Diagramm nach gespeicherter Einheit getrennt.
Die Metadaten ändern weder Aufzeichnungsauswahl noch Sichtbarkeit der Kacheln.
Die Anlagenübersicht zeigt ausschließlich die gespeicherte Aufzeichnungsauswahl,
auch wenn die Übernahme durch den Sammler noch aussteht. Abgewählte Signale
bleiben gespeichert. Auch die Diagrammauswahl folgt ausschließlich der
gespeicherten Aufzeichnungsauswahl. Eine zuvor gemerkte, inzwischen abgewählte
Signalwahl wechselt automatisch zum ersten verfügbaren Signal.
Beim CSV-Upload werden alle interpretierbaren
Einträge mit passender Lesezuordnung im Entwurf vorgewählt, auch bei Reimport.
Vor Speichern prüfen und unerwünschte Werte abwählen; erst Speichern übernimmt sie.
Neun Protokollregister leeren beim Lesen ihre Ausgangsbits und tragen eine
Warnung. Betreibertexte ändern weder Decoder noch Messwerteinheiten;
bestehende Historie bleibt erhalten. START/SOLL erscheinen getrennt als
Steuerungskandidaten, ohne Schreibfunktion.
Format, inkrementelle Importregeln und sichere Übernahme:
[Modbus-Konfiguration](docs/MODBUS.md#aufzeichnung-konfigurieren).
Die Funktion benötigt einen neuen App-/Image-Build; bestehende veröffentlichte
Images werden nicht verändert.

Die neue Gerätetabelle wird vollständig lesend unterstützt: zusätzlich Betriebsart
`1000`, Kessel-Basis-Soll `1007`, Puffer-SOLL `9020` und Puffer-START `9040`.
Temperatur-Basisparameter sind Einstellungen in ganzen °C, keine Sensormessungen.
Auch die mit der V1-Vorlage übernommenen `1005` (Maximalregelgröße in %),
`1012` (Software-Reinigung 0/1/2) und `1013` (gewichteter Intervallzähler in min)
haben Decoder. Alle bleiben quellenbelegt mit 300-s-Intervall und ohne automatische
Aufnahme in gespeicherte Auswahlen. Keine Schreibfunktion.


#### Gespeicherte Aufzeichnung auf eine andere Instanz übertragen

1. Auf der Quellinstanz **Modbus-Aufzeichnung** öffnen und
   **Gespeicherte Aufzeichnung als JSON herunterladen** wählen.
2. Auf der Zielinstanz im gleichen Bereich die Datei
   `sommerauer-aufzeichnung.json` unter **JSON-Datei als Entwurf prüfen** hochladen.
3. Vorschau prüfen und **Entwurf speichern** wählen.

Auswahl, Abwahlen, Importnamen, Betreibereinheiten und Beschreibungen bleiben
erhalten. Zusätzliche Register im Ziel bleiben gespeichert, werden aber
abgewählt. CSV ergänzt dagegen weiterhin die Auswahl. Der Download enthält
die gespeicherte Konfiguration, nicht ungespeicherte Änderungen oder eine
eventuell ältere aktive Sammlerrevision. Vorschau allein speichert nichts;
ein lokaler Entwurf wird nur nach Bestätigung ersetzt.

**Beide Instanzen brauchen einen Build mit dieser Funktion und kompatiblen
Registerzuordnungen.** Alte veröffentlichte Images erhalten den JSON-Import
nicht automatisch. Host, Netzwerk, private Pfade, Erfassungsfreigaben,
Fehlerquittierungen und Messhistorie werden nicht übertragen. Eigene Namen und
Beschreibungen können persönliche Angaben enthalten: Datei nicht ungeprüft
veröffentlichen. [Dateivertrag und Grenzen](docs/MODBUS.md#aufzeichnung-zwischen-instanzen-übertragen).


Fehler einzelner Werte sind jetzt direkt an deren Kachel sichtbar. Fehlende
Wetterdaten werden als „Nicht verfügbar“ weiter im normalen Intervall geprüft;
ungültige Werte und registerbezogene Ablehnungen werden einzeln ausgesetzt,
während die übrige Erfassung weiterläuft. Verbindungsfehler führen im Dauerbetrieb
nicht zum Abschalten; Protokoll- und Speicherprobleme behalten ihre Schutzstopps.
Ein neuer Build übernimmt alte reine Transportstopps automatisch, sofern beide
Laufkonfigurationen unbeschränkt sind und kein Read-to-clear-Register betroffen ist.
Nutzerpause, abgeschlossene Prüfläufe und harte Stopps werden nicht aufgehoben.
[Fehlerbehandlung und bewusste Freigabe](docs/FEHLERVERHALTEN.md).
Vor dem Upgrade konsistent sichern: Schema 1/2/3 wird auf 4 erweitert;
eine alte App-Version kann die migrierte Datenbank nicht öffnen.

## Docker und Unraid

Für Unraid steht [compose.unraid.yaml](compose.unraid.yaml) als eigenständiger
Stack mit **`ghcr.io/lum1nat0r/sommerauer-monitor:0.3.1`** bereit, ohne lokalen
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
Der Release-Git-Tag für Version 0.3.1 heißt **`v0.3.1`**; der Workflow veröffentlicht
nach seinen Offline-Prüfungen das Image mit Tag **`0.3.1`**
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
| [Registerkatalog](docs/register_catalog.json) | Statische Referenz aller 199 dokumentierten Projektzuordnungen; kein aktives Pollingprofil |
| [Datenmodell](docs/DATENMODELL.md) | Signalnamen, Historie, Qualität, Zeitstempel, API-Vertrag |
| [Fehlerverhalten](docs/FEHLERVERHALTEN.md) | Zustände, fortlaufendes Polling und Schutzstopps |
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
