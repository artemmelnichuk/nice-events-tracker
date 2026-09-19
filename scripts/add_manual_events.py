"""CLI: put hand-entered events into the workbook and prepare the review-tool push.

Reads config/manual_events.yaml, appends the events not already tracked to the
processed workbook (existing rows are never touched) and writes the `set`
batches that add them to the review tool's database. Safe to rerun: an event
already in the workbook is skipped, so nothing is added or pushed twice.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from collectors.manual_events import DEFAULT_PATH, ManualEventsCollector
from core.config import load_settings
from core.priority import sort_by_theme_priority
from core.storage import add_untracked_records, load_records, save_records
from core.sync import compute_sync_batches

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = PROJECT_ROOT / "config" / "settings.yaml"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Add hand-entered events to the workbook.")
    parser.add_argument("--manual-path", type=Path, default=DEFAULT_PATH)
    parser.add_argument("--processed-path", type=Path, default=None, help="Default: storage.processed_path from settings.yaml.")
    parser.add_argument("--out", type=Path, default=None, help="Where to write the review-tool batches JSON.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    settings = load_settings(CONFIG_PATH)
    processed_path = args.processed_path or PROJECT_ROOT / settings["storage"]["processed_path"]
    out_path = args.out or processed_path.parent / "manual_sync_batches.json"

    result = ManualEventsCollector(args.manual_path).collect()
    for message in result.error_messages:
        print(f"ERROR: {message}")

    existing = load_records(processed_path)
    merged, added, skipped = add_untracked_records(existing, result.records)
    print(f"{len(result.records)} manual events: {len(added)} added, {len(skipped)} already tracked")
    for record in skipped:
        print(f"  already tracked, left as is: {record.start_date} {record.title}")

    if added:
        deprioritized = settings.get("collection", {}).get("deprioritized_themes", [])
        save_records(sort_by_theme_priority(merged, deprioritized), processed_path, workbook_kind="processed")
        # New ids have no live document yet, so plain `set`s -- no version pins needed.
        batches = compute_sync_batches(added, {})
        out_path.write_text(json.dumps(batches, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"Workbook updated: {processed_path}")
        print(f"Review-tool batches ({sum(len(b) for b in batches)} writes): {out_path}")

    return 1 if result.errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
