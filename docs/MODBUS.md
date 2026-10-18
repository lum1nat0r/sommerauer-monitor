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

Das bestätigte Kernprofil `core` bleibt in
[`backend/registers.py`](../backend/registers.py) unverändert. Das explizite
`READ_PROFILE` ergänzt ausschließlich die weiteren 75 Wörter der bereitgestellten
V2-Auswahl: insgesamt 80 Registerwörter und 78 Signale. Die beiden Zählerpaare
ergeben jeweils ein Signal. Keine beliebigen Adressen und kein Vollscan.
Neue Signale tragen Herkunft `extended/1/1`; alte Kernmessungen behalten
`core/1/1`. Der 199er-Katalog bleibt eine historische statische Referenz,
nicht die ausführbare Pollingliste.

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
Formatquelle war zunächst das Betreiberbeispiel in Issue #55. Für die
V2-Erweiterung wurden die privat bereitgestellte 80er-CSV und rekonstruierte
Herstellerquellen lokal geprüft; Originaldateien und Quellcode bleiben privat.

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

Beim Upload werden alle interpretierbaren Einträge mit passender Lesezuordnung
im Entwurf vorgewählt. Das gilt auch für zuvor abgewählte hochgeladene Einträge
beim Reimport; fehlende CSV-Zeilen behalten ihre gespeicherte Auswahl.
Unbekannte Codes, abweichende Offsets und unvollständige Zählerzuordnungen
bleiben abgewählt und gesperrt. Bei wiederhergestellter gültiger Zuordnung
ist der Eintrag wieder vorgewählt. Dies ist kein Live-/Displaynachweis oder
Hersteller-Verträglichkeitsversprechen. Erst **Entwurf speichern** übernimmt
die Auswahl; vorher kann jede geeignete Zeile wieder abgewählt werden.
Die Zählerpaare **7010/7011** und **7012/7013** werden jeweils gemeinsam
geschaltet und als Gesamtminuten dekodiert. Ein hochgeladenes Wort wählt auch
seinen bereits vorhandenen, korrekt zugeordneten Partner vor. Stokerzeit bezeichnet die
softwaregezählte Freigabezeit, nicht mechanisch nachgewiesene Bewegung.
Puffer oben/unten bleiben separat abwählbar, aber im bestätigten Zweierblock.
Alle anderen Zusatzregister werden einzeln gelesen, ohne ungeprüfte Lücken.

**Neun Protokollregister sind Read-to-clear:** `12F0`, `85E0`, `85E1`, `8BF0`,
`8BF1`, `8E0F`, `8E1F`, `95E0`, `95E1`. Ihre Auslesung leert aufgesammelte
Modul-Ausgangsbits. Auch sie werden beim Upload im Entwurf vorgewählt;
Warnungen stehen direkt an der Auswahl. Vor dem Speichern prüfen und bei
Bedarf abwählen. Konkurrierende Leser können Informationen verlieren.
Diese Werte sind kein Störungsjournal. Nach einem ungewissen
Ausleseausgang erfolgt keine automatische Wiederholung, auch nicht nach Neustart.

Einheiten/Skalen sind kanalbezogen: Temperaturen in ganzen °C mit jeweils
eigenen Grenzen, Versorgung in 0,1 V, interne Leistungsregelgrößen in Prozent,
Förder-/Pausentakte in 0,1 s und Stokerzähler als Tage/Restminuten.
Lambda-/Gebläsewerte ohne belegte physikalische Skalierung bleiben ausdrücklich
Herstellerrohwerte. Settings, Regelgrößen, Steuerungsdatum/-zeit und Messwerte
sind im Dashboard unterschieden. Raumtemperatur 0 und Abgastemperatur 299 können
Initialzustände oder echte Werte sein; diese Mehrdeutigkeit bleibt dokumentiert.

Folgeimporte erhalten Betreibertexte und alle nicht mehr enthaltenen Einträge.
Identische/umsortierte Importe erzeugen weder Duplikate noch falsche Importfeld-
Änderungsmarker. Sie setzen jedoch die Vorbelegung hochgeladener geeigneter
Zeilen erneut; zuvor gespeicherte Abwahlen dieser Zeilen werden im Entwurf
aufgehoben. Nur inhaltlich unverändertes Speichern bleibt ein Revisions-No-op. Doppelte
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
umgedeutet. Schema 1/2/3 wird additiv auf 4 migriert; vor Upgrade eine konsistente
Sicherung erstellen. Alte App-Versionen unterstützen Schema 4 nicht.

Fehlende Wetterwerte erscheinen jetzt als `unavailable` an der Kachel, ohne die
übrigen Werte zu stoppen. Ungültige Einzelwerte und registerbezogene
Modbus-Ausnahmen 2/3 werden persistent ausgesetzt; gesunde Nachbarn bleiben
auslesbar. Globale Geräte-/Protokollfehler bleiben Stopps.
Details und bewusste Freigabe: [Fehlerverhalten](FEHLERVERHALTEN.md).

## FC03-Transport und Offline-Simulator

`backend/modbus.py` akzeptiert nur vollständig übereinstimmende `RegisterBlock`-
Einträge des expliziten `READ_PROFILE` und sendet FC03/Unit 255 mit maximal
zwei Registern. START/SOLL sind nicht Teil dieses Leseprofils. Jede synchrone
Socketanfrage verwendet eine feste 3-s-Gesamtdeadline
(einschließlich Warten auf den Client-Lock, Verbindungsaufbau und Empfang).
Es gibt keine Retry- oder parallele Request-Ebene.

Der Transport setzt die erwartete Antwortlänge nach MBAP-Header und Profilblock
zusammen und prüft Transaktions-ID, Protokoll-ID 0, MBAP-Länge, Unit, FC03,
Exception-PDU und Byteanzahl. Empfangene Bytes werden in Fehlern geführt.
Timeout/Abbruch ohne Antwortbytes ist `ConnectionError`; Deadline-/Verbindungsabbruch
nach Teilantwort ist `IncompleteResponseError`; fehlerhafte vollständige Protokolle
sind `ProtocolError`. TCP-Fragmentierung wird bis zur Deadline zusammengesetzt.

`backend/modbus_simulator.py` liefert ausdrücklich synthetische Werte für alle
80 Register und bildet das Leeren der Protokollakkumulatoren nach. Bestehende
Faults bleiben erhalten. Modulstart bindet ausschließlich auf Loopback;
Bibliotheks-/API-Start aktiviert keinen Simulator. Kein Schreibbefehl/Diagnosemodus.

## Weitere Kandidaten

| Offset / Anzahl | Tabellenbezeichnung | Stand |
|---|---|---|
| 4098 / 2 | Fehler_Min + Leistung_Ist | Fehlerkennung (keine Minuten) und interne Leistungsregelgröße in Prozent; statisch geprüft, nicht live abgenommen. Im erweiterten Profil getrennte Einzelreads. |
| 4104 / 1 | Leistung_Soll | Interne Leistungssollgröße in Prozent; keine thermische kW-Messung, kein Schreibparameter dieses Codes. |
| 33408 / 1 | Aussen_Ist | signed16, ganze °C, kanalspezifische Grenze −50 < T < 50; nicht live abgenommen. |
| 4354 / 1 | Abgas_Sensor | Statisch belegter Ganzgradkanal, −5 < T < 330; 299 kann Initialwert sein. Nicht live abgenommen. |

Die V2-Erweiterung hat die privaten Lese-, Konversions- und Anzeigepfade für
den bereitgestellten Umfang statisch ausgewertet. Dies ersetzt weder
Geräteantwort noch Display-/Hardwareabgleich. Es wurde keine Live-Anfrage
ausgeführt und kein privater Zielwert in Beispiele übernommen.
Kernblöcke bleiben mindestens 60 s, Zusatzblöcke mindestens 300 s auseinander,
jeweils ab Abschluss. Der zentrale Sammler überspringt noch nicht fällige
Zusätze, statt die Kernwerte bis zu deren 300-s-Termin warten zu lassen.
Die API markiert Zusatzwerte nach 600 s als veraltet; Diagramme berücksichtigen
das längere Intervall. Kein automatisches Nachholen verpasster Messungen.

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
