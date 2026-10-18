"""Explicit read profiles and source-backed decoders; no write operations."""

from dataclasses import dataclass
from datetime import timedelta
from typing import Final


PROFILE_ID: Final = "core"
PROFILE_VERSION: Final = "1"
DECODER_VERSION: Final = "1"
SOURCE: Final = "modbus_fc03"


class DecodeError(ValueError):
    """A register block does not satisfy the documented core data contract."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True, slots=True)
class RegisterBlock:
    offset: int
    count: int
    signal_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class DecodedSignal:
    signal_id: str
    value: int | float | None
    unit: str
    offset: int
    raw_words: tuple[int, ...]
    profile_id: str = PROFILE_ID
    profile_version: str = PROFILE_VERSION
    decoder_version: str = DECODER_VERSION
    source: str = SOURCE
    quality: str = "ok"
    error_code: str | None = None
    error_message: str | None = None


CORE_PROFILE: Final = (
    RegisterBlock(4102, 1, ("boiler.temperature",)),
    RegisterBlock(28688, 2, ("boiler.operating_minutes",)),
    RegisterBlock(36864, 2, ("buffer.top_temperature", "buffer.bottom_temperature")),
)

# Each additional word is isolated: some FC03 reads clear device-side state.
_REGISTER_ROWS = (
    ("1006", "Kessel_Ist", "°C", "measurement", "water_temperature", "Kesseltemperatur; bestätigter Anlagenkanal."),
    ("7010", "Betrieb_Tage", "min", "counter", "days_minutes", "Betriebszeit: Tage und Restminuten, kein 32-Bit-Wortpaar."),
    ("7011", "Betrieb_Min", "min", "counter", "days_minutes", "Restminuten des Betriebszeitzählers (0–1439)."),
    ("7012", "Stoker_Tage", "min", "counter", "days_minutes", "Softwaregezählte Stoker-Freigabezeit; kein Nachweis mechanischer Bewegung oder Pelletmasse."),
    ("7013", "Stoker_Min", "min", "counter", "days_minutes", "Restminuten der Stoker-Freigabezeit (0–1439); Snapshot und Resetpolitik nicht bestätigt."),
    ("1001", "Betriebsstatus", "Rohwert", "status", "boiler_state", "Software-Steuerungszustand des Kessels: 0 Aus, 2 Regelbetrieb, 3 Gluterhaltung, 4 Zündung; Zusatzbit 0x8000 als Mindestlaufzeit-Kennzeichen. Keine unabhängige Flammen- oder Aktorrückmeldung; anlagenseitiger Abgleich offen."),
    ("1000", "Betriebsart", "Rohwert", "setting", "boiler_mode", "Betriebsart der Software: 0 Dauerbetrieb, 1 Uhrzeitbetrieb, 2 Boiler-/Mehrkesselbetrieb (gemeinsamer Lesecode), 3 Uhr-/Boilerbetrieb, 6 Handbetrieb, 7 Automatik, 9 Speicherregelung, 10 Extern-Start. Kein Ein-/Aus- oder Flammennachweis; Lesekodierung nicht als Schreibkodierung verwenden."),
    ("1007", "Kessel_Soll", "°C", "setting", "boiler_target_temperature", "Eingestellte Kessel-Basis-Solltemperatur in ganzen °C (60–90); keine Sensormessung. Nur lesend; keine Parameteränderung."),
    ("9020", "BO01_SOLL", "°C", "setting", "buffer_threshold_temperature", "Pufferkanal 1: SOLL-Basisparameter in ganzen °C (10–90), bei Zweifühlerbetrieb Bezug zum unteren Fühler. Zeit-/Wettermodifikatoren können wirksame Schwellen verändern; keine Sensormessung oder Schreibfreigabe."),
    ("9040", "BO01_START", "°C", "setting", "buffer_threshold_temperature", "Pufferkanal 1: START-Basisparameter in ganzen °C (10–90), Bezug zum oberen Fühler. Keine globale Startsperre; weitere Anforderungen und Modifikatoren möglich. Nur lesend, kein autonomer Rückfall nach Änderungen nachgewiesen."),
    ("1005", "Leistung_Max", "%", "setting", "power_limit", "Eingestellte maximale interne Leistungsregelgröße im Normalbetrieb (30–100 %); keine thermische Leistung in kW."),
    ("1012", "Reinigung", "Rohwert", "status", "cleaning_state", "Software-Reinigungszustand: 0 inaktiv, 1 aktiv ohne Motor-Ein-Kennzeichen, 2 aktiv mit Motor-Ein-Kennzeichen. Keine unabhängige mechanische Rückmeldung."),
    ("1013", "Reinig_Interv", "min", "counter", "raw", "Interner Reinigungsintervallzähler in min; softwareseitig leistungsabhängig gewichtet erhöht. Kein Restzeit-Countdown und keine gemessene mechanische Laufzeit."),
    ("1002", "Fehler_Min", "Rohwert", "status", "raw", "Kleinste Fehlernummer der aktuell geführten Fehlerliste; 0 bedeutet Liste leer, nicht garantierte physische Fehlerfreiheit. Kein Zähler, keine Minuten und kein vollständiges Fehlerjournal."),
    ("1003", "Leistung_Ist", "%", "derived", "raw", "Interne Istgröße der Leistungsregelung in Prozent; keine gemessene thermische Leistung in kW."),
    ("1008", "Leistung_Soll", "%", "derived", "raw", "Aktuelle interne Leistungssollgröße in Prozent, kein editierbarer Sollparameter dieses Codes."),
    ("1009", "CPU_Temp", "°C", "measurement", "cpu_temperature", "Elektroniktemperatur; 80 °C ist Sensorgrenze/Fehlerersatz, 110 Initialwert."),
    ("100A", "Versorgung_Raw", "V", "measurement", "voltage", "Elektronikversorgung in Zehntelvolt, kein ADC-Rohwort; 0 ist Resetwert und wird nicht als Messung ausgegeben."),
    ("1010", "Asche_Ist", "min", "counter", "raw", "Rücksetzbarer Asche-Wartungszähler auf Stoker-Minutenbasis; keine Aschemasse."),
    ("1020", "Wetter_Temp", "°C", "derived", "weather_temperature", "Gespeicherte Wettertemperatur jetzt, kein lokaler Außenfühler; Frische und Herkunft unbekannt; −50 bedeutet fehlend."),
    ("1021", "Wetter_Status", "Rohwert", "status", "weather_status", "Gespeicherter Wetterzustand, kein Verbindungsstatus; −1 bedeutet fehlend; Frische unbekannt."),
    ("1022", "Wetter_T_5h", "°C", "derived", "weather_temperature", "Gespeicherte Wettertemperatur für +5 h; Frische unbekannt; −50 bedeutet fehlend."),
    ("1023", "Wetter_S_5h", "Rohwert", "status", "weather_status", "Gespeicherter Wetterzustand für +5 h; −1 bedeutet fehlend; Frische unbekannt."),
    ("10D1", "Leistungsstufe", "Rohwert", "setting", "raw", "Index der ausgewählten Leistungsstufe, keine kW-Angabe."),
    ("1100", "Abgas_Ist", "°C", "measurement", "exhaust_temperature", "Abgastemperatur; gleiche Sensorquelle wie 1102. 299 kann Initialwert oder echter Messwert sein und wird nicht verworfen."),
    ("1101", "Abgas_Soll", "°C", "derived", "signed", "Aktueller Abgas-Regelsollwert; 0 außerhalb Regelbetrieb ist gültig."),
    ("1102", "Abgas_Sensor", "°C", "measurement", "exhaust_temperature", "Identischer ausgewerteter Temperaturwert wie 1100, kein zusätzlicher Sensor oder elektrischer Rohwert. 299 ist als Initialwert nicht von echter Temperatur unterscheidbar."),
    ("1104", "Lambda_Ist", "Rohwert", "raw", "raw", "Ganzzahliger Lambda-Sonden-/Regelwert ohne physikalische Einheit; keine belegte Umrechnung in Lambda oder O₂-Prozent."),
    ("1105", "Lambda_Soll", "Rohwert", "derived", "raw", "Berechneter ganzzahliger Lambda-Regelsollwert derselben internen Skala ohne physikalische Einheit; 0 außerhalb Regelbetrieb gültig."),
    ("1106", "V1_Ist", "%", "derived", "raw", "Aktuelle intern geführte Saugzugansteuerung in Prozent; keine gemessene Drehzahl."),
    ("1107", "V1_Soll", "%", "derived", "raw", "Saugzug-Sollansteuerung in Prozent; außerhalb Regelbetrieb 0, auch wenn ein Nachlauf anderweitig aktiv ist."),
    ("1108", "V1_Drehz_Raw", "%", "raw", "raw", "Modulgelieferte Saugzug-Drehzahlrückmeldung, am Touch in Prozent angezeigt. Bezugsdrehzahl und Umrechnung in U/min nicht belegt; 0 auch bei Messsperre möglich."),
    ("110E", "Foerderzeit", "s", "derived", "tenths", "Berechnete Fördertaktlänge in 100-ms-Schritten, keine gemessene Förderdauer."),
    ("1110", "Pausenzeit", "s", "derived", "tenths", "Berechnete Pausentaktlänge in 100-ms-Schritten; 0 ist regulär möglich."),
    ("1112", "Einschub_Ist", "s/min", "derived", "raw", "Berechnete Einschubregelgröße, kein Massenstrom; Sonderbetrieb kann 60 liefern."),
    ("1113", "Einschub_Soll", "s/min", "derived", "raw", "Einschub-Regelsoll; außerhalb Regelbetrieb ist 0 gültig."),
    ("1200", "Ruecklauf_Ist", "°C", "measurement", "water_temperature", "Rücklauftemperatursensor; 110 ist Initial-/Fehlergrenze."),
    ("1202", "Ruecklauf_Soll", "°C", "derived", "signed", "Wirksamer Rücklauf-Regelsollwert, nicht einstellbarer Basisparameter."),
    ("12F0", "RL_Protokoll", "Rohwert", "status", "raw", "Rücklauf-Modul-Ausgangsbits; Modulzuordnung konfigurationsabhängig."),
    ("1300", "V1_Nennlast", "%", "setting", "raw", "Saugzugansteuerung bei Nennlast in Prozent für die gewählte Leistungsstufe; im Prüfbetrieb eigener Prüfparameter, keine Drehzahlmessung."),
    ("1301", "V1_Teillast", "%", "setting", "raw", "Saugzugansteuerung bei Teillast in Prozent für die gewählte Leistungsstufe; im Prüfbetrieb eigener Prüfparameter."),
    ("1302", "V1_Zuendung", "%", "setting", "raw", "Saugzugansteuerung für die Zündung in Prozent für die gewählte Leistungsstufe; kein historischer Messwert."),
    ("1320", "Lambda_Nenn", "Rohwert", "setting", "raw", "Ganzzahliger Lambda-Nennlastparameter ohne physikalische Einheit; leistungsstufenabhängig, im Prüfbetrieb Prüfparameter."),
    ("1321", "Lambda_Teil", "Rohwert", "setting", "raw", "Ganzzahliger Lambda-Teillastparameter ohne physikalische Einheit; leistungsstufenabhängig, im Prüfbetrieb Prüfparameter."),
    ("1323", "Lambda_Stop", "Rohwert", "setting", "raw", "Stoppschwelle derselben internen Lambda-Skala: Ist ≥ Schwelle sperrt die normale Materialförderung, nicht die gesamte Heizung. Sonderzweig Gluterhaltung kann die Förderung trotzdem freigeben."),
    ("1330", "Einschub_Nenn", "s/min", "setting", "raw", "Einschub-Nennlastparameter, keine Pelletmassenmessung."),
    ("1331", "Einschub_Teil1", "s/min", "derived", "raw", "Berechneter Einschub-Teillastwert, regulär ganzzahlig Nennlast × 30 / 100; im Prüfbetrieb eigener Parameter."),
    ("1332", "Einschub_Teil2", "s/min", "derived", "raw", "Identische Lesequelle wie 1331; derselbe Teillastwert ist auch der gekoppelte Zündtakt-Einschub. Kein unabhängiger Parameter und kein Wert der letzten Zündung."),
    ("7002", "Wochentag", "Rohwert", "device_time", "raw", "Steuerungsuhr: Montag 0 bis Sonntag 6; kein Empfangszeitstempel."),
    ("7003", "Tag", "Rohwert", "device_time", "raw", "Kalendertag der Steuerungsuhr; kein atomarer Datumssnapshot."),
    ("7004", "Monat", "Rohwert", "device_time", "raw", "Kalendermonat der Steuerungsuhr."),
    ("7005", "Jahr", "Rohwert", "device_time", "raw", "Vollständiges Kalenderjahr der Steuerungsuhr, nicht zweistellig umrechnen."),
    ("7006", "Uhrzeit_Min", "min", "device_time", "raw", "Minuten seit Mitternacht der Steuerungsuhr, kein HHMM; Zeitzone unbekannt."),
    ("8000", "HK01_Aktiv", "Rohwert", "setting", "raw", "Ausbaukonfiguration Heizkreis 1: 0 aus, 1 aktiv, 2 mit Raumgerät, 3 Rücklaufanhebung. Am Touch 0/1 beobachtet; kein Pumpenstatus oder Nachweis momentaner Wärmeanforderung."),
    ("8001", "HK02_Aktiv", "Rohwert", "setting", "raw", "Ausbaukonfiguration Heizkreis 2: 0 aus, 1 aktiv, 2 mit Raumgerät. Am Touch 0/1 beobachtet; kein Pumpenstatus oder Nachweis momentaner Wärmeanforderung."),
    ("8020", "HK01_Ist", "°C", "measurement", "water_temperature", "Isttemperatur des Vorlauffühlers von Heizkreis 1."),
    ("8021", "HK02_Ist", "°C", "measurement", "water_temperature", "Isttemperatur des Vorlauffühlers von Heizkreis 2."),
    ("8030", "HK01_Speis", "°C", "measurement", "water_temperature", "Temperatur der konfigurierten Wärmequelle von Heizkreis 1, kein zusätzlicher Vorlauf- oder Zulauffühler; konkrete Quellenzuordnung nicht unabhängig geprüft."),
    ("8031", "HK02_Speis", "°C", "measurement", "water_temperature", "Temperatur der konfigurierten Wärmequelle von Heizkreis 2, kein zusätzlicher Vorlauf- oder Zulauffühler; konkrete Quellenzuordnung nicht unabhängig geprüft."),
    ("8040", "HK01_Soll", "°C", "derived", "signed", "Aktuell berechnete Vorlauf-Solltemperatur von Heizkreis 1, unter anderem aus Heizkurve, Absenkung und Zeitprogramm; kein bloß fest eingestellter Wunschwert."),
    ("8041", "HK02_Soll", "°C", "derived", "signed", "Aktuell berechnete Vorlauf-Solltemperatur von Heizkreis 2; abhängig von Regelbetrieb und Programm, nicht bloß ein fester Wunschwert."),
    ("8280", "Aussen_Ist", "°C", "measurement", "outdoor_temperature", "Lokaler Außenfühler; Grenzen −50/50, 50 Initial-/Fehlerwert; kein Wetterdienst."),
    ("82E0", "HK01_Raum", "°C", "measurement", "room_temperature", "Zugeordneter Raumfühler HK01; 0 kann Reset oder echte Temperatur sein und bleibt gültig; Zuordnung unbestätigt."),
    ("82E1", "HK02_Raum", "°C", "measurement", "room_temperature", "Zugeordneter Raumfühler HK02; 0 ist nicht sicher von Reset unterscheidbar und bleibt gültig."),
    ("85E0", "HK01_Protok", "Rohwert", "status", "raw", "Ausgangsbits des Heizkreismoduls HK01."),
    ("85E1", "HK02_Protok", "Rohwert", "status", "raw", "Ausgangsbits des Heizkreismoduls HK02."),
    ("8B00", "NM01_Ist", "°C", "measurement", "water_temperature", "Netzmischerfühler 1; Modul laut Betreiber inaktiv. Lesbare Werte sind kein Nachweis einer aktiven Anlagenmessung."),
    ("8B01", "NM02_Ist", "°C", "measurement", "water_temperature", "Netzmischerfühler 2; Modul laut Betreiber inaktiv. Lesbare Werte sind kein Nachweis einer aktiven Anlagenmessung."),
    ("8BF0", "NM01_Protok", "Rohwert", "status", "raw", "Ausgangsbits des Netzmischermoduls 01."),
    ("8BF1", "NM02_Protok", "Rohwert", "status", "raw", "Ausgangsbits des Netzmischermoduls 02."),
    ("8E00", "SP1_Fuehl1", "°C", "measurement", "water_temperature", "Speichermodul 1, Fühler 1; laut Betreiber inaktiv, nicht der bestätigte Puffer oben."),
    ("8E01", "SP1_Fuehl2", "°C", "measurement", "water_temperature", "Speichermodul 1, Fühler 2; laut Betreiber inaktiv, keine aktive Anlagenmessung belegt."),
    ("8E0F", "SP1_Protokoll", "Rohwert", "status", "raw", "Ausgangsbefehle des laut Betreiber inaktiven Speichermoduls 1."),
    ("8E10", "SP2_Fuehl1", "°C", "measurement", "water_temperature", "Speichermodul 2, Fühler 1; laut Betreiber inaktiv, keine aktive Anlagenmessung belegt."),
    ("8E11", "SP2_Fuehl2", "°C", "measurement", "water_temperature", "Speichermodul 2, Fühler 2; laut Betreiber inaktiv, keine aktive Anlagenmessung belegt."),
    ("8E1F", "SP2_Protokoll", "Rohwert", "status", "raw", "Ausgangsbefehle des laut Betreiber inaktiven Speichermoduls 2."),
    ("8E40", "SP01_Ladezust", "Rohwert", "derived", "raw", "Temperaturbasierter Speicherindex 0–100, keine gemessene Energie. Speichermodul 1 laut Betreiber inaktiv; 0 auch bei Deaktivierung/Reset. Separate Logik, nicht der bestätigte BO-Puffer."),
    ("8E41", "SP02_Ladezust", "Rohwert", "derived", "raw", "Temperaturbasierter Speicherindex 0–100, keine gemessene Energie. Speichermodul 2 laut Betreiber inaktiv; 0 auch bei Deaktivierung/Reset. Separate Logik, nicht der bestätigte BO-Puffer."),
    ("9000", "BO01_Ist", "°C", "measurement", "water_temperature", "Bestätigter Anlagenkanal: Puffer oben, kein separater Boiler."),
    ("9001", "BO02_Ist", "°C", "measurement", "water_temperature", "Bestätigter Anlagenkanal: Puffer unten."),
    ("9060", "BO01_Speis", "°C", "measurement", "water_temperature", "Temperatur der konfigurierten Wärmequelle von Puffer 1; kein eigener Zulauffühler, Startwert oder Pumpenfreigabeparameter."),
    ("9061", "BO02_Speis", "°C", "measurement", "water_temperature", "Temperatur der konfigurierten Wärmequelle des eigenständigen Pufferkanals 2; laut Betreiber inaktiv. Nicht automatisch die Quelle des aktiven unteren Fühlers 9001."),
    ("9140", "BO01_PT100", "Rohwert", "setting", "raw", "Fühlerbetriebsart Puffer 1: 0 ein PT100, 1 zwei PT100, 2 Start/Stopp. Keine Temperatur und kein PT100-Rohmesswert."),
    ("9141", "BO02_PT100", "Rohwert", "setting", "raw", "Fühlerbetriebsart des eigenständigen Pufferkanals 2: 0 ein PT100, 1 zwei PT100, 2 Start/Stopp; laut Betreiber inaktiv. Kein Rohmesswert und nicht automatisch Betriebsart des unteren Fühlers 9001."),
    ("91E0", "BO01_Ladezust", "%", "derived", "raw", "Am Touch als Prozent angezeigter Ladezustand von Puffer 1. Die ausgewertete Software berechnet temperatur- und schwellwertabhängige Anzeigestufen 10/50/90; keine kontinuierliche oder kalorimetrische Energiemessung."),
    ("91E1", "BO02_Ladezust", "%", "derived", "raw", "Prozentanzeige des eigenständigen Pufferkanals 2, laut Betreiber inaktiv. Berechnete Anzeigestufen 10/50/90, keine Energieprozentmessung; eigene Berechnung am Folgeindex, nicht Ladezustand des unteren Fühlers 9001."),
    ("95E0", "BO01_Protok", "Rohwert", "status", "raw", "Gesammelte Ausgangsbefehle des Puffer-Softwarekanals 1; keine physische Rückmeldung von Pumpen oder Aktoren."),
    ("95E1", "BO02_Protok", "Rohwert", "status", "raw", "Gesammelte Ausgangsbefehle des eigenständigen Pufferkanals 2, laut Betreiber inaktiv; nicht der Zustand des aktiven unteren Fühlers 9001."),
)
_CORE_IDS = {
    "1006": "boiler.temperature",
    "7010": "boiler.operating_minutes",
    "7011": "boiler.operating_minutes",
    "9000": "buffer.top_temperature",
    "9001": "buffer.bottom_temperature",
}
_CLEAR_CODES = frozenset(("12F0", "85E0", "85E1", "8BF0", "8BF1", "8E0F", "8E1F", "95E0", "95E1"))
_INACTIVE_CODES = frozenset((
    "8B00", "8B01", "8BF0", "8BF1",
    "8E00", "8E01", "8E0F", "8E10", "8E11", "8E1F", "8E40", "8E41",
    "9061", "9141", "91E1", "95E1",
))
_ACTIVE_CODES = frozenset(("1006", "9000", "9001", "9060", "9140", "91E0", "95E0"))
# Anzeigenamen sind unabhängig von den unveränderten CSV-Importnamen.
_DISPLAY_LABELS = {
    "1006": "Kesseltemperatur",
    "7010": "Anlagen-Betriebszähler", "7011": "Anlagen-Betriebszähler",
    "7012": "Stoker-Freigabezeit", "7013": "Stoker-Freigabezeit",
    "1001": "Kessel – Steuerungszustand",
    "1000": "Kessel – Betriebsart", "1007": "Kessel – Basis-Solltemperatur",
    "9020": "Puffer 1 – SOLL-Basisparameter", "9040": "Puffer 1 – START-Basisparameter",
    "1005": "Leistungsregelung – Maximalparameter",
    "1012": "Reinigung – Softwarezustand", "1013": "Reinigung – gewichteter Intervallzähler",
    "1002": "Fehlernummer – kleinster Listeneintrag",
    "1003": "Leistungsregelung – Istwert", "1008": "Leistungsregelung – Sollwert",
    "1009": "Elektroniktemperatur", "100A": "Elektronikversorgung",
    "1010": "Asche-Wartungszähler",
    "1020": "Wettertemperatur – jetzt", "1021": "Wetterzustand – jetzt",
    "1022": "Wettertemperatur – in 5 Stunden", "1023": "Wetterzustand – in 5 Stunden",
    "10D1": "Ausgewählte Leistungsstufe",
    "1100": "Abgastemperatur", "1101": "Abgastemperatur – Regelsollwert",
    "1102": "Abgastemperatur – zweiter Registerzugang",
    "1104": "Lambda-Regelwert – Ist", "1105": "Lambda-Regelwert – Soll",
    "1106": "Saugzug – aktuelle Ansteuerung", "1107": "Saugzug – Sollansteuerung",
    "1108": "Saugzug – Drehzahlrückmeldung",
    "110E": "Fördertakt – berechnete Einschaltzeit", "1110": "Fördertakt – berechnete Pausenzeit",
    "1112": "Einschub – aktueller Regelwert", "1113": "Einschub – Regelsollwert",
    "1200": "Rücklauftemperatur", "1202": "Rücklauf – Regelsolltemperatur",
    "12F0": "Rücklauf – gesammelte Ausgangsbefehle",
    "1300": "Saugzug – Nennlastparameter", "1301": "Saugzug – Teillastparameter",
    "1302": "Saugzug – Zündparameter",
    "1320": "Lambda – Nennlastparameter", "1321": "Lambda – Teillastparameter",
    "1323": "Lambda – Stoppschwelle der Materialförderung",
    "1330": "Einschub – Nennlastparameter", "1331": "Einschub – Teillastwert",
    "1332": "Einschub – Teillast-/Zündtaktwert",
    "7002": "Steuerungsuhr – Wochentag", "7003": "Steuerungsuhr – Kalendertag",
    "7004": "Steuerungsuhr – Monat", "7005": "Steuerungsuhr – Jahr",
    "7006": "Steuerungsuhr – Minuten seit Mitternacht",
    "8000": "Heizkreis 1 – Ausbaukonfiguration", "8001": "Heizkreis 2 – Ausbaukonfiguration",
    "8020": "Heizkreis 1 – Vorlauftemperatur", "8021": "Heizkreis 2 – Vorlauftemperatur",
    "8030": "Heizkreis 1 – Wärmequellentemperatur", "8031": "Heizkreis 2 – Wärmequellentemperatur",
    "8040": "Heizkreis 1 – berechnete Vorlauf-Solltemperatur", "8041": "Heizkreis 2 – berechnete Vorlauf-Solltemperatur",
    "8280": "Außentemperatur",
    "82E0": "Heizkreis 1 – Raumtemperatur", "82E1": "Heizkreis 2 – Raumtemperatur",
    "85E0": "Heizkreis 1 – gesammelte Ausgangsbefehle", "85E1": "Heizkreis 2 – gesammelte Ausgangsbefehle",
    "8B00": "Netzmischer 1 – Temperatur", "8B01": "Netzmischer 2 – Temperatur",
    "8BF0": "Netzmischer 1 – gesammelte Ausgangsbefehle", "8BF1": "Netzmischer 2 – gesammelte Ausgangsbefehle",
    "8E00": "Speichermodul 1 – Fühler 1", "8E01": "Speichermodul 1 – Fühler 2",
    "8E0F": "Speichermodul 1 – gesammelte Ausgangsbefehle",
    "8E10": "Speichermodul 2 – Fühler 1", "8E11": "Speichermodul 2 – Fühler 2",
    "8E1F": "Speichermodul 2 – gesammelte Ausgangsbefehle",
    "8E40": "Speichermodul 1 – berechneter Speicherindex", "8E41": "Speichermodul 2 – berechneter Speicherindex",
    "9000": "Puffer oben", "9001": "Puffer unten",
    "9060": "Puffer 1 – Wärmequellentemperatur", "9061": "Pufferkanal 2 – Wärmequellentemperatur",
    "9140": "Puffer 1 – Fühlerbetriebsart", "9141": "Pufferkanal 2 – Fühlerbetriebsart",
    "91E0": "Puffer 1 – Ladezustandsanzeige", "91E1": "Pufferkanal 2 – Ladezustandsanzeige",
    "95E0": "Puffer 1 – gesammelte Ausgangsbefehle", "95E1": "Pufferkanal 2 – gesammelte Ausgangsbefehle",
}
REGISTER_DEFINITIONS: Final[dict[str, dict]] = {}
SIGNAL_DEFINITIONS: Final[dict[str, dict]] = {}
for _code, _name, _unit, _kind, _decoder, _description in _REGISTER_ROWS:
    _signal_id = _CORE_IDS.get(_code, "stoker.operating_minutes" if _code in ("7012", "7013") else f"modbus.{_code}")
    _clear = _code in _CLEAR_CODES
    if _clear:
        _description += " Gesammelte Befehls-Bitmaske seit dem vorherigen Lesen, beim Lesen gelöscht; konkurrierende Leser verändern das Ergebnis. 0 beweist nicht, dass alle Ausgänge aus sind. Kein verlässlicher momentaner Aktorzustand, keine physische Rückmeldung und kein Störungsjournal."
    _definition = {
        "offset": int(_code, 16), "name": _name, "signal_id": _signal_id,
        "unit": _unit, "description": _description, "kind": _kind,
        "live_confirmed": _code in _CORE_IDS, "read_to_clear": _clear, "decoder": _decoder,
        "interval_seconds": 60 if _code in _CORE_IDS else 300,
        "verification_status": "source_only" if _code in ("10D1", "1001", "1000", "1007", "9020", "9040", "1005", "1012", "1013") else "operator_touch_confirmed",
        "module_status": "inactive" if _code in _INACTIVE_CODES else "active" if _code in _ACTIVE_CODES else "unknown",
    }
    REGISTER_DEFINITIONS[_code] = _definition
    SIGNAL_DEFINITIONS.setdefault(_signal_id, {
        "label": _DISPLAY_LABELS[_code],
        **{key: _definition[key] for key in (
            "unit", "kind", "live_confirmed", "read_to_clear", "description", "interval_seconds",
            "verification_status", "module_status",
        )},
    })

CONTROL_CANDIDATES: Final = [
    {
        "code": code, "name": name, "kind": "control_candidate",
        "live_confirmed": False, "read_to_clear": False,
        "description": f"Basisparameter {name} für Pufferkanal 1 ist jetzt lesend importierbar; nicht notwendigerweise die wirksame Schaltschwelle. Eine spätere Schreibnutzung ist weiterhin nur Kandidat: keine Schreibfreigabe, keine Ausführung und kein belegter automatischer Rückfall.",
    }
    for code, name in (("9020", "SOLL"), ("9040", "START"))
]

READ_PROFILE: Final = CORE_PROFILE + (
    RegisterBlock(0x7012, 2, ("stoker.operating_minutes",)),
) + tuple(
    RegisterBlock(definition["offset"], 1, (definition["signal_id"],))
    for code, definition in REGISTER_DEFINITIONS.items()
    if code not in _CORE_IDS and code not in ("7012", "7013")
)
_BLOCKS_BY_OFFSET: Final = {block.offset: block for block in READ_PROFILE}


def signed16(raw: int) -> int:
    """Interpret one unsigned 16-bit word as two's-complement signed16."""
    _validate_word(raw)
    return raw if raw < 0x8000 else raw - 0x10000


def decode_register_block(offset: int, words: tuple[int, ...] | list[int]) -> tuple[DecodedSignal, ...]:
    """Decode exactly one explicitly listed FC03 block; never infer other channels."""
    block = _BLOCKS_BY_OFFSET.get(offset)
    if block is None:
        raise DecodeError("unknown_register_block", f"Offset {offset} is not in the read profile")

    raw_words = tuple(words)
    if len(raw_words) != block.count:
        raise DecodeError(
            "invalid_word_count",
            f"Offset {offset} requires {block.count} words, got {len(raw_words)}",
        )
    for word in raw_words:
        try:
            _validate_word(word)
        except ValueError as exc:
            raise DecodeError("invalid_register_word", str(exc)) from exc

    decoded = []
    for index, signal_id in enumerate(block.signal_ids):
        unit = SIGNAL_DEFINITIONS[signal_id]["unit"]
        value = None
        quality = "ok"
        error_code = error_message = None
        try:
            if offset in (28688, 0x7012):
                days, remaining_minutes = raw_words
                if remaining_minutes >= 1440:
                    raise DecodeError(
                        "invalid_counter",
                        f"Restminuten des Betriebszählers außerhalb 0..1439: {remaining_minutes}",
                    )
                value = days * 1440 + remaining_minutes
            elif offset in (4102, 36864):
                value = _validated_temperature(signed16(raw_words[index]))
            else:
                definition = REGISTER_DEFINITIONS[f"{offset:04X}"]
                value = _decode_extended_word(raw_words[0], definition["decoder"])
        except DecodeError as exc:
            quality = "unavailable" if exc.code == "missing_weather" else "invalid"
            error_code, error_message = exc.code, str(exc)
        decoded.append(DecodedSignal(
            signal_id, value, unit, offset, raw_words,
            profile_id=PROFILE_ID if block in CORE_PROFILE else "extended",
            quality=quality, error_code=error_code, error_message=error_message,
        ))
    return tuple(decoded)


def validate_operating_counter_progression(
    previous_minutes: int,
    current_minutes: int,
    elapsed: timedelta,
) -> None:
    """Reject counter rollback or growth beyond elapsed wall time plus minute quantization.

    One additional minute is allowed for the unknown phase of the device's minute
    boundary. This does not infer a counter reset/rollover policy or heating duty cycle.
    """
    if elapsed < timedelta(0):
        raise DecodeError("invalid_counter_time", "Zeitabstand des Betriebszählers ist negativ")
    if previous_minutes < 0 or current_minutes < 0:
        raise DecodeError("invalid_counter", "Betriebsminuten dürfen nicht negativ sein")
    if current_minutes < previous_minutes:
        raise DecodeError("invalid_counter_regression", "Betriebszähler ist rückwärts gelaufen")

    elapsed_whole_minutes = elapsed // timedelta(minutes=1)
    maximum_increase = elapsed_whole_minutes + 1
    if current_minutes - previous_minutes > maximum_increase:
        raise DecodeError(
            "implausible_counter_increase",
            "Betriebszähler ist stärker gestiegen als die verstrichene Zeit erlaubt",
        )


def _validated_temperature(value: int) -> int:
    if value == 110 or not -5 < value < 110:
        raise DecodeError("invalid_temperature", f"Kerntemperatur außerhalb -5..110 °C (Grenzen ausgeschlossen): {value} °C")
    return value


def _decode_extended_word(raw: int, decoder: str) -> int | float:
    if decoder == "raw":
        return raw
    if decoder == "boiler_mode":
        if raw not in (0, 1, 2, 3, 6, 7, 9, 10):
            raise DecodeError("unknown_boiler_mode", "Unbekannte Betriebsart des Kessels")
        return raw
    if decoder == "cleaning_state":
        if raw not in (0, 1, 2):
            raise DecodeError("unknown_cleaning_state", "Unbekannter Software-Reinigungszustand")
        return raw
    if decoder == "power_limit":
        if not 30 <= raw <= 100:
            raise DecodeError("invalid_power_limit", "Maximale Leistungsregelgröße außerhalb 30..100 %")
        return raw
    if decoder == "boiler_state":
        if raw not in (0, 2, 3, 4, 0x8002, 0x8003, 0x8004):
            raise DecodeError("unknown_boiler_state", "Unbekannter Steuerungszustand des Kessels")
        return raw
    if decoder == "tenths":
        return raw / 10
    value = signed16(raw)
    if decoder in ("boiler_target_temperature", "buffer_threshold_temperature"):
        lower = 60 if decoder == "boiler_target_temperature" else 10
        if not lower <= value <= 90:
            raise DecodeError("invalid_temperature_setting", f"Temperatur-Basisparameter außerhalb {lower}..90 °C: {value}")
        return value
    if decoder == "signed":
        return value
    if decoder == "weather_status":
        if value == -1:
            raise DecodeError("missing_weather", "Kein gespeicherter Wetterzustand")
        return value
    if decoder == "weather_temperature":
        if value == -50:
            raise DecodeError("missing_weather", "Keine gespeicherte Wettertemperatur")
        return value
    if decoder == "voltage":
        if raw == 0:
            raise DecodeError("invalid_voltage", "Versorgung 0 ist ein Resetwert")
        return raw / 10
    if decoder == "cpu_temperature":
        if not 0 <= raw < 80:
            raise DecodeError("invalid_temperature", f"CPU-Temperatur außerhalb 0..79 °C: {raw}")
        return raw
    limits = {
        "water_temperature": (-5, 110),
        "outdoor_temperature": (-50, 50),
        "room_temperature": (-10, 35),
        "exhaust_temperature": (-5, 330),
    }
    lower, upper = limits[decoder]
    if not lower < value < upper:
        raise DecodeError("invalid_temperature", f"Temperatur außerhalb Kanalgrenzen ({lower}, {upper}): {value} °C")
    return value


def _validate_word(value: int) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 0xFFFF:
        raise ValueError(f"Register word must be an integer in 0..65535, got {value!r}")
