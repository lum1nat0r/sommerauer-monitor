# Nächste Schritte

Stand 14.10.2026: Projektgrundlage sowie das offlinefähige, enge `core`-Profil und
reine Registerdecoder umgesetzt. Es gibt weiterhin keinen Modbus-Transport,
Sammler, Speicher oder Gerätezugriff. Nächster Implementierungsschritt: [Issue #4](https://github.com/lum1nat0r/sommerauer-monitor/issues/4)
– strikter FC03-Leseclient und lokaler Modbus-Simulator.

Zuerst [AGENTS](AGENTS.md), [Plan](docs/PLAN.md), [Entscheidungen](docs/ENTSCHEIDUNGEN.md),
[Registerwissen](docs/MODBUS.md) und [Fehlerverhalten](docs/FEHLERVERHALTEN.md) lesen.

Zieladresse und Unraid-Poolpfad sind private Deployment-Konfiguration. Für spätere
Live-Arbeit aktuelle freigegebene Werte aus Betreiberkontext verwenden, nicht erraten.
Bei fehlendem Gerätezugang die Offline-Arbeit fortsetzen und Live-Nachweise offen lassen.

Lizenz (MIT weiterhin nur Vorschlag) und Zugriffsschutz bei den zugeordneten Issues
festlegen. Foundation-Laufzeiten und -Bibliotheken sind festgepinnt; MQTT/
Solarprognose/START-SOLL sind spätere Arbeitspakete. Keine Aktivierung von
Heizungsänderungen aus dieser Übergabe ableiten.
