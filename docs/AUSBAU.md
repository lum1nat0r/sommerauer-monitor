# Spätere Erweiterungen

Diese Arbeit gehört zur Roadmap nach Version 1. Jetzt nur stabile Signalnamen,
Herkunft, Qualitäts-/Zeitinformationen und klare Modulgrenzen berücksichtigen.

## MQTT / Home Assistant

Vorhandenen Broker verwenden, keine zweite Modbus-Erfassung. Optionaler Adapter
publiziert validierte Messwerte mit stabilen Unique IDs, Gerätenamen, Einheiten,
passenden Klassen und MQTT Discovery. Verfügbarkeit/Last Will und Datenalter
abbilden; nach Neustart keine alten Werte als frisch publizieren. Brokerausfall
darf lokale Erfassung/DB nicht stoppen. Zugangsdaten privat und redigiert halten.
Nachrichten sind Telemetrie, keine MQTT-Steuerbefehle für die Heizung.
Quellen: [MQTT](https://www.home-assistant.io/integrations/mqtt/),
[MQTT Sensor](https://www.home-assistant.io/integrations/sensor.mqtt/).

## Tatsächliche Solarthermie-Messungen

Laut bisheriger Projektdokumentation Hanazeder FP-2; keine bestätigte digitale
Anbindung. Verfügbare Hardware/Schnittstelle, Sensoren, Durchfluss/Wärmemengenzähler
und Einheiten erst klären. Zwei Pufferfühler liefern allein keinen gemessenen
Solarertrag. Gemessene Wärme, modellierte Wärme und Wetterdaten separat kennzeichnen.
Hardwarezugriffe/-änderungen sind keine reine App-Implementierung.

Ein gemeinsamer Puffer versorgt Heizkörper, Fußbodenheizung und Warmwasser.
Früher dokumentiertes Volumen 725 l ist eine Projektangabe, keine durch Codex
ausgemessene Größe; beim Modellaufbau prüfen. Schichtung und Entnahmen beachten.

## Externe Prognoseschnittstelle

Das Modell kommt später/extern; hier keinen Wetteranbieter oder Algorithmus
vorweg festlegen. Vorgesehene Felder: Schemaversion, Anbieter/Modellversion,
Erstellungszeit `issued_at`, zugrunde liegende Messzeit, Gültigkeit, Zeitzone/UTC,
Qualität, Unsicherheitsbeschreibung und geordneter zeitlicher Verlauf.

Erwartete nutzbare Wärme in kWh oder absolute obere/untere Puffertemperaturen
klar unterscheiden; Temperaturanstieg in K getrennt. Annahme ohne Pelletnachladung
ausdrücklich mitführen, wenn daraus ein Solaraufschub abgeleitet werden soll.
Standort, Ausrichtung/Neigung, Kollektor-/Pufferdaten, Verbrauch/Verluste und
Modellparameter bleiben lokal konfigurierbar. Originale ausgegebene Prognosen
archivieren, statt sie beim späteren Vergleich durch aktualisierte zu ersetzen.

Validierung: endliche Zahlen, Einheiten, Offset-Zeitstempel, geordnete Intervalle,
Lücken/Horizont, Datenalter, unbekannte Qualität. Wetter/PV-Ertrag nicht automatisch
als Solarthermie-Ertrag behandeln. Unsicherheit nicht als erfundene Wahrscheinlichkeit
ausgeben; anhand geeigneter Verläufe bewerten.

## Vorhandener privater Offline-Entwurf als fachliche Vorarbeit

Im Übergabeprojekt existiert ein rein lokaler Entscheider ohne Netzwerk/Aktor.
Er ist nicht Bestandteil der neuen App und nicht produktiv kalibriert. Sein
bisheriger Vertrag ist für spätere Implementierer hier vollständig fachlich skizziert:

- `schema_version: 1`; Herkunft `synthetischer_test` oder `beobachtung`.
- `telemetry`: `observed_at`, Qualität, `top_c`, `bottom_c`, Kesselzustand
  `idle/running/unknown`, andere/dringende Wärmeanforderung als bool oder null.
- `forecast.kind: puffer_oben_ohne_pellets`, Qualität, `issued_at`,
  `based_on_observed_at` und lückenlose Intervalle mit `from`, `until`,
  `top_min_lower_c`, `top_end_lower_c`. Konservative Untergrenzen müssen vom
  validierten Modell stammen; ein Punktwert ist kein nachgewiesenes Intervallminimum.
- `window`: unveränderter `started_at`, fester `release_at`, `already_proposed`.
- `policy`: `assumptions_validated`, `minimum_top_c`, `target_top_c`,
  `max_cooling_k_per_hour`, `recovery_minutes`, `entry_margin_k`,
  `max_delay_minutes`, `max_telemetry_age_s`, `max_forecast_age_s`,
  `max_interval_minutes`. Keine produktiven Standardwerte festgelegt.
- Reservegrenze = minimum_top_c + max_cooling_k_per_hour * recovery_minutes / 60.
  Aktueller Wert und alle konservativen Intervallminima müssen darüber liegen;
  erstmaliger Einstieg zusätzlich mit entry_margin_k. Ziel am release_at erreichen;
  Prognosehorizont bis release_at + recovery_minutes, keine Extrapolation.
- Ergebnis: `aufschub_vorschlagen`, `normalregelung` oder `lauf_beibehalten`,
  Grund/Detail und begrenztes `valid_until`; stets `actuation_allowed: false`.

Ein Kesselzustand oder Wärmebedarf lässt sich aus den fünf Kernregistern nicht
zuverlässig ableiten. Unbekannte Voraussetzungen blockieren positive Empfehlungen.
Die ursprüngliche reine Funktion speichert keinen Episodenzustand: ein späterer
Aufrufer muss Neustarts und wiederholt angelegte Fenster gegen unbegrenzte Verlängerung
absichern. Reale Annahmen sind noch nicht validiert. Laufende Kesselzyklen erhalten.
`valid_until` ist kein Rückfalltimer in der Heizung. [Separate Rückfallanforderung](START_RUECKFALL.md).
