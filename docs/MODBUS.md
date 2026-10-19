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
`READ_PROFILE` ergänzt die expliziten Wörter der bereitgestellten V2-Auswahl
und den separat quellenbelegten Steuerungszustand `1001`. Die beiden Zählerpaare
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

## Betreiberabgleich und Feldbedeutung

Die ergänzten Betreiber-Notizen bestätigen für 79 Wörter der ursprünglichen
V2-Auswahl den Touch-Abgleich / die Lesbarkeit. Für `10D1` und den neu ergänzten
Steuerungszustand `1001` fehlt diese Bestätigung. `verification_status`
unterscheidet `operator_touch_confirmed` von `source_only`.
Das bestätigt weder eine unabhängige Sensorprüfung noch jede physikalische
Interpretation. Der bestehende `live_confirmed`-Wert bleibt als historischer
Nachweis des fünf Wörter umfassenden Kernprofils erhalten, nicht als pauschale
Sicherheitsfreigabe. Zeitplan und Frische verwenden weiterhin `interval_seconds`
(Kern 60 s, Zusatz 300 s), nicht den Verifikationsstatus.

`module_status` trennt die Anlagenbeobachtung davon: Netzmischer, SP-Speichermodule
und die eigenständigen Puffer-2-Parameter `9061`, `9141`, `91E1`, `95E1` sind laut
Betreiber `inactive`; die bestätigten Pufferfühler `9000` / `9001` bleiben `active`.
Der aktive untere Fühler gehört zu demselben Puffer wie der obere. Inaktive
Parameter am Folgeindex werden dadurch nicht zu Messungen dieses unteren Fühlers.
`unknown` bedeutet keine bestätigte Modulaktivität, nicht automatisch inaktiv.
Lesbare inaktive Werte sind kein Nachweis aktiver Anlagenmessungen.
Keiner dieser Statuswerte verändert die gespeicherte Aufzeichnungsauswahl oder
blendet vorhandene Kacheln aus. `/api/signals` liefert die bereinigten Anzeigenamen,
Beschreibungen und Statusfelder; CSV-Importnamen bleiben davon unabhängig.

| Codes (hex) | Quellen- und anlagengerechte Bedeutung |
|---|---|
| `1002` | Kleinste Nummer der aktuell geführten Fehlerliste; 0 = Liste leer, kein Fehlerzähler und kein Beweis physischer Fehlerfreiheit. |
| `1100`, `1102` | Identische ausgewertete Abgastemperaturquelle; kein zweiter Sensor oder ADC-Rohwert. |
| `1106`, `1107`, `1300`–`1302` | Saugzugansteuerung bzw. Betriebsparameter in Prozent, keine gemessene Drehzahl. |
| `1108` | Modulgelieferte Drehzahlrückmeldung, am Touch mit % angezeigt; Bezugsdrehzahl / U/min-Umrechnung nicht belegt. |
| `1104`, `1105`, `1320`, `1321`, `1323` | Ganzzahlige Lambda-Regelskala ohne belegte physikalische Einheit; keine Umrechnung in λ oder O₂-%. `1323` sperrt die normale Materialförderung, kein globaler Heizungsstopp; Gluterhaltung hat einen Sonderzweig. |
| `110E`, `1110` | Berechnete Förder-/Pausentaktlängen, Rohwort ÷ 10 in Sekunden; keine gemessenen Laufzeiten oder Countdowns. |
| `1331`, `1332` | Dieselbe Teillast-Lesequelle; zugleich gekoppelter Zündtaktwert, kein unabhängiger letzter Zündwert. |
| `8000`, `8001` | Heizkreis-Ausbaukonfiguration, nicht Pumpenlauf: 0 aus, 1 aktiv, 2 mit Raumgerät; zusätzlich 3 Rücklaufanhebung nur bei HK1. |
| `8020/21`, `8030/31`, `8040/41` | Heizkreis-Vorlauf-Isttemperatur, Temperatur der konfigurierten Wärmequelle und aktuell berechneter Vorlauf-Sollwert. |
| `9060/61` | Temperatur der konfigurierten Wärmequelle; kein eigener Zulauffühler, Start- oder Pumpenfreigabewert. |
| `9140/41` | Fühlerbetriebsart: 0 ein PT100, 1 zwei PT100, 2 Start/Stopp; kein PT100-Rohmesswert. |
| `91E0/1` | Prozentanzeige mit berechneten Stufen 10/50/90; keine kontinuierliche oder kalorimetrische Energiemessung. Eigene Berechnung je Softwareindex, kein „Ladezustand unten“. |

Die neuen %-Einheiten ändern nur die Bedeutung neu dekodierter Beobachtungen:
die Rohwort-Decoder bleiben unverändert und skalieren oder begrenzen nichts
zusätzlich auf 0–100 bzw. 10/50/90. Frühere Beobachtungen behalten ihre gespeicherte
Einheit in Current-/History-API und CSV; es gibt keine Datenmigration oder
Umdeutung alter `Rohwert`-Beobachtungen. Das Dashboard zeichnet unterschiedliche
gespeicherte Einheiten getrennt und verbindet sie nicht zu einer gemeinsamen Linie.

## Kessel-Steuerungszustand: nur lesend und ausdrücklich auswählen

`modbus.1001` (FC03, Offset 4097, ein Wort) ist als reine Leserweiterung
quellenbelegt, nicht live oder am Touch bestätigt. Zulässig sind ausschließlich
die unveränderten unsigned Wörter `0`, `2`, `3`, `4`, `0x8002`, `0x8003`,
`0x8004`. Basiszustand `raw & 0x7FFF`: 0 Aus, 2 Regelbetrieb,
3 Gluterhaltung, 4 Zündung. Die letzten drei Zustände werden als „Ein“
angezeigt; das ist ein Software-Steuerungszustand, keine unabhängige Flammen-
oder Aktorrückmeldung. Bit `0x8000` ist ein Mindestlaufzeit-Kennzeichen,
kein sekundengenauer Countdown. Insbesondere sind `1` und `0x8000` allein
keine gültigen Lesestatuswerte. Unbekannte Wörter bleiben mit Rohwort,
`value=null`, `quality=invalid` und `unknown_boiler_state` erhalten.

Zusatzintervall 300 s, API-Frische 1200 s (vier Intervalle, Grenze inklusiv); kein neues Minutenpolling.
Upgrade und Katalogabfrage ändern die gespeicherte Auswahl nicht.
Zur ausdrücklich lokalen Aufnahme eine UTF-8-CSV mit der Zeile
`Betriebsstatus;4097;1001` importieren, Auswahl prüfen und Entwurf speichern.
Vorschau allein speichert nichts. Dieser Import ändert ausschließlich den
Monitor, niemals die Gerätetabelle. Kein Schreibadapter und keine Migration.

**Anlagengrenze:** Der Betreiber meldet die neue Tabelle mit dieser Zuordnung
inzwischen installiert. Das ist kein eigener Messwert-/Displaynachweis.
Neue Reads weiterhin endlich planen, andere Leser ausschließen und Stopps beachten.
Keine automatische Tabellenreparatur; lokale Software-/Simulatorprüfung und
die laufende CSV-Vorschau ersetzen keine Geräteabnahme.

### Neu zugeordnete Betriebsart und Basisparameter

Die Decoder unterstützen `1000` (Offset 4096) als Betriebsart mit exakt den
Lesecodes 0, 1, 2, 3, 6, 7, 9 und 10. Code 2 fasst Boiler-/Mehrkesselbetrieb
zusammen; −1/`0xFFFF` und andere unbekannte Wörter sind
`invalid`/`unknown_boiler_mode`, kein gültiger Aus-Zustand.
Die vollständige Bedeutungszuordnung steht in den Signalmetadaten.

`1007`/4103 ist die eingestellte Kessel-Basis-Solltemperatur, ganze °C,
einschließlich der Grenzen 60–90. `9020`/36896 (Puffer 1 SOLL) und
`9040`/36928 (Puffer 1 START) sind ganze °C einschließlich 10–90.
Außerhalb dieser quellenbelegten Parametergrenzen entsteht
`invalid_temperature_setting` mit unverändertem Rohwort und leerem Wert.
Keine Skalierung oder Umdeutung als Temperaturmessung. Wirksame Schaltschwellen
können durch weitere Anforderungen und Zeit-/Wettermodifikatoren abweichen.

Die zusätzlich aus der vollständigen CSV übernommenen Kanäle `1005` (maximale
interne Normalbetriebs-Regelgröße, 30–100 %), `1012` (Software-Reinigung 0/1/2)
und `1013` (gewichteter Reinigungsintervallzähler in min, kein Countdown) werden
ebenfalls dekodiert. Unbekannte Reinigungszustände sind Fehler, keine Nullwerte.

Alle neuen Kanäle sind `source_only`, nicht automatisch live-/Touch-bestätigt,
keine Read-to-clear-Werte, Intervall 300 s und API-Frische 1200 s.
Kein Upgrade ändert die Auswahl. Nur FC03-Einzelblöcke im bestehenden
Leseprofil; Kernprofil, Signalsperren und Stopps unverändert. Keine Schreibfunktion.


### Betriebsanzeige ohne bereitgestellten Statuskanal

Eine gültige, frische und ausdrücklich ausgewählte Beobachtung von `modbus.1001`
hat Vorrang, auch „Aus“ vor einer positiven Istregelgröße. Fehlt ein brauchbarer
Status, nutzt das Dashboard vorhandene ausgewählte gültige `modbus.1003`-
Beobachtungen in der gespeicherten Einheit `%` als **indirekten Betriebshinweis**.
Ein positiver Wert ergibt „Leistungsregelung aktiv“ mit Originalregelgröße und
Beobachtungszeit, keinen bestätigten Steuerungs- oder Flammenzustand.
0 % bleibt „Betriebszustand nicht eindeutig“: Aus oder Gluterhaltung sind möglich,
andere Zustände nicht ausgeschlossen. Kein Schwellwertmodell aus Temperaturen,
Abgas, Sollwerten oder Anlagen-Betriebszähler.

Bei abgewählten, fehlenden, veralteten, ungültigen oder einheitenfremden Quellen
und bei API-Ausfall keine aktuelle Zustandsbehauptung. „Betriebszustand unbekannt“
erklärt den konkreten Grund, nicht „Heizung aus“. Beide Quellen behalten 300 s
Intervall und 1200 s Frische einschließlich fortlaufendem Browseralter.
Die Ersatzanzeige erzeugt keine Reads, Auswahländerungen oder Statushistorie.
Das Band verwendet ausschließlich gespeicherte `1001`-Statusbeobachtungen.




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
Lambda-Ganzzahlen bleiben ohne belegte physikalische Einheit als `Rohwert`
gekennzeichnet; Saugzugwerte verwenden die belegte Prozentanzeige, ohne neue
physikalische Normierung. Settings, Regelgrößen, Steuerungsdatum/-zeit und Messwerte
sind im Dashboard unterschieden. Raumtemperatur 0 und Abgastemperatur 299 können
Initialzustände oder echte Werte sein; diese Mehrdeutigkeit bleibt dokumentiert.

CSV-Folgeimporte erhalten Betreibertexte und alle nicht mehr enthaltenen Einträge.
Identische/umsortierte Importe erzeugen weder Duplikate noch falsche Importfeld-
Änderungsmarker. Sie setzen jedoch die Vorbelegung hochgeladener geeigneter
Zeilen erneut; zuvor gespeicherte Abwahlen dieser Zeilen werden im Entwurf
aufgehoben. Nur inhaltlich unverändertes Speichern bleibt ein Revisions-No-op. Doppelte
Codes oder Offsets, widersprüchliche Zuordnungen und ungültige Dateien werden
vollständig abgelehnt. Ein neuer Import basiert auf der gespeicherten
Konfiguration; vorangehende ungespeicherte Importfelder daher zuerst speichern,
wenn sie Grundlage des nächsten Imports sein sollen.

Gespeicherte und tatsächlich im Sammler geladene Revision/Auswahl sind getrennt
sichtbar. Ein laufender Zyklus verwendet seinen festen Snapshot; Übernahme erst
an der nächsten Zyklusgrenze, auch nach Verbindungsfehlern. Eine
pausierte/gestoppte Erfassung bleibt pausiert/gestoppt; Änderungen können bis zum
nächsten Start als „ausstehend“ erscheinen. Bei Prozessstart wird die gespeicherte
Auswahl geladen; Nutzerpause, Signalsperren und harte Stopps bleiben erhalten. Fehlgeschlagenes
Speichern oder ein Versionskonflikt verändert weder Speicherung noch aktive
Auswahl; nach Konflikt ausdrücklich neu laden. Upload und Speichern führen selbst
keinen Gerätezugriff aus. Bei leerer Auswahl wartet der normale Zeitplan ohne Reads.
Endliche Anfragebudgets und harte Stopps bleiben erhalten, siehe
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

### Aufzeichnung zwischen Instanzen übertragen

Unter **Modbus-Aufzeichnung** liefert **Gespeicherte Aufzeichnung als JSON
herunterladen** die Datei `sommerauer-aufzeichnung.json`.
`GET /api/logging-config/export` liest ausschließlich die gespeicherte Auswahl,
nicht den Browserentwurf oder eine eventuell noch ältere aktive Sammlerrevision.
Die Datei enthält Formatversion `1` und `entries`; je Eintrag ausschließlich
`code`, `offset`, `name`, `record`, `unit`, `description`. Abgewählte und
gesperrte Einträge bleiben als solche erhalten.

Im Ziel **JSON-Datei als Entwurf prüfen** verwenden. Anders als der ergänzende
CSV-Import ersetzt JSON die Auswahl und übernimmt die Betreibertexte aus der
Datei. Nur im Ziel vorhandene Zeilen samt Metadaten bleiben erhalten, aber
`record=false`; kein Löschen vorhandener Einträge. Auch eine leere Auswahl ist
gültig. Der Benutzer muss einen vorhandenen lokalen Entwurf vor dessen Ersetzung
ausdrücklich bestätigen.

`POST /api/logging-config/import-preview` erwartet
`{"revision": <aktuelle lokale Revision>, "configuration": <Dateiobjekt>}`.
Die Vorschau schreibt nichts; erst das bestehende revisionsgesicherte PUT
übernimmt sie atomar. Formatversion, Felder, Registerzuordnung, Zählerpaare,
Duplikate und Datenlimits werden lokal erneut validiert. Nicht kompatible
ausgewählte Register werden abgelehnt, nicht stillschweigend aktiviert.
Quelle und Ziel benötigen einen kompatiblen neuen Build. Unbekannte Format-
oder Freigabefelder werden abgelehnt; kein Übernehmen fremder Revisionen.
HTTP 409 erhält den bisherigen Entwurf.

UTF-8-JSON, kanonischer Download höchstens 4 MiB abzüglich 1 KiB Anfragehülle;
gesamte Importanfrage höchstens 4 MiB. Zu große Konfigurationen ergeben einen
sichtbaren Fehler statt einer nicht wieder importierbaren Datei.
Keine Geräteadresse, Netzwerkeinstellung, privaten Dateipfade, Sammlerzustände,
Anfragebudgets, Signalsperren, Decoderfreigaben oder Messhistorie enthalten.
Export/Vorschau starten keine Erfassung; Speichern setzt keine Schutzstopps
oder Budgets zurück. Bei laufendem Sammler kann die bewusst gespeicherte Auswahl
wie bisher an einer Zyklusgrenze wirksam werden. Eigene Namen/Beschreibungen vor
Weitergabe auf persönliche Angaben prüfen.


## FC03-Transport und Offline-Simulator

`backend/modbus.py` akzeptiert nur vollständig übereinstimmende `RegisterBlock`-
Einträge des expliziten `READ_PROFILE` und sendet FC03/Unit 255 mit maximal
zwei Registern. START/SOLL sind jetzt ausdrücklich lesend unterstützt. Jede synchrone
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
unterstützten Register (Steuerungszustand 2) und bildet das Leeren der Protokollakkumulatoren nach. Bestehende
Faults bleiben erhalten. Modulstart bindet ausschließlich auf Loopback;
Bibliotheks-/API-Start aktiviert keinen Simulator. Kein Schreibbefehl/Diagnosemodus.

## Weitere Kandidaten

| Offset / Anzahl | Tabellenbezeichnung | Stand |
|---|---|---|
| 4098 / 2 | Fehler_Min + Leistung_Ist | Kleinste Fehlernummer der Liste (0 leer) und interne Leistungsregelgröße in Prozent; Betreiber-Touch-Abgleich notiert. Im erweiterten Profil getrennte Einzelreads. |
| 4104 / 1 | Leistung_Soll | Interne Leistungssollgröße in Prozent; keine thermische kW-Messung, kein Schreibparameter dieses Codes. |
| 33408 / 1 | Aussen_Ist | signed16, ganze °C, kanalspezifische Grenze −50 < T < 50; Betreiber-Touch-Abgleich notiert. |
| 4354 / 1 | Abgas_Sensor | Dieselbe ausgewertete Quelle wie 1100, −5 < T < 330; 299 kann Initialwert sein. Betreiber-Touch-Abgleich notiert, keine zusätzliche unabhängige Sensorprüfung. |

Die V2-Erweiterung hat die privaten Lese-, Konversions- und Anzeigepfade für
den bereitgestellten Umfang statisch ausgewertet. Der ergänzte Betreiberabgleich
ist oben separat erfasst; er ersetzt keine unabhängige Geräte-/Hardwareprüfung.
Für diesen Feldabgleich wurde keine neue Live-Anfrage ausgeführt und kein privater
Zielwert in Beispiele übernommen.
Kernblöcke bleiben mindestens 60 s, Zusatzblöcke mindestens 300 s auseinander,
jeweils ab Abschluss. Der zentrale Sammler überspringt noch nicht fällige
Zusätze, statt die Kernwerte bis zu deren 300-s-Termin warten zu lassen.
Die API markiert Zusatzwerte nach Überschreiten von 1200 s als veraltet
(`fresh_until_age_seconds = 4 * interval_seconds`, Grenze inklusiv).
Kernwerte haben bei 60 s Intervall entsprechend 240 s Frische.
Nur gültige, nichtleere Werte können frisch sein; Diagramme berücksichtigen
das längere Intervall. Kein automatisches Nachholen verpasster Messungen.

Ein erfolgreicher einzelner zukünftiger Read wäre kein Beleg für dauerhaft
gültige Skalierung oder Betriebsfreigabe.

Die Zuordnungen dieses Abschnitts sind explizit unterstützte Lesezuordnungen mit
dem oben getrennt beschriebenen Belegstatus, keine generelle Betriebsfreigabe.
Nie alle 199 Einträge ungeprüft pollen. Ein Fehler beendet jeden begrenzten Testdurchgang.

## Vollkatalog und Grenzen

[`docs/register_catalog.json`](register_catalog.json) enthält alle 199
Projektzuordnungen: 5 historisch live/Display bestätigt, 194 nur statisch.
Felder: Offset, interner Code, Projektname, Wortanzahl, dokumentierter Importstatus,
Prüfstatus, Einheit/Decoder soweit bekannt. Unbekannte Semantik bleibt unbekannt.
Alle `polling_enabled` sind absichtlich false: Dokumentation ist keine Aktivierung.

Der Betreiber meldet die Zuordnungen für `1001`/4097, Betriebsart `1000`/4096,
Kessel-Basis-Soll `1007`/4103, START `9040`/36928 und SOLL `9020`/36896
mit der neuen Tabelle installiert. Eigener Messwertabgleich bleibt offen.
Keine dieser Zuordnungen ist eine abgenommene Schreibfunktion. Die internen Wetterausgaben
4128–4131 sind kein nachgewiesener Eingang für externe Prognosen.

Bekannte Altfehler: Exception 2 bei nicht geeigneten Adress-/Tabellenkombinationen.
Die damaligen erfolglosen Tests nicht blind wiederholen. Nicht zugeordnete Lücken
können ganze Blockabfragen scheitern lassen. Nur dokumentierte enge Blöcke lesen.
Ein gültiges Telegramm beweist keine unabhängige Sensoraktualität/Kalibrierung.

Die Importdatei und Schreibfunktionen werden nicht mitgeliefert: bestehende Tabelle
ist beim Betreiber bereits importiert; deren Änderung gehört nicht zur Monitoring-
Implementierung. Herkunft und Prüfsummen: [Quellen](QUELLEN.md).
