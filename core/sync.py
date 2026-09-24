"""Diff local collector output against the review tool's live database.

The review tool (a published Artifact) keeps its own `events` collection,
readable and writable only through Claude's own tooling -- there is no
public API a script can call directly, so this module never talks to the
database itself. It only computes *what* should be written, so that part of
the process stops being manual arithmetic done in a chat turn.
"""

from __future__ import annotations

import json
from pathlib import Path

from core.models import EventRecord

# The live document schema is a curated subset of EventRecord's fields, plus
# a derived `sort_date` -- it deliberately excludes event_id (the doc_id
# already carries it), date_collected, status and note, none of which the
# review tool has ever used, and above all `rating`/`ratedAt`, which belong
# to the person rating events, never to the collector.
LIVE_FIELDS = (
    "source",
    "title",
    "description",
    "category",
    "theme",
    "start_date",
    "end_date",
    "venue",
    "location",
    "price",
    "url",
    "availability",
)

BATCH_SIZE = 50


def _live_fields_from_record(record: EventRecord) -> dict[str, str]:
    data = {field: getattr(record, field) for field in LIVE_FIELDS}
    data["sort_date"] = record.start_date
    return data


def compute_sync_batches(
    local_records: list[EventRecord],
    live_snapshot: dict[str, dict],
) -> list[list[dict]]:
    """Build the write batches needed to bring the live DB in line with local data.

    `live_snapshot` maps event_id -> {"version": int, ...current field
    values}, as read back from the review tool's database. A record missing
    from the snapshot becomes a `set`; a record present but differing on any
    collector-owned field becomes an `update` carrying only the changed
    fields (pinned to the version it was read at); an unchanged record
    produces nothing. Results are chunked to `ArtifactData`'s batch-write
    cap of 50 entries.
    """
    writes: list[dict] = []
    for record in local_records:
        target = _live_fields_from_record(record)
        live_doc = live_snapshot.get(record.event_id)

        if live_doc is None:
            writes.append(
                {
                    "op": "set",
                    "collection": "events",
                    "doc_id": record.event_id,
                    "data": target,
                }
            )
            continue

        changed = {field: value for field, value in target.items() if live_doc.get(field, "") != value}
        if changed:
            writes.append(
                {
                    "op": "update",
                    "collection": "events",
                    "doc_id": record.event_id,
                    "data": changed,
                    "if_version": live_doc["version"],
                }
            )

    return [writes[i : i + BATCH_SIZE] for i in range(0, len(writes), BATCH_SIZE)]


def load_snapshot(directory: Path, versions: dict[str, int] | None = None) -> dict[str, dict]:
    """Read an ArtifactData `out_dir` dump into the shape `compute_sync_batches` expects.

    The dump is `<directory>/events/<doc_id>.json`. Those files carry no
    document version -- it only shows in the tool's printed listing -- so
    versions come from `versions`; a document missing there gets 0, which
    `unpinned_updates` flags before anything is written.
    """
    versions = versions or {}
    snapshot: dict[str, dict] = {}
    for path in sorted((Path(directory) / "events").glob("*.json")):
        doc = json.loads(path.read_text(encoding="utf-8"))
        doc["version"] = versions.get(path.stem, 0)
        snapshot[path.stem] = doc
    return snapshot


def unpinned_updates(batches: list[list[dict]]) -> list[str]:
    """Ids of `update` writes whose document version is unknown (a pin of 0)."""
    return [write["doc_id"] for batch in batches for write in batch if write["op"] == "update" and not write.get("if_version")]
