"""Synthetische formale Bewertung ohne Transport oder Anlagenkonfiguration."""

import json
import socket

import pytest
from pydantic import ValidationError

from backend.control_plans import (
    ControlPlanDraft,
    assess_control_plan,
    build_control_plan_document,
)


TEXT_FIELDS = (
    "purpose", "source_reference", "address_evidence", "encoding_evidence",
    "before_value", "test_value", "restore_value", "value_unit", "allowed_range_evidence",
    "stop_conditions", "verification_steps", "restore_steps", "host_loss_behavior",
    "network_loss_behavior", "device_restart_behavior", "operator_approval_reference",
)


def complete_draft(candidate_id="control:buffer.start"):
    return {
        "candidate_id": candidate_id,
        **{name: "Synthetische Angabe" for name in TEXT_FIELDS},
        "function_code": 6,
        "max_duration_seconds": 30,
        "max_write_requests": 2,
    }


@pytest.mark.parametrize("candidate", ["control:buffer.start", "control:buffer.target"])
def test_missing_sources_and_restore_are_named_and_never_executable(candidate, monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("Offline-Entwurf darf keinen Socket öffnen")

    monkeypatch.setattr(socket, "socket", forbidden)
    data = complete_draft(candidate)
    data.update(source_reference=None, restore_value=" \t")
    draft = ControlPlanDraft.model_validate(data)
    assessment = assess_control_plan(draft)
    assert assessment.status == "draft"
    assert assessment.missing_fields == ["source_reference", "restore_value"]
    data.update(source_reference="Synthetische Quelle", restore_value="40 (ungeprüft)")
    document = build_control_plan_document(
        ControlPlanDraft.model_validate(data), plan_id="synthetic", revision=2,
        created_at="2026-10-15T00:00:00+00:00",
    )
    exported = json.loads(json.dumps(document))
    assert exported["assessment"]["status"] == "ready_for_review"
    assert exported["assessment"]["missing_fields"] == []
    assert exported["assessment"]["blockers"] == assessment.blockers
    assert "autonomous_fallback_on_host_or_network_loss_unverified" in assessment.blockers
    assert "actuation_path_requires_source_evidence" in assessment.blockers
    assert "encoding_requires_source_evidence" in assessment.blockers
    assert "device_change_requires_separate_approval" in assessment.blockers
    assert "execution_not_available" in assessment.blockers
    assert exported["execution_enabled"] is False
    assert exported["source_status"] == {
        "kind": "operator_provided", "independently_verified": False,
    }
    assert exported["draft"]["restore_value"] == "40 (ungeprüft)"


@pytest.mark.parametrize("candidate", ["register:4102", "register:36864", "register:36865"])
def test_sensor_blocker_survives_complete_revision_export(candidate, tmp_path):
    from backend.storage import SQLiteStore

    store = SQLiteStore(tmp_path / "plans.sqlite3")
    first = store.save_control_plan(None, None, {"candidate_id": candidate, "purpose": "Test"})
    second = store.save_control_plan(first["plan_id"], 1, complete_draft(candidate))
    reopened = SQLiteStore(store.path)
    for document in (first, second, reopened.get_control_plan(first["plan_id"], 1),
                     reopened.get_control_plan(first["plan_id"])):
        assert "sensor_value_must_not_be_overridden" in document["assessment"]["blockers"]
        assert document["execution_enabled"] is False
    assert second["assessment"]["status"] == "ready_for_review"


@pytest.mark.parametrize("field", TEXT_FIELDS)
def test_text_boundaries_and_empty_prerequisites(field):
    data = complete_draft()
    data[field] = "x" * 4000
    assert getattr(ControlPlanDraft.model_validate(data), field) == data[field]
    data[field] += "x"
    with pytest.raises(ValidationError):
        ControlPlanDraft.model_validate(data)
    data[field] = " \n"
    if field == "purpose":
        with pytest.raises(ValidationError):
            ControlPlanDraft.model_validate(data)
    else:
        draft = ControlPlanDraft.model_validate(data)
        assert field in assess_control_plan(draft).missing_fields


@pytest.mark.parametrize("field,value", [
    ("candidate_id", "register:4103"), ("candidate_id", "control:unknown"),
    ("candidate_id", "register:04102"), ("candidate_id", ""),
    ("candidate_id", "x" * 4001), ("candidate_id", None), ("purpose", None),
    ("function_code", 0), ("function_code", 128), ("function_code", True),
    ("function_code", 6.0), ("function_code", "6"),
    ("max_duration_seconds", 0), ("max_duration_seconds", -1),
    ("max_duration_seconds", float("inf")), ("max_duration_seconds", float("nan")),
    ("max_duration_seconds", True), ("max_write_requests", 0),
    ("max_write_requests", -1), ("max_write_requests", 1.5),
    ("max_write_requests", True), ("execute", False), ("before_value", 42),
])
def test_invalid_inputs_rejected(field, value):
    data = complete_draft()
    data[field] = value
    with pytest.raises(ValidationError):
        ControlPlanDraft.model_validate(data)


def test_nulls_and_numeric_boundaries():
    data = complete_draft("register:4104")  # „Soll“ beweist keine Schreibbarkeit.
    for code in (1, 127):
        data.update(function_code=code, max_duration_seconds=0.25, max_write_requests=1)
        draft = ControlPlanDraft.model_validate(data)
        assert assess_control_plan(draft).status == "ready_for_review"
    minimal = ControlPlanDraft(candidate_id="register:4104", purpose="Offline")
    assert set(assess_control_plan(minimal).missing_fields) == set(data) - {
        "candidate_id", "purpose",
    }
    assert all(value is None for name, value in minimal.model_dump().items()
               if name not in {"candidate_id", "purpose"})


@pytest.mark.parametrize("field", [
    name for name in (*TEXT_FIELDS, "function_code", "max_duration_seconds", "max_write_requests")
    if name != "purpose"
])
def test_each_explicit_null_is_preserved_and_reported(field):
    data = complete_draft()
    data[field] = None
    draft = ControlPlanDraft.model_validate(data)
    assert draft.model_dump()[field] is None
    assert assess_control_plan(draft).missing_fields == [field]
