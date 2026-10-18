import json
from datetime import timedelta
from pathlib import Path

import pytest

from backend.registers import (
    CORE_PROFILE,
    CONTROL_CANDIDATES,
    READ_PROFILE,
    REGISTER_DEFINITIONS,
    SIGNAL_DEFINITIONS,
    DecodeError,
    decode_register_block,
    signed16,
    validate_operating_counter_progression,
)


@pytest.mark.parametrize(
    ("offset", "words", "signal_id", "value", "unit"),
    [
        (4102, (65,), "boiler.temperature", 65, "°C"),
        (36864, (64, 32), "buffer.top_temperature", 64, "°C"),
        (36864, (64, 32), "buffer.bottom_temperature", 32, "°C"),
        (28688, (12, 34), "boiler.operating_minutes", 17314, "min"),
    ],
)
def test_core_decoder_returns_values_with_raw_words_and_provenance(
    offset: int, words: tuple[int, ...], signal_id: str, value: int, unit: str
) -> None:
    decoded = decode_register_block(offset, words)
    signal = next(item for item in decoded if item.signal_id == signal_id)

    assert (signal.value, signal.unit, signal.offset, signal.raw_words) == (
        value,
        unit,
        offset,
        words,
    )
    assert (signal.profile_id, signal.profile_version, signal.decoder_version) == (
        "core",
        "1",
        "1",
    )
    assert signal.source == "modbus_fc03"


def test_profile_contains_only_the_three_confirmed_read_blocks() -> None:
    assert [(block.offset, block.count) for block in CORE_PROFILE] == [
        (4102, 1),
        (28688, 2),
        (36864, 2),
    ]


def test_documentation_catalog_is_not_the_active_polling_profile() -> None:
    catalog_path = Path(__file__).parents[1] / "config" / "register_catalog.json"
    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))

    assert catalog["summary"]["profile_entries"] == 199
    assert catalog["summary"]["static_unqueried"] == 194
    assert all(not register["polling_enabled"] for register in catalog["registers"])


def test_synthetic_decoder_examples_match_the_core_decoder() -> None:
    fixture_path = Path(__file__).parents[1] / "examples" / "decoder_cases.synthetic.json"
    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))

    for case in fixture["cases"]:
        if "expected_error" in case:
            decoded = decode_register_block(case["offset"], tuple(case["words"]))
            assert any(signal.error_code == case["expected_error"] for signal in decoded)
            assert all(signal.value is None for signal in decoded if signal.quality != "ok")
        elif "signed16_result" in case:
            assert signed16(case["words"][0]) == case["signed16_result"]
        else:
            actual = {
                signal.signal_id: signal.value
                for signal in decode_register_block(case["offset"], tuple(case["words"]))
            }
            assert actual == case["expected"]


def test_signed16_boundaries_and_temperature_validity() -> None:
    assert signed16(32768) == -32768
    assert signed16(65532) == -4
    assert decode_register_block(4102, (65532,))[0].value == -4

    for word in (65531, 110, 32767):
        signal, = decode_register_block(4102, (word,))
        assert signal.error_code == "invalid_temperature"
        assert signal.quality == "invalid"
        assert signal.value is None


def test_counter_accepts_1439_and_rejects_1440_minutes() -> None:
    assert decode_register_block(28688, (3, 1439))[0].value == 5759

    signal, = decode_register_block(28688, (3, 1440))
    assert signal.error_code == "invalid_counter"
    assert signal.quality == "invalid"
    assert signal.value is None


def test_counter_day_transition_is_continuous_in_total_minutes() -> None:
    before = decode_register_block(28688, (3, 1439))[0]
    after = decode_register_block(28688, (4, 0))[0]

    assert after.value - before.value == 1
    validate_operating_counter_progression(before.value, after.value, timedelta(minutes=1))


def test_counter_progression_uses_elapsed_time_and_rejects_regressions() -> None:
    validate_operating_counter_progression(100, 102, timedelta(minutes=1, seconds=1))

    with pytest.raises(DecodeError) as regression:
        validate_operating_counter_progression(100, 99, timedelta(minutes=10))
    assert regression.value.code == "invalid_counter_regression"

    with pytest.raises(DecodeError) as implausible:
        validate_operating_counter_progression(100, 103, timedelta(minutes=1))
    assert implausible.value.code == "implausible_counter_increase"

    with pytest.raises(DecodeError) as invalid_time:
        validate_operating_counter_progression(100, 100, timedelta(seconds=-1))
    assert invalid_time.value.code == "invalid_counter_time"


def test_decoder_rejects_unconfirmed_blocks_bad_counts_and_non_words() -> None:
    with pytest.raises(DecodeError) as unknown:
        decode_register_block(0xFFFF, (20,))
    assert unknown.value.code == "unknown_register_block"

    with pytest.raises(DecodeError) as wrong_count:
        decode_register_block(4102, (65, 66))
    assert wrong_count.value.code == "invalid_word_count"

    with pytest.raises(DecodeError) as invalid_word:
        decode_register_block(4102, (True,))
    assert invalid_word.value.code == "invalid_register_word"


def test_extended_profile_is_exactly_the_eighty_explicit_words() -> None:
    offsets = [block.offset + index for block in READ_PROFILE for index in range(block.count)]
    assert len(offsets) == len(set(offsets)) == len(REGISTER_DEFINITIONS) == 80
    assert set(offsets) == {definition["offset"] for definition in REGISTER_DEFINITIONS.values()}
    assert READ_PROFILE[:3] == CORE_PROFILE
    assert len(SIGNAL_DEFINITIONS) == 78
    assert sum(definition["live_confirmed"] for definition in REGISTER_DEFINITIONS.values()) == 5
    assert {
        code for code, definition in REGISTER_DEFINITIONS.items() if definition["read_to_clear"]
    } == {"12F0", "85E0", "85E1", "8BF0", "8BF1", "8E0F", "8E1F", "95E0", "95E1"}
    assert {definition["kind"] for definition in REGISTER_DEFINITIONS.values()} <= {
        "measurement", "derived", "counter", "status", "setting", "raw", "device_time",
    }


def test_control_candidates_have_no_read_block_or_signal() -> None:
    assert {candidate["code"] for candidate in CONTROL_CANDIDATES} == {"9020", "9040"}
    for candidate in CONTROL_CANDIDATES:
        assert candidate["kind"] == "control_candidate"
        assert candidate["code"] not in REGISTER_DEFINITIONS
        with pytest.raises(DecodeError) as error:
            decode_register_block(int(candidate["code"], 16), (50,))
        assert error.value.code == "unknown_register_block"


@pytest.mark.parametrize(
    ("code", "raw", "expected", "unit"),
    [
        ("1003", 0, 0, "%"),
        ("1008", 100, 100, "%"),
        ("1009", 0, 0, "°C"),
        ("1009", 79, 79, "°C"),
        ("100A", 243, 24.3, "V"),
        ("110E", 15, 1.5, "s"),
        ("1110", 0, 0.0, "s"),
        ("1112", 60, 60, "s/min"),
        ("1330", 20, 20, "s/min"),
        ("8280", 65516, -20, "°C"),
        ("82E0", 0, 0, "°C"),
        ("1100", 299, 299, "°C"),
        ("1102", 329, 329, "°C"),
        ("1200", 65532, -4, "°C"),
        ("1202", 110, 110, "°C"),
        ("8040", 0, 0, "°C"),
        ("1020", 65535, -1, "°C"),
        ("1104", 999, 999, "Rohwert"),
        ("1002", 65535, 65535, "Rohwert"),
        ("9140", 2, 2, "Rohwert"),
        ("91E0", 90, 90, "%"),
        ("95E0", 255, 255, "Rohwert"),
    ],
)
def test_source_backed_extended_decoders(code: str, raw: int, expected: int | float, unit: str) -> None:
    signal, = decode_register_block(int(code, 16), (raw,))
    assert signal.signal_id == f"modbus.{code}"
    assert signal.value == expected
    assert signal.unit == unit
    assert signal.raw_words == (raw,)
    assert (signal.profile_id, signal.profile_version, signal.decoder_version) == ("extended", "1", "1")


@pytest.mark.parametrize(
    ("code", "raw"),
    [
        ("1009", 80), ("1009", 110), ("1009", 65535),
        ("1200", 110), ("1200", 65531),
        ("8280", 50), ("8280", 65486),
        ("82E0", 35), ("82E0", 65526),
        ("1100", 330), ("1102", 65526),
        ("8020", 110), ("8030", 110), ("8B00", 110),
        ("8E00", 110), ("9060", 110),
    ],
)
def test_extended_temperature_errors_are_not_replaced_with_zero(code: str, raw: int) -> None:
    signal, = decode_register_block(int(code, 16), (raw,))
    assert signal.error_code == "invalid_temperature"
    assert signal.quality == "invalid"
    assert signal.value is None
    assert signal.raw_words == (raw,)


@pytest.mark.parametrize(("code", "raw", "error_code"), [
    ("1020", 65486, "missing_weather"), ("1022", 65486, "missing_weather"),
    ("1021", 65535, "missing_weather"), ("1023", 65535, "missing_weather"),
    ("100A", 0, "invalid_voltage"),
])
def test_explicit_missing_values_reject_measurements(code: str, raw: int, error_code: str) -> None:
    signal, = decode_register_block(int(code, 16), (raw,))
    assert signal.error_code == error_code
    assert signal.quality == ("unavailable" if error_code == "missing_weather" else "invalid")
    assert signal.value is None
    assert signal.error_message


def test_stoker_pair_uses_days_and_validated_remaining_minutes() -> None:
    signal, = decode_register_block(0x7012, (3, 1439))
    assert signal.signal_id == "stoker.operating_minutes"
    assert signal.value == 5759
    assert signal.unit == "min"
    assert signal.profile_id == "extended"
    assert REGISTER_DEFINITIONS["7012"]["signal_id"] == REGISTER_DEFINITIONS["7013"]["signal_id"]
    for words in ((3, 1440), (3, 65535)):
        signal, = decode_register_block(0x7012, words)
        assert signal.error_code == "invalid_counter"
        assert signal.quality == "invalid"
        assert signal.value is None
    with pytest.raises(DecodeError):
        decode_register_block(0x7013, (1,))
    with pytest.raises(DecodeError):
        decode_register_block(0x7012, (1,))


def test_ambiguous_temperature_initial_values_are_explained() -> None:
    assert "Reset" in REGISTER_DEFINITIONS["82E0"]["description"]
    assert "299" in REGISTER_DEFINITIONS["1100"]["description"]


@pytest.mark.parametrize("words", [(110, 32), (64, 110)])
def test_buffer_channels_are_validated_independently(words):
    signals = decode_register_block(36864, words)
    for signal, word in zip(signals, words, strict=True):
        assert signal.raw_words == words
        assert signal.quality == ("invalid" if word == 110 else "ok")
        assert signal.value == (None if word == 110 else word)
        assert signal.error_code == ("invalid_temperature" if word == 110 else None)


def test_buffer_mapping_stays_active_and_in_the_original_core_block() -> None:
    top, bottom = decode_register_block(0x9000, (64, 32))
    assert (top.signal_id, top.value, top.unit) == ("buffer.top_temperature", 64, "°C")
    assert (bottom.signal_id, bottom.value, bottom.unit) == ("buffer.bottom_temperature", 32, "°C")
    assert CORE_PROFILE[2].offset == 0x9000
    assert CORE_PROFILE[2].count == 2
    assert CORE_PROFILE[2].signal_ids == ("buffer.top_temperature", "buffer.bottom_temperature")
    assert REGISTER_DEFINITIONS["9001"]["module_status"] == "active"
    for code in ("9061", "9141", "91E1", "95E1"):
        assert REGISTER_DEFINITIONS[code]["module_status"] == "inactive"
        assert REGISTER_DEFINITIONS[code]["signal_id"] == f"modbus.{code}"


@pytest.mark.parametrize("code", ("1106", "1107", "1108", "1300", "1301", "1302", "91E0", "91E1"))
@pytest.mark.parametrize("word", (0, 10, 50, 90, 100, 101, 65535))
def test_display_percent_metadata_does_not_scale_or_restrict_register_words(code, word) -> None:
    signal, = decode_register_block(int(code, 16), (word,))
    assert signal.unit == "%"
    assert signal.value == word
    assert signal.raw_words == (word,)
    assert signal.quality == "ok"
    assert signal.error_code is None
    assert REGISTER_DEFINITIONS[code]["decoder"] == "raw"


def test_touch_confirmation_is_independent_of_activity_core_provenance_and_interval() -> None:
    assert sum(row["verification_status"] == "operator_touch_confirmed" for row in REGISTER_DEFINITIONS.values()) == 79
    assert REGISTER_DEFINITIONS["10D1"]["verification_status"] == "source_only"
    assert REGISTER_DEFINITIONS["8E00"]["module_status"] == "inactive"
    assert REGISTER_DEFINITIONS["8E00"]["verification_status"] == "operator_touch_confirmed"
    assert REGISTER_DEFINITIONS["8E00"]["live_confirmed"] is False
    assert REGISTER_DEFINITIONS["8E00"]["interval_seconds"] == 300
    assert REGISTER_DEFINITIONS["9001"]["interval_seconds"] == 60
