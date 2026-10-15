# Nächste Schritte

Stand 15.10.2026: Projektgrundlage, `core`-Profil/Decoder, strikter FC03-Lesetransport,
Loopback-Simulator, SQLite-Speicherung, zentraler Sammler, persistente Fehlerzustände,
lesende API, Dashboard und Offline-Ende-zu-Ende-Abnahme (#12) umgesetzt. Offen:
Unraid-Deployment und Geräteprüfung; keine Live-Gerätezugriffe für Issue #12.

Zuerst [AGENTS](AGENTS.md), [Plan](docs/PLAN.md), [Entscheidungen](docs/ENTSCHEIDUNGEN.md),
[Registerwissen](docs/MODBUS.md) und [Fehlerverhalten](docs/FEHLERVERHALTEN.md) lesen.

Zieladresse und Unraid-Poolpfad sind private Deployment-Konfiguration. Für spätere
Live-Arbeit aktuelle freigegebene Werte aus Betreiberkontext verwenden, nicht erraten.
Bei fehlendem Gerätezugang die Offline-Arbeit fortsetzen und Live-Nachweise offen lassen.

## Begrenzter Ersttest am Gerät

Einzeltestplan (noch nicht ausgeführt): Ziel ausschließlich aus der privaten
Laufzeitkonfiguration `MODBUS_HOST`; Port 502, Unit 255, Modbus TCP/FC03.
Zweck: neue Verbindung und die drei historisch bestätigten Kernblöcke prüfen:
4102/1, 28688/2, 36864/2. Höchstens drei Anfragen insgesamt, je Anfrage
maximal zwei Register und feste 3-s-Gesamtdeadline; seriell, ohne zusätzliche
Wartezeit zwischen Antworten und keinerlei Retry. Nach erster Verbindung,
Protokoll- oder Datenabweichung sofort stoppen; keine zusätzlichen Register.
Voraussetzung: andere Modbus-Leser einschließlich Altlogger sind beendet.
Ergebnisse sind pro Block zu prüfen; ein Einzeltest belegt weder Dauerbetrieb
noch Hersteller-Verträglichkeit. Keine Displaywerte voraussetzen.

Lizenz (MIT weiterhin nur Vorschlag) und Zugriffsschutz bei den zugeordneten Issues
festlegen. Foundation-Laufzeiten und -Bibliotheken sind festgepinnt; MQTT/
Solarprognose/START-SOLL sind spätere Arbeitspakete. Keine Aktivierung von
Heizungsänderungen aus dieser Übergabe ableiten.
