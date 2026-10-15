# Nächste Schritte

Stand 15.10.2026: Projektgrundlage, `core`-Profil/Decoder, strikter FC03-Lesetransport,
Loopback-Simulator, versionierte SQLite-Speicherung, zentraler Sammler sowie persistente
Fehlerzustände/limitierte Wiederaufnahme und eine lesende Status-API/UI umgesetzt. Offen:
vollständige Erfassungs-/Verlaufs-API, gesicherte Verwaltungssteuerung, Deployment und
Geräteprüfung; keine Live-Arbeit für Issue #7.

Zuerst [AGENTS](AGENTS.md), [Plan](docs/PLAN.md), [Entscheidungen](docs/ENTSCHEIDUNGEN.md),
[Registerwissen](docs/MODBUS.md) und [Fehlerverhalten](docs/FEHLERVERHALTEN.md) lesen.

Zieladresse und Unraid-Poolpfad sind private Deployment-Konfiguration. Für spätere
Live-Arbeit aktuelle freigegebene Werte aus Betreiberkontext verwenden, nicht erraten.
Bei fehlendem Gerätezugang die Offline-Arbeit fortsetzen und Live-Nachweise offen lassen.

Lizenz (MIT weiterhin nur Vorschlag) und Zugriffsschutz bei den zugeordneten Issues
festlegen. Foundation-Laufzeiten und -Bibliotheken sind festgepinnt; MQTT/
Solarprognose/START-SOLL sind spätere Arbeitspakete. Keine Aktivierung von
Heizungsänderungen aus dieser Übergabe ableiten.
