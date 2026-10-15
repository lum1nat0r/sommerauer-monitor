import hashlib
import json
import subprocess
import sys
from collections.abc import Mapping
from dataclasses import FrozenInstanceError
from datetime import timedelta
from importlib import resources
from pathlib import Path

import pytest

import backend.catalog as catalog_module
from backend.catalog import (
    CONTROL_CANDIDATES,
    CatalogSelectionError,
    CatalogUnavailable,
    build_read_blocks,
    load_catalog,
)
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


@pytest.fixture
def isolated_catalog(tmp_path, monkeypatch):
    """Ausschließlich eine synthetische Ressource, kein Geräte-/Deploymentziel."""
    raw = resources.files("backend").joinpath("resources/register_catalog.json").read_bytes()
    resource_dir = tmp_path / "resources"
    resource_dir.mkdir()
    path = resource_dir / "register_catalog.json"
    path.write_bytes(raw)
    catalog_module._catalog_snapshot.cache_clear()
    monkeypatch.setattr(catalog_module.resources, "files", lambda package: tmp_path)
    yield path, json.loads(raw)
    catalog_module._catalog_snapshot.cache_clear()


def _plain(value):
    if isinstance(value, Mapping):
        return {key: _plain(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_plain(item) for item in value]
    return value


def test_catalog_preserves_all_evidence_and_file_hash_from_another_cwd(tmp_path, monkeypatch):
    raw = resources.files("backend").joinpath("resources/register_catalog.json").read_bytes()
    document = json.loads(raw)
    monkeypatch.chdir(tmp_path)
    catalog = load_catalog()

    assert catalog.sha256 == hashlib.sha256(raw).hexdigest()
    assert catalog.sha256 != document["profile_sha256"]
    assert _plain(catalog.metadata) == {
        key: value for key, value in document.items() if key != "registers"
    }
    assert [_plain(entry.fields) for entry in catalog.entries.values()] == document["registers"]
    assert all(entry.polling_enabled is False for entry in catalog.entries.values())
    raw_entries = [entry for entry in catalog.entries.values() if entry.read_support == "documented_raw"]
    assert len(raw_entries) == 194
    assert all(entry.unit is None and entry.decoded_value is None for entry in raw_entries)
    assert all(entry.write_support == "unknown" for entry in catalog.entries.values())
    assert catalog.entries[4102].unit == "degC"
    assert catalog.entries[4104].csv_label == "Leistung_Soll"
    assert catalog.entries[4104].evidence_status == "static_only_unqueried"


def test_catalog_snapshot_is_deeply_immutable_and_never_hot_reloads(isolated_catalog):
    path, document = isolated_catalog
    document["registers"][0]["additional_evidence"] = {"notes": ["synthetisch"]}
    path.write_text(json.dumps(document), encoding="utf-8")
    catalog = load_catalog()
    entry = catalog.entries[4098]
    with pytest.raises(FrozenInstanceError):
        catalog.sha256 = "changed"
    with pytest.raises(TypeError):
        catalog.entries[4098] = catalog.entries[4099]
    with pytest.raises(FrozenInstanceError):
        entry.fields = {}
    with pytest.raises(TypeError):
        entry.fields["evidence_status"] = "live_and_display_confirmed"
    with pytest.raises(TypeError):
        entry.fields["additional_evidence"]["notes"][0] = "changed"
    with pytest.raises(TypeError):
        catalog.metadata["summary"]["profile_entries"] = 0
    with pytest.raises(TypeError):
        catalog.metadata["known_read_blocks"][0]["count"] = 2
    block = build_read_blocks(["register:28689"])[0]
    with pytest.raises(FrozenInstanceError):
        block.count = 1

    path.unlink()
    assert load_catalog() is catalog
    assert build_read_blocks(["register:4098"])[0].count == 1


@pytest.mark.parametrize(
    ("ids", "expected"),
    [
        (["register:33408", "register:4099", "register:4098"],
         [(4098, 1), (4099, 1), (33408, 1)]),
        (["register:28689"], [(28688, 2)]),
        (["register:28688", "register:28689", "register:28688"], [(28688, 2)]),
        (["register:36865"], [(36864, 2)]),
        (["register:36865", "register:36864", "register:4102"], [(4102, 1), (36864, 2)]),
    ],
)
def test_catalog_selection_resolves_exact_sorted_blocks(ids, expected):
    assert [(block.offset, block.count) for block in build_read_blocks(ids)] == expected


@pytest.mark.parametrize("ids", [
    [], ["register:4103"], ["register:65535"], ["foreign:4098"],
    ["control:buffer.start"], ["control:buffer.target"], ["register:36928"],
    ["register:36896"], ["4098"], ["register:04098"], ["register:+4098"],
    ["register:0x1002"], ["register:4098\n"], [4098],
    ["register:4098", "register:4099", "register:4102", "register:33408"],
])
def test_catalog_selection_rejects_non_catalog_ids_and_excess_blocks(ids):
    with pytest.raises(CatalogSelectionError) as error:
        build_read_blocks(ids)
    assert error.value.code == "invalid_register_selection"


def test_every_catalog_word_is_selectable_without_changing_evidence():
    catalog = load_catalog()
    core_words = {
        word for block in CORE_PROFILE for word in range(block.offset, block.offset + block.count)
    }
    for offset, entry in catalog.entries.items():
        evidence = entry.evidence_status
        blocks = build_read_blocks([entry.register_id])
        if offset in core_words:
            expected = next(
                block for block in CORE_PROFILE
                if block.offset <= offset < block.offset + block.count
            )
            assert [(block.offset, block.count) for block in blocks] == [
                (expected.offset, expected.count)
            ]
        else:
            assert [(block.offset, block.count) for block in blocks] == [(offset, 1)]
            assert entry.read_support == "documented_raw"
        assert entry.evidence_status == evidence


@pytest.mark.parametrize("fault", [
    "missing", "empty", "malformed", "not_object", "no_registers", "empty_registers",
    "schema_version", "bool_schema", "unit_id", "read_function", "duplicate",
    "bool_offset", "negative_offset", "large_offset", "float_offset", "hex",
    "word_count", "bool_words", "missing_core_word", "missing_blocks", "extra_block",
    "bool_block_offset", "bool_block_count",
])
def test_bad_resource_blocks_only_diagnostics_and_remains_blocked(isolated_catalog, fault):
    path, document = isolated_catalog
    original = path.read_bytes()
    first = document["registers"][0]
    if fault == "missing":
        path.unlink()
    elif fault == "empty":
        path.write_bytes(b"")
    elif fault == "malformed":
        path.write_bytes(b"{")
    else:
        if fault == "not_object":
            document = []
        elif fault == "no_registers":
            del document["registers"]
        elif fault == "empty_registers":
            document["registers"] = []
        elif fault in ("schema_version", "unit_id", "read_function"):
            document[fault] = 2
        elif fault == "bool_schema":
            document["schema_version"] = True
        elif fault == "duplicate":
            document["registers"].append(dict(first))
        elif fault.endswith("_offset") and fault != "bool_block_offset":
            first["offset_zero_based"] = {
                "bool_offset": True, "negative_offset": -1,
                "large_offset": 65536, "float_offset": 4098.0,
            }[fault]
        elif fault == "hex":
            first["sl_code_hex"] = "1003"
        elif fault in ("word_count", "bool_words"):
            first["register_words"] = True if fault == "bool_words" else 2
        elif fault == "missing_core_word":
            document["registers"] = [
                record for record in document["registers"] if record["offset_zero_based"] != 28689
            ]
        elif fault == "missing_blocks":
            del document["known_read_blocks"]
        elif fault == "extra_block":
            document["known_read_blocks"].append({"offset": 4098, "count": 2})
        elif fault == "bool_block_offset":
            document["known_read_blocks"][0]["offset"] = True
        elif fault == "bool_block_count":
            document["known_read_blocks"][0]["count"] = True
        path.write_text(json.dumps(document), encoding="utf-8")

    for operation in (load_catalog, lambda: build_read_blocks(["register:4102"])):
        with pytest.raises(CatalogUnavailable) as error:
            operation()
        assert error.value.code == "catalog_unavailable"
    assert decode_register_block(4102, (65,))[0].value == 65
    assert decode_register_block(28688, (1, 2))[0].value == 1442

    # Eine ersetzte Datei ist kein Hot-Reload und umgeht keinen Fehlerstopp.
    path.write_bytes(original)
    with pytest.raises(CatalogUnavailable):
        load_catalog()


def test_control_candidates_cannot_become_fc03_reads():
    expected = {
        "control:buffer.start": ("9040", 36928),
        "control:buffer.target": ("9020", 36896),
    }
    assert set(CONTROL_CANDIDATES) == set(expected)
    for candidate_id, candidate in CONTROL_CANDIDATES.items():
        assert (candidate.sl_code_hex, candidate.potential_offset) == expected[candidate_id]
        assert candidate.read_block is None
        assert candidate.write_support == "unknown"
        with pytest.raises(FrozenInstanceError):
            candidate.read_block = catalog_module.CatalogReadBlock(candidate.potential_offset, 1)
        with pytest.raises(CatalogSelectionError):
            build_read_blocks([candidate_id])


def test_fresh_import_is_lazy_and_planning_never_opens_a_socket(tmp_path):
    code = '''
import importlib.resources
import socket
original_files = importlib.resources.files
def forbidden(*args, **kwargs):
    raise AssertionError("Unerlaubter Geräte-/Ressourcenzugriff")
socket.socket = forbidden
importlib.resources.files = forbidden
from backend.catalog import load_catalog, build_read_blocks
from backend.registers import decode_register_block
assert decode_register_block(4102, (65,))[0].value == 65
importlib.resources.files = original_files
assert [(block.offset, block.count) for block in build_read_blocks(["register:28689"])] == [(28688, 2)]
assert load_catalog().entries[4098].unit is None
'''
    # Absolute Importwurzel statt CWD-abhängigem Katalogpfad.
    code = f"import sys; sys.path.insert(0, {str(Path(__file__).parents[1])!r})\n" + code
    result = subprocess.run([sys.executable, "-c", code], cwd=tmp_path, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
