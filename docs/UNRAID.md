# Deployment- und Release-Anforderungen

Ziel: Unraid 7.3.2; ein nicht privilegierter Container, ein Webport, persistentes
lokales `/data`. Dies ist eine Bauanleitung für das Implementierungs-Issue,
noch keine ausführbare Installationsanleitung und kein existierender Image-Tag.

Liefern: mehrstufiges Dockerfile (Frontendbuild + Pythonruntime), Compose-Beispiel,
Unraid-Template, Healthcheck, versioniertes Release-Image und getestete Anleitung.
Port, UID/GID, Datenpfad, Zeitzonenanzeige und lokale Konfiguration erklären.
Vorhandenen Poolnamen nicht voraussetzen; Betreiber wählt lokalen appdata-Pfad.
Kein `privileged`, Docker-Socket-Mount oder Host-Netzwerk als Standard erforderlich.
Zugriff ausschließlich LAN/Tailscale; keine Portfreigabe ins Internet einrichten.

Die Anwendung legt `/data/monitor.sqlite3` an und nutzt SQLite-WAL mit `synchronous=FULL`.
`DATA_DIR` kann lokal abweichen; das Verzeichnis muss persistent und beschreibbar sein.
WAL-Datenbanken ausschließlich auf geeignetem lokalem Dateisystem betreiben, nicht über
SMB/NFS. Konfigurations-/Tokenwerte nicht in Image, Browserbundle, URLs oder Logs einbetten.
Erstinstallation ohne Polling.

Healthcheck unterscheidet App-/DB-Erreichbarkeit von angehaltener Erfassung.
Ein harter Messstopp soll nicht durch automatische Container-Neustarts umgangen
werden. Neustartbudget und Quittierung aus FEHLERVERHALTEN gelten auch hier.

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
