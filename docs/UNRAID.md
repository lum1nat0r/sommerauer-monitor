# Deployment- und Release-Anforderungen

Zielplattform: `linux/amd64` (Unraid x86_64). Ein nicht privilegierter Container
liefert Frontend und FastAPI über Port 8000 und nutzt lokales persistentes `/data`.
`Dockerfile`, `compose.yaml` und `unraid-template.xml` enthalten den Paketentwurf.
Das Template erwartet `ghcr.io/lum1nat0r/sommerauer-monitor:0.1.0`; dieses Image
ist noch nicht veröffentlicht. Es gibt keinen Release-Tag. Ein Betreiber muss den
Image-Tag vor Installation auf eine tatsächlich veröffentlichte Version setzen.

Der Container läuft als UID 99/GID 100 (`nobody:users`), ohne Docker-Socket,
Privilegien oder Host-Netzwerk. Das Datenverzeichnis auf dem Host muss für diese
UID/GID schreibbar sein. Im Template einen vorhandenen lokalen Pfad auswählen;
`/mnt/user/appdata/sommerauer-monitor` ist nur ein editierbarer Beispielpfad,
kein vorausgesetzter Pool. SQLite-WAL nicht über SMB/NFS betreiben.

Erststart: `COLLECTOR_ENABLED=false`, `MODBUS_HOST` leer. Das Image startet
keine Gerätezugriffe, sofern der Betreiber nicht lokal sowohl eine Zieladresse
setzt als auch die Erfassung ausdrücklich einschaltet. Keine Zieladresse in
Repository, Image-Buildargumente, Logs oder öffentliche Dokumentation eintragen.

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
Bei benutzerdefiniertem `DATA_PATH` das Verzeichnis vor dem Start anlegen und
für die konfigurierte UID/GID beschreibbar machen. Der Daten-Bind-Mount bleibt
beim Containerersatz erhalten. Compose-`.env` und Unraid-Umgebungsvariablen
liegen außerhalb von `/data` und müssen separat geschützt gesichert werden.
`PUID`/`PGID` steuern den Build- und Laufzeitbenutzer (Standard `99`/`100`);
bei Änderungen müssen Image und Volume-Berechtigungen zusammenpassen. `WEB_PORT`
setzt den Hostport, intern bleibt Port 8000. `APP_VERSION` und `BUILD_REVISION`
liefern Image-Label und `/api/version`-Metadaten; `unknown` ist kein Release-Nachweis.
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
IMAGE=ghcr.io/lum1nat0r/sommerauer-monitor:0.1.0
docker run --rm --user 99:100 -v "$DATA_PATH:/data" --entrypoint python "$IMAGE" -c "from backend.storage import SQLiteStore; SQLiteStore.restore_from('/data/pre-upgrade.sqlite3', '/data/monitor.sqlite3')"
```

Dabei bleibt der Collectorzustand vorsorglich pausiert. Externe Sicherung vor
Schema-Upgrades behalten; keine aktive Hauptdatei ohne WAL-Sicherung kopieren.

## Build- und Prüfgrenzen

Das Dockerfile pinnt Python 3.12.9, Node 22.14.0, npm-Lockdatei und uv 0.12.2;
Compose setzt das Ziel auf `linux/amd64`. Es gibt derzeit weder veröffentlichtes
Image noch Release-Tag. Lokale Docker-Prüfungen sind keine Prüfung auf Unraid 7.3.2.
Eine tatsächliche Unraid-Installation, Hardware- oder Geräteprüfung wird nur nach
Ausführung als bestanden bezeichnet.

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

Quellen: [Unraid Container](https://docs.unraid.net/unraid-os/using-unraid-to/run-docker-containers/managing-and-customizing-containers/),
[SQLite WAL](https://www.sqlite.org/wal.html), [SQLite Backup](https://www.sqlite.org/backup.html).
