"""Raw and processed data storage helpers."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Iterable

import pandas as pd

from core.ids import build_deduplication_key, build_event_id, normalize_title_for_matching
from core.models import EVENT_RECORD_COLUMNS, EventRecord


TRANSIENT_FIELDS = {"event_id", "date_collected", "status", "note"}

VIEW_COLUMNS = (
    "event_id",
    "source",
    "title",
    "category",
    "theme",
    "start_date",
    "end_date",
    "venue",
    "location",
    "url",
)


def records_to_dataframe(records: Iterable[EventRecord]) -> pd.DataFrame:
    """Convert records to the canonical column order used by exports."""
    rows = [record.to_dict() for record in records]
    return pd.DataFrame(rows, columns=EVENT_RECORD_COLUMNS)


def _write_sheet(dataframe: pd.DataFrame, writer: pd.ExcelWriter, sheet_name: str) -> None:
    dataframe.to_excel(writer, sheet_name=sheet_name, index=False)
    worksheet = writer.book[sheet_name]
    worksheet.freeze_panes = "A2"
    worksheet.auto_filter.ref = worksheet.dimensions
    for column_cells in worksheet.columns:
        values = [str(cell.value or "") for cell in column_cells[:100]]
        width = min(max(max((len(value) for value in values), default=10) + 2, 10), 42)
        worksheet.column_dimensions[column_cells[0].column_letter].width = width


def save_records(
    records: Iterable[EventRecord],
    output_path: Path,
    *,
    workbook_kind: str = "processed",
) -> tuple[Path, Path]:
    """Save records as a canonical UTF-8-BOM CSV and a structured XLSX workbook."""
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    csv_path = output_path.with_suffix(".csv")
    records = list(records)
    dataframe = records_to_dataframe(records)

    dataframe.to_csv(csv_path, index=False, encoding="utf-8-sig")
    with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
        if workbook_kind == "raw":
            _write_sheet(dataframe, writer, "raw_events")
        else:
            _write_sheet(dataframe, writer, "events_master")
            _write_sheet(
                dataframe.loc[:, [column for column in VIEW_COLUMNS if column in dataframe]],
                writer,
                "events_view",
            )

    return output_path, csv_path


def load_records(input_path: Path) -> list[EventRecord]:
    """Load canonical records from an XLSX or CSV export."""
    input_path = Path(input_path)
    if not input_path.exists():
        return []

    if input_path.suffix.casefold() == ".csv":
        dataframe = pd.read_csv(input_path)
    else:
        with pd.ExcelFile(input_path) as workbook:
            if "events_master" in workbook.sheet_names:
                sheet_name = "events_master"
            else:
                sheet_name = "raw_events"
            dataframe = pd.read_excel(workbook, sheet_name=sheet_name)

    return [EventRecord.from_mapping(row.to_dict()) for _, row in dataframe.iterrows()]


def _content_signature(record: EventRecord) -> tuple[str, ...]:
    values = record.to_dict()
    return tuple(
        str(values[field])
        for field in EVENT_RECORD_COLUMNS
        if field not in TRANSIENT_FIELDS
    )


def _title_date_key(record: EventRecord) -> tuple[str, str] | None:
    title = normalize_title_for_matching(record.title)
    if not title or not record.start_date:
        return None
    return title, record.start_date


def merge_records(
    existing: Iterable[EventRecord],
    incoming: Iterable[EventRecord],
) -> tuple[list[EventRecord], dict[str, int]]:
    """Merge a run into the processed dataset and classify its changes."""
    merged = list(existing)
    by_key = {build_deduplication_key(record): index for index, record in enumerate(merged)}
    by_title_date = {
        title_date: index
        for index, record in enumerate(merged)
        if (title_date := _title_date_key(record))
    }
    counts = {"new": 0, "existing": 0, "updated": 0}

    for incoming_record in incoming:
        incoming_record.event_id = incoming_record.event_id or build_event_id(incoming_record)
        key = build_deduplication_key(incoming_record)
        existing_index = by_key.get(key)

        # A cross-source merge takes its url from whichever member is richest,
        # so a new source joining an event can swap the url -- and with it the
        # identity key -- of a record already stored. Same normalized title on
        # the same day is the project's own definition of "same event".
        title_date = _title_date_key(incoming_record)
        if existing_index is None and title_date:
            existing_index = by_title_date.get(title_date)
            if existing_index is not None:
                by_key[key] = existing_index

        if existing_index is None:
            merged.append(replace(incoming_record, status="new"))
            by_key[key] = len(merged) - 1
            if title_date:
                by_title_date[title_date] = len(merged) - 1
            counts["new"] += 1
            continue

        previous = merged[existing_index]
        status = "updated" if _content_signature(previous) != _content_signature(incoming_record) else "existing"
        merged[existing_index] = replace(
            incoming_record,
            event_id=previous.event_id or incoming_record.event_id,
            status=status,
        )
        counts[status] += 1

    return merged, counts
