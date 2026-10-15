# Arbeitsregeln für Sommerauer Monitor

## Auftrag und Einstieg

- Auf Deutsch antworten und dokumentieren; `python` verwenden, nicht `py -3`.
- Zuerst README, NEXT_STEPS, docs/PLAN.md, docs/ENTSCHEIDUNGEN.md,
  docs/MODBUS.md, docs/FEHLERVERHALTEN.md und das zu bearbeitende Issue lesen.
- Dieses Repository enthält zunächst eine Planungsübergabe. Die Issues beschreiben
  noch zu implementierende Funktionen, keine bereits verfügbaren Fähigkeiten.
- Bei Beauftragung eines Issues notwendige Entwicklungsarbeit selbst erledigen,
  sinnvoll prüfen und Ergebnis/Restpunkte dokumentieren. Abhängigkeiten beachten.
  Spätere Roadmap-Issues nicht ungefragt als Teil von Version 1 umsetzen.
- Benutzerangaben, tatsächliche Geräteantworten, statische Quellenbefunde,
  synthetische Tests und Hypothesen ausdrücklich unterscheiden.
- Keine Messwerte, Einheiten, Adressen oder Gerätefunktionen erfinden.

## Erlaubte Entwicklung und Gerätegrenze

Der Betreiber erlaubt selbstständige Projektentwicklung, Dokumentation,
Offline-Simulation und begründete FC03-/FC04-Lesearbeit an seiner Anlage.
Das konkrete Leseregisterprofil für diese App verwendet FC03.
Die tatsächlich freigegebene Zieladresse kommt ausschließlich aus der privaten
Projekt-/Deployment-Konfiguration; keine Ziele erraten oder historische Adressen verwenden.
Diese Betreiberfreigabe gilt nicht pauschal für fremde Anlagen oder fremde Netze.

**Tatsächliche verändernde Befehle an die Heizung erfordern eine ausdrückliche
Erlaubnis des Betreibers für die konkrete Änderung bzw. einen begrenzten Plan
einschließlich Rückstellwerten.** Das gilt auch für kombinierte Lese-/Schreibfunktionen,
Start/Stop, Importe, Firmware, Reset/Restart und andere Geräteschnittstellen.
Vor einer solchen Anfrage lokale Vorbereitung abschließen. Bereits passende
Erlaubnis nicht erneut abfragen. Hardwareeingriffe sind keine Offline-Entwicklung.

Version 1 enthält keinen Schreibadapter, keinen Schreibendpunkt und keinen
allgemeinen Registereditor. Spätere Schreibentwürfe dürfen getrennt offline
vorbereitet werden; ein Issue oder eine Simulation ist keine Gerätefreigabe.
Echte Sensormesswerte bleiben unverändert. Später allenfalls START/SOLL ändern.

## Live-Lesearbeit

- Vorher Quellen/Ergebnisse prüfen und in NEXT_STEPS einen konkreten endlichen Plan
  mit Ziel aus privater Konfiguration, Funktion, Unit, Offsets, Anzahl, Zweck,
  Intervall, Laufzeit, maximaler Anfragezahl und Stopbedingungen dokumentieren.
  Private Zieladressen nur in privatem Laufplan, öffentlich über Alias referenzieren.
  Dies ist Arbeitsdokumentation, keine zusätzliche pauschale Zustimmungshürde.
- Standard: Unit 255, höchstens zwei Register, 3 Sekunden Gesamtdeadline,
  mindestens 10 Sekunden nach voriger Antwort/Fehler, ein Client/eine Anfrage.
- Einzeltest-Durchgang höchstens drei begründete Anfragen, Ergebnis jeweils
  sofort prüfen; keine Fehler-Retries. Bei Fehler/Stop/Auffälligkeit anhalten.
- Keine Port-/Subnetzscans, keine Unit-/Adresssuche, kein Fuzzing, keine Broadcasts,
  Diagnosen oder parallelen Clients. Ein Agent und eine App dürfen nicht parallel lesen.
- Wiederkehrende Tests zuerst offline, danach mit endlichem Anfragebudget.
  Dauerbetrieb erst nach gestufter, dokumentierter Inbetriebnahme.
- Nur der neue Monitoring-Dienst darf reine Verbindungsfehler begrenzt automatisch
  wiederaufnehmen: siehe docs/FEHLERVERHALTEN.md. Keine Wiederholung nach
  Protokoll-/Datenfehlern; Budgets und harte Stopps über Neustarts erhalten.
- Technisch erforderlichen Displayabgleich gezielt erfragen. Kein allgemeiner
  Beobachtungs-/Zustimmungsdialog vor jeder erlaubten Lesesitzung.
- Netzwerk-/Sandboxbeschränkungen sind keine Gerätefehler. Erforderliche gezielte
  Freigaben beachten; Schutzmechanismen nicht umgehen.
- Diese Grenzwerte sind Projektvorgaben, keine Hersteller-Verträglichkeitszusage.

## Daten, Tests und Übergabe

- Alle Minutenmessungen dauerhaft erhalten. Aggregate zusätzlich; Transportlogs
  dürfen separat rotieren. Datenlücken nicht mit erfundenen Messwerten füllen.
- Unbestätigte Register nicht automatisch aktivieren. Fünf bestätigte Register
  beweisen weder die übrigen 194 noch einen störungsfreien Dauerbetrieb.
- CI/Standardtests ausschließlich synthetisch/in-process oder Loopback. Kein
  CI-Zugriff auf die Anlage, keine automatische Live-Verifikation beim Start.
- Private Logs, Fotos, Exporte, rekonstruierter Herstellercode, Netzwerkdetails,
  Tokens und reale Konfiguration nicht committen oder in Issues posten.
- Fachliche Originalbelege liegen beim Betreiber. Fehlende Belege gezielt klären;
  das öffentliche Repo ersetzt sie nicht. Keine unabhängige Prüfung behaupten,
  wenn nur die hier dokumentierte Zusammenfassung gelesen wurde.

## GitHub-Änderungen für Issues

- Issue-Arbeit erfolgt auf einem eigenen Branch; Änderungen NIEMALS direkt auf `main` committen.
- Nach Implementierung und erfolgreicher Verifikation dürfen die Issue-Änderungen gestaged und committet werden. Commit-Nachricht kurz halten und Issue zuordnen.
- Den Issue-Branch zum konfigurierten Remote pushen und nach Abschluss der Verify-Sektion einen Pull Request erstellen.
- PR-Beschreibung enthält eine knappe Zusammenfassung der Änderungen und `Closes #<Issue-Nummer>` (oder gleichwertige GitHub-Schließsyntax mit Issue-Link), damit GitHub das Issue beim Merge automatisch schließt.
- PR nicht selbst mergen. Keine vorhandenen Commits ändern, Tags/Releases erstellen oder destruktive Git-Befehle verwenden, die Änderungen verwerfen.
- Vorhandene Nutzeränderungen bewahren; nur Issue-bezogene Änderungen stagen/committen.
- Issue/Kommentare nicht separat ändern; die PR-Schließreferenz ist die vorgesehene Verknüpfung.
- Nach einem Arbeitspaket Issue/PR mit Änderung, echten Prüfungen, Grenzen und
  nächsten Schritten aktualisieren. Neue Ergebnisse in reports/RESULTS.md ergänzen;
  Simulator und Live-Ergebnisse getrennt, öffentlich nur bereinigte Zusammenfassungen.
