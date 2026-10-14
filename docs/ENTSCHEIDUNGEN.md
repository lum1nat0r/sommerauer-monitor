# Entscheidungen und offene Punkte

Stand 14.10.2026; Herkunft jeweils angegeben.

| Entscheidung | Stand/Herkunft |
|---|---|
| Version 1 = Modbus-Logging + eigenes Dashboard | Nutzerauftrag |
| Alle Minutenwerte dauerhaft | Explizite Nutzerantwort |
| Begrenzte Wiederverbindung bei Verbindungsausfall, Stopp bei Protokoll/Datenfehler | Explizite Nutzerantwort |
| Weitere Werte nach schrittweiser Prüfung | Nutzerantwort; kein automatischer Vollscan |
| Unraid 7.3.2; Home Assistant und MQTT vorhanden | Nutzerangabe |
| Zugriff Heimnetz/Tailscale; kein Tailscale-Aufbau im Auftrag | Nutzerantwort |
| START/SOLL später, keine Manipulation echter Messwerte | Explizite Nutzerantwort |
| Externes/späteres Prognosemodell | Nutzerantwort |
| Öffentliches Repo `sommerauer-monitor` und umsetzbare Issues | Expliziter Folgeauftrag |
| Python/FastAPI + SQLite + React/TypeScript in einem Container | Architekturvorschlag im positiv aufgenommenen Plan; bei Umsetzung konkretisieren |
| 60 s für Kernblöcke; Zusatzwerte langsamer | Technischer Entwurf, Lastvorgaben einhalten |
| 5 Wiederaufnahmen mit 1/2/5/10/15 min Pause; Reset nach 3 guten Vollzyklen | Konkreter Entwurfswert für Implementierung und Offline-Tests |

| Projektgrundlage | Entscheidung / Herkunft |
|---|---|
| Python-Laufzeit CPython 3.12.9; Abhängigkeiten in `uv.lock` | Konservative unterstützte Laufzeit, eingefrorener reproduzierbarer Satz |
| Node.js 22.14.0, npm 10.9.2; Frontend-Abhängigkeiten in `package-lock.json` | Node-22-LTS Buildbasis, feste Entwicklungs-/CI-Versionen |
| Erststart ohne Host, Erfassung standardmäßig deaktiviert; Host in API-Ausgabe redigiert | Offline-sichere Projektkonfiguration; keine Gerätezugriffe implementiert |
| CI nur mit synthetischen/in-process Tests und Frontend-Build | GitHub Actions workflow `.github/workflows/ci.yml`; keine Anlagenzugriffe/Secrets |

Noch offen: Lizenz (MIT vorgeschlagen), Wahl einer Modbus-Bibliothek vs. kleinem
eigenem Lesetransport, Zugriffsschutz der lokalen Verwaltungsfunktionen,
Unraid-Poolpfad/UID/GID, geprüfte Einheiten und Grenzen der Zusatzregister.
Die Foundation-Abhängigkeiten sind in `pyproject.toml` und `package.json` exakt
fixiert; konkrete Modbus-Abhängigkeit folgt erst im Transport-Issue.

Später offen: digitale FP-2-Anbindung, Kollektordaten, Modellgüte, X Minuten bis
Rückfall, Temperatur-/Versorgungsgrenzen, geeigneter autonomer Rückfallmechanismus.
Diese Punkte blockieren Version 1 nicht.

Nicht unterstellt: laufender Brenner aus Betriebszähler, thermische kW aus interner
Leistung, Solarertrag aus zwei Puffertemperaturen, unabhängige temporäre START-Vorgabe,
Herstellerfreigabe der selbst gewählten Pollinggrenzen.
