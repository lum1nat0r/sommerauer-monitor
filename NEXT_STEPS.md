# Nächste Schritte

## Separates START/SOLL-Testwerkzeug (20.10.2026)

Auf Betreiberwunsch auf Branch `feature/start-soll-schreibtest` ein eigenständiges
CLI-Testwerkzeug samt eigenem Dockerfile vorbereitet: [Bedienung](docs/SCHREIBTEST.md).
Betreiber bestätigt START `9040` und SOLL `9020` und wünscht einen späteren
Gerätetest nach Deployment. Transportcode für genau diese FC03-/FC06-Einzelwörter,
privater Plan, persistentes Journal, endlicher Ablauf mit aktiver Rückstellung.
Keine Hardwarekommunikation ausgeführt und keine Änderung der Monitoring-App.

Den vom Betreiber bereitgestellten rekonstruierten Originalexport erneut statisch
geprüft: FC06 interpretiert Dezimaltext als Hexzahl. Nur 16–25, 32–41, 48–57,
64–73 und 80–89 °C innerhalb der Parametergrenzen sind damit darstellbar.
Auch Rückstellwerte prüfen; ein Ausgangswert von 60 °C sperrt den Versuch.
Vor echtem Test Übereinstimmung der installierten Version bestätigen und einen
konkreten endlichen Plan mit aktuellen Ausgangs-/Test-/Rückstellwerten erstellen.
Hier ist noch kein Live-Lauf geplant oder freigegeben; aktuelle Ausgangswerte
und Zielkonfiguration fehlen. Autonomer Rückfall bleibt ungeklärt.
Keinen automatischen Rückfall durch die Heizung behaupten:
der Client muss aktiv zurückschreiben; bei Host-/Netzausfall manuell am Touch prüfen.
Lokaler Docker-Zugriff ist durch Socketrechte gesperrt. Der separate Imagebuild
und Container-Smoke ohne Netzwerk sind inzwischen in
[CI erfolgreich](https://github.com/lum1nat0r/sommerauer-monitor/actions/runs/39466537764),
ebenso Python-Prüfungen und Frontend-Build. Unraid-Deployment bleibt ungeprüft.
Branch ist gepusht; PR-Anlage über die GitHub-Integration scheitert mit HTTP 403
(`Resource not accessible by integration`). #18 bleibt offen.

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

## Fortlaufendes Polling bei Verbindungsfehlern

Betreiberauftrag vom 19.10.2026 umgesetzt: kein Fünf-Versuche-Limit, keine
steigenden Retry-Pausen und kein Drei-Kernzyklen-Budgetreset mehr.
Ausgewählte Kernblöcke bleiben bei mindestens 60 s, normale Zusatzblöcke bei
mindestens 300 s; Verbindungsfehler verdrängen andere fällige Werte nicht.
Historie und sichtbare Fehlerbeobachtungen bleiben erhalten.

Beim Start eines aktivierten Sammlers mit dem neuen Build werden alte reine
Transportstopps automatisch fortgesetzt, wenn alter und neuer Lauf unbeschränkt
sind und kein Read-to-clear-Block betroffen ist. Nutzerpause, `completed`,
endliche Budgets, Signalsperren und harte Fehlerstopps bleiben erhalten.
Eine deaktivierte Instanz wird nicht automatisch aktiviert. Vor Upgrade
konsistent sichern; keine Datenbank löschen. Für Dauerbetrieb muss
`COLLECTOR_MAX_REQUESTS` leer bleiben; endliche Prüfläufe bleiben absichtlich begrenzt.

Prüfungen ausschließlich synthetisch/Loopback: 419 Python-Tests, 25 Node-Tests,
Build und Ruff erfolgreich. Echter FC03-Transport mit 21 aufeinanderfolgenden
Verbindungsfehlern und anschließender Erholung; virtuelle Schedulerzeit,
reguläre Blockintervalle und unveränderte Fehlerhistorie nachgewiesen.
Gebautes Dashboard mit isolierter API im Chromium-Browser geprüft:
kein Budgetbruch, Hinweis „ohne Versuchslimit“, nächster Abfragetermin sichtbar.
Details: [Ergebnisbericht](reports/RESULTS.md#19102026--fortlaufendes-polling-statt-fehlversuchslimit).

Noch nicht deployt oder an der Anlage geprüft. Private Konfiguration, laufende
Heizungs-App und Gerät blieben unverändert. Nach Bereitstellung des neuen Builds
die tatsächliche Instanz regulär neu starten; keine zusätzliche Live-Abfrage
aus dieser Offline-Verifikation ableiten.

## Dashboard und neuer Steuerungszustand: Anlagengrenze

Dashboardumbau und Leserweiterung `1001` sind lokal mit synthetischer App,
Loopback, vollständigen Verlauf-/CSV-Daten und Browser abgenommen.
330 Python- und 15 Node-Tests, Build und Ruff erfolgreich; Details und
Nachweisgrenzen im [Ergebnisbericht](reports/RESULTS.md).
Reale App, private Konfiguration, Aufzeichnungsauswahl und Gerätetabelle
blieben unangetastet.

Nachtrag: Sonne-/Mond-Iconbutton und instanzübergreifender JSON-Transfer der
gespeicherten Aufzeichnung sind offline umgesetzt. Beide Instanzen benötigen
einen passenden Build; Datei im Ziel als Entwurf prüfen und bewusst speichern.
Ohne brauchbaren `1001`-Status verwendet die Betriebsanzeige ausschließlich eine
ausgewählte aktuelle `1003`-Istregelgröße als klar bezeichneten indirekten Hinweis.
0 % ist kein Aus-Nachweis; keine automatischen neuen Lesekanäle oder Geräteeingriffe.
Prüfstand: 357 Python- und 23 Node-Tests, Build und Ruff erfolgreich.
Übertragungsablauf: [README](README.md#gespeicherte-aufzeichnung-auf-eine-andere-instanz-übertragen).

Der Betreiber bestätigt inzwischen die Installation der neuen Gerätetabelle
einschließlich `1001`/4097. Das ist ein Betreiberbericht, kein eigener Read-/Displaynachweis.
Vor einer neuen Statusabnahme andere Leser ausschließen. Bis dahin keine direkte Anlagenanfrage.
Vor einer späteren Lesesitzung einen privaten endlichen Laufplan mit tatsächlichem Ziel aus aktueller
Deploymentkonfiguration dokumentieren; öffentlich nur Alias `Anlage-aktuell`.
Vorgesehene Grenze: Port aus derselben Konfiguration, FC03, Unit 255,
Offset 4097, Anzahl 1, maximal eine Anfrage, 3-s-Gesamtdeadline,
keine Wiederholung und kein paralleler Client. Zweck ist der zeitnahe
Betreiber-Displayabgleich genau des beobachteten Software-Steuerungszustands.
Bei Fehler, „unsupported“, Auffälligkeit oder Betreiber-Stopp sofort Ende,
keine Folgeabfrage oder automatische Tabellenreparatur. Ein Erfolg beweist
weder andere Zustände noch Dauerbetrieb.

Eine nötige Mappingänderung ist nicht freigegeben; vorher gesonderte konkrete
Erlaubnis mit Sicherung und Rückstellplan einholen. Status nicht automatisch
in die reale Dauerauswahl aufnehmen, reale App nicht starten oder quittieren.
Semantik und lokale CSV-Aufnahme: [Modbus](docs/MODBUS.md#kessel-steuerungszustand-nur-lesend-und-ausdrücklich-auswählen).

### Vorbereitete Gerätetabelle mit Statuskanal

Historischer Ausgangspunkt: Betreiber bestätigte zunächst die fehlende `1001`-Zuordnung;
inzwischen meldet er die neue Tabelle installiert. Eigenständiger Geräteabgleich bleibt offen.
Auf Auftrag offline `Modbus_P190317R_V3_Status.csv` aus der vollständigen
bisherigen V1-Vorlage vorbereitet: aktuell 76 Zeilen, HK03–HK16 und sämtliche
NM/SP entfernt. Neu sind Betriebsstatus `1001`, Betriebsart `1000`,
Kessel-Soll `1007`, Puffer START `9040` und SOLL `9020` für Kanal 1.
Die vier zusätzlichen Parameter wurden anschließend ausdrücklich beauftragt.
Datei privat bereitgestellt; keine Übertragung oder Geräteabfrage.

Vor manuellem Geräteimport aktuell aktive Tabelle separat sichern und alle
Modbus-Leser pausieren. Der Tabellenimport ersetzt die bestehende Zuordnung,
statt nur eine Zeile anzuhängen. Rückweg ist die gesicherte bisherige Tabelle;
`.ls1`/`.ls2` sind dafür kein gezieltes Tabellenbackup. Bei abweichendem Menü,
Importfehler oder Auffälligkeit stoppen, keine Wiederholung.
Alle fünf neu zugeordneten Codes besitzen auch einen Schreibzweig: Die CSV
erzwingt keinen reinen Lesezugriff. Monitor bleibt FC03-lesend; fremde
Schreibclients ausschließen. Aufnahme in die Datei ist keine Schreibprüfung;
Kodierung, konkrete Stellwerte und Rückstellplan bleiben vor Nutzung zu klären.
Vor Wiederaufnahme die Monitor-Auswahl anpassen: entfernte NM/SP-Kanäle
explizit abwählen; der ergänzende CSV-Import entfernt keine alten Auswahlen.
Status erst nach bestätigtem Import und begrenztem Displayabgleich wie oben
weiter abnehmen. Keine automatische Aktivierung durch diese Vorbereitung.
Offlineprüfung der erweiterten Datei: 76 eindeutige Codes/Offsets, Filter
erhalten, ASCII ohne BOM mit 76 CRLF-Zeilen, Monitorparser akzeptiert.
SHA256: `8448d7c8f4e5cd31cb9095a5aa6fe306be10835d887fe75a876a5855461a94d7`.

### Decoderabnahme nach gemeldetem Tabellenimport

Decoder für `1000`, `1007`, `9020`, `9040` sowie die weiteren CSV-Lücken
`1005`, `1012`, `1013` ergänzt; sämtliche 76 CSV-Zeilen sind jetzt zuordenbar.
Betriebsart: 0/1/2/3/6/7/9/10; Kessel-Basis-Soll 60–90 °C,
Puffer START/SOLL 10–90 °C. Unbekannte Kodierungen und ungültige Parameter
bleiben Fehlerbeobachtungen mit Originalrohwort, nicht künstliche Nullwerte.
392 Python-Tests, 23 Node-Tests, Build und Ruff erfolgreich.
In der laufenden, vom Betreiber neu gestarteten API und im tatsächlichen Editor
die vollständige CSV als ungespeicherten Entwurf geprüft. Keine Auswahländerung
gespeichert, Revision 5 erhalten, Erfassung weiterhin `stopped_transport`.
Vor Erfassung Ursache des Transportstopps klären; Decoderergänzung quittiert
diesen nicht. Neue Gerätewerte und Displayübereinstimmung sind noch nicht geprüft.




## Individuelle Aufzeichnung (#55)

Die separate Seite **Modbus-Aufzeichnung** unterstützt CSV-Entwurf,
inkrementellen Abgleich, Betreiber-Metadaten und atomare persistente Auswahl.
Der Sammler übernimmt sie an einer Zyklusgrenze; gespeicherte und aktive Revision
sind sichtbar. Keine zusätzlichen Decoder oder Gerätezugriffe durch den Import.
Bedienung: [Modbus-Konfiguration](docs/MODBUS.md#aufzeichnung-konfigurieren).

Offline mit synthetischen Daten und Loopback-Simulator abgenommen;
Prüfnachweise im [Ergebnisbericht](reports/RESULTS.md).
Vor Deployment neuen Build verwenden und konsistente SQLite-Sicherung erstellen:
Schema 1/2/3 wird unter Erhalt der Historie auf 4 erweitert, kein Rückstart mit
alter App auf dieser Datenbank. Die V2-Erweiterung unterstützt jetzt alle
80 bereitgestellten Register mit quellengeprüften Decodern oder ausdrücklich
gekennzeichneten Herstellerrohwerten. Auf ausdrücklichen Betreiberwunsch sind
sie auswählbar/aktivierbar. Beim Upload werden passende interpretierbare Einträge
bereits im Entwurf vorgewählt, auch zuvor abgewählte hochgeladene Werte.
Vor Speichern prüfen; ohne Speichern bleibt die aktive Auswahl unverändert.
Nur fünf Register sind live bestätigt. Neun Read-to-clear-Protokollwerte
beeinflussen bereits beim Lesen den Geräte-Zustand und sind entsprechend
gekennzeichnet. Kein neuer Anlagenzugriff oder Unraid-Nachweis aus der
Offline-Abnahme ableiten. Eine spätere Geräteprüfung weiterhin endlich,
gezielt und ohne parallelen Leser planen.

Wertbezogene Fehler werden nun mit Zeit, Ursache und Leseblock an der jeweiligen
Anlagenkachel gespeichert/angezeigt. Fehlende Wetterdaten blockieren nicht mehr
den Sammler; echte ungültige Signale und Modbus-Ablehnungen 2/3 werden isoliert
ausgesetzt. Globale Geräte-/Protokoll-/Speicherfehler bleiben Stopps. Sperren
überstehen Neustart und CSV-Speichern; Freigabe erst bewusst nach Ursachenprüfung.
Die laufende Heizungs-App wurde dafür nicht neu gestartet oder quittiert.
Vor Nutzung neuen Build laden, konsistent sichern und den bisherigen gespeicherten
Fehlerstopp erst nach Prüfung bewusst quittieren. Details: [Fehlerverhalten](docs/FEHLERVERHALTEN.md).

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

## Rückbau der Diagnosefunktion

Diagnosefunktion und Offline-Steuerentwürfe sind entfernt; die App bleibt
auf Monitoring beschränkt. Die Git-Historie bleibt erhalten. Vorhandene
Datenbanken und Minutenhistorien nicht löschen.
Der [Registerkatalog](docs/register_catalog.json) bleibt eine statische
Referenz, keine Registerauswahl oder zusätzliche Lesefunktion der App.

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
`vX.Y.Z` veröffentlichen erst nach Offline-Prüfungen. Version 0.3.0 ist veröffentlicht;
die Veröffentlichung von 0.3.1 mit fortlaufendem Polling ist ausdrücklich beauftragt.
MIT ist für eigenen App-Code festgelegt. Branch-/Tag-Schutz und
GHCR-Sichtbarkeit bleiben bei der Veröffentlichung zu beachten.
Details: [Unraid-/Release-Strategie](docs/UNRAID.md#github-image-build-und-veröffentlichungsgrenze).

Für Version 0.3.1 ist `compose.unraid.yaml` auf
`ghcr.io/lum1nat0r/sommerauer-monitor:0.3.1` festgelegt, ohne lokalen Build.
Git-Tag dafür: `v0.3.1`, nicht `0.3.1`. Nach erfolgreichem Release-Workflow
die öffentliche GHCR-Verfügbarkeit anonym prüfen; erst danach auf Unraid
mit privater `.env` und vorbereitetem Datenpfad starten
([Anleitung](docs/UNRAID.md#unraid-veröffentlichtes-image-verwenden)).
Die lokale Build-Datei `compose.yaml` bleibt getrennt. Release- und Image-Nachweis
werden im GitHub-Release verlinkt; das Betreiber-Deployment bleibt davon getrennt.
