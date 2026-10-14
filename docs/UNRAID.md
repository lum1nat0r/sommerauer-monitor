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

DB und Laufzustand über Containerersatz erhalten. SQLite-WAL nur auf geeignetem
lokalem Dateisystem; aktive DB nicht auf SMB/NFS. Konfigurations-/Tokenwerte nicht
in Image, Browserbundle, URLs oder Logs einbetten. Erstinstallation ohne Polling.

Healthcheck unterscheidet App-/DB-Erreichbarkeit von angehaltener Erfassung.
Ein harter Messstopp soll nicht durch automatische Container-Neustarts umgangen
werden. Neustartbudget und Quittierung aus FEHLERVERHALTEN gelten auch hier.

## Sicherung, Update und Wiederherstellung

- Konsistente DB-Sicherung über SQLite-Backup-API oder bei geschlossener DB;
  aktive Hauptdatei allein reicht bei WAL nicht.
- Konfiguration, Schema-/App-Version und Sammlerzustand konsistent berücksichtigen.
- Backup/Restore und Migration mit echten synthetischen Daten praktisch testen.
- Vor Migration Sicherung; Schemaänderungen/Abwärtskompatibilität dokumentieren.
- Restore darf alte Steuerungs-/Erfassungszustände nicht unbemerkt aktivieren;
  kontrolliert pausiert prüfen. Noch keine aktive Heizungssteuerung in V1.
- Speicherverbrauch anzeigen; volles Volume führt zum Erfassungsstopp.
- Sicherungen dürfen rotieren, dauerhaft aufbewahrte Originalmessungen nicht.

Release-Prüfungen: nicht-root starten, Volume-Rechte, Neustart/Persistenz, Offline-
Start, gesperrte Erfassung, Backup/Restore, Versionsanzeige, Image-Reproduzierbarkeit.
Hardware- oder Unraid-Prüfung nur als bestanden melden, wenn tatsächlich ausgeführt.

Quellen: [Unraid Container](https://docs.unraid.net/unraid-os/using-unraid-to/run-docker-containers/managing-and-customizing-containers/),
[SQLite WAL](https://www.sqlite.org/wal.html), [SQLite Backup](https://www.sqlite.org/backup.html).
