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

### Diagnosejournal (Issue #31)

Schema 2 ergänzt `diagnostic_runs`, `diagnostic_requests` und `control_plans`,
getrennt von Kernanfragen und `observations`. Migration 0→1→2 beziehungsweise
1→2 erfolgt in einer Transaktion; bestehende Minutenzeilen, Signale und Profile
bleiben unverändert. Die dort angelegte Steuerrevisionstabelle wird durch #34
mit den folgenden Offline-Operationen verwendet.

Ein Lauf speichert einen unveränderlichen Plan (Schema 1): Kataloghash,
ausgewählte IDs, aufgelöste Blockliste, Zweck, Quelle, privaten Host-/Port-Snapshot,
Ziel-Fingerprint, FC03/Unit 255, 3 s Deadline, exakt 1–3 Anfragen entsprechend
der Blockanzahl, 60 s Mindestabstand, 600 s Höchstdauer und Stopbedingungen.
Die Settings-basierte Zielbindung und monotone Zeitprüfung liefert erst #33.

Planfelder: `schema_version`, `catalog_sha256`, `register_ids`, `blocks`
(jeweils `offset`/`count`), `purpose`, `source`, `target` (`host`/`port`),
`target_fingerprint`, `function_code`, `unit_id`, `deadline_seconds`,
`request_budget`, `min_interval_seconds`, `max_duration_seconds`,
`stop_conditions`. Der Runner berechnet den Fingerprint als SHA-256 der UTF-8-Bytes
von `json.dumps({"host": settings.modbus_host.casefold(),
"port": settings.modbus_port, "unit_id": 255,
"source": settings.diagnostics_source, "catalog_sha256": catalog.sha256},
sort_keys=True, separators=(",", ":"))`. Keine HTTP-Zieldaten verwenden;
die Blockliste bleibt zusätzlich unveränderlich. Der Speicher prüft die Form,
nicht die Gleichheit mit der aktuellen Deployment-Konfiguration.
`create_diagnostic_run` erzeugt UUID und UTC-Zeit serverseitig; keine Planaktualisierung
bei späterem Ziel-, Quellen- oder Katalogwechsel.

`reserve_diagnostic_request` verbraucht den Versuch vor einer Netzoperation
dauerhaft. `finish_diagnostic_request` speichert tatsächliche Rohworte,
optionale bestätigte Kerninterpretation, Fehlerklasse und empfangene Bytes atomar.
Bewertungen stehen separat in `review_json`; Antworten werden nicht überschrieben.
Auch diagnostisch gelesene Kernwerte erzeugen keine Minutenbeobachtung.

`get_diagnostic_run` und `list_diagnostic_runs` sind **private interne**
Speicheroperationen: `plan` enthält den privaten Snapshot, `requests` enthält
`raw_words`, `decoded` und `review`. Diese Dicts niemals direkt veröffentlichen.
#35 muss eine explizite bereinigte Projektion mit Quelle und Alias
`Anlage-aktuell` beziehungsweise `Simulator` erstellen, ohne Host, lokale Pfade,
Fingerprint oder rohe Exceptions.

Restore akzeptiert ausschließlich Backups mit Schema 1 oder 2 und verlangt ein
noch nicht existierendes Offline-Ziel. Es überschreibt deshalb kein laufendes
Volume. Nur das kopierte Ziel wird migriert; die Quelle bleibt schreibgeschützt.
Aktive Diagnosen werden unterbrochen, nicht neu gestartet; Budget, Antworten,
Bewertungen, harte Stopps und sämtliche Steuerrevisionen bleiben erhalten.
Ein Austausch des Betriebsvolumes erfolgt erst bei kontrolliert beendeten Lesern.

### Steuerentwürfe und Revisionen (Issue #34)

`backend/control_plans.py` definiert `ControlPlanDraft` mit exakt den 20 Feldern
aus #34. ID und nichtleerer Zweck sind Pflicht; alle übrigen Voraussetzungen
dürfen `null` bleiben und erscheinen dann namentlich unter `missing_fields`.
Texte sind auf 4000 Zeichen begrenzt; reine Leerangaben werden zu `null`,
tatsächliche Werte bleiben unverändert Text. Keine Umwandlung in Schreibwerte.
Funktionscode strikt ganzzahlig 1..127, Anfragezahl strikt positiv ganzzahlig,
Dauer positiv und endlich (auch Bruchteile von Sekunden). Keine Bool-/String-
Konvertierung numerischer Angaben, Zusatzfelder oder unbekannten Kandidaten.

`assess_control_plan()` liefert ausschließlich `status`, `missing_fields` und
`blockers`. `ready_for_review` bedeutet nur formal vollständig, **nie**
fachlich verifiziert, freigegeben oder ausführbar. Ständige Blockercodes:

- `actuation_path_requires_source_evidence`
- `encoding_requires_source_evidence`
- `device_change_requires_separate_approval`
- `execution_not_available`

Bestätigte reale Temperaturkanäle tragen zusätzlich unveränderlich
`sensor_value_must_not_be_overridden`; START und SOLL behalten
`autonomous_fallback_on_host_or_network_loss_unverified`. Betreibertext und
Python-Timer beseitigen diese Grenzen nicht. Katalog und separate
`CONTROL_CANDIDATES` bleiben unverändert; „Soll“ ist kein Schreibbeleg.

`SQLiteStore.save_control_plan(plan_id, expected_revision, draft)` validiert vor
Speicherung. Neuanlage ausschließlich mit beiden Parametern `None`: UUID und
UTC-Zeit entstehen serverseitig. Updates verlangen bestehende ID und positive
erwartete Revision. Vergleich und ausschließlich neuer Insert laufen gemeinsam
unter `BEGIN IMMEDIATE`; veraltete Revisionen liefern
`RevisionConflict(StorageError)` mit `code="revision_conflict"`.
Eine unbekannte Update-ID erzeugt keinen Plan. Speicherfehler erhalten bereinigte
Meldungen, ohne rohe SQLite-/Pfaddetails.

`get_control_plan(plan_id, revision=None)` liefert die neueste oder ausdrücklich
gewählte gespeicherte Revision, bei fehlender ID/Revision `None`.
`list_control_plans() -> list[dict]` liefert ausschließlich die neueste Revision
je Plan, sortiert nach `created_at DESC, plan_id`, keine Historienliste und keine
Pagination. Alte Entwürfe und Bewertungen werden beim Laden nicht neu berechnet.

Die gemeinsame Dokument-/Exportprojektion aus `build_control_plan_document()`
enthält `plan_id`, `revision`, `created_at`, `draft`, `assessment`,
`source_status: {kind: "operator_provided", independently_verified: false}` und
zwingend `execution_enabled: false`. Sie ist ein **privater** Download; Freitext
kann private Betreiberangaben enthalten und gehört nicht in öffentliche Berichte.
Keine Geräte-I/O beim Speichern, Laden, Listen oder Exportieren. HTTP-Routen und
CSRF-Anbindung folgen in #35, Formular in #36. Kein Schreibadapter, Telegramm,
Timer, Import oder Ausführungsendpunkt.

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

Mutierende Requests benötigen eine exakt gleiche `Origin`-Quelle, dürfen nicht
als `cross-site` markiert sein und müssen `X-Requested-With: SommerauerMonitor`
setzen. Dadurch werden formularbasierte und cross-origin Browseraktionen abgewiesen.
Dies ist CSRF-Schutz, kein Ersatz für Netzwerk-/Betriebssystem-Zugriffsschutz:
App nur im vertrauenswürdigen LAN/Tailscale bereitstellen.

Die API-Konfiguration ändert ausschließlich die Anzeigezeitzone. Modbus-Ziel,
Port, Unit, Profil und Datenpfad bleiben Deployment-Konfiguration und werden
niemals per Verwaltungsroute geändert. Verwaltungsaktionen benötigen einen
konfigurierten Collector; fehlt er, antwortet die Route mit HTTP 409.
