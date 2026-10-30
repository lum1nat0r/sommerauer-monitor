# Erfassung, Fehler und Wiederaufnahme

Ein Client, eine Anfrage; Kernblöcke jeweils mindestens 60 s auseinander.
Der Sammler zählt konservativ ab Abschluss der vorherigen Verarbeitung desselben
Blocks mit einer hochauflösenden monotonen Uhr (`time.perf_counter`), nicht ab
einer vorgelagerten Speicherreservierung. Speicher-/Antwortlaufzeiten kommen
zum Mindestintervall hinzu; das 60-s-Ziel ist kein exakt phasenstarres Raster.
Maximal zwei Register, 3 s Transport-Gesamtdeadline einschließlich Verbindungsaufbau/
Antwort. Kein Nachholen in Bursts. Zusatzgruppen bleiben bis zur gesonderten
fachlichen Prüfung und Kapazitätsplanung deaktiviert.

**Betreiberentscheidung 19.10.2026:** Im Dauerbetrieb kein Fehlversuchslimit und
keine steigenden Wartezeiten bei reinen Verbindungsfehlern. Ausgewählte Kern-
und Zusatzblöcke bleiben in ihrem normalen 60-/300-s-Zeitplan. Endliche
Prüfläufe, harte Fehler und ungewisse Read-to-clear-Auslesungen behalten ihre Stopps.

## Zustände und Übergänge

| Zustand | Verhalten / erlaubter Übergang |
|---|---|
| `unconfigured` | Kein Ziel/Profil, keine Verbindung; konfigurieren -> `paused` |
| `paused` | Nutzerpause oder Erstinstallation; expliziter App-Start -> `running` |
| `running` | Geplante Reads; erfolgreicher Zyklus bleibt running |
| `completed` | Endliches Anfrage-/Zeitlimit erreicht; keine weiteren Reads bis zu bewusstem `acknowledge_and_start` |
| `reconnect_wait` | Verbindungsfehler sichtbar; normale Abfragefolge und Blockintervalle laufen ohne Versuchslimit weiter |
| `stopped_transport` | Endlicher Lauf nach Transportfehler oder ungewisse Read-to-clear-Auslesung; Ursache prüfen, bewusst quittieren |
| `stopped_protocol` | Ungültige/teilweise Antwort oder übergreifender Modbus-Gerätefehler; keine automatischen Reads |
| `stopped_data` | Strukturell ungültige Registerblockdaten; keine automatischen Reads |
| `stopped_storage` | Speicherung/Zustand nicht sicher möglich; keine neuen Reads |

Nutzer-Stopp oder Anlagenauffälligkeit überstimmt alles. Harte Fehlerstopps können
nur nach Klärung bewusst quittiert werden; ein Neustart ist keine Quittierung.
Web-API/Diagramme bleiben unabhängig vom Messzustand erreichbar.
Ein gespeicherter Zustand `completed` bleibt auch bei deaktiviertem Sammler
über die lesende API „Erfassung abgeschlossen“, nicht `stopped_storage`.

Die SQLite-Zustandszeile speichert Fehlerstatus, Ursache, Anfragezähler, nächsten
Block, letzten Anfrageblock und Abschlusszeiten. Jeder Socketzugriff wird vorher
persistent reserviert. Die Konfiguration wird nur als SHA-256-Fingerprint aus
Ziel, Port, Unit und Profil gespeichert; eine abweichende Konfiguration liest
nicht automatisch weiter. Laufzeitfristen verwenden eine monotone Uhr.
Nach Neustart wartet ein unterbrochener oder zur Wiederaufnahme vorgesehener
Block wieder sein volles reguläres Intervall; andere fällige Blöcke laufen weiter.
Gespeicherte Abschlusszeiten bestimmen deren Fälligkeit. Eine Nutzerpause bleibt pausiert.

Alte `stopped_transport`-Zustände werden beim Start des aktivierten Sammlers
automatisch in reguläres Polling überführt, sofern weder der gespeicherte noch
der neue Lauf endlich ist und kein Read-to-clear-Block betroffen ist.
Das entfernt die alte Budgetsperre ohne Löschen von Historie oder Anfragezählern.
`completed`, Nutzerpause, Zielwechsel, Signalsperren und harte Stopps bleiben erhalten.
Eine deaktivierte App führt durch das Upgrade weiterhin keine Reads aus.

`GET /api/collector/status` liefert Zustand, sichere Ursache, nächste Aktion und
den nächsten regulären Abfragetermin bei Verbindungsfehlern. `reconnect_attempts`
ist nur ein Diagnosezähler der Folgeversuche seit dem letzten beantworteten Read;
keine Obergrenze und kein `reconnect_attempt_limit` mehr. Eine erfolgreiche Antwort
setzt den Zähler zurück, ohne drei Kernzyklen abzuwarten. Das Dashboard zeigt
„ohne Versuchslimit“ statt eines verbrauchten Budgets.
Rohe Transport-/Speicherfehler und Konfigurations-Fingerprints bleiben privat.

## Fehler einzelner Werte: übrige Erfassung läuft weiter

Die neue Vorgehensweise trennt fehlende optionale Daten und isolierbare
Wertfehler von übergreifenden Fehlern. Die Anlagenkachel zeigt Qualität,
konkreten Fehlertext/-code, Beobachtungszeit, Blockoffset und Registerzahl.
Ein Fehler ersetzt einen früheren guten Wert nicht durch 0 oder eine frische
Kopie des alten Werts. Historie und CSV behalten Fehlerbeobachtungen mit
`value=null`, Rohwörtern soweit vorhanden und Herkunft.

- **Fehlende Wetterdaten:** Die dokumentierten Fehlwerte −50 bei Wettertemperatur
  und −1 beim Wetterstatus ergeben `unavailable`/`missing_weather`. Die übrigen
  Werte werden weiter erfasst; Wetterwerte werden im normalen 300-s-Intervall
  erneut gelesen. Wenn wieder Daten vorliegen, wird die Kachel wieder aktuell.
- **Unplausibler Einzelwert/Zähler (Änderung 30.10.2026):** `invalid` mit konkreter
  Ursache; der dekodierte Wert (z. B. 110 °C) wird zusammen mit den Rohwörtern
  gespeichert und in Kachel/Diagramm als „unplausibel" markiert (Marker, keine Linie).
  Es gibt keine Signalsperre und keine Freigabe: das Signal wird im normalen Intervall
  weiter gelesen, bei gültigem Wert wieder `ok`. Strukturell unbekannte Zustandswörter
  (`unknown_*`) und Restminuten >=1440 behalten `value=null`. Alte Wertfehler-Sperren
  aus gespeichertem Zustand werden beim Start automatisch verworfen.
- **Gültige Modbus-Ablehnung 2 oder 3:** Der betroffene Registerblock wird mit
  `modbus_exception_2` beziehungsweise `_3` ausgesetzt; andere Blöcke laufen weiter.
  Das umfasst nicht allgemeine Geräte-, Busy- oder Gatewayfehler.

Neustart, normale Pause/Fortsetzung und CSV-Speichern heben Registersperren
(Modbus-Ausnahme 2/3) nicht auf. Zur bewussten Freigabe zuerst die Ursache prüfen und die Erfassung pausieren;
`POST /api/collector/acknowledge-and-start` hebt die Sperren ausdrücklich auf
und startet die Erfassung. Das ist eine erneute Freigabe aller gesperrten Werte,
keine Hintergrundwiederholung. Anfragebudget und Historie bleiben erhalten.
Die Oberfläche besitzt bisher keinen separaten Einzelwert-Freigabeknopf.
Sind alle ausgewählten Signale gesperrt, wartet der Sammler ohne Busy-Loop.

Globale Transport-/Protokollfehler erhalten ebenfalls eine sichere Fehleranzeige
am betroffenen Wert, soweit Speicherung möglich ist. Hostnamen, private Pfade
und rohe Betriebssystemfehler werden nicht als Kacheltexte veröffentlicht.

### Änderungen der Aufzeichnungsauswahl

CSV-Vorschau und Speichern erzeugen selbst keine Modbus-Anfrage und verändern
weder Pause/Fehlerstopp noch ein endliches Anfragebudget. Der Sammler übernimmt
die gespeicherte Auswahl an der nächsten Zyklusgrenze als festen Snapshot;
auch Verbindungsfehler halten diese Übernahme nicht mehr auf.
Gespeicherte und aktive Revision/Auswahl sind über `/api/logging-config` sichtbar.
Bei Pause oder hartem Stopp kann eine neue Revision bis zum nächsten bewussten
Start ausstehen. Bei Prozessstart wird die gespeicherte Auswahl geladen;
Nutzerpause, Signalsperren und harte Fehlerstopps bleiben wirksam.

Abgewählte Blöcke entfallen aus dem normalen Plan. Bei einem teilweise
ausgewählten Zweierblock werden beide Wörter unverändert validiert, aber nur
ausgewählte Signale gespeichert. Auch fehlgeschlagene Blöcke werden nach
Übernahme einer Abwahl nicht mehr gelesen. Eine vollständig leere Auswahl
wartet ohne Reads; kein Busy-Loop.
Bestehende Minutenhistorie bleibt bei jeder Konfigurationsänderung unverändert.

### V2-Zusatzregister

Kernblöcke behalten mindestens 60 s Abstand; die Zusatzblöcke mindestens 300 s,
jeweils ab Abschluss der vorherigen Verarbeitung. Noch nicht fällige Zusätze
werden übersprungen, damit kein 300-s-Warten die Kernwerte verdrängt. Bei
Prozessneustart werden gespeicherte Abschlusszeiten berücksichtigt; die
Anfragezähler und endlichen Laufgrenzen bleiben erhalten.

Nur die fünf Kernregister sind live bestätigt. Auf Betreiberwunsch wählt ein
CSV-Upload interpretierbare Einträge mit passender Lesezuordnung im Entwurf
vor, einschließlich der Protokollregister. Das ist noch keine aktive
Übernahme: Erst Speichern ändert die gespeicherte Auswahl. Die Oberfläche
unterscheidet Livebestätigung, statische Semantik und Herstellerrohwerte.
Neun Protokollregister leeren bereits beim Lesen aufgesammelte Ausgangsbits
(Read-to-clear). Sie sind deshalb zusätzlich unmittelbar an der Auswahl
gekennzeichnet; Wiederholungen oder andere Leser können Informationen verlieren.

Reine Verbindungsfehler bei normalen Zusatzblöcken werden wie bei Kernblöcken
behandelt: nächster regulärer Termin, mindestens 300 s ab Abschluss, ohne
zusätzliche Backoff-Stufe. Fällige Kernwerte werden dadurch nicht verdrängt.
Für Read-to-clear-Blöcke bleibt ein ungewisser Ausgang gesperrt:
Transportfehler führen zu `stopped_transport`, ungültige/teilweise Antworten
zu `stopped_protocol`. Ein Neustart darf solche Auslesungen nicht wiederholen.

## Reine Verbindungsfehler

TCP-Verbindungsfehler oder Timeout ohne empfangene Antwortbytes ergeben im
Dauerbetrieb `reconnect_wait`, aber keinen Abbruch nach einer Zahl von Fehlern.
Der fehlgeschlagene Block wird mit `unavailable`/`transport_error` und `value=null`
gespeichert und frühestens nach seinem normalen Intervall erneut abgefragt.
Andere fällige Blöcke bleiben im Plan. Ziel, Unit, Funktion und Registerauswahl
werden nicht verändert; keine Suche und keine unmittelbaren Zusatzversuche.

Eine wieder erfolgreiche Antwort wird direkt gespeichert; die Verbindung gilt
wieder als erreichbar. Wertfehler behalten unabhängig davon ihre eigene Qualität
und gegebenenfalls Signalsperre. Es gibt keine Erholungszyklen oder Budgetresets mehr.

Explizit endliche App-Läufe (`COLLECTOR_MAX_REQUESTS`) und Einzeltestwerkzeuge
behalten ihren Fehlerstopp ohne automatische Wiederholung. Wenn der gespeicherte
Zustand nicht verlässlich lesbar ist: Speicherstopp statt automatischem Neubeginn.

## Harte Fehler

Falsche Unit/Funktion/Transaktion, ungültige MBAP-Länge oder Protokoll-ID,
falsche Byteanzahl und unvollständige Antworten führen weiterhin zum
Protokollstopp. Ebenso globale Modbus-Fehler, etwa Gerätefehler 4, Busy 6 oder
Gatewayfehler; nur registerbezogene Ausnahmen 2/3 werden isoliert.
Der Transport liefert dazu die empfangene
Byteanzahl: Verbindungsfehler/Timeout ohne Antwortbytes ist von Teilantwort/Abbruch
unterschieden. Normale TCP-Fragmentierung innerhalb der Deadline ist kein Fehler.
Eine abgebrochene Verbindung nach Teilantwort zählt ebenfalls als Protokollfehler,
nicht als reine Nichterreichbarkeit.

Ungültige Wertebereiche, Ersatzwerte wie 110 bei Kern-Temperaturkanälen,
Restminuten >=1440 und widersprüchliche Zähler ergeben isolierte ungültige
Signale (Wert bleibt, soweit dekodierbar, gespeichert) statt eines Stopps aller Werte. Strukturell falsche Wortanzahl oder
ungültige Registerworttypen bleiben globale Datenfehler. Rohworte und sichere
Fehlerdetails werden gespeichert, soweit die Datenbank funktioniert.
DB voll/nicht beschreibbar/Migrationsfehler -> Speicherstopp, keine weiteren Reads.

## Offline-Prüfungen

Synthetische Tests prüfen Ausfälle über die frühere Fünf-Versuche-Grenze hinaus,
unveränderte 60-/300-s-Abstände, Wiederkehr gültiger Werte, fehlende Verdrängung
der Kernwerte durch Zusatzfehler, Systemuhrsprung, Neustart mit alten
Budgetsperren und unterbrochenen Anfragen, Nutzerpause/Fortsetzung, Zielwechsel,
endliche Grenzen sowie unveränderte Protokoll-/Speicher-/Read-to-clear-Stopps.
Ein Loopback-Smoke mit echtem FC03-Transport und virtueller Schedulerzeit belegt
21 Verbindungsfehler und anschließend drei erfolgreiche Reads.
Dies ist kein Geräte- oder Langzeitnachweis.
