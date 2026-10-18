# Signal-, Speicher- und API-Vertrag

Signaldecodierung, SQLite-Speicherung, Erfassung, persistente Sammlerzustände,
lesende Messwert-/Verlaufs-/Ereignis-API, geschützte Sammleraktionen und das
responsive Dashboard sind umgesetzt. Die UI liest ausschließlich die API.

## Signale und Messungen

Stabile IDs: `boiler.temperature`, `buffer.top_temperature`,
`buffer.bottom_temperature`, `boiler.operating_minutes`. Betriebsstunden sind eine
Darstellung derselben Minuten; nicht als unabhängig gemessenes Signal ausgeben.

Zusätzlich liefert das explizite V2-Profil `stoker.operating_minutes` und
`modbus.<HEXCODE>` für die übrigen Zusatzwerte: insgesamt 78 Signale aus
80 Registerwörtern. `GET /api/signals` liefert Bezeichnung, Decoder-Einheit,
Kategorie, Beschreibung, Intervall, Live-Belegstatus und Read-to-clear-Hinweis
sowie getrennte, nicht ausführbare START-/SOLL-Kandidaten. Das Dashboard
verwendet diesen Katalog statt einer fest eingebauten Vierer-Auswahl.
Zusatzwerte sind mindestens 300 s, Kernwerte mindestens 60 s auseinander;
Frischegrenzen sind entsprechend 600 s beziehungsweise 120 s.

Kategorien trennen Sensoren, Regelgrößen, Zähler, Settings, Status, Hersteller-
rohwerte und Steuerungsdatum/-zeit. Eine auswählbare statische Zuordnung ist
kein Live-Nachweis. Physikalisch ungeklärte Herstellerwerte erhalten die Einheit
„Rohwert“. Neue dekodierte Beobachtungen tragen `extended/1/1`; vorhandene
Kernbeobachtungen bleiben unverändert. SQLite speichert auch nicht-ganzzahlige
dekodierte Werte wie 24,5 V verlustfrei als REAL trotz INTEGER-Spaltenaffinität;
dafür ist keine Typmigration nötig. Alte Werte werden nicht nachträglich umgerechnet.

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

Schema 4 ergänzt pro Beobachtung die nullable Felder `error_code` und
`error_message`. Bei einer fehlenden oder ungültigen Beobachtung ist `value`
null, niemals eine erfundene Nullmessung. Die lesende Current-API liefert die
neueste Beobachtung pro Signal einschließlich Fehlern und `block_offset`/
`register_count`; gleiche Zeitstempel werden deterministisch nach Einfügereihenfolge
aufgelöst. Ein früherer guter Wert wird nicht mehr als aktuelle Messung ausgegeben.
Historie/CSV enthalten dieselben Fehlerfelder; die CSV hängt sie hinten an.
Fehlerbeobachtungen unterbrechen Diagrammlinien, auch innerhalb des normalen
Zeitintervalls. Bekannte Wetterfehlwerte können ohne Freigabe wieder verfügbar
werden; wirklich ungültige Signale bleiben bis zur bewussten Freigabe ausgesetzt.

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

Die individuelle Registerauswahl liegt mit Revision und Betreiber-Metadaten
atomar in `logging_config` derselben Datenbank. Aktuelles Schema ist 4:
Schema 1/2/3 wird additiv erweitert, bisherige Beobachtungen erhalten NULL in
den neuen Fehlerfeldern. Minutenhistorie und alte zusätzliche Tabellen bleiben
erhalten. Ein konkurrierender veralteter Entwurf wird über
Revisionsvergleich unter `BEGIN IMMEDIATE` abgewiesen. Inhaltlich unveränderte
Speicherung ist ein No-op. Die aktive Zyklusrevision steht zusätzlich im
Sammlerzustand; Importfelder sind keine nachträgliche Decoderänderung.

## HTTP-API

FastAPI veröffentlicht OpenAPI unter `/openapi.json` und Swagger UI unter `/docs`.
Alle Leseendpunkte arbeiten ausschließlich mit SQLite; kein Refresh löst Modbus aus.

| Route | Vertrag |
|---|---|
| `GET /api/health` | App- und Datenbankstatus; unabhängig vom Sammlerzustand |
| `GET /api/config` | Redigierte Konfiguration; Hostwert und Datenpfad fehlen |
| `PUT /api/config` | Nur `display_timezone`; speichert Version und Ereignis |
| `GET /api/signals` | Dynamische Definitionen aller unterstützten Signale und getrennte START-/SOLL-Kandidaten; keine Geräteabfrage |
| `GET /api/logging-config` | Gespeicherte Einträge/Revision, aktive Einträge/Revision und Übernahmestatus |
| `POST /api/logging-config/preview` | JSON `{revision, csv_text}`: validierter inkrementeller Entwurf ohne Speicherung/Read |
| `PUT /api/logging-config` | JSON `{revision, entries}`: vollständige atomare Auswahl und Metadaten; HTTP 409 bei Versionskonflikt |
| `GET /api/signals/current` | Letzter Wert, Einheit, Messzeit, Alter, Qualität und Freshness |
| `GET /api/history/{signal_id}` | ISO-8601-Zeitbereich, UTC-normalisiert, seitenweise bis 10.000 Rohpunkte |
| `GET /api/events` | Neueste Ereignisse mit `limit`/`offset` |
| `GET /api/export.csv` | Streamt alle passenden Originalmessungen ohne Downsampling |
| `GET /api/collector/status` | Zustand und begrenzte Wiederaufnahme |
| `POST /api/collector/pause`, `/resume`, `/acknowledge-and-start` | Geschützte Sammleraktionen, keine Heizungsbefehle |

Zeitfilter müssen eine Zeitzone enthalten; Start ist inklusiv, Ende exklusiv.
Historienseiten sortieren nach Messzeit und Beobachtungs-ID. CSV-Zeitstempel
bleiben als gespeicherte ISO-8601-UTC-Werte erhalten; Rohworte, Qualität und
Decoderherkunft sind enthalten. Kontrollierte wertbezogene Fehlertexte werden
angezeigt; rohe Transport-/Speicherfehler mit privaten Details nicht.

Mutierende Requests benötigen die direkt erkannte Request-Origin oder die explizit
über `PUBLIC_ORIGIN` konfigurierte Browser-Origin des Reverse-Proxys. Sie dürfen
nicht als `cross-site` markiert sein und müssen
`X-Requested-With: SommerauerMonitor` setzen. Ohne `PUBLIC_ORIGIN` bleibt nur die
direkte Request-Origin erlaubt; fremde Browser-Origins bleiben abgewiesen.
Schema, Host und Port gehören zur Origin. Keine Wildcards, URL-Pfade oder
Zugangsdaten; die private Freigabe erscheint nicht in `/api/config`.
Dies ist CSRF-Schutz, kein Ersatz für Netzwerk-/Betriebssystem-Zugriffsschutz:
App nur im vertrauenswürdigen LAN/Tailscale bereitstellen.

`PUT /api/config` ändert ausschließlich die Anzeigezeitzone; die separate
Aufzeichnungskonfiguration Auswahl und Betreiber-Metadaten; nur bestätigte
Signale sind zur Erfassung aktivierbar. Modbus-Ziel, Port, Unit, Profil und
Datenpfad bleiben unveränderliche Deployment-Konfiguration. Sammleraktionen benötigen einen konfigurierten
Collector (sonst HTTP 409); CSV-Vorschau und Speicherung sind auch offline ohne
Collector möglich. Import-/Save-Anfragen sind auf 4 MiB JSON begrenzt.
