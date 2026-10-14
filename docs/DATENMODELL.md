# Signal-, Speicher- und API-Vertrag

Die Signaldecodierung und SQLite-Speicherbasis sind implementiert; API-Verläufe
und Sammler-Integration bleiben spätere Arbeitspakete.

## Signale und Messungen

Stabile IDs: `boiler.temperature`, `buffer.top_temperature`,
`buffer.bottom_temperature`, `boiler.operating_minutes`. Betriebsstunden sind eine
Darstellung derselben Minuten; nicht als unabhängig gemessenes Signal ausgeben.

Pro Beobachtung: eindeutige ID, Signal-ID, tatsächlich beobachteter UTC-Zeitpunkt,
Empfangs-/Speicherzeit bei Bedarf separat, Rohwortliste, dekodierter Wert oder null,
Einheit, Qualität, Datenquelle, Registerprofil- und Decoderversion, Anfrage-ID.
Die reinen Decoder binden diese Interpretation an `source`, Profil-/Decoderversion,
Blockoffset und Rohworte. Metadaten der Anfrage: Start/Ende, Offset/Anzahl,
Funktion/Unit, Ergebnis/Fehlerklasse. Tatsächliche Zeitpunkte pro Gruppe; kein
vorgetäuschter simultaner Gesamtsnapshot.

Qualität mindestens `ok`, `invalid`, `unavailable`; `stale` entsteht beim Lesen aus
dem Alter relativ zum jeweiligen Erfassungsintervall und ist nicht automatisch
ein ungültiger ursprünglicher Messwert. API liefert Alter und Frischegrenze.
Netzausfall erzeugt Ereignis/Lücke, keine fiktive Null oder wiederholte Messung.
Eine zuvor gültige Messung wird nicht nachträglich ungültig umgeschrieben.

`backend/storage.py` verwaltet versionierte Tabellen für Signaldefinitionen/Profile,
Leseanfragen, Beobachtungen, Ereignisse, Konfigurationsversionen, Sammlerzustand und
Schema-Migrationen. Beobachtungen plus Anfrage werden in einer Transaktion gespeichert.
Eine Anfrage-ID ist idempotent: Wiederholung wird ignoriert statt Messwerte zu duplizieren.
Ein eindeutiger Index unterstützt Signal-/Zeitabfragen; diese sind chronologisch,
halb-offen nach Zeitbereich und auf höchstens 10.000 Punkte begrenzt. Es gibt keine
zeitgesteuerte Löschung und noch keine Aggregation.

## Dauerhafte Speicherung

Keine automatische Löschung der Minutenmessungen. Historische Decoderfassung
erhalten; Korrekturen zusätzlich versionieren, nicht Originale überschreiben.
Transportdiagnostik darf getrennt rotieren. Aggregate mit Anzahl gültiger Werte,
Minimum/Maximum/Mittelwert nur zusätzlich. Diagramme mit großen Zeiträumen erhalten
begrenzte Punktzahl, ohne Lücken/Gültigkeitsgrenzen zu glätten oder Rohdaten zu verlieren.
Status-/Fehlerereignisse und Konfigurationswechsel unabhängig von Messwerten speichern.

UTC intern; Europe/Vienna für Anzeige. CSV mit ISO-8601-Zeit/Offset, Einheit und
Qualität, frei wählbarem Zeitraum. Keine doppelten/ausgelassenen Stunden beim
Sommerzeitwechsel. Große Exporte streamen; Abfrageumfang/Sortierung deterministisch.

## Geplante API-Funktionen

| Funktion | Erwarteter Inhalt |
|---|---|
| App-Gesundheit | Prozess/DB separat vom Messzustand |
| Aktuelle Signale | letzter Wert, Messzeit, Alter, Qualität, Einheit |
| Verlauf | Signal(e), Zeitraum, Auflösung/Punktlimit, Lücken |
| Ereignisse | sortiert, Filter, Pagination |
| CSV | Originalmessungen im Zeitraum; keine stillen Aggregate |
| Erfassungszustand | Zustand, Fehlergrund, verbleibende Versuche, nächste Aktion |
| Pause/Fortsetzen | ausschließlich Sammlersteuerung; kein Kesselbefehl |
| Konfiguration | validierte App-Konfiguration, redigierte Geheimnisse |

HTTP-Routen und Schemas beim API-Issue festlegen, OpenAPI und Fehlerantworten
dokumentieren. Reads lösen nie Modbus aus. Verwaltungsaktionen erfordern einen
konkreten lokalen Zugriffsschutz und Schutz gegen unbeabsichtigte Browseraufrufe.
Konfigurationsänderungen transaktional, bei relevanten Änderungen kontrolliert
pausieren. Keine beliebigen Register/Funktionen als HTTP-Parameter anbieten.
