# Erfassung, Fehler und Wiederaufnahme

Entwurfswerte aus dem besprochenen Plan, vor Live-Betrieb offline prüfen.
Ein Client, eine Anfrage; Kernblöcke jeweils mindestens 60 s auseinander,
mindestens 10 s nach Ende der vorherigen Anfrage. Maximal zwei Register, 3 s
Gesamtdeadline einschließlich Verbindungsaufbau/Antwort. Kein Nachholen in Bursts.
Zusatzgruppen zunächst 300 s, genaue Reihenfolge nach Prüfung/Kapazitätsrechnung.

## Zustände und Übergänge

| Zustand | Verhalten / erlaubter Übergang |
|---|---|
| `unconfigured` | Kein Ziel/Profil, keine Verbindung; konfigurieren -> `paused` |
| `paused` | Nutzerpause oder Erstinstallation; expliziter App-Start -> `running` |
| `running` | Geplante Reads; erfolgreicher Zyklus bleibt running |
| `reconnect_wait` | Normale Folge pausiert; genau ein Versuch nach Ablauf der Wartezeit |
| `stopped_transport` | Budget ausgeschöpft; Ursache prüfen, manuell fortsetzen |
| `stopped_protocol` | Protokollfehler/Exception; keine automatischen Reads |
| `stopped_data` | Ungültige/widersprüchliche Daten; keine automatischen Reads |
| `stopped_storage` | Speicherung/Zustand nicht sicher möglich; keine neuen Reads |

Nutzer-Stopp oder Anlagenauffälligkeit überstimmt alles. Fehlerstopp kann nur nach
Klärung der Ursache bewusst quittiert werden; ein Neustart ist keine Quittierung.
Web-API/Diagramme bleiben unabhängig vom Messzustand erreichbar.

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

Modbus-Exception, falsche Unit/Funktion/Transaktion, ungültige MBAP-Länge oder
Protokoll-ID, falsche Byteanzahl, vollständige ungültige Antwort oder nach Deadline
unvollständige Antwort -> Protokollstopp. Normale TCP-Fragmentierung innerhalb der
Deadline ist kein Fehler. Eine abgebrochene Verbindung nach Teilantwort zählt
ebenfalls als Protokollfehler, nicht als reine Nichterreichbarkeit.

110 bei Kern-Temperaturkanälen, ungültiger Wertebereich, Restminuten >=1440 oder
widersprüchlicher Zähler -> Datenstopp. Keine Null einsetzen, nicht korrigieren,
kein automatischer Folgeversuch. Rohworte und Fehler speichern, soweit Speicher
funktioniert. DB voll/nicht beschreibbar/Migrationsfehler -> Speicherstopp.

## Unverzichtbare Offline-Prüfungen

Kein Timeout-Retry nach Teilantwort; korrekt zusammengesetzte fragmentierte Antwort;
Wartezeiten/Versuchsanzahl; Flattern der Verbindung; Crash vor/nach Anfrage;
Neustart in Wartezustand und hartem Stopp; drei gute Zyklen; Scheduler-Verzögerung;
Uhrsprung; DB-Ausfall; konkurrierender Sammler; Stop während wartender Anfrage.
