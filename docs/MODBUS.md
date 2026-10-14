# Register, Auswertung und Belegstatus

Referenz: Projektprofil für Pellets 190317.R. Alle Offsets sind **dezimal und
nullbasierte PDU-Adressen**. Kein +1 und kein 40001-Offset. Der Betreiber hat eine
projektspezifische Tabelle importiert; diese Zuordnung gilt nicht automatisch für
andere Geräte. Host privat konfigurieren, Port 502, Unit 255, Modbus TCP, FC03.

## Bestätigte Kerngruppen

Historische Geräteantworten und Displayabgleich am 09.10.2026 bestätigen fünf
Register. Neue Netzwerkadresse und dauerhafter Betrieb sind noch nicht geprüft.
Die privaten Rohdaten werden hier nicht veröffentlicht.

| Offset / Anzahl | Interne Codes (hex) | Signal | Dekodierung |
|---|---|---|---|
| 4102 / 1 | 1006 | `boiler.temperature` | signed16, ganze °C |
| 28688 / 2 | 7010, 7011 | `boiler.operating_minutes` | Zwei uint16: Tage und Restminuten |
| 36864 / 2 | 9000, 9001 | `buffer.top_temperature`, `buffer.bottom_temperature` | signed16, ganze °C |

Big-endian pro 16-Bit-Wort. `signed = raw if raw < 32768 else raw - 65536`.
Bei den Kern-Temperaturkanälen ist 110 Ersatz-/Fehlerwert. Gültig ist strikt
`-5 < signed < 110`; keine Soll-/Betriebstemperaturgrenzen. Diese Grenze nicht auf
die unbestätigte Außentemperatur übertragen.

Das ausführbare Erstprofil `core` ist ausschließlich in
[`backend/registers.py`](../backend/registers.py) definiert: exakt die drei oben
aufgeführten Blöcke. `config/register_catalog.json` bleibt eine getrennte
Faktenreferenz und keine Pollingliste; die 194 statischen Einträge sind nicht aktiv.
Dekodierte Werte tragen Rohworte, Blockoffset, Quelle sowie Profil- und
Decoderversion, damit eine Interpretation nachvollziehbar bleibt.

`Gesamtminuten = Tage * 1440 + Restminuten`, Restminuten 0..1439.
Das ist kein Float und kein üblicher 32-Bit-Zähler. Die Tagesgrenze wird durch
Umrechnung in Gesamtminuten behandelt. Für Verlaufskontrollen werden Rückgänge
abgewiesen; ein Zuwachs darf höchstens die verstrichene Zeit in ganzen Minuten
plus eine Minute für die unbekannte Phase der Zähler-Minutenkante betragen.
Verglichen wird die tatsächlich verstrichene Zeit zwischen Beobachtungen. Diese
konservative Schranke setzt weder Heizungs-Tastgrad noch Zählerrücksetzung oder
Überlauf voraus. Unplausible Verläufe sind Datenfehler und werden nicht korrigiert.
Es sind Anlagen-Betriebsminuten, nicht bewiesene Flammenlaufzeit oder Brennerstarts.
BO01/BO02 bezeichnen an dieser Anlage oben/unten desselben Puffers.

## Weitere Kandidaten

| Offset / Anzahl | Tabellenbezeichnung | Stand |
|---|---|---|
| 4098 / 2 | Fehler_Min + Leistung_Ist | Statische Zuordnung, ungeprüfte Gerätewerte/Einheiten |
| 4104 / 1 | Leistung_Soll | Statisch; keine automatische kW-/Prozentannahme |
| 33408 / 1 | Aussen_Ist | Statisch; eigener plausibler Bereich/Skalierung nötig |
| 4354 / 1 | Abgasfühler-Kandidat | Optional, Hardware/Skalierung prüfen |

Zuerst Semantik und Dekodierung anhand Belegen klären, dann eigener kleiner Read-Plan,
dann gegebenenfalls Displayabgleich. Nie alle 199 Einträge ungeprüft pollen.
Ein Fehler beendet den Testdurchgang; nicht zur nächsten Adresse wechseln.

## Vollkatalog und Grenzen

[`config/register_catalog.json`](../config/register_catalog.json) enthält alle 199
Projektzuordnungen: 5 historisch live/Display bestätigt, 194 nur statisch.
Felder: Offset, interner Code, Projektname, Wortanzahl, dokumentierter Importstatus,
Prüfstatus, Einheit/Decoder soweit bekannt. Unbekannte Semantik bleibt unbekannt.
Alle `polling_enabled` sind absichtlich false: Dokumentation ist keine Aktivierung.

Nicht enthalten im importierten Profil: Zustandskanal 4097; START-Code 9040 hex
(potenzieller Offset 36928), SOLL-Code 9020 hex (potenzieller Offset 36896).
Diese Zahlen sind keine nutzbaren Schreibadressen. Die internen Wetterausgaben
4128–4131 sind kein nachgewiesener Eingang für externe Prognosen.

Bekannte Altfehler: Exception 2 bei nicht geeigneten Adress-/Tabellenkombinationen.
Die damaligen erfolglosen Tests nicht blind wiederholen. Nicht zugeordnete Lücken
können ganze Blockabfragen scheitern lassen. Nur dokumentierte enge Blöcke lesen.
Ein gültiges Telegramm beweist keine unabhängige Sensoraktualität/Kalibrierung.

Die Importdatei und Schreibfunktionen werden nicht mitgeliefert: bestehende Tabelle
ist beim Betreiber bereits importiert; deren Änderung gehört nicht zur Monitoring-
Implementierung. Herkunft und Prüfsummen: [Quellen](QUELLEN.md).
