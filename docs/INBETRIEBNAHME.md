# Gestufte Inbetriebnahme

Stand: Offline-E2E-Abnahme #12 am 15.10.2026 abgeschlossen (siehe
[`reports/RESULTS.md`](../reports/RESULTS.md)). Keine neue Geräteantwort oder
Displayprüfung; Standardtests und CI verwenden keine Heizung.

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
