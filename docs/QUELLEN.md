# Herkunft und Nachweisgrenzen

Diese öffentliche Übergabe fasst das private Projekt sachlich zusammen. Keine
Herstellerdateien, rekonstruierten Quelltexte, Fotos, Rohlogs oder reale IPs enthalten.
Neue Agenten können mit synthetischen Daten entwickeln; sie können aus diesem Repo
allein keine unabhängige Neuauswertung der privaten Rohbelege behaupten.

## Private Primärbelege beim Betreiber

| Referenz | Inhalt / Nachweis |
|---|---|
| Projekt-Lesetabelle für Pellets 190317.R | 199 eigene Zuordnungen; Import vom Betreiber berichtet |
| Registerstand 10.10.2026 | Alle 199 Einträge mit Status und Verweisen auf Originalbelege |
| Softwareexport und statische/IL-Prüfung | Decoder-/Parametersemantik; nicht pauschaler Nachweis der laufenden Gerätekonfiguration |
| Original-JSONL vom 09.10.2026 | 40 erfolgreiche FC03-Anfragen; davon 37 im kurzen Loggerlauf; 5 Register bestätigt |
| Display-/Benutzerabgleich | Kesseltemperatur, Betriebszähler, Puffer oben/unten an dokumentierten Zeitpunkten |
| Private Offline-Tests | Probe/Logger/Entscheider; deren damaliges Bestehen ist kein Test der noch ungebauten App |

SHA-256 der Projekt-Lesetabelle: `cfe358b11ffa11936ec1c39b7df41da9f11f9dbfbfe8e45d1c9d21dae62ad8e2`.
SHA-256 der statisch ausgewerteten rekonstruierten Quelle: `9965d1d31300a0e96e60a75730d23628632b161679d5c5356462edeca3496323`.
Die Hashes sind Referenzanker, keine mitgelieferten Dateien und kein aktueller
Konfigurationsnachweis. Die öffentliche Registerreferenz lässt Originalmessungen,
Quellcodeausdrücke, Quellzeilen und private Dateipfade bewusst weg.

Am 20.10.2026 stellte der Betreiber den privaten Übergabeordner für die Entwicklung
des separaten START-/SOLL-Testwerkzeugs bereit. Der rekonstruierte Export mit
obigem SHA256 wurde gezielt erneut gelesen: FC06-Eingang, Zahlenkonversion,
START-/SOLL-Parameter und Speicherung. Das ist eine erneute statische Prüfung
des bereitgestellten Texts, keine neue Dekompilierung oder Live-Abnahme.
Bereinigte Ableitungen und Nachweisgrenzen: [Schreibtest](SCHREIBTEST.md).

Historisch sechs Exception-Antworten und ein Trockenlauf zusätzlich dokumentiert;
nicht mit erfolgreichen Reads vermischen. Der kurze Loggerlauf belegt keinen
Dauerbetrieb. Alte Netzadresse nicht mehr verwenden; neue privat konfigurieren.
FC04 war nicht der bestätigte erfolgreiche App-Pfad; FC03 ist hier belegt.

## Öffentliche technische Primärquellen

- [Modbus Application Protocol](https://www.modbus.org/file/secure/modbusprotocolspecification.pdf)
- [Modbus TCP Guide](https://www.modbus.org/file/secure/messagingimplementationguide.pdf)
- [SQLite WAL](https://www.sqlite.org/wal.html)
- [SQLite Backup](https://www.sqlite.org/backup.html)
- [Unraid Container](https://docs.unraid.net/unraid-os/using-unraid-to/run-docker-containers/managing-and-customizing-containers/)
- [Home Assistant MQTT](https://www.home-assistant.io/integrations/mqtt/)
- [Home Assistant MQTT Sensor](https://www.home-assistant.io/integrations/sensor.mqtt/)

Diese Quellen belegen Protokoll-/Werkzeugverhalten, keine Registerkompatibilität
der konkreten Heizung. Bibliotheksdetails/Versionen bei Implementierung aktuell prüfen.
