# Nächste Schritte

Stand 14.10.2026: Projektgrundlage, enges `core`-Profil/Decoder, strikter
FC03-Lesetransport ohne Retries sowie der Loopback-Modbus-Simulator sind umgesetzt.
Es gibt weiterhin keinen Sammler, Speicher oder Gerätezugriff. Nächste Schritte gemäß
Issue-Roadmap; kein Live-Test in diesem Arbeitsschritt.

Zuerst [AGENTS](AGENTS.md), [Plan](docs/PLAN.md), [Entscheidungen](docs/ENTSCHEIDUNGEN.md),
[Registerwissen](docs/MODBUS.md) und [Fehlerverhalten](docs/FEHLERVERHALTEN.md) lesen.

Zieladresse und Unraid-Poolpfad sind private Deployment-Konfiguration. Für spätere
Live-Arbeit aktuelle freigegebene Werte aus Betreiberkontext verwenden, nicht erraten.
Bei fehlendem Gerätezugang die Offline-Arbeit fortsetzen und Live-Nachweise offen lassen.

Lizenz (MIT weiterhin nur Vorschlag) und Zugriffsschutz bei den zugeordneten Issues
festlegen. Foundation-Laufzeiten und -Bibliotheken sind festgepinnt; MQTT/
Solarprognose/START-SOLL sind spätere Arbeitspakete. Keine Aktivierung von
Heizungsänderungen aus dieser Übergabe ableiten.
