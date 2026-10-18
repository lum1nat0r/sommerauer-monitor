# Deployment- und Release-Anforderungen

Zielplattform: `linux/amd64` (Unraid x86_64). Ein nicht privilegierter Container
liefert Frontend und FastAPI über Port 8000 und nutzt lokales persistentes `/data`.
`compose.yaml` baut lokal; `compose.unraid.yaml` ist ein eigenständiger Stack
ohne Build-Schritt und lädt `ghcr.io/lum1nat0r/sommerauer-monitor:0.3.0`.
Das alternative `unraid-template.xml` verwendet denselben Image-Tag.
Für Version 0.3.0 ist der Git-Tag **`v0.3.0`** vorgesehen; der Image-Tag
lautet **`0.3.0`**. Vor erfolgreicher Veröffentlichung und öffentlicher
GHCR-Freigabe ist das Image nicht anonym abrufbar.

Der Container läuft als UID 99/GID 100 (`nobody:users`), ohne Docker-Socket,
Privilegien oder Host-Netzwerk. Das Datenverzeichnis auf dem Host muss für diese
UID/GID schreibbar sein. Im Template einen vorhandenen lokalen Pfad auswählen;
`/mnt/user/appdata/sommerauer-monitor` ist nur ein editierbarer Beispielpfad,
kein vorausgesetzter Pool. SQLite-WAL nicht über SMB/NFS betreiben.

Erststart: `COLLECTOR_ENABLED=false`, `MODBUS_HOST` leer. Das Image startet
keine Gerätezugriffe, sofern der Betreiber nicht lokal sowohl eine Zieladresse
setzt als auch die Erfassung ausdrücklich einschaltet. Keine Zieladresse in
Repository, Image-Buildargumente, Logs oder öffentliche Dokumentation eintragen.

## Unraid: veröffentlichtes Image verwenden

Voraussetzung: Docker Compose auf Unraid, erfolgreich veröffentlichte Version
`0.3.0` und öffentliche Sichtbarkeit des GHCR-Pakets. Nur
`compose.unraid.yaml` auf den Server kopieren; kein Quellcode und kein lokaler
Image-Build nötig. Im selben Stackverzeichnis eine private `.env` anlegen:

```dotenv
# Beispielpfad: durch den tatsächlichen lokalen Unraid-Datenpfad ersetzen.
DATA_PATH=/mnt/user/appdata/sommerauer-monitor
WEB_PORT=8000
PUID=99
PGID=100
MODBUS_HOST=
COLLECTOR_ENABLED=false
DISPLAY_TIMEZONE=Europe/Vienna
```

`DATA_PATH` muss ausdrücklich gesetzt sein. Vorher das ausgewählte Verzeichnis
anlegen und UID 99/GID 100 Schreibrechte geben; bei anderem `PUID`/`PGID` die
Rechte entsprechend anpassen. Compose legt fehlende Mountquellen absichtlich
nicht automatisch an. Keine SMB-/NFS-Freigabe für SQLite verwenden.
Die `.env` enthält private Deploymentwerte und wird nicht veröffentlicht.

Im Stackverzeichnis ausführen:

```sh
chmod 600 .env
docker compose -f compose.unraid.yaml config --quiet
docker compose -f compose.unraid.yaml pull
docker compose -f compose.unraid.yaml up -d --no-build
docker compose -f compose.unraid.yaml ps
docker compose -f compose.unraid.yaml logs --tail=50 monitor
```

Das Dashboard ist unter `http://<Unraid-Host>:8000` erreichbar, bei geändertem
`WEB_PORT` entsprechend. Nur im Heimnetz/Tailscale bereitstellen, keine
Router-Portfreigabe. `/api/health`, `/api/version` (Version `0.3.0` samt Revision)
und `/api/collector/status` prüfen; ohne Ziel bleibt die Erfassung `unconfigured`.
Healthcheck und Container-Neustart aktivieren keine Messung.

Diese Datei **allein** verwenden, nicht als Override mit `compose.yaml`
kombinieren und nicht zusätzlich zum Unraid-Template starten: nur eine Instanz.
Bei einem Compose-Manager entweder diese Datei auswählen oder ihren Inhalt als
eigenständigen Stack hinterlegen und die Variablen im Stack konfigurieren.
`APP_VERSION` und `BUILD_REVISION` werden nicht zur Laufzeit gesetzt; sie stammen
aus dem veröffentlichten Image. Der Image-Tag bleibt fest auf `0.3.0`.

Erst nach den Unraid-Prüfungen und gemäß
[Inbetriebnahmeplan](INBETRIEBNAHME.md#betriebsplan-nach-der-begrenzten-abnahme)
ein privates Modbus-Ziel und das vereinbarte endliche Anfragebudget setzen,
`COLLECTOR_ENABLED=true` bewusst aktivieren und den Dienst mit demselben
`up -d --no-build` neu erstellen. Hierdurch wird keine Erfassung aktiviert.
Für Sicherungen mit diesem Stack
`docker compose -f compose.unraid.yaml exec monitor …` verwenden; die Hinweise
zu Backup/Restore und persistenten Stopps unten gelten unverändert.

## Domain und HTTPS-Reverse-Proxy

Dashboard und `/api` müssen unter derselben Browser-Domain erreichbar sein.
Bei TLS-Terminierung am Proxy sieht das Backend unter Umständen nur dessen
interne HTTP-Adresse. Dann scheitern Aktionen mit HTTP 403
`Same-origin request required`, obwohl GETs und der direkte IP-Zugriff funktionieren.
Das ist die Origin-/CSRF-Prüfung, keine fehlende allgemeine CORS-Freigabe.

Mit einem Image, das die `PUBLIC_ORIGIN`-Korrektur enthält, in der privaten
Compose-`.env` beziehungsweise als Unraid-Containervariable setzen:

```dotenv
PUBLIC_ORIGIN=https://monitor.example.invalid
```

Durch die tatsächliche Browser-Origin ersetzen: Schema, Host und gegebenenfalls
nicht standardmäßiger Port, kein URL-Pfad, keine Zugangsdaten oder Wildcards.
Beide Compose-Dateien reichen den Wert weiter; das Unraid-Template enthält
ein entsprechendes Feld. Container anschließend mit unverändertem `/data` und
unveränderten Erfassungseinstellungen neu erstellen; ein bloßer Prozessneustart
übernimmt geänderte Containervariablen nicht. Der bereits veröffentlichte
Image-Tag wird durch diese Quellcodekorrektur nicht nachträglich aktualisiert;
eine passende neue Veröffentlichung oder ein lokaler Build ist erforderlich.

Die konfigurierte Origin wird zusätzlich zur direkt erkannten Request-Origin
zugelassen. `X-Requested-With: SommerauerMonitor` bleibt Pflicht; `cross-site`
bleibt verboten. Ungeprüfte `X-Forwarded-Host`-/`X-Forwarded-Proto`-Header werden
von der App nicht zur Freigabe verwendet. Keine CORS-Wildcard und kein pauschales
Vertrauen in alle Proxy-Absender einschalten. Die Domain bleibt private
Deploymentkonfiguration und wird nicht von `/api/config` ausgegeben.

Nach dem Update zuerst eine reine App-Aktion über die Domain prüfen, etwa die
Anzeigezeitzone speichern, und den Collectorstatus unverändert kontrollieren.
Keinen Erfassungsstart als Proxytest verwenden. Domainzugang
ersetzt keine Authentisierung: weiterhin nur vertrauenswürdiges LAN/Tailscale,
keine öffentliche Freigabe der ungeschützten Verwaltungs-API.

## Lokalen Entwicklungsstand bauen

Compose lokal bauen/starten:

```sh
cp .env.example .env
mkdir -p data
sudo chown 99:100 data # Linux-Host; unter Docker Desktop ein beschreibbares Volume verwenden
docker compose up --build -d
docker compose ps
docker compose logs --tail=50 monitor
```

Vorher in `.env` `DATA_PATH` auf ein lokales beschreibbares Verzeichnis setzen.
Für einen begrenzten Lauf kann `COLLECTOR_MAX_REQUESTS` eine Gesamtzahl festlegen;
bei einem solchen endlichen Lauf führen Transportfehler nicht zu Wiederaufnahmen.
Ohne Wert bleibt der reguläre Betrieb unverändert. Bei benutzerdefiniertem
`DATA_PATH` das Verzeichnis vor dem Start anlegen und für die konfigurierte UID/GID
beschreibbar machen. Der Daten-Bind-Mount bleibt beim Containerersatz erhalten.
Compose-`.env` und Unraid-Container-Variablen liegen außerhalb von `/data` und müssen
separat geschützt gesichert werden.
`PUID`/`PGID` steuern beim lokalen Build den Build- und Laufzeitbenutzer
(Standard `99`/`100`); beim Unraid-Image nur den Laufzeitbenutzer. Das gemountete
Verzeichnis muss zu den gewählten IDs passen. `WEB_PORT` setzt den Hostport,
intern bleibt Port 8000. Beim lokalen Build liefern `APP_VERSION` und
`BUILD_REVISION` Image-Label und `/api/version`-Metadaten;
`unknown` ist kein Release-Nachweis.
Der Compose-Dienst bindet an `linux/amd64`, Bridge-Netzwerk, schreibgeschütztes
Root-Dateisystem und 20 Sekunden Shutdown-Frist.

Healthcheck prüft API- und Datenbank-Erreichbarkeit (`/api/health`), nicht den
Erfassungszustand. Neustartstrategie `unless-stopped` beziehungsweise Unraid
`unless-stopped`: persistierte harte Stopps und Wiederaufnahmebudgets bleiben in
SQLite erhalten; ein Container-Neustart quittiert sie nicht. SIGTERM sperrt neue
Reads und wartet auf die begrenzte Transportdeadline und geordneten Sammler-Shutdown.

Vor einem Upgrade zuerst eine konsistente SQLite-Sicherung per Online-Backup-API
erstellen, während der Container läuft:

```sh
docker compose exec monitor python -c "from backend.storage import SQLiteStore; SQLiteStore('/data/monitor.sqlite3').backup_to('/data/pre-upgrade.sqlite3')"
```

Bei Unraid `docker exec sommerauer-monitor` statt `docker compose exec monitor`
verwenden. Die Sicherung anschließend aus dem persistenten Host-Datenpfad auf ein
getrenntes Backupziel kopieren. `.env` beziehungsweise die Unraid-Container-
Variablen separat und geschützt sichern; darin können private Verbindungsdaten
stehen. Danach einen veröffentlichten Image-Tag einsetzen und den Container
ersetzen; `/data` bleibt unverändert gemountet. Nach Start `/api/health`,
`/api/version` und den Collectorstatus prüfen.

Restore nur bei gestopptem App-Container. Auf Unraid Host-Datenpfad und tatsächlich
veröffentlichtes Image einsetzen:

```sh
DATA_PATH=/mnt/user/appdata/sommerauer-monitor
IMAGE=ghcr.io/lum1nat0r/sommerauer-monitor:0.3.0
docker run --rm --user 99:100 -v "$DATA_PATH:/data" --entrypoint python "$IMAGE" -c "from backend.storage import SQLiteStore; SQLiteStore.restore_from('/data/pre-upgrade.sqlite3', '/data/monitor.sqlite3')"
```

Dabei bleibt der Collectorzustand vorsorglich pausiert. Externe Sicherung vor
Schema-Upgrades behalten; keine aktive Hauptdatei ohne WAL-Sicherung kopieren.

## Build- und Prüfgrenzen

Das Dockerfile pinnt Python 3.12.9, Node 26.7.0, npm 12.0.2, npm-Lockdatei und uv 0.12.2;
Compose setzt das Ziel auf `linux/amd64`. Der Tag `v0.1.0` existiert bereits;
ein verfügbares Image für 0.3.0 ist noch nicht belegt. Lokale Docker-Prüfungen sind keine Prüfung auf Unraid 7.3.2.
Eine tatsächliche Unraid-Installation, Hardware- oder Geräteprüfung wird nur nach
Ausführung als bestanden bezeichnet.

### GitHub-Image-Build und Veröffentlichungsgrenze

`.github/workflows/image.yml` baut und startet auf jedem Pull Request ein
`linux/amd64`-Image offline ohne Registry-Anmeldung und ohne Push. Die bestehende
Offline-CI prüft Python und Frontend; ein normaler Push auf `main` veröffentlicht
und baut kein Image.
Ein manueller Workflow-Start ist kein Veröffentlichungsweg. CI und Image-Build
enthalten weder private Zieladressen noch Gerätezugriffe.

Erst ein Push eines Versionstags `vX.Y.Z` im Original-Repository startet den
Release-Job. Er verlangt eine vorhandene Lizenzdatei `LICENSE`, eine zu
`pyproject.toml` passende Version, einen Tag-Commit aus `main` und ein
geschlossenes Inbetriebnahme-Issue #13. Der Job führt Offline-Tests, Lint und
Frontend-Build erneut aus, baut das Image genau einmal und prüft den gestarteten
Container ohne Modbus-Ziel und mit
`COLLECTOR_ENABLED=false` auf API-/Datenbankgesundheit, Version und inaktive
Erfassung. Erst danach meldet sich der Job mit `GITHUB_TOKEN` (nur dieser Job
besitzt `packages: write`) bei GHCR an und pusht das geprüfte Image als
`ghcr.io/lum1nat0r/sommerauer-monitor:X.Y.Z`. Es gibt keinen `latest`- oder
`main`-Tag und keinen automatischen Austausch des Betreibercontainers. Der
Workflow gibt den Registry-Digest im Job-Ergebnis aus; für ein festes
Deployment kann `ghcr.io/lum1nat0r/sommerauer-monitor@sha256:…` verwendet
werden. PR-Builds haben nur Leserechte.

MIT für eigenen App-Code ist am 15.10.2026 bestätigt (`LICENSE`).
Vor dem ersten Versionstag: #13 einschließlich
der noch offenen Geräte-/Unraid-Nachweise auswerten, die Releasefreigabe im Rahmen
von #14 festhalten und Branch-/Tag-Rulesets so einrichten, dass ausschließlich
`main`-Commits getaggt werden. Der Workflow prüft Lizenzdatei, Version,
Commit-Zugehörigkeit und Issue-Status technisch; ein geschlossenes Issue
ersetzt **nicht** die fachliche Abnahme von #13 oder die Tag-Berechtigungen.
GHCR-Pakete sind bei Erstveröffentlichung
standardmäßig privat; die Sichtbarkeit erst nach Lizenz- und Releasefreigabe
bewusst auf öffentlich setzen und einen anonymen Pull prüfen. Bis dahin bleiben
die Imageverweise in `compose.unraid.yaml` und im Unraid-Template vorbereitete
Releaseziele, kein Nachweis eines verfügbaren Images. Das Betreiber-Deployment
erfolgt weiterhin manuell mit gesichertem `/data` und lokaler Konfiguration.

Quellen: [GitHub-Workflow-Syntax](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax),
[GHCR-Berechtigungen und Sichtbarkeit](https://docs.github.com/en/packages/working-with-a-github-packages-registry/working-with-the-container-registry).

## Sicherung, Update und Wiederherstellung

- `SQLiteStore.backup_to()` nutzt die SQLite-Online-Backup-API; die aktive Hauptdatei
  allein ist wegen WAL unvollständig.
- `SQLiteStore.restore_from()` prüft Integrität und Schema und setzt gespeicherten
  Collector-Zustand vorsorglich auf `paused`.
- Schema-Version steht in `PRAGMA user_version`; unbekannte neuere Versionen stoppen
  den Start. Vor späteren Schema-Upgrades bleibt ein externes Backup erforderlich.
- Speicherverbrauch umfasst Datenbank-, WAL- und SHM-Datei. Speicherfehler werden als
  `StorageError` an den Aufrufer gemeldet; der Sammler muss darauf stoppen.
- Sicherungen dürfen rotieren, dauerhaft aufbewahrte Originalmessungen nicht.

Release-Prüfungen: nicht-root starten, Volume-Rechte, Neustart/Persistenz, Offline-
Start, gesperrte Erfassung, Backup/Restore, Versionsanzeige, Image-Reproduzierbarkeit.
Hardware- oder Unraid-Prüfung nur als bestanden melden, wenn tatsächlich ausgeführt.

Stand nach Geräteabnahme #13 am 15.10.2026: Der Betreiber hat den Monitor noch
nicht auf Unraid installiert. Erfolgreiche endliche Windows-FC03-Läufe,
lokales SQLite-Backup/Restore und frühere Podman-Smokes sind **kein**
bestandener Unraid-Betriebs-/Persistenzcheck. Vor dauerhaftem Betrieb muss
der Betreiber Image/Revision, tatsächlichen lokalen Mount und UID/GID-Rechte,
endliche Erfassung, Containerersatz/Neustart sowie externes Backup/Restore
auf seiner Installation protokollieren. Der
[Betriebsplan](INBETRIEBNAHME.md#betriebsplan-nach-der-begrenzten-abnahme)
aktiviert weder Deployment noch Erfassung.


Quellen: [Unraid Container](https://docs.unraid.net/unraid-os/using-unraid-to/run-docker-containers/managing-and-customizing-containers/),
[SQLite WAL](https://www.sqlite.org/wal.html), [SQLite Backup](https://www.sqlite.org/backup.html).
