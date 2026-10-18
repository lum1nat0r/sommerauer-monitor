# Erfassung, Fehler und Wiederaufnahme

Ein Client, eine Anfrage; Kernblöcke jeweils mindestens 60 s auseinander.
Der Sammler zählt konservativ ab Abschluss der vorherigen Verarbeitung desselben
Blocks mit einer hochauflösenden monotonen Uhr (`time.perf_counter`), nicht ab
einer vorgelagerten Speicherreservierung. Speicher-/Antwortlaufzeiten kommen
zum Mindestintervall hinzu; das 60-s-Ziel ist kein exakt phasenstarres Raster.
Maximal zwei Register, 3 s Transport-Gesamtdeadline einschließlich Verbindungsaufbau/
Antwort. Kein Nachholen in Bursts. Zusatzgruppen bleiben bis zur gesonderten
fachlichen Prüfung und Kapazitätsplanung deaktiviert.

## Zustände und Übergänge

| Zustand | Verhalten / erlaubter Übergang |
|---|---|
| `unconfigured` | Kein Ziel/Profil, keine Verbindung; konfigurieren -> `paused` |
| `paused` | Nutzerpause oder Erstinstallation; expliziter App-Start -> `running` |
| `running` | Geplante Reads; erfolgreicher Zyklus bleibt running |
| `completed` | Endliches Anfrage-/Zeitlimit erreicht; keine weiteren Reads bis zu bewusstem `acknowledge_and_start` |
| `reconnect_wait` | Normale Folge pausiert; genau ein Versuch nach Ablauf der Wartezeit |
| `stopped_transport` | Wiederaufnahmebudget ausgeschöpft oder endlicher Lauf nach Transportfehler; Ursache prüfen, bewusst quittieren |
| `stopped_protocol` | Ungültige/teilweise Antwort oder übergreifender Modbus-Gerätefehler; keine automatischen Reads |
| `stopped_data` | Strukturell ungültige Registerblockdaten; keine automatischen Reads |
| `stopped_storage` | Speicherung/Zustand nicht sicher möglich; keine neuen Reads |

Nutzer-Stopp oder Anlagenauffälligkeit überstimmt alles. Fehlerstopp kann nur nach
Klärung der Ursache bewusst quittiert werden; ein Neustart ist keine Quittierung.
Web-API/Diagramme bleiben unabhängig vom Messzustand erreichbar.
Ein gespeicherter Zustand `completed` bleibt auch bei deaktiviertem Sammler
über die lesende API „Erfassung abgeschlossen“, nicht `stopped_storage`.

Die SQLite-Zustandszeile speichert Fehlerstatus, Ursache, Wiederaufnahmezähler,
Zyklusfortschritt, nächsten Block und Retry-Deadline. Jede Wiederaufnahme wird vor
dem Socketzugriff reserviert. Die Konfiguration wird nur als SHA-256-Fingerprint
aus Ziel, Port, Unit und Profil gespeichert; eine abweichende Konfiguration liest
nicht automatisch weiter. Laufzeitfristen verwenden eine monotone Uhr. Nach Prozessneustart
wird die volle aktuelle Wartezeit erneut angesetzt, damit Vorwärts-/Rückwärtssprünge
der Systemuhr den Schutz nicht verkürzen. Ein unterbrochener, vorab reservierter
Socketversuch zählt gegen das Wiederaufnahmebudget. Ein alter Zustand `running` wird
konservativ zu `reconnect_wait`; ein gespeicherter Nutzerstopp bleibt pausiert.

`GET /api/collector/status` und das Dashboard zeigen Zustand, Fehlerkategorie,
verbrauchte Versuche, nächste Aktion und geplanten Retry. Der Endpunkt gibt keine
rohen Transport-/Speicherfehler oder Konfigurations-Fingerprints zurück. Ein explizites
`acknowledge_and_start` setzt harte Stopps erst nach Ursachenklärung zurück;
Prozessstart quittiert sie nicht.

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
- **Ungültiger Einzelwert/Zähler:** `invalid` mit konkreter Ursache. Nur das
  betroffene Signal wird ausgesetzt und in `blocked_signals` persistent gesperrt.
  Ein gesunder Nachbar im selben Pufferblock wird weiter gelesen und gespeichert;
  für das gesperrte Signal entstehen keine automatischen Wiederholungsmessungen.
- **Gültige Modbus-Ablehnung 2 oder 3:** Der betroffene Registerblock wird mit
  `modbus_exception_2` beziehungsweise `_3` ausgesetzt; andere Blöcke laufen weiter.
  Das umfasst nicht allgemeine Geräte-, Busy- oder Gatewayfehler.

Neustart, normale Pause/Fortsetzung und CSV-Speichern heben Signalsperren nicht
auf. Zur bewussten Freigabe zuerst die Ursache prüfen und die Erfassung pausieren;
`POST /api/collector/acknowledge-and-start` hebt die Sperren ausdrücklich auf
und startet die Erfassung. Das ist eine erneute Freigabe aller gesperrten Werte,
keine Hintergrundwiederholung. Anfragebudget und Historie bleiben erhalten.
Die Oberfläche besitzt bisher keinen separaten Einzelwert-Freigabeknopf.
Sind alle ausgewählten Signale gesperrt, wartet der Sammler ohne Busy-Loop.
Fehlerhafte Kernsignale zählen nicht als erfolgreiche Erholungszyklen.

Globale Transport-/Protokollfehler erhalten ebenfalls eine sichere Fehleranzeige
am betroffenen Wert, soweit Speicherung möglich ist. Hostnamen, private Pfade
und rohe Betriebssystemfehler werden nicht als Kacheltexte veröffentlicht.

### Änderungen der Aufzeichnungsauswahl

CSV-Vorschau und Speichern erzeugen selbst keine Modbus-Anfrage und verändern
weder Pause/Fehlerstopp noch das Wiederaufnahmebudget. Der Sammler übernimmt die
gespeicherte Auswahl vor dem nächsten Kerndurchlauf als festen Zyklus-Snapshot;
ein laufender Zyklus einschließlich Retry wird nicht dazwischen umkonfiguriert.
Gespeicherte und aktive Revision/Auswahl sind über `/api/logging-config` sichtbar.
Bei Pause oder hartem Stopp kann eine neue Revision bis zum nächsten bewussten
Start ausstehen. Bei Prozessstart wird die gespeicherte Auswahl geladen; der
gespeicherte Fehlerzustand und die konservative Retry-Wartezeit bleiben wirksam.

Abgewählte Blöcke entfallen aus dem normalen Plan. Bei einem teilweise
ausgewählten Zweierblock werden beide Wörter unverändert validiert, aber nur
ausgewählte Signale gespeichert. Bereits geplante begrenzte Wiederaufnahmen
bleiben am selben bestätigten Block, auch wenn dessen Signale inzwischen
abgewählt wurden; unter der neuen Auswahl entstehen dafür keine Beobachtungen.
Eine vollständig leere Auswahl wartet ohne normale Reads; kein Busy-Loop.

Eine Auswahländerung setzt keinen Versuchszähler zurück. Drei vollständige
erfolgreiche **Kernzyklen aller drei Blöcke** bleiben Voraussetzung für den
automatischen Budgetreset. Mit einem Teilprofil bleibt das verbrauchte Budget
daher konservativ bestehen. Bestehende Minutenhistorie bleibt bei jeder
Konfigurationsänderung unverändert.

### V2-Zusatzregister

Kernblöcke behalten mindestens 60 s Abstand; die Zusatzblöcke mindestens 300 s,
jeweils ab Abschluss der vorherigen Verarbeitung. Noch nicht fällige Zusätze
werden übersprungen, damit kein 300-s-Warten die Kernwerte verdrängt. Bei
Prozessneustart werden gespeicherte Abschlusszeiten berücksichtigt; die
Wiederaufnahmegrenzen und Anfragezähler bleiben erhalten.

Nur die fünf Kernregister sind live bestätigt. Auf Betreiberwunsch wählt ein
CSV-Upload interpretierbare Einträge mit passender Lesezuordnung im Entwurf
vor, einschließlich der Protokollregister. Das ist noch keine aktive
Übernahme: Erst Speichern ändert die gespeicherte Auswahl. Die Oberfläche
unterscheidet Livebestätigung, statische Semantik und Herstellerrohwerte.
Neun Protokollregister leeren bereits beim Lesen aufgesammelte Ausgangsbits
(Read-to-clear). Sie sind deshalb zusätzlich unmittelbar an der Auswahl
gekennzeichnet; Wiederholungen oder andere Leser können Informationen verlieren.

Für Zusatzblöcke gibt es nach einem Transportfehler oder ungewissem Ausgang
keinen automatischen Folgeversuch. Reine Verbindungsfehler führen zu
`stopped_transport`, ungültige/teilweise Protokollantworten weiterhin zu
`stopped_protocol`. Auch ein Neustart darf eine ungewisse Zusatzanfrage nicht
erneut ausführen. Die begrenzte automatische Wiederaufnahme bleibt den
bestätigten Kernblöcken vorbehalten.

## Reine Verbindungsfehler

TCP-Verbindungsfehler oder Timeout ohne empfangene Antwortbytes dürfen in
`reconnect_wait` wechseln. Nach initialem Fehler höchstens fünf Wiederaufnahmeversuche,
mit Wartezeiten **1, 2, 5, 10, 15 Minuten nach dem jeweiligen Fehler**.
Keine Hintergrundbibliotheks-Retries und keine zusätzliche versteckte Retry-Ebene.
Jeder Versuch zählt bereits vor dem Netzwerkzugriff persistent gegen das Budget.
Nach einem Crash darf er nicht nochmals kostenlos erfolgen.

Versuch mit einem bereits bestätigten Kernblock am selben Ziel/Unit. Erfolg setzt
den normalen Zeitplan fort, setzt aber nicht sofort das Budget zurück. Erst drei
vollständige aufeinanderfolgende erfolgreiche Kernzyklen ohne neuen Fehler erlauben
Reset. Ein neuer Fehler davor nutzt das verbleibende Budget. Zusatzwerte dürfen
diese Kernprüfung nicht verdrängen. Nach Budgetende -> `stopped_transport`.

Budget, Zustand, Fehlergrund, nächster Versuch und erfolgreiche Erholungszyklen
über Neustarts sichern. Wartezeiten bei Neustart nicht verkürzen; monotone Zeit
im Prozess, konservativ definierte Wiederherstellung nach Uhrsprung/Neustart.
Wenn der Zustand nicht verlässlich lesbar ist: gestoppt, nicht automatisch neu anfangen.

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
Signale statt eines Stopps aller Werte. Strukturell falsche Wortanzahl oder
ungültige Registerworttypen bleiben globale Datenfehler. Rohworte und sichere
Fehlerdetails werden gespeichert, soweit die Datenbank funktioniert.
DB voll/nicht beschreibbar/Migrationsfehler -> Speicherstopp, keine weiteren Reads.

## Offline-Prüfungen

Die synthetischen Tests prüfen Retry-Abstand und denselben Block, Systemuhrsprung
ohne verkürzte monotone Wartezeit, genau fünf Wiederaufnahmeversuche, Protokoll-/
Teilantwortstopp ohne Folge-Read, Crash-Recovery, drei vollständige gute Zyklen,
Zielwechsel und pausierten Neustart. Weitere Störungsprüfungen bleiben für den Ausbau:
Flattern, DB-Ausfall, konkurrierender Sammler und Stop während wartender Anfrage.
