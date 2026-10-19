# Gestufte Inbetriebnahme

Stand 15.10.2026: Offline-E2E-Abnahme #12 und gestufte lokale Kernregister-Abnahme
#13 durchgeführt (siehe [`reports/RESULTS.md`](../reports/RESULTS.md)).
Aktuelle Verbindung und endliche Loggerläufe belegt; Displayübereinstimmung vom
Betreiber bestätigt. Kein aktivierter Dauerbetrieb und keine Unraid-Installation.
Standardtests und CI verwenden weiterhin keine Heizung.

## Voraussetzungen

Offline-Tests für Transport, Decoder, Zeitplan, Fehlerzustände, Speicherung und UI
bestanden. Konkretes lokales Ziel bekannt, Profil zur Anlage passend, bestehender
Logger/andere Modbus-Clients gestoppt. Das alte private Probierwerkzeug hat eigene
Grenzen und darf nicht blind als dauerhafter App-Prozess gestartet werden.
Vorhandene Originalprotokolle erhalten; neue private Logs in neue Dateien schreiben.

## Ablauf

1. Endlichen lokalen Plan dokumentieren. Erster Durchgang höchstens drei Anfragen
   an die bekannten Blöcke 4102/1, 28688/2, 36864/2 mit Unit255/FC03, 3s Deadline.
2. Jede Antwort sofort auswerten. Bei Fehlern sofort stoppen. Die neue Verbindung
   und Plausibilität protokollieren; technisch nötigen Displayabgleich gezielt
   anfordern. Alte Messungen sind keine aktuellen Vergleichswerte.
3. Danach einen eigenen kurzen endlichen Loggerlauf planen: Dauer, Zeitplan,
   maximale Anfragezahl einschließlich eventueller Wiederaufnahmen und Endbedingung.
   Hier keine konkrete Laufzeit als bereits freigegeben/ausgeführt behaupten.
4. Nach Auswertung größere begrenzte Läufe. Abstände, Fehler, Speicher, Neustarts
   und Anlagenbeobachtungen prüfen. Belastende Fehlerfälle wie falsche Antworten
   und Netzabbrüche offline simulieren, nicht am laufenden Kessel erzwingen.
5. Erst danach Dauerbetrieb nach dokumentiertem Betriebsplan. Der Betreiber
   deployt auf Unraid; ohne tatsächlichen Zugriff keinen abgeschlossenen
   Unraid-/Hardwaretest behaupten.

Zusatzregister separat in kleinen begründeten Plänen prüfen, niemals als Fallback
bei Fehlschlag eines Kernblocks. Noch ungeprüfte Zusatzwerte bleiben deaktiviert
und blockieren nicht die Veröffentlichung einer ehrlich auf Kernwerte begrenzten App.

## Protokollvorlage pro Lauf

- Datum/Zeitzone, App-Version/Commit, Konfigurations- und Profilversion.
- Privates Ziel aliasbasiert, Unit/Funktion, konkrete Offsets/Anzahlen.
- Zweck, Voraussetzungen, Zeitplan, Höchstdauer, maximale Anfragezahl.
- Tatsächlich gesendet/empfangen; Ergebnis pro Anfrage, Unterbrechungs-/Stopgrund.
- Strikte Trennung von Benutzerbeobachtung, Geräteantwort und Simulator.
- Interpretation mit Unsicherheit, keine Rohdaten in öffentlichen Issues.
- Nächster begründeter Schritt; bei Fehler erst Ursache klären.

## Betriebsplan nach der begrenzten Abnahme

Erst nach Auswertung des erfolgreichen 15-Anfragen-Kurzlaufs und des
90-Anfragen-Langlaufs festgelegt. **Plan für das spätere Betreiber-Deployment,
nicht gestarteter Dauerbetrieb und keine Hersteller-Verträglichkeitszusage.**
Die Laufpläne und tatsächlichen Ergebnisse bleiben in `NEXT_STEPS.md` und
`reports/RESULTS.md` nachvollziehbar; private Rohbelege unter
`data/issue13-abnahme/` nicht veröffentlichen oder löschen.

- **Ziel und Umfang:** Alias `Anlage-aktuell`, ausschließlich aktuelles
  `MODBUS_HOST` aus privater Deployment-Konfiguration, Port 502, FC03,
  Unit 255, Profil `core`/1: 4102/1, 28688/2, 36864/2. Keine Zusatzregister,
  Zielsuche, Fallbackadresse oder Heizungsänderung.
- **Zuständigkeit und Start:** Betreiber deployt genau einen Container/einen
  Webworker und beendet andere Modbus-Leser. Zunächst Erfassung deaktiviert
  lassen; tatsächliches Image/Revision, lokalen `/data`-Mount, Rechte und
  Sicherung auf Unraid prüfen. Danach eigener endlicher Deployment-Lauf mit
  dokumentiertem Budget; die Windows-Abnahme ersetzt diesen Plattformcheck nicht.
  Bestehende `completed`-/harte Fehlerzustände nicht durch Löschen der DB oder
  Neustarts umgehen; nur nach Prüfung bewusst quittieren.
- **Zeitplan:** ein synchroner Client, eine Anfrage gleichzeitig, höchstens
  zwei Register, 3 s Transport-Gesamtdeadline. Derselbe Block frühestens
  60 s nach Abschluss seiner vorherigen Verarbeitung, hochauflösend monoton
  gemessen. Keine Nachhol-Bursts, keine separate Zwangspause zwischen
  verschiedenen Blöcken. Antwort-/Speicherlaufzeit verlängert das Raster.
  Rechnerische Obergrenze im ungestörten Normalbetrieb: 4320 Kernanfragen
  pro 24 Stunden; das ist keine Herstellerfreigabe.
- **Betriebsdauer/Budget:** unbeschränkte Erfassung erst vom Betreiber nach
  Plattformprüfung bewusst konfigurieren (`COLLECTOR_MAX_REQUESTS` dann leer).
  Dieser Plan aktiviert sie nicht. Endliche Prüfungen behalten immer ein
  eigenes Gesamtbudget und stoppen auch bei Verbindungsfehlern ohne Retry.
  Für regulären Dauerbetrieb gilt [FEHLERVERHALTEN.md](FEHLERVERHALTEN.md):
  Reine Verbindungsfehler lassen die normalen Blockintervalle ohne Versuchslimit
  oder Backoff weiterlaufen. Alte reine Transport-Budgetsperren werden beim
  aktivierten, weiterhin unbeschränkten Dienststart automatisch aufgehoben.
- **Harte Stopps:** Protokoll-/Teilantwort-/strukturelle Daten-/Speicherfehler,
  ungewisse Read-to-clear-Auslesungen, Betreiber-Stopp oder Anlagenauffälligkeit
  beenden weitere Reads. Keine automatische Quittierung oder künstliche Live-Störung.
  Bei Auffälligkeit Zeitpunkt und Ursache prüfen, nicht blind erneut starten.
- **Persistenz/Beobachtung:** Alle Minutenbeobachtungen dauerhaft erhalten,
  Lücken/Alter/Qualität sichtbar lassen; Transportlogs getrennt behandeln.
  Konsistente SQLite-Backups auf ein separates geschütztes Ziel sichern.
  Nach Start und in den ersten 24 Stunden Anfragezahlen/-abstände, Status,
  Lücken, freien Speicher sowie Betreiberbeobachtungen auswerten.
  Unraid-Neustart, Containerersatz und Restore tatsächlich protokollieren,
  bevor sie als bestanden gelten.

Die begrenzte Abnahme umfasst fünf historisch bestätigte Register und vier
Kernsignale. Sie belegt weder die übrigen 194 Katalogeinträge noch langfristige
Störungsfreiheit, Sensor-Kalibrierung, Brennerfunktion oder Unraid-Persistenz.
