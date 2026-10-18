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
    ("1002", "Fehler_Min", "Rohwert", "status", "raw", "Aktuelle Fehlerkennung, keine Minuten und kein vollständiges Fehlerjournal."),
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
    ("1102", "Abgas_Sensor", "°C", "measurement", "exhaust_temperature", "Abgassensor; gleiche Quelle wie 1100. 299 ist als Initialwert nicht von echter Temperatur unterscheidbar."),
    ("1104", "Lambda_Ist", "Rohwert", "raw", "raw", "Istgröße der Lambdaregelung; physikalische Lambda-/O₂-Skalierung nicht belegt."),
    ("1105", "Lambda_Soll", "Rohwert", "derived", "raw", "Lambda-Regelsoll; Skalierung offen, 0 außerhalb Regelbetrieb gültig."),
    ("1106", "V1_Ist", "Rohwert", "derived", "raw", "Gebläse-Regleristgröße; weder Prozent noch Drehzahl belegt."),
    ("1107", "V1_Soll", "Rohwert", "derived", "raw", "Gebläse-Reglersoll; Skalierung offen, 0 außerhalb Regelbetrieb gültig."),
    ("1108", "V1_Drehz_Raw", "Rohwert", "raw", "raw", "Gebläsedrehzahl-Rohwert; Umrechnung in U/min nicht belegt."),
    ("110E", "Foerderzeit", "s", "derived", "tenths", "Berechnete Fördertaktlänge in 100-ms-Schritten, keine gemessene Förderdauer."),
    ("1110", "Pausenzeit", "s", "derived", "tenths", "Berechnete Pausentaktlänge in 100-ms-Schritten; 0 ist regulär möglich."),
    ("1112", "Einschub_Ist", "s/min", "derived", "raw", "Berechnete Einschubregelgröße, kein Massenstrom; Sonderbetrieb kann 60 liefern."),
    ("1113", "Einschub_Soll", "s/min", "derived", "raw", "Einschub-Regelsoll; außerhalb Regelbetrieb ist 0 gültig."),
    ("1200", "Ruecklauf_Ist", "°C", "measurement", "water_temperature", "Rücklauftemperatursensor; 110 ist Initial-/Fehlergrenze."),
    ("1202", "Ruecklauf_Soll", "°C", "derived", "signed", "Wirksamer Rücklauf-Regelsollwert, nicht einstellbarer Basisparameter."),
    ("12F0", "RL_Protokoll", "Rohwert", "status", "raw", "Rücklauf-Modul-Ausgangsbits; Modulzuordnung konfigurationsabhängig."),
    ("1300", "V1_Nennlast", "Rohwert", "setting", "raw", "Gebläse-Nennlastparameter; Skalierung offen, keine Drehzahlmessung."),
    ("1301", "V1_Teillast", "Rohwert", "setting", "raw", "Gebläse-Teillastparameter; Skalierung offen."),
    ("1302", "V1_Zuendung", "Rohwert", "setting", "raw", "Gebläse-Zündparameter; Skalierung offen."),
    ("1320", "Lambda_Nenn", "Rohwert", "setting", "raw", "Lambda-Nennlastparameter; physikalische Skalierung offen."),
    ("1321", "Lambda_Teil", "Rohwert", "setting", "raw", "Lambda-Teillastparameter; physikalische Skalierung offen."),
    ("1323", "Lambda_Stop", "Rohwert", "setting", "raw", "Lambda-Abschaltparameter, keine Statusmeldung; Skalierung offen."),
    ("1330", "Einschub_Nenn", "s/min", "setting", "raw", "Einschub-Nennlastparameter, keine Pelletmassenmessung."),
    ("1331", "Einschub_Teil1", "s/min", "derived", "raw", "Abgeleiteter Einschub-Teillastwert; im Prüfbetrieb eigener Parameter."),
    ("1332", "Einschub_Teil2", "s/min", "derived", "raw", "Identische Lesequelle wie 1331, kein unabhängiger zweiter Messwert."),
    ("7002", "Wochentag", "Rohwert", "device_time", "raw", "Steuerungsuhr: Montag 0 bis Sonntag 6; kein Empfangszeitstempel."),
    ("7003", "Tag", "Rohwert", "device_time", "raw", "Kalendertag der Steuerungsuhr; kein atomarer Datumssnapshot."),
    ("7004", "Monat", "Rohwert", "device_time", "raw", "Kalendermonat der Steuerungsuhr."),
    ("7005", "Jahr", "Rohwert", "device_time", "raw", "Vollständiges Kalenderjahr der Steuerungsuhr, nicht zweistellig umrechnen."),
    ("7006", "Uhrzeit_Min", "min", "device_time", "raw", "Minuten seit Mitternacht der Steuerungsuhr, kein HHMM; Zeitzone unbekannt."),
    ("8000", "HK01_Aktiv", "Rohwert", "setting", "raw", "Ausbaukonfiguration HK01 (0–3), kein Pumpenstatus."),
    ("8001", "HK02_Aktiv", "Rohwert", "setting", "raw", "Ausbaukonfiguration HK02 (0–2), kein Pumpenstatus."),
    ("8020", "HK01_Ist", "°C", "measurement", "water_temperature", "Vorlauffühler HK01; reale Modulverfügbarkeit unbestätigt."),
    ("8021", "HK02_Ist", "°C", "measurement", "water_temperature", "Vorlauffühler HK02; reale Modulverfügbarkeit unbestätigt."),
    ("8030", "HK01_Speis", "°C", "measurement", "water_temperature", "Temperatur der zugeordneten Energiequelle HK01, kein eigener Zähler; Zuordnung unbestätigt."),
    ("8031", "HK02_Speis", "°C", "measurement", "water_temperature", "Temperatur der zugeordneten Energiequelle HK02; Zuordnung unbestätigt."),
    ("8040", "HK01_Soll", "°C", "derived", "signed", "Aktueller Heizkreis-Regelsollwert HK01, keine reine Konfiguration."),
    ("8041", "HK02_Soll", "°C", "derived", "signed", "Aktueller Heizkreis-Regelsollwert HK02."),
    ("8280", "Aussen_Ist", "°C", "measurement", "outdoor_temperature", "Lokaler Außenfühler; Grenzen −50/50, 50 Initial-/Fehlerwert; kein Wetterdienst."),
    ("82E0", "HK01_Raum", "°C", "measurement", "room_temperature", "Zugeordneter Raumfühler HK01; 0 kann Reset oder echte Temperatur sein und bleibt gültig; Zuordnung unbestätigt."),
    ("82E1", "HK02_Raum", "°C", "measurement", "room_temperature", "Zugeordneter Raumfühler HK02; 0 ist nicht sicher von Reset unterscheidbar und bleibt gültig."),
    ("85E0", "HK01_Protok", "Rohwert", "status", "raw", "Ausgangsbits des Heizkreismoduls HK01."),
    ("85E1", "HK02_Protok", "Rohwert", "status", "raw", "Ausgangsbits des Heizkreismoduls HK02."),
    ("8B00", "NM01_Ist", "°C", "measurement", "water_temperature", "Netzmischerfühler 01; Modulverfügbarkeit unbestätigt."),
    ("8B01", "NM02_Ist", "°C", "measurement", "water_temperature", "Netzmischerfühler 02; Modulverfügbarkeit unbestätigt."),
    ("8BF0", "NM01_Protok", "Rohwert", "status", "raw", "Ausgangsbits des Netzmischermoduls 01."),
    ("8BF1", "NM02_Protok", "Rohwert", "status", "raw", "Ausgangsbits des Netzmischermoduls 02."),
    ("8E00", "SP1_Fuehl1", "°C", "measurement", "water_temperature", "Speichermodul 1 Fühler 1, nicht automatisch der bestätigte Puffer oben."),
    ("8E01", "SP1_Fuehl2", "°C", "measurement", "water_temperature", "Speichermodul 1 Fühler 2; Anlagenzuordnung unbestätigt."),
    ("8E0F", "SP1_Protokoll", "Rohwert", "status", "raw", "Ausgangsbits des Speichermoduls 1."),
    ("8E10", "SP2_Fuehl1", "°C", "measurement", "water_temperature", "Speichermodul 2 Fühler 1; Anlagenzuordnung unbestätigt."),
    ("8E11", "SP2_Fuehl2", "°C", "measurement", "water_temperature", "Speichermodul 2 Fühler 2; Anlagenzuordnung unbestätigt."),
    ("8E1F", "SP2_Protokoll", "Rohwert", "status", "raw", "Ausgangsbits des Speichermoduls 2."),
    ("8E40", "SP01_Ladezust", "Rohwert", "derived", "raw", "Temperaturbasierter Speicherindex 0–100, keine gemessene Energie; 0 auch bei Deaktivierung/Reset."),
    ("8E41", "SP02_Ladezust", "Rohwert", "derived", "raw", "Temperaturbasierter Speicherindex 0–100, keine Energieprozentmessung; 0 auch bei Deaktivierung/Reset."),
    ("9000", "BO01_Ist", "°C", "measurement", "water_temperature", "Bestätigter Anlagenkanal: Puffer oben, kein separater Boiler."),
    ("9001", "BO02_Ist", "°C", "measurement", "water_temperature", "Bestätigter Anlagenkanal: Puffer unten."),
    ("9060", "BO01_Speis", "°C", "measurement", "water_temperature", "Temperatur der zugeordneten Energiequelle Softwarekanal 01; Zuordnung unbestätigt."),
    ("9061", "BO02_Speis", "°C", "measurement", "water_temperature", "Temperatur der zugeordneten Energiequelle Softwarekanal 02; Zuordnung unbestätigt."),
    ("9140", "BO01_PT100", "Rohwert", "setting", "raw", "Sensormodus Kanal 01: 0 ein PT100, 1 zwei PT100, 2 Start/Stopp; keine Temperatur."),
    ("9141", "BO02_PT100", "Rohwert", "setting", "raw", "Sensormodus Kanal 02: 0 ein PT100, 1 zwei PT100, 2 Start/Stopp; keine Temperatur."),
    ("91E0", "BO01_Ladezust", "Rohwert", "derived", "raw", "Berechnete Ladezustandsklasse 10/50/90, kein Energieprozentwert; abhängig von Modus und Schaltschwellen."),
    ("91E1", "BO02_Ladezust", "Rohwert", "derived", "raw", "Berechnete Klasse 10/50/90; im Mehrfühlermodus weiterer Kanal beteiligt; keine Energieprozentmessung."),
    ("95E0", "BO01_Protok", "Rohwert", "status", "raw", "Ausgangsbits des Boiler-/Puffer-Softwarekanals 01; Hardwarezuordnung unbestätigt."),
    ("95E1", "BO02_Protok", "Rohwert", "status", "raw", "Ausgangsbits des Boiler-/Puffer-Softwarekanals 02; Hardwarezuordnung unbestätigt."),
)
_CORE_IDS = {
    "1006": "boiler.temperature",
    "7010": "boiler.operating_minutes",
    "7011": "boiler.operating_minutes",
    "9000": "buffer.top_temperature",
    "9001": "buffer.bottom_temperature",
}
_CLEAR_CODES = frozenset(("12F0", "85E0", "85E1", "8BF0", "8BF1", "8E0F", "8E1F", "95E0", "95E1"))
REGISTER_DEFINITIONS: Final[dict[str, dict]] = {}
SIGNAL_DEFINITIONS: Final[dict[str, dict]] = {}
for _code, _name, _unit, _kind, _decoder, _description in _REGISTER_ROWS:
    _signal_id = _CORE_IDS.get(_code, "stoker.operating_minutes" if _code in ("7012", "7013") else f"modbus.{_code}")
    _clear = _code in _CLEAR_CODES
    if _clear:
        _description += " Achtung: Lesen leert die aufgesammelten Modul-Ausgangsbits; konkurrierende Leser verändern das Ergebnis. Kein Störungsjournal."
    _definition = {
        "offset": int(_code, 16), "name": _name, "signal_id": _signal_id,
        "unit": _unit, "description": _description, "kind": _kind,
        "live_confirmed": _code in _CORE_IDS, "read_to_clear": _clear, "decoder": _decoder,
        "interval_seconds": 60 if _code in _CORE_IDS else 300,
    }
    REGISTER_DEFINITIONS[_code] = _definition
    SIGNAL_DEFINITIONS.setdefault(_signal_id, {
        "label": "Stoker-Betriebszeit" if _signal_id == "stoker.operating_minutes" else _name.replace("_", " "),
        **{key: _definition[key] for key in ("unit", "kind", "live_confirmed", "read_to_clear", "description", "interval_seconds")},
    })
for _signal_id, _label in (
    ("boiler.temperature", "Kesseltemperatur"),
    ("boiler.operating_minutes", "Anlagen-Betriebszähler"),
    ("buffer.top_temperature", "Puffer oben"),
    ("buffer.bottom_temperature", "Puffer unten"),
):
    SIGNAL_DEFINITIONS[_signal_id]["label"] = _label

CONTROL_CANDIDATES: Final = [
    {
        "code": code, "name": name, "kind": "control_candidate",
        "live_confirmed": False, "read_to_clear": False,
        "description": f"Statisch belegter Basisparameter {name} für Softwarekanal 01; nicht notwendigerweise die wirksame Schaltschwelle. Nur sichtbarer Steuerungskandidat: keine Schreibfreigabe, keine Ausführung und kein belegter automatischer Rückfall.",
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
    if decoder == "tenths":
        return raw / 10
    value = signed16(raw)
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
