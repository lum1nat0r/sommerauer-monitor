# Nächste Schritte

Stand 15.10.2026: Projektgrundlage, `core`-Profil/Decoder, strikter FC03-Lesetransport,
Loopback-Simulator, SQLite-Speicherung, zentraler Sammler, persistente Fehlerzustände,
lesende API, Dashboard und Offline-Ende-zu-Ende-Abnahme (#12) umgesetzt. Offen:
Unraid-Deployment und Geräteprüfung; keine Live-Gerätezugriffe für Issue #12.

Zuerst [AGENTS](AGENTS.md), [Plan](docs/PLAN.md), [Entscheidungen](docs/ENTSCHEIDUNGEN.md),
[Registerwissen](docs/MODBUS.md) und [Fehlerverhalten](docs/FEHLERVERHALTEN.md) lesen.

Zieladresse und Unraid-Poolpfad sind private Deployment-Konfiguration. Für spätere
Live-Arbeit aktuelle freigegebene Werte aus Betreiberkontext verwenden, nicht erraten.
Bei fehlendem Gerätezugang die Offline-Arbeit fortsetzen und Live-Nachweise offen lassen.

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

Lizenz (MIT weiterhin nur Vorschlag) und Zugriffsschutz bei den zugeordneten Issues
festlegen. Foundation-Laufzeiten und -Bibliotheken sind festgepinnt; MQTT/
Solarprognose/START-SOLL sind spätere Arbeitspakete. Keine Aktivierung von
Heizungsänderungen aus dieser Übergabe ableiten.

Image-Workflow: Pull Requests bauen `linux/amd64` ohne Push; Release-Tags
`vX.Y.Z` veröffentlichen erst nach Offline-Prüfungen. Es gibt noch keinen Tag,
keine erteilte Lizenz und kein veröffentlichtes GHCR-Image. Vor dem ersten
Release die offenen Nachweise aus #13 und die Releasefreigabe aus #14 auswerten,
Branch-/Tag-Schutz einrichten sowie die GHCR-Sichtbarkeit bewusst festlegen.
Details: [Unraid-/Release-Strategie](docs/UNRAID.md#github-image-build-und-veröffentlichungsgrenze).
