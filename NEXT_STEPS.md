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

## Domainaktionen hinter einem Reverse-Proxy

Die Originprüfung unterstützt jetzt die optionale private Deploymentvariable
`PUBLIC_ORIGIN` zusätzlich zum direkten Zugriff. Compose-Dateien und
Unraid-Template reichen sie weiter; kein CORS-Wildcard und keine pauschale
Proxy-Headerfreigabe. Konfiguration und sichere App-Prüfung:
[Unraid-Anleitung](docs/UNRAID.md#domain-und-https-reverse-proxy).
Offline reproduziert und mit laufender Loopback-API geprüft; die reale
Domain-/Unraid-Konfiguration wurde nicht verändert oder geprüft.
Vor Nutzung ein Image mit dieser Korrektur bauen/veröffentlichen, dann den
privaten tatsächlichen Browser-Origin setzen und den Container unter Erhalt
von Datenvolume und Erfassungseinstellungen neu erstellen.
Keine Geräteanfrage für die Proxyprüfung nötig; Ergebnisse im
[Ergebnisbericht](reports/RESULTS.md#15102026--domainaktionen-hinter-einem-reverse-proxy).

## Register-Prüfwerkzeug: Abschluss von Epic #29

Die Pakete #30–#39 sind zusammengeführt. Die
[Abschlussmatrix](reports/RESULTS.md#15102026--issue-29-epicabschluss)
ordnet Anforderungen, PRs und vorhandene Laufzeitbelege zu.
Kein weiteres Implementierungspaket aus #29 offen; Container-/Unraid-Nachweis,
Langzeitbetrieb und Stellweg/autonomer Rückfall (#18) sind dadurch nicht erfüllt.

Die kanonische Ressource liegt ausschließlich unter
[`backend/resources/register_catalog.json`](backend/resources/register_catalog.json).
`backend.catalog.load_catalog()` liefert einen validierten, unveränderlichen
Snapshot mit Dateibytes-Hash; `build_read_blocks()` löst nur Katalog-IDs in
1–3 enge Blöcke auf. 194 Rohregister bleiben uninterpretierte Diagnosekandidaten,
START/SOLL getrennte Steuerkandidaten ohne Leseblock oder Schreibfähigkeit.
Kein neues Polling und keine Geräteabfrage durch Import, Laden oder Auswahl.

Paket #31 ergänzt Schema 2, Diagnosejournal und transaktionale Reservierungen
ohne Geräte-I/O. Aktive/unquittierte Fehlerläufe sperren Planung und Ausführung;
eine Quittierung reaktiviert niemals eine alte ID. Restore übernimmt Budget,
Antworten, Bewertungen und Steuerrevisionen in ein neues Offline-Ziel und
unterbricht dort aktive Diagnosen. [Speichervertrag](docs/DATENMODELL.md#diagnosejournal-issue-31).

Paket #32 ergänzt den gemeinsamen privaten FC03-Pfad, katalogvalidierte
Einzelreads und den expliziten synthetischen Simulator-Katalogmodus. Standard-
Kernreads bleiben katalogunabhängig; keine automatische Folgeanfrage.
Paket #33 ergänzt `ReadCheckRunner`, `DeviceLock` und `DIAGNOSTICS_SOURCE`
(Standard `device`; `simulator` nur exakt mit Loopback `127.0.0.1`). Start stoppt
den sauberen Collector einschließlich Join, übernimmt denselben `collector.lock`
und sendet noch keine Anfrage. Jede manuelle Anfrage braucht eine dauerhafte
Reservierung; 60 s vor dem ersten Read und ab abgeschlossener Speicherung,
600 s Gesamtfrist, kein Retry. Diagnosefehler sperren auch alle Kernstartpfade.
Der frühere ungesperrte Direktleser ist entfernt.

Paket #35 erzeugt den Runner in der Lifespan und führt zuerst
`runner.recover_interrupted()` unter gemeinsamer OS-Sperre aus, erst danach
einen möglichen Collectorstart. Fremder Gerätebesitz/Recoveryfehler sperrt
Geräteaktionen, nicht lesende APIs; fremder Zustand bleibt unverändert.
Sammleraktionen teilen `runner.mode_lock`; Shutdown beendet zuerst
`runner.close()`, danach den eigenen Collector. Kein automatischer Neustart
nach Diagnoseende oder Quittierung. HTTP-Start verlangt zusätzlich die
ausdrückliche Betreiberangabe `{other_readers_stopped: true}`. Die App erkennt
keine Leser auf fremden Volumes oder anderen Geräten.

Paket #34 ergänzt formale Steuerplanbewertung und unveränderliche Revisionen
über `save_control_plan`/`get_control_plan`/`list_control_plans`. Gemeinsames
Dokument enthält Entwurf, Quellenstatus, Bewertung und `execution_enabled:false`.
Die Liste liefert ausschließlich neueste Revisionen; veraltete Updates werfen
`RevisionConflict` mit Code `revision_conflict`. API-/Lifespan-Anbindung ist
mit #35 umgesetzt; die Bedienung im bestehenden Dashboard ist mit #36 umgesetzt.
Details: [Steuerplanvertrag](docs/DATENMODELL.md#steuerentwürfe-und-revisionen-issue-34).
Private Speicherdicts werden nicht als API ausgegeben; explizite Projektionen
erhalten Quelle/Rohbelege, aber keine Ziele/Pfade/Fingerprintwerte.
Wheel-Laufzeitnachweis außerhalb des Checkouts und gebaute StaticFiles-UI mit #39
bestanden: 199 Einträge, identischer Ressourcenhash, hostlose Planblockade.
Offline-Nachweise: [Ergebnisse](reports/RESULTS.md); keine zusätzlichen Live-Belege.

Für weitere Arbeit: verbindliche OpenAPI-Modelle in `backend/diagnostics_api.py`,
die Oberfläche `frontend/src/Diagnostics.tsx` mit `ReadRuns.tsx` und
`ControlPlans.tsx` sowie den [HTTP-Vertrag](docs/DATENMODELL.md#diagnose-http-api-issue-35)
verwenden.
Inventar: `entries`, getrennte `control_candidates`, `blockade`;
je Eintrag `latest_diagnostic` mit `completed_at`, `source`, `target_changed`.
Laufstatus: `plan`, `requests_reserved`, `next_step_index`,
`wait_remaining_seconds`, `duration_remaining_seconds`, `requests`.
HTTP 409 `read_not_due` darf weder warten noch automatisch erneut anfragen.
Jede Antwort muss ausdrücklich bewertet werden; Freitexte und Exporte bleiben
privat. LAN/Tailscale und CSRF sind keine Authentisierung oder Schreibfreigabe.

Paket #36 bietet 50er-Katalogseiten, drei Suchformen, Belegfilter, Details und
getrennte START-/SOLL-Kandidaten. `api.ts` und `format.ts` sind die einzigen
gemeinsamen Fetch-/Anzeigehelfer; `ApiError.message` bleibt `HTTP <Status>`.
Serverpläne, Leserbestätigung, manuelle Reads/Reviews, sicherer Stopp und
Ursachenquittierung sind angebunden, ohne automatischen Diagnose-POST oder
Diagnosepolling. Bereichswechsel erhält den gemounteten Zustand.
Alle Steuerplanfelder, Nullwerte, unveränderliche Blocker, Revisionen und
Konfliktübernahme sind bedienbar; Export lädt die aktuelle Serverrevision.
Der Vite-Proxy erhält mit `changeOrigin:false` den Browser-Hostheader, damit
der bestehende Same-Origin-Vertrag auch bei lokaler Entwicklung gilt.

Eigene Browserprüfung gegen echte Loopback-API/Katalogsimulator mit temporärem
DATA_DIR bestanden: drei manuelle Rohreads, reale 60-s-Schranken,
Pflichtbewertungen, Refresh/Downloads, Neustart/Recovery, Revisionenkonflikt,
Exception-Stopp und Desktop/390 px. Speicher-/Netzfehleranzeigen zusätzlich
mit synthetischen Browserantworten geprüft, nicht als echte DB-Ausfälle.
Details und Grenzen: [Ergebnisse](reports/RESULTS.md).
Die automatisierte Verbraucherabnahme #37 ist bestanden: 644 Tests der
vereinbarten Gesamtsuite und 63 zusätzliche Steuerplantests auf CPython 3.12.9;
Ruff und Frontendbuild erfolgreich. Jeder Matrixfall ist im Ergebnisbericht
konkreten Verhaltenstests zugeordnet. Neue Nachweise umfassen echte
Zweitprozessbesitzer, gegatete Reservierungs-/Antwort-/Collector-Speicherrennen,
Fehler am ersten/zweiten Versuch und echte Steuerrevisionen nach Restore.
Die Runner-Tests isolieren auch geerbte Deploymentvariablen.
Ein zusätzlicher realer Loopbacklauf mit drei manuellen Reads und echten
60,050-s-Wartezeiten endete `completed`, ohne neue Kernbeobachtungen.
Die reproduzierbare Screenshot-/Request-/Persistenzabnahme #38 belegt zusätzlich
den tatsächlich bedienten Vite-Browser bei Desktopbreite und 390 px,
exakt drei bewusste Rohreads mit mindestens 60 s Abstand, echte JSON-Downloads
mit SQLite-Abgleich, unveränderliche Steuerrevisionen/Revisionskonflikt sowie
Neustartpersistenz und einen separaten harten Exception-Stopp ohne Retry.
Bereinigte Screenshots und genaue Messwerte:
[Abnahmebericht #38](reports/RESULTS.md#15102026--issue-38-reale-offline-browserabnahme).
Keine Produktionsänderung erforderlich. Paketabnahme #39 bestanden:
Wheel in frischer CPython-3.12.9-Umgebung außerhalb des Checkouts importiert;
gebaute Oberfläche über den bestehenden StaticFiles-Pfad tatsächlich bedient.
Containerlauf lokal ungeprüft: Docker nicht verfügbar.
CLI vorhanden, Linux-Engine nicht erreichbar; kein Containerbuild oder -lauf.
[Konkrete Artefakt-/Browserbelege](reports/RESULTS.md#15102026--issue-39-wheel-und-gebaute-laufzeitoberfläche).
Offen bleiben Linux-/Unraid-Deployment und Langzeitbetrieb. Vor späterer
Live-Diagnose aktuelle private Konfiguration und Quellen prüfen, andere Leser
anhalten und einen eigenen endlichen Aliasplan mit genau begründeten Blöcken,
Budget, Intervall, Laufzeit und Stopbedingungen dokumentieren; keinen
pauschalen 199-Register-Liveplan aus der Offline-Abnahme ableiten.
`npm audit` meldet eine bestehende hohe Vite-Sicherheitslücke; keine automatische
Lockfileänderung im Abnahmeauftrag. Devserver ausschließlich auf Loopback betreiben;
den Abhängigkeitsbefund vor nicht vertrauenswürdiger Bereitstellung beheben.
Windows-Sperrnachweise ersetzen keinen Linux-/Unraid-Nachweis.
Kein Deployment, Live-Test oder Heizungs-Schreibauftrag aus dieser Abnahme ableiten.


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
`vX.Y.Z` veröffentlichen erst nach Offline-Prüfungen. Der Tag `v0.1.0`
existiert bereits; eine Veröffentlichung von 0.2.1 ist noch nicht belegt.
MIT ist für eigenen App-Code festgelegt. Branch-/Tag-Schutz und
GHCR-Sichtbarkeit bleiben bei der Veröffentlichung zu beachten.
Details: [Unraid-/Release-Strategie](docs/UNRAID.md#github-image-build-und-veröffentlichungsgrenze).

Für Version 0.2.1 ist `compose.unraid.yaml` auf
`ghcr.io/lum1nat0r/sommerauer-monitor:0.2.1` festgelegt, ohne lokalen Build.
Git-Tag dafür: `v0.2.1`, nicht `0.2.1`. Nach erfolgreichem Release-Workflow
GHCR-Paket öffentlich schalten und anonymen Pull prüfen; erst danach auf Unraid
mit privater `.env` und vorbereitetem Datenpfad starten
([Anleitung](docs/UNRAID.md#unraid-veröffentlichtes-image-verwenden)).
Die lokale Build-Datei `compose.yaml` bleibt getrennt. Dieser Arbeitsstand
erstellt keinen Tag und aktiviert weder Deployment noch Erfassung.
