# Signal-, Speicher- und API-Vertrag

Signaldecodierung, SQLite-Speicherung, Erfassung, persistente Sammlerzustände,
lesende Messwert-/Verlaufs-/Ereignis-API, geschützte Sammleraktionen und das
responsive Dashboard sind umgesetzt. Die UI liest ausschließlich die API.

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

## HTTP-API

FastAPI veröffentlicht OpenAPI unter `/openapi.json` und Swagger UI unter `/docs`.
Alle Leseendpunkte arbeiten ausschließlich mit SQLite; kein Refresh löst Modbus aus.

| Route | Vertrag |
|---|---|
| `GET /api/health` | App- und Datenbankstatus; unabhängig vom Sammlerzustand |
| `GET /api/config` | Redigierte Konfiguration; Hostwert und Datenpfad fehlen |
| `PUT /api/config` | Nur `display_timezone`; speichert Version und Ereignis |
| `GET /api/signals/current` | Letzter Wert, Einheit, Messzeit, Alter, Qualität und Freshness |
| `GET /api/history/{signal_id}` | ISO-8601-Zeitbereich, UTC-normalisiert, seitenweise bis 10.000 Rohpunkte |
| `GET /api/events` | Neueste Ereignisse mit `limit`/`offset` |
| `GET /api/export.csv` | Streamt alle passenden Originalmessungen ohne Downsampling |
| `GET /api/collector/status` | Zustand und begrenzte Wiederaufnahme |
| `POST /api/collector/pause`, `/resume`, `/acknowledge-and-start` | Geschützte Sammleraktionen, keine Heizungsbefehle |

Zeitfilter müssen eine Zeitzone enthalten; Start ist inklusiv, Ende exklusiv.
Historienseiten sortieren nach Messzeit und Beobachtungs-ID. CSV-Zeitstempel
bleiben als gespeicherte ISO-8601-UTC-Werte erhalten; Rohworte, Qualität und
Decoderherkunft sind enthalten. Fehlerdetails aus Transport und Speicher werden
nicht öffentlich ausgegeben.

Mutierende Requests benötigen die direkt erkannte Request-Origin oder die explizit
über `PUBLIC_ORIGIN` konfigurierte Browser-Origin des Reverse-Proxys. Sie dürfen
nicht als `cross-site` markiert sein und müssen
`X-Requested-With: SommerauerMonitor` setzen. Ohne `PUBLIC_ORIGIN` bleibt nur die
direkte Request-Origin erlaubt; fremde Browser-Origins bleiben abgewiesen.
Schema, Host und Port gehören zur Origin. Keine Wildcards, URL-Pfade oder
Zugangsdaten; die private Freigabe erscheint nicht in `/api/config`.
Dies ist CSRF-Schutz, kein Ersatz für Netzwerk-/Betriebssystem-Zugriffsschutz:
App nur im vertrauenswürdigen LAN/Tailscale bereitstellen.

Die API-Konfiguration ändert ausschließlich die Anzeigezeitzone. Modbus-Ziel,
Port, Unit, Profil und Datenpfad bleiben Deployment-Konfiguration und werden
niemals per Verwaltungsroute geändert. Verwaltungsaktionen benötigen einen
konfigurierten Collector; fehlt er, antwortet die Route mit HTTP 409.
