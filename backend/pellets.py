"""Rechenwerte zum Pelletlager aus erfassten Lieferungen; keine Gerätemessung."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

OPERATING_COUNTER_SIGNAL = "boiler.operating_minutes"


def pellet_status(
    deliveries: Sequence[Mapping[str, Any]],
    capacity_tonnes: float | None,
    current_hours: float | None,
) -> dict[str, float | None]:
    """Berechnet Verbrauch und Füllstand; Lieferungen aufsteigend nach Betriebsstunden.

    Betreiberangabe: Jede Lieferung füllt den Tank randvoll. Deshalb entspricht eine
    Liefermenge dem Verbrauch seit der vorherigen Lieferung; die erste zählt nicht.
    """
    rate = None
    if len(deliveries) >= 2:
        hours = deliveries[-1]["operating_hours"] - deliveries[0]["operating_hours"]
        rate = sum(item["tonnes"] for item in deliveries[1:]) * 1000 / hours
    consumed = None
    if rate is not None and current_hours is not None:
        # Der gespeicherte Zähler kann bei gestoppter Erfassung hinter der Lieferung liegen.
        consumed = max(0.0, current_hours - deliveries[-1]["operating_hours"]) * rate / 1000
    level = None
    if consumed is not None and capacity_tonnes is not None:
        level = max(0.0, capacity_tonnes - consumed)
    return {
        "consumption_kg_per_hour": rate,
        "consumed_since_fill_tonnes": consumed,
        "tank_level_tonnes": level,
    }
