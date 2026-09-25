"""Raw and processed data storage helpers."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Iterable

import pandas as pd

from core.deduplication import _FILLABLE_FIELDS, covers_same_event
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


def _keep_other_sources(
    stored: EventRecord,
    incoming: EventRecord,
    run_sources: set[str] | None,
) -> EventRecord:
    """Carry over what sources outside this run contributed to a stored row.

    A `--source X` run only sees X's version of an event that an earlier full
    run merged from several sources. Taken as is, it would wipe the theme or
    venue those other sources supplied. When the stored row names a source
    the run did not collect, the incoming record keeps its own non-empty
    fields, fills the blanks from the stored row, keeps the stored merged
    title and url, and keeps every source in `source`.
    """
    stored_sources = {source for source in stored.source.split("+") if source}
    if run_sources is None or stored_sources <= run_sources:
        return incoming
    kept = replace(
        incoming,
        title=stored.title or incoming.title,
        url=stored.url or incoming.url,
        source="+".join(sorted(stored_sources | {s for s in incoming.source.split("+") if s})),
    )
    for field in _FILLABLE_FIELDS:
        if not getattr(kept, field) and getattr(stored, field):
            setattr(kept, field, getattr(stored, field))
    return kept


def add_untracked_records(
    existing: Iterable[EventRecord],
    incoming: Iterable[EventRecord],
) -> tuple[list[EventRecord], list[EventRecord], list[EventRecord]]:
    """Append only the incoming records not already tracked; never overwrite one.

    Unlike merge_records this leaves an existing row untouched -- the right
    behaviour for a partial batch (hand-entered events) that must not clobber
    a row already merged from several sources. Returns (all, added, skipped).
    """
    merged = list(existing)
    known_keys = {build_deduplication_key(record) for record in merged}
    known_title_dates = {title_date for record in merged if (title_date := _title_date_key(record))}
    added: list[EventRecord] = []
    skipped: list[EventRecord] = []

    for record in incoming:
        record.event_id = record.event_id or build_event_id(record)
        key = build_deduplication_key(record)
        title_date = _title_date_key(record)
        if key in known_keys or (title_date and title_date in known_title_dates):
            skipped.append(record)
            continue

        new_record = replace(record, status="new")
        merged.append(new_record)
        added.append(new_record)
        known_keys.add(key)
        if title_date:
            known_title_dates.add(title_date)

    return merged, added, skipped


def merge_records(
    existing: Iterable[EventRecord],
    incoming: Iterable[EventRecord],
    *,
    run_sources: Iterable[str] | None = None,
) -> tuple[list[EventRecord], dict[str, int]]:
    """Merge a run into the processed dataset and classify its changes.

    An incoming record is matched to a stored row by identity key, then by
    (normalized title, date), then -- for rows nothing else claimed -- by
    `covers_same_event`. The last step is what keeps a row's id (and the
    ratings hung on it) when a new source joins its event and changes its
    title and url ("Acid Pauli @ Le 109" becoming "ACID PAULI x REF SESSION
    #18"). Any further stored rows the same record covers are its former
    duplicates and are dropped, counted as "absorbed".

    `run_sources` names the sources this run collected. A matched stored row
    that also comes from other sources is completed rather than replaced
    (see `_keep_other_sources`); without it every match replaces the row.
    """
    run_sources = set(run_sources) if run_sources is not None else None
    merged = list(existing)
    stored_rows = list(merged)
    stored_count = len(merged)
    by_key = {build_deduplication_key(record): index for index, record in enumerate(merged)}
    by_title_date = {
        title_date: index
        for index, record in enumerate(merged)
        if (title_date := _title_date_key(record))
    }
    counts = {"new": 0, "existing": 0, "updated": 0, "absorbed": 0}
    matched: set[int] = set()

    def update_row(index: int, incoming_record: EventRecord) -> None:
        previous = merged[index]
        incoming_record = _keep_other_sources(previous, incoming_record, run_sources)
        status = "updated" if _content_signature(previous) != _content_signature(incoming_record) else "existing"
        merged[index] = replace(
            incoming_record,
            event_id=previous.event_id or incoming_record.event_id,
            status=status,
        )
        matched.add(index)
        counts[status] += 1

    unmatched: list[EventRecord] = []
    for incoming_record in incoming:
        incoming_record.event_id = incoming_record.event_id or build_event_id(incoming_record)
        key = build_deduplication_key(incoming_record)
        existing_index = by_key.get(key)

        # A cross-source merge takes its url from whichever member is richest,
        # so a new source joining an event can swap the url -- and with it the
        # identity key -- of a record already stored. Same normalized title on
        # the same day is the project's own definition of "same event".
        if existing_index is None and (title_date := _title_date_key(incoming_record)):
            existing_index = by_title_date.get(title_date)
            if existing_index is not None:
                by_key[key] = existing_index

        if existing_index is None or existing_index in matched:
            unmatched.append(incoming_record)
        else:
            update_row(existing_index, incoming_record)

    absorbed: set[int] = set()
    for incoming_record in unmatched:
        key = build_deduplication_key(incoming_record)
        covered = [
            index
            for index in range(stored_count)
            if index not in matched and covers_same_event(merged[index], incoming_record)
        ]
        if covered:
            update_row(covered[0], incoming_record)
            by_key[key] = covered[0]
            continue

        merged.append(replace(incoming_record, status="new"))
        matched.add(len(merged) - 1)
        counts["new"] += 1

    # Stored rows no incoming record claimed, but that a record which did match
    # now covers, are its former duplicates (a second Songkick listing of the
    # same festival, say). Compared against the row as it was stored.
    for index in range(stored_count):
        if index in matched:
            continue
        stored_row = stored_rows[index]
        if any(covers_same_event(stored_row, merged[claimed]) for claimed in matched):
            absorbed.add(index)

    counts["absorbed"] = len(absorbed)
    if absorbed:
        merged = [record for index, record in enumerate(merged) if index not in absorbed]
    return merged, counts
