"""CLI: work out what to write to the review tool's database, without writing it.

Claude reads the live `events` collection with ArtifactData (`list`, with
`out_dir` pointing into data/tmp) and runs this against the processed
workbook. The script never talks to the database -- it only prints what
differs and writes the batches Claude then pushes:

    python scripts/sync_diff.py --snapshot-dir data/tmp/live_snapshot

Only `set` (new documents) and `update` (changed collector fields) are ever
produced, never a delete and never `rating`/`ratedAt`. Documents present live
but not in the workbook are listed for a human decision, not removed. Each
write's document goes into data/tmp/sync_docs/<doc_id>.json and the batches
file only references it (`file_path`), so titles and descriptions are never
retyped on their way to the database.
An `update` needs the document's version (`--versions`, a JSON object of
doc_id -> version taken from the tool's printed listing); without one the
run stops before writing anything.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.config import load_settings
from core.models import EventRecord
from core.storage import load_records
from core.sync import compute_sync_batches, load_snapshot, unpinned_updates

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = PROJECT_ROOT / "config" / "settings.yaml"
DEFAULT_OUT = PROJECT_ROOT / "data" / "tmp" / "sync_batches.json"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Diff the processed workbook against a dump of the review database.")
    parser.add_argument("--snapshot-dir", type=Path, required=True, help="ArtifactData out_dir holding events/<doc_id>.json.")
    parser.add_argument("--versions", type=Path, default=None, help="JSON {doc_id: version}; needed for every update.")
    parser.add_argument("--exclude-source", action="append", default=[], help="Hold back records that exist only because of this source (repeatable).")
    parser.add_argument("--processed-path", type=Path, default=None, help="Default: storage.processed_path from settings.yaml.")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT, help="Where to write the batches JSON.")
    return parser.parse_args(argv)


def without_sources(records: list[EventRecord], excluded: set[str]) -> tuple[list[EventRecord], list[EventRecord]]:
    """Split off records whose every source is excluded; a merged "a+b" record stays if b is not."""
    kept, held = [], []
    for record in records:
        (held if excluded and set(record.source.split("+")) <= excluded else kept).append(record)
    return kept, held


def as_file_batches(batches: list[list[dict]], docs_dir: Path) -> list[list[dict]]:
    """Move each write's document into its own JSON file and point the write at it.

    ArtifactData can read a write's data from `file_path`, so the text of a
    title or description reaches the database byte for byte instead of being
    retyped through a chat turn -- which once turned the non-breaking spaces
    inside "« Exsultate »" into ordinary ones. What is left to paste is short
    and plain ASCII.
    """
    docs_dir.mkdir(parents=True, exist_ok=True)
    for stale in docs_dir.glob("*.json"):
        stale.unlink()
    result = []
    for batch in batches:
        entries = []
        for write in batch:
            doc_path = (docs_dir / f"{write['doc_id']}.json").resolve()
            doc_path.write_text(json.dumps(write["data"], ensure_ascii=False, indent=1), encoding="utf-8")
            entries.append({**{key: value for key, value in write.items() if key != "data"}, "file_path": str(doc_path)})
        result.append(entries)
    return result


def describe_updates(batches: list[list[dict]], snapshot: dict[str, dict]) -> list[str]:
    lines = []
    for write in (w for batch in batches for w in batch if w["op"] == "update"):
        live = snapshot[write["doc_id"]]
        lines.append(f"  {write['doc_id']}  ({live.get('title', '')[:50]})")
        for field, value in write["data"].items():
            lines.append(f"      {field}: {str(live.get(field, ''))[:60]!r} -> {str(value)[:60]!r}")
    return lines


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    settings = load_settings(CONFIG_PATH)
    processed_path = args.processed_path or PROJECT_ROOT / settings["storage"]["processed_path"]
    versions = json.loads(args.versions.read_text(encoding="utf-8")) if args.versions else {}

    records = load_records(processed_path)
    records, held = without_sources(records, set(args.exclude_source))
    snapshot = load_snapshot(args.snapshot_dir, versions)
    batches = compute_sync_batches(records, snapshot)
    writes = [write for batch in batches for write in batch]

    local_ids = {record.event_id for record in records} | {record.event_id for record in held}
    orphans = sorted(set(snapshot) - local_ids)
    print(f"workbook {len(records) + len(held)} records ({len(held)} held back), live {len(snapshot)} documents")
    print(f"writes: {sum(w['op'] == 'set' for w in writes)} set, {sum(w['op'] == 'update' for w in writes)} update, in {len(batches)} batch(es)")
    for line in describe_updates(batches, snapshot):
        print(line)
    if held:
        print(f"held back ({', '.join(sorted(args.exclude_source))}): " + "; ".join(f"{r.start_date} {r.title[:40]}" for r in held))
    if orphans:
        print(f"in the live database but not in the workbook, needs a human decision, nothing will be deleted: {', '.join(orphans)}")

    missing = unpinned_updates(batches)
    if missing:
        print(f"ERROR: no version for {len(missing)} update(s); add them to --versions: {', '.join(missing)}")
        return 2

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(as_file_batches(batches, args.out.parent / "sync_docs"), ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"batches written to {args.out} (document contents in {args.out.parent / 'sync_docs'})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
