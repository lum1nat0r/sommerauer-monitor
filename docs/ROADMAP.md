# Roadmap und Arbeitsreihenfolge

Stand 14.10.2026. Alle Implementierungs-Issues sind zunächst offen.
Dieses Repository enthält Dokumentation; noch keine implementierte Monitoring-App.

Für ein Arbeitspaket zuerst AGENTS, Plan und die im Issue genannten Quellen lesen.
Abhängigkeiten sind fachliche Voraussetzungen, keine bloße Sortierung.
Fehlender Gerätezugang blockiert nur die betreffenden Live-Nachweise, nicht Offline-Arbeit.

## Version 1

| Issue | Aufgabe | Voraussetzungen |
|---|---|---|
| [#1](https://github.com/lum1nat0r/sommerauer-monitor/issues/1) | Version 1: Modbus-Monitoring auf Unraid umsetzen | – |
| [#2](https://github.com/lum1nat0r/sommerauer-monitor/issues/2) | Projektgrundlage, Konfiguration und Offline-CI einrichten | – |
| [#3](https://github.com/lum1nat0r/sommerauer-monitor/issues/3) | Geprüftes Kernprofil und reine Registerdecoder implementieren | #2 |
| [#4](https://github.com/lum1nat0r/sommerauer-monitor/issues/4) | Strikten FC03-Leseclient und lokalen Modbus-Simulator bauen | #2, #3 |
| [#5](https://github.com/lum1nat0r/sommerauer-monitor/issues/5) | SQLite-Historie, Ereignisse, Migrationen und Sicherung implementieren | #2, #3 |
| [#6](https://github.com/lum1nat0r/sommerauer-monitor/issues/6) | Einen zentralen Sammler mit begrenztem Laufmodus implementieren | #4, #5 |
| [#7](https://github.com/lum1nat0r/sommerauer-monitor/issues/7) | Persistente Fehlerzustände und begrenzte Wiederverbindung umsetzen | #4, #5, #6 |
| [#8](https://github.com/lum1nat0r/sommerauer-monitor/issues/8) | Lokale API, Konfiguration, Erfassungssteuerung und CSV-Export liefern | #5, #6, #7 |
| [#9](https://github.com/lum1nat0r/sommerauer-monitor/issues/9) | Dashboard mit Live-Übersicht, Verläufen und Fehleranzeige bauen | #8 |
| [#10](https://github.com/lum1nat0r/sommerauer-monitor/issues/10) | Docker-Paket und Unraid-Template erstellen | #2, #8, #9 |
| [#11](https://github.com/lum1nat0r/sommerauer-monitor/issues/11) | Außentemperatur, Fehlercode und Leistungsregister schrittweise prüfen **optional** | #3, #4, #7 |
| [#12](https://github.com/lum1nat0r/sommerauer-monitor/issues/12) | Monitoring-Ende-zu-Ende und Wiederherstellung offline abnehmen | #7, #8, #9, #10 |
| [#13](https://github.com/lum1nat0r/sommerauer-monitor/issues/13) | Kernregister am aktuellen Ziel prüfen und Betrieb gestuft in Betrieb nehmen | #12 |
| [#14](https://github.com/lum1nat0r/sommerauer-monitor/issues/14) | Version 0.1 veröffentlichen und Betreiberübergabe abschließen | #12, #13 |

Die Erstversion kann mit den Kernwerten abgenommen werden, wenn Zusatzregister
noch nicht belegbar sind. Das Zusatz-Issue bleibt dann ausdrücklich offen.

## Spätere Roadmap

| Issue | Aufgabe | Voraussetzungen |
|---|---|---|
| [#15](https://github.com/lum1nat0r/sommerauer-monitor/issues/15) | Später: Messwerte per MQTT Discovery in Home Assistant bereitstellen | #14 |
| [#16](https://github.com/lum1nat0r/sommerauer-monitor/issues/16) | Später: Solarthermie-Datenquelle und tatsächliche Kennzahlen klären | #14 |
| [#17](https://github.com/lum1nat0r/sommerauer-monitor/issues/17) | Später: Externe Solarprognose aufnehmen und offline bewerten | #14, #16 |
| [#18](https://github.com/lum1nat0r/sommerauer-monitor/issues/18) | Später: START/SOLL-Stellweg mit autonomem Rückfall nachweisen | #14 |

Die Rückfall-Untersuchung benötigt kein fertiges Prognosemodell.
Ein aktiver Steuerungsversuch wäre ein separater konkreter Änderungsplan
mit Betreibererlaubnis; die Roadmap erteilt diese nicht.

## Statuspflege

- Issues enthalten Abnahmekriterien und Prüfungen. Nur belegte Arbeit abhaken.
- Umsetzung/PR mit Issue verknüpfen; tatsächliche Prüfungen und Grenzen nennen.
- Neue Entscheidungen in ENTSCHEIDUNGEN, neue Befunde in RESULTS festhalten.
- Keine technischen Annahmen als Live-Befund oder Herstellerfreigabe ausgeben.
