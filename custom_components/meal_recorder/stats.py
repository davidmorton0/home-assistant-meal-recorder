"""The daily totals Home Assistant keeps as long-term statistics.

The CSV files are the record, so a person's whole series is rewritten from
them. A day filled in or corrected later then reaches the graphs, which read
these statistics and not the sensors.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from homeassistant.components.recorder.models import StatisticData, StatisticMetaData
from homeassistant.components.recorder.statistics import async_add_external_statistics
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from . import aggregate
from .const import DOMAIN, NUTRIENTS
from .storage import CsvStore

UNITS = {"kcal": "kcal", "protein": "g", "carbohydrate": "g", "fat": "g"}

Series = list[tuple[date, dict[str, float], dict[str, float]]]

# Home Assistant replaced has_mean with mean_type, and added unit_class, which
# must stay empty or grams would be shown converted.
_META_FIELDS = set(StatisticMetaData.__annotations__)


def _mean_and_unit_class() -> dict[str, Any]:
    if "mean_type" not in _META_FIELDS:
        return {"has_mean": False}

    from homeassistant.components.recorder.models import (  # noqa: PLC0415
        StatisticMeanType,
    )

    return {"mean_type": StatisticMeanType.NONE, "unit_class": None}


def statistic_id(folder: str, field: str) -> str:
    """The id one of a person's daily totals is written under."""
    return f"{DOMAIN}:{folder}_{field}"


def read_series(store: CsvStore, folder: str, end: date) -> Series:
    """A person's daily series, from every file they have. Blocking."""
    records: list[dict[str, Any]] = []
    for year, month in store.months(folder):
        records.extend(store.read_month(folder, year, month))
    return aggregate.daily_series(records, end)


def write(hass: HomeAssistant, folder: str, person: str, series: Series) -> None:
    """Rewrite a person's daily totals. A day already written is replaced."""
    if not series:
        return

    for field in NUTRIENTS:
        rows: list[StatisticData] = [
            {
                "start": dt_util.start_of_local_day(day),
                "state": totals[field],
                "sum": running[field],
            }
            for day, totals, running in series
        ]
        metadata: StatisticMetaData = {
            "has_sum": True,
            "name": f"Meals {person} {field}",
            "source": DOMAIN,
            "statistic_id": statistic_id(folder, field),
            "unit_of_measurement": UNITS[field],
            **_mean_and_unit_class(),
        }
        async_add_external_statistics(hass, metadata, rows)
