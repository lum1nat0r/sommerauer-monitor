# Nächste Schritte

Stand 15.10.2026: Projektgrundlage, `core`-Profil/Decoder, strikter FC03-Lesetransport,
Loopback-Simulator, SQLite-Speicherung, zentraler Sammler, persistente Fehlerzustände,
lesende API, Dashboard und Offline-Ende-zu-Ende-Abnahme (#12) umgesetzt.
Kernregister-Abnahme #13 mit endlichen Live-Läufen und Betreiber-Displayabgleich
bestanden; Timing- und gespeicherten API-Endzustandsfehler korrigiert.
Unraid-Deployment und Langzeitbetrieb bleiben ungeprüft und nicht aktiviert.

Zuerst [AGENTS](AGENTS.md), [Plan](docs/PLAN.md), [Entscheidungen](docs/ENTSCHEIDUNGEN.md),
[Registerwissen](docs/MODBUS.md) und [Fehlerverhalten](docs/FEHLERVERHALTEN.md) lesen.

Zieladresse und Unraid-Poolpfad sind private Deployment-Konfiguration. Für spätere
Live-Arbeit aktuelle freigegebene Werte aus Betreiberkontext verwenden, nicht erraten.
Bei fehlendem Gerätezugang die Offline-Arbeit fortsetzen und Live-Nachweise offen lassen.

## Register-Prüfwerkzeug: Übergabe nach #30

Die kanonische Ressource liegt ausschließlich unter
[`backend/resources/register_catalog.json`](backend/resources/register_catalog.json).
`backend.catalog.load_catalog()` liefert einen validierten, unveränderlichen
Snapshot mit Dateibytes-Hash; `build_read_blocks()` löst nur Katalog-IDs in
1–3 enge Blöcke auf. 194 Rohregister bleiben uninterpretierte Diagnosekandidaten,
START/SOLL getrennte Steuerkandidaten ohne Leseblock oder Schreibfähigkeit.
Kein neues Polling und keine Geräteabfrage durch Import, Laden oder Auswahl.

Nächstes Paket des Epics #29 ist #31: Diagnosejournal, dauerhafte Reservierungen
und Migration/Restore. Danach #32 Transport, dann #33 Runner; noch keine
Diagnoserouten oder UI integrieren. Wheel-Laufzeitnachweis außerhalb des Checkouts
bleibt #39 vorbehalten. Offline-Nachweise zu #30: [Ergebnisse](reports/RESULTS.md).


## Begrenzter Full-Stack-Test am Gerät

Durchgeführt am 15.10.2026: Ziel aus privater `.env`; Port 502, Unit 255,
Modbus TCP/FC03, Profil `core`. Der App-Sammler las einmal jeden bestätigten
Block 4102/1, 28688/2 und 36864/2; Prozesslimit 3, feste 3-s-Gesamtdeadline,
keine Wiederaufnahme im endlichen Lauf. Alle drei Antworten waren erfolgreich,
SQLite speicherte vier Kernsignal-Beobachtungen mit Qualität `ok`; Collector
beendete sich bei 3/3 Anfragen. API/Datenbank waren gesund. Das Dashboard
zeigte alle vier Werte; nach Überschreiten der Frischegrenze markierte es sie
als veraltet. `completed` wird explizit als „Erfassung abgeschlossen“
dargestellt. Keine zusätzlichen Anfragen beim Neustart zur UI-Prüfung.

Der Lauf war einmalig und belegt weder Displayübereinstimmung noch Dauerbetrieb
oder Hersteller-Verträglichkeit. Keine Zusatzregister oder Schreibbefehle.
Das Anfragebudget war ein Prozess-Override; `.env` blieb unverändert. Der
App-Prozess und der Dashboard-Devserver wurden nach der Prüfung beendet.

## Abnahmeplan #13: kurzer endlicher Loggerlauf

Vor Beginn am 15.10.2026 festgelegt; Betreiber bestätigt alle anderen Leser
beendet, Displayabgleich möglich, noch keine Unraid-Installation.
Zielalias `Anlage-aktuell`: ausschließlich `MODBUS_HOST` aus privater `.env`;
konkretes Ziel und Laufplan privat unter `data/issue13-abnahme/short/`.
Stand: Commit `64521b5`, App 0.1.0, Profil/Decoder `core`/1.

- Modbus TCP, Port 502, FC03, Unit 255; nur 4102/1, 28688/2, 36864/2.
- Zweck: wiederholte Kernzyklen, Zählerplausibilität, Zeitabstände,
  dauerhafte Speicherung und zeitnaher Displayabgleich.
- Genau ein synchroner Client/eine Anfrage; je Block mindestens 60 s;
  3 s Transport-Gesamtdeadline; kein separates 10-s-Intervall zwischen Blöcken.
- Höchstens 300 s, höchstens 15 Anfragen (5 Kernzyklen), null Wiederaufnahmen.
  Anfragebudget persistent; separater Laufzeittimer verhindert weitere Reads
  nach der Höchstdauer. Eine laufende Anfrage darf ihre Deadline beenden.
- Sofortiger Stopp bei Transport-, Protokoll-, Daten- oder Speicherfehler,
  Betreiber-Stopp oder Anlagenauffälligkeit; keine automatische Quittierung.
  Jede Antwort wird vom Sammler unmittelbar validiert und gespeichert.
- Privater Nachweis: SQLite, monotone Transportzeiten und Rohworte.
  Öffentliche Auswertung nur Anfragezahlen, Timing, Qualität und Stopgrund.
- Erst nach Auswertung dieses Laufs einen eigenen längeren endlichen Plan
  festlegen; kein automatischer Übergang in längeren oder dauerhaften Betrieb.

### Auswertung und neuer Kurzlauf nach Timingkorrektur

Der erste Kurzlauf endete nach 240,687 s regulär bei 15/15 Anfragen;
20 Beobachtungen `ok`, keine Wiederaufnahme, SQLite-Integrität `ok`.
Der Betreiber bestätigte alle vier Displaywerte. Die Timingabnahme bestand
jedoch nicht: gemessene Abstände am Transportaufruf 59,984–60,047 s.
Die ursprüngliche Windows-Uhr hat nur 15,625 ms Auflösung; diese Messung
ist kein hochauflösender Paketmitschnitt. Ein Offline-Regressionsfall
belegte unabhängig davon das tatsächliche Problem: variable Reservierungsdauer
konnte den Abstand von Transportaufrufen auf 59,5 s verkürzen.

Vor einem längeren Lauf wird daher ein **neuer** Kurzlauf unter
`data/issue13-abnahme/short-fixed/` ausgeführt, ohne den alten Lauf zu
überschreiben oder dessen Budget zu quittieren. Ziel, Funktion, Unit, Blöcke,
Zweck, Stopbedingungen, 300-s-Limit und separates 15-Anfragen-Budget wie oben.
Codebasis `64521b5` plus lokale Timingkorrektur: hochauflösende monotone
Uhr; neuer 60-s-Abstand konservativ ab Abschluss des vorherigen Blocks.
Vorher wurde das Verhalten offline mit Loopback-Simulator geprüft.
Erst bei bestandener Auswertung darf der längere Plan folgen.

## Abnahmeplan #13: längerer endlicher Loggerlauf

Erst nach Auswertung des korrigierten Kurzlaufs festgelegt: 15/15 erfolgreich,
20 Beobachtungen `ok`, SQLite-Integrität `ok`, 240,661 s, je gleicher Block
60,040320–60,291638 s; Antwortdauern 11,609–268,209 ms.
Endzustand `completed`, Stopgrund Anfragebudget, keine Wiederaufnahme.
Wiederherstellung des gespeicherten Endzustands erzeugte keine weitere Anfrage.

- Zielalias weiterhin `Anlage-aktuell`, aktuelles Ziel ausschließlich aus privater
  `.env`; konkreter Plan unter `data/issue13-abnahme/long/`.
- App 0.1.0, Basis `64521b5` plus dieselbe offline und live geprüfte
  Timingkorrektur; Profil/Decoder `core`/1.
- Modbus TCP, Port 502, FC03, Unit 255; nur 4102/1, 28688/2, 36864/2.
- Zweck: 30 wiederholte Kernzyklen, Timingverteilung, Zählerplausibilität
  und lokale Speicherung vor Erstellung des späteren Betriebsplans.
- Ein synchroner Client/eine Anfrage; mindestens 60 s ab Abschluss der
  vorherigen Verarbeitung desselben Blocks, 3 s Transport-Gesamtdeadline.
- Höchstens 1800 s, höchstens 90 Anfragen insgesamt, null Wiederaufnahmen;
  eigener Laufzeittimer. Laufende Anfrage darf ihre Deadline beenden.
- Sofortiger Stopp bei Transport-, Protokoll-, Daten- oder Speicherfehler,
  Betreiber-Stopp oder Anlagenauffälligkeit. Keine Fehlerquittierung,
  keine Zusatzregister, keine Geräteänderungen, keine künstlichen Störungen.
- Rohworte/SQLite/monotone Transportzeiten bleiben privat. Danach tatsächliche
  Anfragezahl, Zeitabstände, Antwortdauer, Integrität und Stopgrund auswerten.
  Kein automatischer Übergang in Dauerbetrieb oder Unraid-Deployment.

Budgetübersicht der neuen Abnahme: erster Kurzlauf 15, korrigierter Kurzlauf 15,
längerer Lauf höchstens 90 Anfragen, zusammen höchstens 120. Der bereits
vorhandene Erstzyklus umfasste zusätzlich 3 Anfragen. Kein Parallelbetrieb.

## Abnahmeergebnis und nächster Betriebsschritt

Der längere Lauf bestand: 90/90 erfolgreiche Anfragen in 1741,599 s,
120 Beobachtungen `ok`, SQLite-Integrität `ok`; gleiche Blöcke
60,024734–60,124170 s auseinander, Antwortdauer 11,346–97,432 ms.
Stopgrund Anfragebudget, `completed`, keine Wiederaufnahme. Einschließlich
beider Kurzläufe genau 120 neue Anfragen; kein weiterer Gerätezugriff für
API-/CSV-/Dashboardprüfung oder Sicherung/Wiederherstellung.

Der Betreiber bestätigte alle vier Displaywerte und meldete keine neuen
Anlagenauffälligkeiten während der Leseläufe. Das ersetzt keine unabhängige
Anlagenprüfung. Rohbelege und Minutenmessungen bleiben privat erhalten.
Auswertung und Kriterien: [Ergebnisse](reports/RESULTS.md).

Der [Dauerbetriebsplan](docs/INBETRIEBNAHME.md#betriebsplan-nach-der-begrenzten-abnahme)
wurde erst nach Auswertung erstellt. Er ist nicht aktiviert. Der Betreiber
übernimmt später das Deployment; Unraid-Mount-/Neustart-/Restoreprüfung bleibt
offen. Keine Veröffentlichung oder Unraid-Abnahme aus Issue #13 ableiten.
App-/Dashboard-Prüfprozesse wurden beendet; `.env` blieb unverändert.

## Weitere Releasepunkte

MIT für eigenen App-Code ist vom Betreiber bestätigt; Lizenzdatei `LICENSE` vorhanden.
Zugriffsschutz bei den zugeordneten Issues festlegen. Foundation-Laufzeiten und -Bibliotheken sind festgepinnt; MQTT/
Solarprognose/START-SOLL sind spätere Arbeitspakete. Keine Aktivierung von
Heizungsänderungen aus dieser Übergabe ableiten.

Image-Workflow: Pull Requests bauen `linux/amd64` ohne Push; Release-Tags
`vX.Y.Z` veröffentlichen erst nach Offline-Prüfungen. Es gibt noch keinen Tag
und kein veröffentlichtes GHCR-Image. MIT ist für eigenen App-Code festgelegt. Vor dem ersten
Release die offenen Nachweise aus #13 und die Releasefreigabe aus #14 auswerten,
Branch-/Tag-Schutz einrichten sowie die GHCR-Sichtbarkeit bewusst festlegen.
Details: [Unraid-/Release-Strategie](docs/UNRAID.md#github-image-build-und-veröffentlichungsgrenze).

Für das erste Release ist `compose.unraid.yaml` auf
`ghcr.io/lum1nat0r/sommerauer-monitor:0.1.0` festgelegt, ohne lokalen Build.
Git-Tag dafür: `v0.1.0`, nicht `0.1.0`. Nach erfolgreichem Release-Workflow
GHCR-Paket öffentlich schalten und anonymen Pull prüfen; erst danach auf Unraid
mit privater `.env` und vorbereitetem Datenpfad starten
([Anleitung](docs/UNRAID.md#unraid-veröffentlichtes-image-verwenden)).
Die lokale Build-Datei `compose.yaml` bleibt getrennt. Dieser Arbeitsstand
erstellt keinen Tag und aktiviert weder Deployment noch Erfassung.
