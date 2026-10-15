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
Settings-basierte Zielbindung und monotone Zeitprüfung liefert #33.

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
Die HTTP-Projektion aus #35 erhält Quelle und Alias `Anlage-aktuell`
beziehungsweise `Simulator`, ohne Host-/Port-Snapshot, lokale Pfade,
Fingerprintwerte oder rohe Exceptions.

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
CSRF-Anbindung sind mit #35 umgesetzt, Formular bleibt #36. Kein Schreibadapter,
Telegramm, Timer, Import oder Ausführungsendpunkt.

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
Leseendpunkte verwenden SQLite, Katalog und Prozessstatus; kein Refresh löst Modbus aus.

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

### Diagnose-HTTP-API (Issue #35)

`backend/diagnostics_api.py` wird vor dem Frontend-Mount eingebunden. Alle neuen
Bodymodelle verbieten Zusatzfelder; OpenAPI beschreibt auch die bereinigten
Antwortmodelle. Quelle stammt ausschließlich aus `DIAGNOSTICS_SOURCE`, Ziel
aus privaten Settings. Kein Browserfeld für Host, Port, Unit, Funktion, Anzahl,
Budget oder freie Adresse. Steuerentwürfe dürfen dagegen unverifizierte
Funktions-/Wertangaben dokumentieren, niemals ausführen.

| Methode/Pfad unter `/api/diagnostics` | Eingabe / Ergebnis |
|---|---|
| `GET /catalog` | `catalog_sha256`, `source`, `blockade`, alle 199 `entries`, getrennte `control_candidates` |
| `POST /runs` | `register_ids`, nichtleerer `purpose` mit höchstens 2000 Zeichen; **201** mit unveränderlichem Plan und Status |
| `GET /runs` | `{total, limit, offset, items}`; Standard 50, maximal 100, Offset nichtnegativ |
| `GET /runs/{id}` | Bereinigter Plan, Zustand, Budget, nächste Schritt-ID, Warte-/Restlaufzeit, Antworten/Bewertungen |
| `POST /runs/{id}/start` | Zwingend `{other_readers_stopped:true}`; Übergabe ohne Geräteanfrage |
| `POST /runs/{id}/read` | `{step_index}`; genau ein expliziter reservierter Versuch |
| `POST /runs/{id}/review` | `{step_index, verdict, observation}`; `continue`/`finish`/`anomaly`, Beobachtung Text oder `null` |
| `POST /runs/{id}/stop` | Kein Body oder `{}`; Stop-Event vor Warten auf den Moduslock |
| `POST /runs/{id}/acknowledge` | `{resolution}` mit nichtleerem Ursachentext; weder alter Lauf noch Monitoring wird gestartet |
| `GET /runs/{id}/export` | Derselbe vollständige bereinigte Lauf als privater JSON-Download |
| `GET /control-plans` | `{items}` mit jeweils neuesten Revisionen |
| `POST /control-plans` | `ControlPlanDraft`; gespeichertes Dokument mit formaler Bewertung |
| `GET /control-plans/{id}` | Aktuelle gespeicherte Revision mit Quellenstatus und Bewertung |
| `PUT /control-plans/{id}` | `{expected_revision, draft}`; neue unveränderliche Revision oder Konflikt |
| `GET /control-plans/{id}/export` | Privater bewerteter Änderungsplan, immer `execution_enabled:false` |

Außer Diagnoseplananlage liefern erfolgreiche Aktionen/GETs **200**.
`RunDocument` enthält `run_id`, `state`, `plan`, `requests_reserved`, `requests`,
`next_step_index`, `wait_remaining_seconds`, `duration_remaining_seconds`,
`source`, `target_changed` sowie UTC-Anlage-/Änderungs-/Start-/End-/Quittierzeiten
und `resolution_note`. Eine nächste Schritt-ID ist keine Leseerlaubnis:
Zustand, Zeit, Budget und Bindung werden beim expliziten Read erneut geprüft.
Restzeiten sind nur im aktiven eigenen Lauf aussagekräftig; sonst 0.

Inventareinträge tragen `register_id`, `csv_label`, `offset_zero_based`,
`sl_code_hex`, Import-/Belegstatus, bekannte Einheit und Decoderbeschreibung,
`read_support`, `write_support:"unknown"` und `decoded_value:null`.
`latest_diagnostic` ist der letzte gespeicherte Antwortbeleg des Blocks, nicht
der zuletzt angelegte Plan: `run_id`, `completed_at`, `source`,
`target_changed` und `request`. Beide Worte eines Kernblocks erhalten denselben
Beleg. `target_changed` zeigt abweichendes Ziel/Port/Unit/Quelltyp ohne
Fingerprintwert. Quellwechsel macht einen Simulatorbeleg nicht zum Gerätebeleg.
`blockade` enthält einen sicheren Fachcode oder `null`.

Antwortbelege bewahren `raw_words`, `received_bytes`, Erfassungszeit und
separate Betreiberbewertung. Nur bestätigte Kernblöcke enthalten
`decoded_signals` und `interpretation_status:"confirmed_core"`; übrige
Rohbelege bleiben `raw_only`, auch nach erfolgreichem Lesen. Keine Übernahme
in Minutenbeobachtungen. Der öffentliche Plan ersetzt den privaten
Zielsnapshot durch `target_alias`; Schema, Kataloghash, IDs, aufgelöste Blöcke,
Zweck, Quelle, feste Grenzen und Stopbedingungen bleiben erhalten.

Neue Fachfehler liefern `detail:{code,message}` mit festen deutschen Meldungen:
404 `not_found`; 422 `invalid_selection` bzw. `invalid_request`; 409
`target_not_configured`, `target_changed`, `catalog_changed`, `run_conflict`,
`read_not_due`, `collector_blocked`, `diagnostic_stop_unacknowledged`,
`revision_conflict`; 503 `catalog_unavailable` oder `storage_unavailable`.
Validierungsantworten spiegeln keine übermittelten Inhalte oder Exceptiondetails.
Die bestehende CSRF-Abweisung bleibt 403 und gilt für sämtliche Mutationen,
auch Simulatoraktionen und Offlineentwürfe.

GETs/Refresh/Downloads sind mutierungsfrei und senden keine Geräteanfrage.
Diagnoseantworten verwenden `Cache-Control: private, no-store`. Bereinigte
Downloads bleiben privat: Rohbelege und Freitexte sind keine öffentlichen
Berichte. Vertrauenswürdiges LAN/Tailscale plus CSRF ist **keine**
Authentisierung, Benutzeridentität oder Geräte-Schreibfreigabe.
Keine neue Benutzerverwaltung oder `/execute`-Route.

### Diagnosebedienung im Dashboard (Issue #36)

`App` behält Kopf, Erfassungsstatus und die bestehende Übersicht einschließlich
Verlauf und Zeitzoneneinstellung. Die Bereichswahl blendet die gemounteten
Ansichten nur aus; gespeicherte Belege und ungespeicherte Eingaben gehen beim
Wechsel nicht verloren. Ein vollständiger Browserreload lädt gespeicherten
Zustand ausschließlich per GET. Nicht gespeicherte Formulareingaben sind keine
Revision und werden nicht über einen vollständigen Browserreload gesichert.

`Diagnostics` konsumiert den Katalog ohne Zusatzabfrage am Gerät, mit 50
Einträgen je Seite, Name-/Dezimal-/Hexsuche und Belegfiltern. Auswahl umfasst
nur Register-IDs; START/SOLL bleiben getrennte nicht lesbare Kandidaten.
Unbekannte Einheiten bleiben ungeklärt. Diagnosebelege zeigen gespeicherte
Quellart, Alter und Zielabweichung; synthetische Herkunft wird auch bei alten
Läufen nie aus Hostname oder aktueller Konfiguration umgedeutet.

`ReadRuns` verwendet nur den vorhandenen HTTP-Zustandsautomaten. Planung und
Start senden keinen Read. Der aufgelöste Serverplan, Leserbestätigung,
60-s-Schranke einschließlich Speicherung, 3-s-Deadline und 600-s-Gesamtgrenze
werden vor dem Start gezeigt. Der lokale Countdown ist nur Anzeige, ohne
Diagnosepolling oder automatische Aktion. Ein expliziter Read je Schritt,
danach Pflichtbewertung; kein POST-Retry. Bei unklarem Ausgang bleiben Belege
sichtbar, Aktionen bis zum bewussten GET gesperrt. Serverkonflikte bleiben
ausdrücklich als Fehler sichtbar. Stopp/Quittierung setzen Monitoring nicht fort.

`ControlPlans` bildet alle 20 Entwurfsfelder ab. Leerangaben werden `null`;
Vor-/Test-/Rückstellwerte bleiben Text. Ein Update bindet `expected_revision`.
Konflikte erhalten Eingaben und bisherige Bewertung; der aktuelle Serverstand
wird separat geladen und erst nach ausdrücklichem Übernehmen ins Formular
gesetzt. Vor dem Verwerfen geänderter Eingaben ist eine Checkboxbestätigung
erforderlich. Export liefert die aktuelle Serverrevision, nicht zwingend die
noch angezeigte Basisrevision. Bewertung, Quellenstatus und sämtliche
unveränderlichen Blocker bleiben sichtbar; `ready_for_review` bedeutet nur
„formal bereit zur fachlichen Prüfung“, niemals ausführbar.

`api.ts` enthält den einzigen `requestJson`-Helfer. `ApiError.status` und
`detail` ergänzen den bisherigen Vertrag; `message` bleibt `HTTP <Status>`.
Nur die Diagnose zeigt die sichere serverseitige Fachmeldung aus `detail`.
Alle Mutationen verwenden unverändert den Same-Origin-/`X-Requested-With`-
Vertrag. Der lokale Vite-Proxy erhält dazu den ursprünglichen Hostheader;
Browser-Origin und CSRF-Schutz werden nicht auf das Backendziel umgeschrieben.
`format.ts` teilt ausschließlich `formatDate`/`ageLabel` mit der Übersicht,
ohne deren Zeitzonen- oder Verlaufslogik zu verändern.
