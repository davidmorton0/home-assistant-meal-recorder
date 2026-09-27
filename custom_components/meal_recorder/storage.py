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
from typing import Any, Callable, Iterable

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
        self._id_cache: dict[Path, tuple[float, int, set[str]]] = {}

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
            self._id_cache.pop(path, None)

    def delete_item(self, folder: str, item_id: str) -> bool:
        """Remove an item from a person's files. False if it is not there."""
        path = self._find(folder, item_id)
        if path is None:
            return False
        self._rewrite(path, lambda row: None if row.get("id") == item_id else row)
        return True

    def update_item(self, folder: str, item: dict[str, Any]) -> bool:
        """Replace the stored item that has item["id"]. False if it is not there.

        An item moved to another month is written to its new file before it is
        taken out of the old one, so a failure part way leaves it twice, not lost.
        """
        path = self._find(folder, item["id"])
        if path is None:
            return False
        created = item["created_at"]
        if path == self.path_for(folder, created.year, created.month):
            replacement = _row_from_item(item)
            self._rewrite(
                path, lambda row: replacement if row.get("id") == item["id"] else row
            )
        else:
            self.append_items([{**item, "folder": folder}])
            self._rewrite(path, lambda row: None if row.get("id") == item["id"] else row)
        return True

    def get_item(self, folder: str, item_id: str) -> dict[str, Any] | None:
        """A person's stored item by id, or None."""
        path = self._find(folder, item_id)
        if path is None:
            return None
        month, _, year = path.stem.partition("_")
        records = self.read_month(folder, int(year), int(month))
        return next((record for record in records if record["id"] == item_id), None)

    def _find(self, folder: str, item_id: str) -> Path | None:
        for path in sorted((self.base_dir / folder).glob("*.csv")):
            if item_id in self._ids_in(path):
                return path
        return None

    def _rewrite(
        self, path: Path, change: Callable[[dict[str, Any]], dict[str, Any] | None]
    ) -> None:
        """Rewrite a file row by row, through a temporary file, keeping unknown rows."""
        with path.open("r", newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            fieldnames = reader.fieldnames or CSV_COLUMNS
            rows = [row for row in map(change, reader) if row is not None]

        temporary = path.with_suffix(".csv.tmp")
        with temporary.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(
                handle, fieldnames=fieldnames, quoting=csv.QUOTE_MINIMAL, extrasaction="ignore"
            )
            writer.writeheader()
            writer.writerows(rows)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        self._cache.pop(path, None)
        self._id_cache.pop(path, None)

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

    def ids(self) -> set[str]:
        """Every item id stored, for every person and month."""
        found: set[str] = set()
        for path in self.base_dir.glob("*/*.csv"):
            found |= self._ids_in(path)
        return found

    def _ids_in(self, path: Path) -> set[str]:
        """The ids in one file, malformed rows included."""
        try:
            stat = path.stat()
        except OSError:
            return set()
        cached = self._id_cache.get(path)
        if cached and cached[0] == stat.st_mtime and cached[1] == stat.st_size:
            return cached[2]
        with path.open("r", newline="", encoding="utf-8") as handle:
            ids = {row["id"] for row in csv.DictReader(handle) if row.get("id")}
        self._id_cache[path] = (stat.st_mtime, stat.st_size, ids)
        return ids

    def months(self, folder: str) -> list[tuple[int, int]]:
        """The (year, month) of each file a person has."""
        found = []
        for path in (self.base_dir / folder).glob("*.csv"):
            month, _, year = path.stem.partition("_")
            if month.isdigit() and year.isdigit() and 1 <= int(month) <= 12:
                found.append((int(year), int(month)))
        return sorted(found)

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
