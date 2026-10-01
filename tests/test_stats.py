"""The daily totals written for the graphs.

Bad statistics metadata is only logged by the recorder, never raised, so this
reads the statistics back to prove they were accepted.
"""

import pytest

pytest.importorskip("pytest_homeassistant_custom_component")

pytestmark = pytest.mark.usefixtures("recorder_mock", "enable_custom_integrations")

from datetime import timedelta  # noqa: E402

from homeassistant.components.recorder import get_instance  # noqa: E402
from homeassistant.components.recorder.statistics import (  # noqa: E402
    statistics_during_period,
)
from homeassistant.core import HomeAssistant  # noqa: E402
from homeassistant.util import dt as dt_util  # noqa: E402
from pytest_homeassistant_custom_component.common import MockConfigEntry  # noqa: E402
from pytest_homeassistant_custom_component.components.recorder.common import (  # noqa: E402
    async_wait_recording_done,
)

from custom_components.meal_recorder.auth import hash_password  # noqa: E402
from custom_components.meal_recorder.const import (  # noqa: E402
    CONF_PASSWORD_HASH,
    CONF_PERSONS,
    CONF_USERNAME,
    DOMAIN,
)

HEADER = "id,created_at,received_at,name,meal,portion,mass,kcal,protein,carbohydrate,fat\n"


def csv_row(item_id: str, when: str, kcal: float) -> str:
    return f"{item_id},{when},{when},Porridge,breakfast,1 bowl,250,{kcal},10,50,6\n"


async def setup_with_file(hass: HomeAssistant, tmp_path, rows: str, year: int, month: int):
    """Set up the integration with one month's file already stored."""
    hass.config.config_dir = str(tmp_path)
    folder = tmp_path / "meal_recorder" / "david"
    folder.mkdir(parents=True)
    (folder / f"{month:02d}_{year:04d}.csv").write_text(HEADER + rows, encoding="utf-8")

    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Meal Recorder",
        data={
            CONF_USERNAME: "meals",
            CONF_PASSWORD_HASH: hash_password("secret"),
            CONF_PERSONS: {"david": "David"},
        },
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    await async_wait_recording_done(hass)
    return entry


async def read_days(hass: HomeAssistant, statistic_id: str) -> list[dict]:
    """The daily rows the recorder holds for one statistic."""
    start = dt_util.start_of_local_day(dt_util.now().date() - timedelta(days=365))
    return (
        await get_instance(hass).async_add_executor_job(
            statistics_during_period,
            hass,
            start,
            None,
            {statistic_id},
            "day",
            None,
            {"change", "state", "sum"},
        )
    ).get(statistic_id, [])


async def test_a_stored_day_reaches_the_statistics(hass: HomeAssistant, tmp_path):
    today = dt_util.now().date()
    when = f"{today.isoformat()}T08:15:00"
    await setup_with_file(hass, tmp_path, csv_row("a1", when, 300.0), today.year, today.month)

    rows = await read_days(hass, "meal_recorder:david_kcal")
    assert rows, "no statistics were written"
    assert rows[-1]["change"] == 300.0


async def test_a_past_day_added_later_reaches_the_statistics(hass: HomeAssistant, tmp_path):
    """The point of writing these from the files: a day the sensors never saw."""
    today = dt_util.now().date()
    past = today - timedelta(days=3)
    if past.month != today.month:  # One file per month, so keep both days in one.
        pytest.skip("the run crosses a month boundary")
    rows = csv_row("a1", f"{past.isoformat()}T08:15:00", 400.0)
    await setup_with_file(hass, tmp_path, rows, today.year, today.month)

    written = await read_days(hass, "meal_recorder:david_kcal")
    changes = [row["change"] for row in written]
    assert changes[0] == 400.0
    assert changes[1:] == [0.0] * (len(changes) - 1)


async def test_the_page_can_build_the_statistic_id(hass: HomeAssistant, tmp_path):
    """The chart on the Meals page builds the id from this attribute."""
    today = dt_util.now().date()
    when = f"{today.isoformat()}T08:15:00"
    await setup_with_file(hass, tmp_path, csv_row("a1", when, 300.0), today.year, today.month)

    folder = hass.states.get("sensor.meals_day").attributes["folder"]
    assert await read_days(hass, f"meal_recorder:{folder}_kcal")


def write_rows(tmp_path, rows: list[tuple[str, str, float]]) -> None:
    """Write (id, ISO time, kcal) rows into their months' files, replacing what is there."""
    folder = tmp_path / "meal_recorder" / "david"
    folder.mkdir(parents=True, exist_ok=True)
    for path in folder.glob("*.csv"):
        path.unlink()
    files: dict[str, str] = {}
    for item_id, when, kcal in rows:
        name = f"{when[5:7]}_{when[:4]}.csv"
        files[name] = files.get(name, HEADER) + csv_row(item_id, when, kcal)
    for name, text in files.items():
        (folder / name).write_text(text, encoding="utf-8")


async def setup_with_rows(hass: HomeAssistant, tmp_path, rows: list[tuple[str, str, float]]):
    hass.config.config_dir = str(tmp_path)
    write_rows(tmp_path, rows)
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Meal Recorder",
        data={
            CONF_USERNAME: "meals",
            CONF_PASSWORD_HASH: hash_password("secret"),
            CONF_PERSONS: {"david": "David"},
        },
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    await async_wait_recording_done(hass)


async def update_week(hass: HomeAssistant, start) -> None:
    await hass.services.async_call(
        DOMAIN,
        "update_week_statistics",
        {"folder": "david", "start": start.isoformat()},
        blocking=True,
    )
    await async_wait_recording_done(hass)


def changes_by_day(rows: list[dict]) -> dict:
    return {
        dt_util.as_local(dt_util.utc_from_timestamp(row["start"])).date(): row["change"]
        for row in rows
    }


async def test_showing_a_week_zeroes_a_first_day_deleted_by_hand(hass: HomeAssistant, tmp_path):
    today = dt_util.now().date()
    first, later = today - timedelta(days=10), today - timedelta(days=3)
    await setup_with_rows(
        hass,
        tmp_path,
        [("a1", f"{first}T08:15:00", 300.0), ("a2", f"{later}T08:15:00", 200.0)],
    )
    assert changes_by_day(await read_days(hass, "meal_recorder:david_kcal"))[first] == 300.0

    write_rows(tmp_path, [("a2", f"{later}T08:15:00", 200.0)])
    await update_week(hass, first)

    changes = changes_by_day(await read_days(hass, "meal_recorder:david_kcal"))
    assert changes[first] == 0.0
    assert changes[later] == 200.0


async def test_showing_a_week_continues_the_stored_running_totals(hass: HomeAssistant, tmp_path):
    today = dt_util.now().date()
    first, later = today - timedelta(days=10), today - timedelta(days=3)
    await setup_with_rows(
        hass,
        tmp_path,
        [("a1", f"{first}T08:15:00", 100.0), ("a2", f"{later}T08:15:00", 200.0)],
    )

    # The earlier day changes too, but only the shown week on is rewritten.
    write_rows(tmp_path, [("a1", f"{first}T08:15:00", 150.0), ("a2", f"{later}T08:15:00", 250.0)])
    await update_week(hass, later)

    changes = changes_by_day(await read_days(hass, "meal_recorder:david_kcal"))
    assert (changes[first], changes[later], changes[today]) == (100.0, 250.0, 0.0)


async def test_a_week_without_files_is_left_alone(hass: HomeAssistant, tmp_path):
    today = dt_util.now().date()
    await setup_with_rows(hass, tmp_path, [("a1", f"{today}T08:15:00", 300.0)])
    before = await read_days(hass, "meal_recorder:david_kcal")

    await update_week(hass, today - timedelta(days=100))

    assert await read_days(hass, "meal_recorder:david_kcal") == before


async def test_setup_while_starting_waits_to_write_the_statistics(hass: HomeAssistant, tmp_path):
    """The recorder's queue does not move until Home Assistant has started."""
    from homeassistant.const import EVENT_HOMEASSISTANT_STARTED
    from homeassistant.core import CoreState

    today = dt_util.now().date()
    hass.set_state(CoreState.starting)
    await setup_with_rows(hass, tmp_path, [("a1", f"{today}T08:15:00", 300.0)])
    assert await read_days(hass, "meal_recorder:david_kcal") == []

    hass.set_state(CoreState.running)
    hass.bus.async_fire(EVENT_HOMEASSISTANT_STARTED)
    await hass.async_block_till_done()
    await async_wait_recording_done(hass)
    assert changes_by_day(await read_days(hass, "meal_recorder:david_kcal"))[today] == 300.0
