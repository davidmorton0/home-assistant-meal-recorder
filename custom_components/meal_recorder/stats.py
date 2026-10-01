"""The daily totals Home Assistant keeps as long-term statistics.

The CSV files are the record, so a person's series is rewritten from them, from
a given day to today. A day filled in or corrected later then reaches the
graphs, which read these statistics and not the sensors. The running totals
continue from those already stored for the day before; when that day is not
stored, the whole series is rewritten.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from homeassistant.components.recorder import get_instance
from homeassistant.components.recorder.models import StatisticData, StatisticMetaData
from homeassistant.components.recorder.statistics import (
    async_add_external_statistics,
    statistics_during_period,
)
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


def has_files(store: CsvStore, folder: str, start: date, end: date) -> bool:
    """Whether a person has a file for any day from start to end. Blocking."""
    months = set(store.months(folder))
    day = start
    while day <= end:
        if (day.year, day.month) in months:
            return True
        day += timedelta(days=1)
    return False


def read_series(
    store: CsvStore,
    folder: str,
    start: date,
    end: date,
    base: dict[str, float] | None,
) -> Series:
    """A person's daily series from start to end. Blocking.

    With a base, only the files from start's month on are read. Without one the
    series is rebuilt from zero, from the first day with items or from start,
    whichever is earlier.
    """
    records: list[dict[str, Any]] = []
    for year, month in store.months(folder):
        if base is None or (year, month) >= (start.year, start.month):
            records.extend(store.read_month(folder, year, month))
    if base is None and records:
        start = min(start, min(record["created_at"].date() for record in records))
    return aggregate.daily_series(records, end, start, base)


async def async_sums_before(
    hass: HomeAssistant, folder: str, day: date
) -> dict[str, float] | None:
    """The running totals stored for the day before day, or None if not stored."""
    recorder = get_instance(hass)
    # Writes are queued, so let those already sent land before reading.
    await recorder.async_block_till_done()
    ids = {statistic_id(folder, field): field for field in NUTRIENTS}
    rows = await recorder.async_add_executor_job(
        statistics_during_period,
        hass,
        dt_util.start_of_local_day(day - timedelta(days=1)),
        dt_util.start_of_local_day(day),
        set(ids),
        "hour",
        None,
        {"sum"},
    )
    sums: dict[str, float] = {}
    for statistic, field in ids.items():
        found = rows.get(statistic)
        if not found or found[-1].get("sum") is None:
            return None
        sums[field] = found[-1]["sum"]
    return sums


async def async_wait_written(hass: HomeAssistant) -> None:
    """Wait until the statistics written so far can be read."""
    await get_instance(hass).async_block_till_done()


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
