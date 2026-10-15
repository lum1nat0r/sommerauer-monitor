# Register, Auswertung und Belegstatus

Referenz: Projektprofil für Pellets 190317.R. Alle Offsets sind **dezimal und
nullbasierte PDU-Adressen**. Kein +1 und kein 40001-Offset. Der Betreiber hat eine
projektspezifische Tabelle importiert; diese Zuordnung gilt nicht automatisch für
andere Geräte. Host privat konfigurieren, Port 502, Unit 255, Modbus TCP, FC03.

## Bestätigte Kerngruppen

Historische Geräteantworten und Displayabgleich am 09.10.2026 bestätigen fünf
Register. Am 15.10.2026 wurde die Verbindung am aktuellen privaten Ziel durch
den begrenzten Kernzyklus erneut belegt; im Abnahmedialog zu #13 bestätigte der
Betreiber den zeitnahen Displayabgleich aller vier Kernsignale.
Dies ist keine unabhängige Display-/Sensorprüfung durch den Assistenten und kein
Dauerbetriebsnachweis. Die privaten Rohdaten werden hier nicht veröffentlicht.

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
aufgeführten Blöcke. `backend/resources/register_catalog.json` bleibt eine getrennte
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

## FC03-Transport und Offline-Simulator

`backend/modbus.py` akzeptiert nur `RegisterBlock`-Einträge des ausführbaren
`core`-Profils und sendet FC03/Unit 255 mit maximal zwei Registern. Eine synchrone
Socket-Anfrage verwendet eine feste Gesamtdeadline von 3 Sekunden ab Aufruf
(einschließlich Warten auf den Client-Lock, Verbindungsaufbau und Empfang).
Es gibt keine Retry- oder parallele Request-Ebene.

Der Transport setzt die erwartete Antwortlänge nach MBAP-Header und Profilblock
zusammen und prüft Transaktions-ID, Protokoll-ID 0, MBAP-Länge, Unit, FC03,
Exception-PDU und Byteanzahl. Empfangene Bytes werden in Fehlern geführt.
Timeout/Abbruch ohne Antwortbytes ist `ConnectionError`; Deadline-/Verbindungsabbruch
nach Teilantwort ist `IncompleteResponseError`; fehlerhafte vollständige Protokolle
sind `ProtocolError`. TCP-Fragmentierung wird bis zur Deadline zusammengesetzt.

`backend/modbus_simulator.py` liefert feste synthetische Werte für die drei
Kernblöcke und definierte Faults (Fragmentierung, Verzögerung, Teilantwort,
verfälschte Header/PDU, Exception und Verbindungsabbruch). Bibliotheks-/API-Start
aktiviert ihn nicht. Modulstart bindet auf `127.0.0.1:1502`; die Klasse verweigert
nicht-loopback Ziele. Kein Scan, Modbus-Schreibbefehl oder Diagnosemodus.

## Weitere Kandidaten

| Offset / Anzahl | Tabellenbezeichnung | Stand |
|---|---|---|
| 4098 / 2 | Fehler_Min + Leistung_Ist | Zwei statische Einträge im Benutzerbericht-Import; beide ungefragt, Einheit/Decoder/Fehlerwerte/Bereich ungeklärt. |
| 4104 / 1 | Leistung_Soll | Statischer Eintrag im Benutzerbericht-Import; ungefragt, Einheit/Decoder/Fehlerwerte/Bereich ungeklärt. Keine kW-/Prozentannahme. |
| 33408 / 1 | Aussen_Ist | Statischer Eintrag im Benutzerbericht-Import; ungefragt, Einheit/Decoder/Fehlerwerte/Bereich ungeklärt. |
| 4354 / 1 | Abgasfühler-Kandidat | Optionaler statischer Eintrag; ungefragt, Hardware/Einheit/Skalierung ungeklärt. |

Diese Statusangaben stammen ausschließlich aus dem bereinigten statischen
Katalog und der bisherigen Projektdokumentation; die privaten Primärbelege
wurden für Issue #11 nicht eingesehen. Es gibt für diese Kandidaten weder
einen neuen Geräteantwort- noch einen Benutzer-/Displayabgleich. Sie bleiben
außerhalb des ausführbaren `core`-Profils und sind nicht als Messwerte/API-
Signale verfügbar. Vor ihrer Nutzung als interpretierte Monitoring-Signale müssen
Primärbelege Semantik und Decoder klären. Der getrennte Diagnosepfad darf dagegen
dokumentierte Rohworte ohne erfundene Interpretation gezielt auswählen; ein
späterer Live-Lauf braucht einen endlichen privaten Ziel-/Laufplan und den
Ausschluss anderer Leser. In #30 wurde kein Gerätezugriff unternommen und kein
Zusatzintervall aktiviert. Der Kernplan bleibt unverändert: drei bestätigte
Blöcke im 60-s-Raster; Zusatzwerte haben kein eingeplantes Intervall.

Ein erfolgreicher einzelner zukünftiger Read wäre kein Beleg für dauerhaft
gültige Skalierung oder Betriebsfreigabe.

Die Zuordnungen oben sind Kandidaten, kein bestätigter Zusatzumfang. Nie alle
199 Einträge ungeprüft pollen. Ein Fehler beendet jeden begrenzten Testdurchgang.

## Vollkatalog und Grenzen

[`backend/resources/register_catalog.json`](../backend/resources/register_catalog.json) enthält alle 199
Projektzuordnungen: 5 historisch live/Display bestätigt, 194 nur statisch.
Felder: Offset, interner Code, Projektname, Wortanzahl, dokumentierter Importstatus,
Prüfstatus, Einheit/Decoder soweit bekannt. Unbekannte Semantik bleibt unbekannt.
Alle `polling_enabled` sind absichtlich false: Dokumentation ist keine Aktivierung.

### Diagnoseauswahl (Issue #30)

`backend/catalog.py` lädt die einzige kanonische Ressource erst mit
`load_catalog() -> RegisterCatalog` über `importlib.resources.files("backend")`;
der Arbeitsordner spielt keine Rolle. `entries` ist eine unveränderliche
Offset-Zuordnung zu `CatalogEntry`, `metadata` bewahrt alle Top-Level-Felder außer
der separat abgebildeten Registerliste. Auch verschachtelte Belegfelder sind
unveränderlich. `sha256` bezeichnet die geladenen Dateibytes, **nicht** den
historischen Tabellenhash `profile_sha256`.

Schema 1, FC03/Unit 255, eindeutige ganzzahlige Offsets 0..65535, ein Wort je
Eintrag, numerisch passende Hexcodes und vollständige exakte Kernblöcke werden
validiert. Bool gilt nicht als Integer. Fehlende/leere/beschädigte Ressourcen
liefern `CatalogUnavailable.code == "catalog_unavailable"`; keine Teilmenge oder
Ersatzquelle. Erfolg und Fehlschlag werden pro Prozess gecacht; ein neuer
Paketstand benötigt einen Prozessneustart. Kernimport, Kerndecoder und Sammler
benötigen diesen Katalog nicht.

`build_read_blocks(register_ids: list[str]) -> tuple[CatalogReadBlock, ...]`
akzeptiert ausschließlich IDs wie `register:33408`. Es dedupliziert, sortiert
nach Offset und verlangt anschließend 1–3 Blöcke. Ein Wort aus 28688/2 oder
36864/2 erweitert auf den exakten Kernblock. Andere dokumentierte Register
bleiben einzelne Worte: 4098 und 4099 werden **nicht** zusammengefasst.
Leere/fremde Auswahlen, Lücke 4103, Steuer-IDs und vier Blöcke werden mit
`CatalogSelectionError` abgewiesen. Keine freie Adresse, Nachbarzusammenfassung,
Lückenüberbrückung, Folgeanfrage oder Netzwerkaktivität.

Der Inventarvertrag bewahrt Originalfelder unter `CatalogEntry.fields` und
stellt Bezeichnung (`csv_label`), Offset, Hexcode, Import-/Belegstatus und
Decoderbeschreibung bereit. `read_support` ist `confirmed_core` für die fünf
Kernworte, sonst `documented_raw`; `write_support` bleibt immer `unknown`.
Uninterpretierte Einheiten und alle dekodierten Messwerte sind `None`
(später JSON `null`). Textliche Unklarheitsbeschreibungen bleiben erhalten;
Auswahl ändert weder Belegstatus noch Pollingprofil.

`CONTROL_CANDIDATES` enthält separat exakt `control:buffer.start` und
`control:buffer.target`, mit internen Codes 9040/9020 und potenziellen Offsets
36928/36896 aus [START/Rückfall](START_RUECKFALL.md). Beide haben
`read_block = None` und `write_support = "unknown"`, gehören nicht zu den
199 FC03-Auswahlen. Keine Schreibkodierung oder Rückfallfähigkeit abgeleitet.
Ein Name wie `Leistung_Soll` beweist ebenfalls keine Schreibbarkeit.
Diese Bibliotheksreferenz ist noch kein ausführbarer Diagnose-Lesepfad;
Transport, Laufsteuerung, API und Dashboard folgen in eigenen Unterissues.


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
