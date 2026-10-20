# Separates Testwerkzeug für Puffer START/SOLL

Betreiberauftrag vom 20.10.2026: Ein deploybares Werkzeug für `9040` (START,
Offset 36928) und `9020` (SOLL, Offset 36896). Entwicklung auf
`feature/start-soll-schreibtest`. Das Werkzeug ist von der Monitoring-App getrennt;
es benötigt Python und SQLite aus der Standardbibliothek, keine App-Pakete.

**Geräteabnahme noch offen:** Der bereitgestellte rekonstruierte Export wurde
erneut statisch geprüft. Sein FC06-Pfad enthält tatsächlich eine Dezimaltext-/Hex-
Umwandlung. Das Werkzeug berücksichtigt genau dieses Profil, keinen generischen
Standard-Schreibweg. `encoding_confirmed` erst setzen, wenn die tatsächlich
installierte Software diesem geprüften Profil entspricht. Der Exportnachweis
allein bestätigt weder aktuelle Firmware noch Gerätekompatibilität.

## Darstellbare Werte im geprüften Schreibpfad

Das Gerät interpretiert die Dezimalziffern des empfangenen uint16-Worts als
Hexzahl. Beispiel ausschließlich zur Kodierung: Für 40 °C wird das Wort 28
übertragen; die Hexinterpretation von „28“ ergibt 40. Einfach das Wort 40 zu
schreiben würde in diesem Export stattdessen 64 ergeben.

Für Zieltemperaturen, deren Hexdarstellung A–F enthält, existiert kein passendes
positives uint16-Wort in diesem Pfad. Innerhalb 10–90 °C sind nur 16–25, 32–41,
48–57, 64–73 und 80–89 darstellbar. **60 °C ist beispielsweise nicht darstellbar.**
Der Client prüft alle Ausgangs- und Testwerte vor jeder Verbindung. Ist etwa
der ursprüngliche SOLL-Wert 60 °C, ist kein Test an diesem Parameter erlaubt,
weil die Rückstellung über diesen FC06-Pfad nicht möglich wäre. Kein Runden,
Clamping, anderes Register oder anderer Funktionscode als Ausweichversuch.
Alle Angaben sind statische Befunde/Ableitungen, keine gemessenen Geräteeffekte.

## Wie kommt der ursprüngliche Wert zurück?

START/SOLL sind laut bisheriger privater Quellenzusammenfassung persistente
Basisparameter, gemeinsam mit dem Touch. **Ein geräteseitiges automatisches
Zurücksetzen nach einer Frist ist nicht nachgewiesen.**

Der Testclient übernimmt die Rückstellung aktiv. Je Kandidat:

1. Ausgangswert mit FC03 lesen und mit dem ausdrücklich geplanten Vorwert vergleichen.
2. Vorwert und belegtes Rückstell-Schreibwort dauerhaft im privaten Journal sichern.
3. Testwort mit FC06 schreiben und den erwarteten Temperaturwert mit FC03 prüfen.
4. Die im Plan eingestellten 0–60 Sekunden warten, ohne weitere Anfragen.
5. Mit FC03 prüfen, ob noch der Testwert anliegt. Bei einer zwischenzeitlichen
   Änderung stoppen; keine blinde Rückstellung über den abweichenden Wert.
6. Den geplanten Vorwert mit dessen belegtem FC06-Wort zurückschreiben und per
   FC03 prüfen. Erst danach den nächsten Kandidaten bearbeiten.

Die Testdauer ist die Wartezeit ab erfolgreichem Rücklesen. Rückstellprüfung,
Schreibzugriff und Bestätigung benötigen anschließend jeweils bis zu drei Sekunden.
Es gibt keine atomare gemeinsame START-/SOLL-Änderung. Bei unverändertem Zielwert
wird nur einmal gelesen. Die tatsächliche Wirkung auf die Heizungsregelung bleibt
unabhängig vom Telegrammecho zu prüfen; keine globale Startsperre behaupten.

**Host-/Netzausfall:** Dann kann der Testwert bestehen bleiben. Ein Prozess-Timer
ist kein autonomer Geräterückfall. Dasselbe gilt für verlorene Bestätigung,
Rücklesefehler, Nutzerabbruch und Rückstellfehler: sofort Ende, keine Retries oder
zusätzlichen Rückstellversuche. Bediener muss am Touch prüfen und gegebenenfalls
manuell zurückstellen. Eine Touch-Änderung auf denselben Testwert ist durch
Rücklesen nicht von einem unveränderten Parameter unterscheidbar.

Das Journal bewahrt mögliche Änderungen und Rückstellwerte. Neustart desselben
Laufs führt keine neue Geräteanfrage aus. Journal/Volume nach einem Fehler nicht
löschen, wechseln oder durch ein neues Laufjournal umgehen.

## Privaten Plan vorbereiten

```sh
mkdir -p data/write-test
python -m write_test template > data/write-test/plan.json
```

Die Vorlage führt keine Anfrage aus und enthält absichtlich `null` für unbekannte
Werte. Privat ausfüllen:

| Feld | Bedeutung |
|---|---|
| `target_ip`, `port` | Tatsächlich freigegebenes Ziel ausschließlich aus aktueller privater Deploymentkonfiguration; numerische IP, keine Zielsuche |
| `unit` | Fest 255 |
| `hold_seconds` | Vereinbarte Wartezeit, 0–60 s je Kandidat |
| `encoding_source`, `encoding_confirmed` | Fest vorgegebener SHA256 des geprüften Exports und bestätigte Übereinstimmung der installierten Version; keine bloße Annahme |
| `registers` | Ein oder beide Kandidaten, eindeutige Codes `9040` / `9020` |
| `original_c`, `test_c` | Tatsächlicher freigegebener Ausgangs-/Testwert in ganzen °C, innerhalb dokumentierter Lesebereiche 10–90 |

Die konkreten FC06-Wörter werden aus dem geprüften Profil berechnet und in der
Planprüfung angezeigt; der Plan bietet keinen beliebigen Rohworteditor.

Eine zulässige Beziehung der START-/SOLL-Parameter wird ohne Beleg nicht erfunden.
Echte Sensormesswerte, andere Register und beliebige Modbus-Funktionen sind nicht
zugänglich. Temperaturgrenzen stammen aus der Lesesemantik und sind keine
Hersteller-Verträglichkeitszusage für Schreibtests.

```sh
python -m write_test review --plan data/write-test/plan.json
```

Die lokale Prüfung öffnet keine Verbindung. Sie zeigt den Hash des vollständigen
Plans sowie Ausgangs-/Testwerte und Rückstellzeit. Die Zieladresse wird nicht
ausgegeben. Eine spätere Planänderung macht den Freigabehash ungültig.

## Deployment als eigener CLI-Container

```sh
docker build -f Dockerfile.write-test -t sommerauer-write-test:local .
docker run --rm --network none sommerauer-write-test:local --help
```

Alternativ `docker compose -f compose.write-test.yaml build` und
`docker compose -f compose.write-test.yaml run --rm write-test --help`.
Der Compose-Standard hat ebenfalls kein Netzwerk. CI baut das separate Image
und prüft das synthetische Beispiel mit `--network none`, ohne Veröffentlichung.

Kein Port, kein Web-Schreibendpunkt und keine Neustartregel. Das Image startet
standardmäßig nur die Hilfe. Es wird hier weder veröffentlicht noch automatisch
an eine reale Anlage angeschlossen. Das Datenverzeichnis muss für UID 99/GID 100
beschreibbar sein; Hostpfad anhand der eigenen Deploymentkonfiguration setzen.

Ein synthetischer Plan liegt unter `examples/write_plan.synthetic.json`.
Die darin frei gewählten Temperaturen sind keine Einstellempfehlungen oder
Messwerte. `encoding_confirmed=false` verhindert die echte Ausführung. Das
Speichermodell bildet den statisch geprüften Umwandlungspfad nach, keine komplette
Herstellerregelung. Lokal lässt sich derselbe Test ohne Docker ausführen:

```sh
python -m write_test simulate --plan examples/write_plan.synthetic.json --journal data/write-test/synthetic.sqlite
```

```sh
docker run --rm --network none -v ./examples/write_plan.synthetic.json:/plan.json:ro -v ./data/write-test:/data sommerauer-write-test:local simulate --plan /plan.json --journal /data/synthetic.sqlite
```

Fehlerfälle mit `simulate --fault lost-ack` beziehungsweise `reject-write`,
`readback-mismatch` oder `restore-failure`. Je neuem synthetischen Durchlauf ein
eigenes Journal verwenden; das reale Journal niemals für Simulationen nutzen.

## Späterer konkreter Gerätetest

Noch nicht durchgeführt oder freigegeben. Vorher installiertes Schreibprofil bestätigen,
darstellbare Test- und Rückstellwerte mit dem Betreiber festlegen, andere Leser einschließlich
Monitor nachweislich pausieren und manuelle Rückstellung am Touch bereithalten.
Privaten Laufplan mit konkretem Ziel und öffentlich nur dessen Alias dokumentieren.

Technischer Rahmen des vorbereiteten Werkzeugs: FC03/FC06, Unit 255, ein Wort
pro Anfrage, feste 3-s-Gesamtdeadline, ein Client, keine Retries. Je Kandidat
zwei Phasen zu je höchstens drei Anfragen mit sofortiger Antwortprüfung:
Setzen/Prüfen und Kontrollieren/Rückstellen/Prüfen. Ein Kandidat zuerst;
maximal sechs Anfragen. Beide Kandidaten erst nach Auswertung getrennt oder
in einem ausdrücklich vereinbarten Plan; obere Werkzeuggrenze zwölf Anfragen,
höchstens 156 s reines Warte-/Transportbudget bei zwei maximalen Wartezeiten
und Transportdeadlines, zuzüglich lokaler Speicherung und Prozessplanung.
Auf Fehler oder Nutzerstopp endet der Lauf sofort, auch wenn ein Parameter noch
verändert sein könnte. Ungewisse Anfragen sind im Journal als `unknown` markiert.

Nur nach konkreter Betreiberfreigabe des angezeigten Plans ausführen:

```sh
python -m write_test execute --plan data/write-test/plan.json --journal data/write-test/live.sqlite --approve <PLAN-SHA256>
```

Der Container verwendet dieselben Argumente mit privaten `/data`-Pfaden und
gezielt eingerichtetem Netzwerk zum genehmigten Ziel. Keine automatische
Wiederaufnahme/Restart-Policy einrichten. Alle lokalen Werkzeuginstanzen müssen
dasselbe private Datenverzeichnis verwenden; dort verhindert ein Dateilock
parallele Aufrufe. Fremde Modbus-Clients können damit nicht gesperrt werden.

```sh
python -m write_test status --journal data/write-test/live.sqlite
```

`manual_review_restore_values` enthält Code, Vorwert in °C und belegtes
Rückstellwort für noch nicht bestätigte Rückstellungen. Keine automatische
Wiederholung daraus ableiten. Journal und Plan sind private Artefakte;
nicht committen oder ungeprüft in Issues veröffentlichen.

Exitcodes: 0 abgeschlossen/lokal angezeigt, 1 Lauf-/Planfehler, 2 CLI-Fehler.
Das bestehende Issue #18 bleibt wegen des offenen autonomen Rückfalls offen.
Quellen zum Transportformat: [Modbus-Spezifikation, Abschnitte 6.3/6.6](https://www.modbus.org/file/secure/modbusprotocolspecification.pdf)
und [TCP Guide](https://www.modbus.org/file/secure/messagingimplementationguide.pdf).
Sie belegen keine Heizungs-Schreibsemantik.

Prüfung ohne Projektpakete oder Netzwerk:

```sh
python -m unittest discover -s tests -p test_write_tool.py -v
```
