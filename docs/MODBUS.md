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
aufgeführten Blöcke. `docs/register_catalog.json` bleibt eine getrennte
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

## Aufzeichnung konfigurieren

Unter **Modbus-Aufzeichnung** (`#/modbus`) wird ausschließlich die lokale
Monitor-Auswahl bearbeitet, niemals die Modbus-Tabelle der Heizung.
Formatquelle ist das [Betreiberbeispiel in Issue #55](https://github.com/lum1nat0r/sommerauer-monitor/issues/55#issuecomment-6218867012);
ein privater Originalexport wurde nicht unabhängig geprüft.

1. CSV als UTF-8 (optionaler BOM), ohne Kopfzeile hochladen:
   `Name;dezimaler Offset;interner Hexcode`, z. B. `Kessel_Ist;4102;1006`.
   Der interne Code besteht aus vier Hexzeichen; Groß-/Kleinschreibung ist
   unerheblich. Maximal 1 MiB und 5.000 Einträge. CSV-Anführungszeichen für
   Namen mit Semikolon werden unterstützt.
2. Die Vorschau ergänzt/aktualisiert nach **internem Code als stabiler Identität**,
   nicht nach Reihenfolge oder Name. Neue Zeilen stehen grün als „Neu“, geänderte
   gelb als „Geändert“ oben; betroffene Importfelder sind benannt.
3. **Aufzeichnen**, **Einheit** und **Beschreibung** bearbeiten. Einheit/Beschreibung
   sind Betreiber-Metadaten, keine Umrechnung oder fachliche Bestätigung.
   Messungen, Diagramme und CSV-Messwertexport behalten ihre Decoder-Einheit.
4. **Entwurf speichern** schreibt alle Einträge und Einstellungen atomar in
   `monitor.sqlite3` im persistenten Datenverzeichnis. Ohne Speichern bleibt
   die bisherige Konfiguration unverändert. „Entwurf verwerfen und neu laden“
   verwirft lokale Änderungen ausdrücklich.

Neue Einträge sind zunächst abgewählt. Nur exakte bestätigte Code-/Offset-
Zuordnungen des `core`-Profils haben einen Decoder; andere Einträge sind mit
Begründung gesperrt. Offsetänderungen deaktivieren die betroffene Auswahl,
beim Mehrwortzähler beide Wörter. Bei wiederhergestellter bestätigter Zuordnung
ist eine bewusste erneute Auswahl möglich. Eine reine Namensänderung erhält
die Auswahl. **7010/7011** werden gemeinsam geschaltet und als ein
Anlagen-Betriebsminutensignal dekodiert. Die beiden Pufferkanäle sind separat
abwählbar; technisch wird weiterhin der bestätigte Zweierblock gelesen und
validiert, aber nur der ausgewählte Kanal gespeichert.

Folgeimporte erhalten Betreibertexte und alle nicht mehr enthaltenen Einträge.
Identische/umsortierte Importe erzeugen weder Duplikate noch Änderungsmarker;
inhaltlich unverändertes Speichern erhöht auch die Revision nicht. Doppelte
Codes oder Offsets, widersprüchliche Zuordnungen und ungültige Dateien werden
vollständig abgelehnt. Ein neuer Import basiert auf der gespeicherten
Konfiguration; vorangehende ungespeicherte Importfelder daher zuerst speichern,
wenn sie Grundlage des nächsten Imports sein sollen.

Gespeicherte und tatsächlich im Sammler geladene Revision/Auswahl sind getrennt
sichtbar. Ein laufender Zyklus einschließlich Wiederaufnahme verwendet seinen
festen Snapshot; Übernahme erst am Beginn des nächsten Kerndurchlaufs. Eine
pausierte/gestoppte Erfassung bleibt pausiert/gestoppt; Änderungen können bis zum
nächsten Start als „ausstehend“ erscheinen. Bei Prozessstart wird die gespeicherte
Auswahl geladen, ohne einen gespeicherten Stopp zu quittieren. Fehlgeschlagenes
Speichern oder ein Versionskonflikt verändert weder Speicherung noch aktive
Auswahl; nach Konflikt ausdrücklich neu laden. Upload und Speichern führen selbst
keinen Gerätezugriff aus. Bei leerer Auswahl wartet der normale Zeitplan ohne Reads.
Wiederaufnahmebudget und harte Stopps bleiben erhalten, siehe
[Fehlerverhalten](FEHLERVERHALTEN.md).

Ohne gespeicherte Auswahl bleiben die fünf bestätigten Register wie bisher
ausgewählt; weder CSV-Upload noch Installation aktiviert die Erfassung.
Historische Beobachtungen werden nicht gelöscht oder anhand neuer Importfelder
umgedeutet. Schema 1/2 wird additiv auf 3 migriert; vor Upgrade eine konsistente
Sicherung erstellen. Alte App-Versionen unterstützen Schema 3 nicht.

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
Signale verfügbar. Vor einem begründeten privaten FC03-Lauf müssen die
Primärbelege Semantik und Decoder klären; der private Ziel-/Laufplan und der
Ausschluss anderer Leser sind hier nicht verfügbar. Daher wurde kein
Gerätezugriff unternommen und kein Zusatzintervall aktiviert. Der Kernplan
bleibt unverändert: drei bestätigte Blöcke im 60-s-Raster; die Zusatzwerte
haben kein eingeplantes Intervall.

Ein erfolgreicher einzelner zukünftiger Read wäre kein Beleg für dauerhaft
gültige Skalierung oder Betriebsfreigabe.

Die Zuordnungen oben sind Kandidaten, kein bestätigter Zusatzumfang. Nie alle
199 Einträge ungeprüft pollen. Ein Fehler beendet jeden begrenzten Testdurchgang.

## Vollkatalog und Grenzen

[`docs/register_catalog.json`](register_catalog.json) enthält alle 199
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
