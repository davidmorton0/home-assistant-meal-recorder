"""CSV storage: a folder per person, one file per month.

Pure file handling. Every call here is blocking and is run in an executor by
the Home Assistant side of the integration.
"""

from __future__ import annotations

import csv
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

from .const import CSV_COLUMNS, NUTRIENTS

_LOGGER = logging.getLogger(__name__)


def month_file_name(year: int, month: int) -> str:
    """Return the file name for a month, MM_YYYY.csv."""
    return f"{month:02d}_{year:04d}.csv"


class CsvStore:
    """Reads and writes the CSV files under one base directory."""

    def __init__(self, base_dir: str | os.PathLike[str]) -> None:
        self.base_dir = Path(base_dir)
        self._cache: dict[Path, tuple[float, int, list[dict[str, Any]]]] = {}

    # Writing -------------------------------------------------------------

    def path_for(self, folder: str, year: int, month: int) -> Path:
        return self.base_dir / folder / month_file_name(year, month)

    def append_items(self, items: Iterable[dict[str, Any]]) -> None:
        """Append items, grouping them by person folder and month.

        Items must already carry a "folder" key.
        """
        grouped: dict[Path, list[dict[str, Any]]] = {}
        for item in items:
            created = item["created_at"]
            path = self.path_for(item["folder"], created.year, created.month)
            grouped.setdefault(path, []).append(item)

        for path, rows in grouped.items():
            path.parent.mkdir(parents=True, exist_ok=True)
            is_new = not path.exists() or path.stat().st_size == 0
            with path.open("a", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(
                    handle, fieldnames=CSV_COLUMNS, quoting=csv.QUOTE_MINIMAL
                )
                if is_new:
                    writer.writeheader()
                for item in rows:
                    writer.writerow(_row_from_item(item))
                handle.flush()
                os.fsync(handle.fileno())
            self._cache.pop(path, None)

    # Reading -------------------------------------------------------------

    def read_month(self, folder: str, year: int, month: int) -> list[dict[str, Any]]:
        """Return a month's records, sorted by created_at. Missing file: empty."""
        path = self.path_for(folder, year, month)
        try:
            stat = path.stat()
        except OSError:
            return []

        cached = self._cache.get(path)
        if cached and cached[0] == stat.st_mtime and cached[1] == stat.st_size:
            return cached[2]

        records: list[dict[str, Any]] = []
        with path.open("r", newline="", encoding="utf-8") as handle:
            for line_number, raw in enumerate(csv.DictReader(handle), start=2):
                record = _item_from_row(raw)
                if record is None:
                    _LOGGER.warning("Skipping malformed row %s in %s", line_number, path)
                    continue
                records.append(record)

        records.sort(key=lambda record: record["created_at"])
        self._cache[path] = (stat.st_mtime, stat.st_size, records)
        return records

    def folders(self) -> list[str]:
        """Return the person folders that exist."""
        try:
            return sorted(entry.name for entry in self.base_dir.iterdir() if entry.is_dir())
        except OSError:
            return []


def _row_from_item(item: dict[str, Any]) -> dict[str, Any]:
    row = {
        "id": item["id"],
        "created_at": item["created_at"].isoformat(),
        "received_at": item["received_at"].isoformat(),
        "name": item["name"],
        "meal": item["meal"],
        "portion": item["portion"],
    }
    for field in ["mass", *NUTRIENTS]:
        row[field] = _format_number(item[field])
    return row


def _format_number(value: float) -> str:
    if float(value).is_integer():
        return str(int(value))
    return repr(float(value))


def _item_from_row(row: dict[str, Any]) -> dict[str, Any] | None:
    try:
        record: dict[str, Any] = {
            "id": row["id"],
            "created_at": datetime.fromisoformat(row["created_at"]),
            "received_at": datetime.fromisoformat(row["received_at"]),
            "name": row["name"],
            "meal": row["meal"],
            "portion": row.get("portion") or "",
        }
        for field in ["mass", *NUTRIENTS]:
            record[field] = float(row[field])
    except (KeyError, TypeError, ValueError, AttributeError):
        return None
    return record
