"""Formale Offline-Entwürfe, keine Gerätefreigabe und kein Ausführungspfad."""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from backend.catalog import CONTROL_CANDIDATES, load_catalog


Text = Annotated[str, Field(strict=True, max_length=4000)]
PositiveDuration = Annotated[float, Field(strict=True, gt=0, allow_inf_nan=False)]
PositiveCount = Annotated[int, Field(strict=True, gt=0)]


class ControlPlanDraft(BaseModel):
    """Betreiberangaben bleiben Text; Vollständigkeit ist kein Stellwegnachweis."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    candidate_id: Text
    purpose: Text
    source_reference: Text | None = None
    address_evidence: Text | None = None
    function_code: Annotated[int, Field(strict=True, ge=1, le=127)] | None = None
    encoding_evidence: Text | None = None
    before_value: Text | None = None
    test_value: Text | None = None
    restore_value: Text | None = None
    value_unit: Text | None = None
    allowed_range_evidence: Text | None = None
    max_duration_seconds: PositiveDuration | None = None
    max_write_requests: PositiveCount | None = None
    stop_conditions: Text | None = None
    verification_steps: Text | None = None
    restore_steps: Text | None = None
    host_loss_behavior: Text | None = None
    network_loss_behavior: Text | None = None
    device_restart_behavior: Text | None = None
    operator_approval_reference: Text | None = None

    @field_validator("*")
    @classmethod
    def reject_empty_required_text(cls, value, info):
        # Nur Leerangaben normalisieren, tatsächliche Vor-/Zielwerte nicht verändern.
        if isinstance(value, str) and not value.strip():
            if info.field_name in {"candidate_id", "purpose"}:
                raise ValueError("ID und Zweck dürfen nicht leer sein.")
            return None
        return value

    @field_validator("candidate_id")
    @classmethod
    def known_candidate(cls, value: str) -> str:
        if value not in CONTROL_CANDIDATES and not any(
            entry.register_id == value for entry in load_catalog().entries.values()
        ):
            raise ValueError("Unbekannter Steuerkandidat.")
        return value


class ControlPlanAssessment(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    status: Literal["draft", "ready_for_review"]
    missing_fields: list[str]
    blockers: list[str]


def assess_control_plan(draft: ControlPlanDraft) -> ControlPlanAssessment:
    """Prüft nur Vollständigkeit; unverifizierte Texte beseitigen keine Grenzen."""
    missing = [name for name, value in draft.model_dump().items() if value is None]
    blockers = [
        "actuation_path_requires_source_evidence",
        "encoding_requires_source_evidence",
        "device_change_requires_separate_approval",
        "execution_not_available",
    ]
    if draft.candidate_id in CONTROL_CANDIDATES:
        blockers.append("autonomous_fallback_on_host_or_network_loss_unverified")
    else:
        entry = next(
            entry for entry in load_catalog().entries.values()
            if entry.register_id == draft.candidate_id
        )
        if entry.read_support == "confirmed_core" and entry.unit == "degC":
            blockers.append("sensor_value_must_not_be_overridden")
    return ControlPlanAssessment(
        status="draft" if missing else "ready_for_review",
        missing_fields=missing,
        blockers=blockers,
    )


def build_control_plan_document(
    draft: ControlPlanDraft, *, plan_id: str, revision: int, created_at: str,
) -> dict:
    """Gemeinsame gespeicherte Darstellung und privater JSON-Download für #35/#36."""
    return {
        "plan_id": plan_id,
        "revision": revision,
        "created_at": created_at,
        "draft": draft.model_dump(mode="json"),
        "source_status": {
            "kind": "operator_provided",
            "independently_verified": False,
        },
        "assessment": assess_control_plan(draft).model_dump(mode="json"),
        "execution_enabled": False,
    }
