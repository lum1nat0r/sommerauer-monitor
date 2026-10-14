import json
from datetime import timedelta
from pathlib import Path

import pytest

from backend.registers import (
    CORE_PROFILE,
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
            with pytest.raises(DecodeError) as error:
                decode_register_block(case["offset"], tuple(case["words"]))
            assert error.value.code == case["expected_error"]
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
        with pytest.raises(DecodeError, match="Core temperature") as error:
            decode_register_block(4102, (word,))
        assert error.value.code == "invalid_temperature"


def test_counter_accepts_1439_and_rejects_1440_minutes() -> None:
    assert decode_register_block(28688, (3, 1439))[0].value == 5759

    with pytest.raises(DecodeError) as error:
        decode_register_block(28688, (3, 1440))
    assert error.value.code == "invalid_counter"


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
        decode_register_block(33408, (20,))
    assert unknown.value.code == "unknown_register_block"

    with pytest.raises(DecodeError) as wrong_count:
        decode_register_block(4102, (65, 66))
    assert wrong_count.value.code == "invalid_word_count"

    with pytest.raises(DecodeError) as invalid_word:
        decode_register_block(4102, (True,))
    assert invalid_word.value.code == "invalid_register_word"
