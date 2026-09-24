"""CLI: remove a switched-off source's records from the processed workbook.

Disabling a source in settings.yaml only stops new collection: rows already
stored stay in the workbook for good, because `merge_records` never drops a
row a run no longer produces. This removes the records that exist only
because of the named source(s); a record merged from several sources ("a+b")
is kept and reported, since another source still vouches for it.

Nothing is deleted from the review tool's database -- documents already
pushed there stay, and `scripts/sync_diff.py` will list them for a human
decision. A copy of the workbook is kept next to it before it is rewritten.
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.config import load_settings
from core.models import EventRecord
from core.storage import load_records, save_records

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = PROJECT_ROOT / "config" / "settings.yaml"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Drop the records of a switched-off source from the workbook.")
    parser.add_argument("--source", action="append", required=True, help="Source to drop (repeatable).")
    parser.add_argument("--processed-path", type=Path, default=None, help="Default: storage.processed_path from settings.yaml.")
    parser.add_argument("--dry-run", action="store_true", help="Only report what would be dropped.")
    return parser.parse_args(argv)


def split_by_source(records: list[EventRecord], sources: set[str]) -> tuple[list[EventRecord], list[EventRecord], list[EventRecord]]:
    """Return (kept, dropped, shared): shared records mix a named source with others and stay."""
    kept, dropped, shared = [], [], []
    for record in records:
        atoms = set(record.source.split("+"))
        if atoms <= sources:
            dropped.append(record)
        else:
            kept.append(record)
            if atoms & sources:
                shared.append(record)
    return kept, dropped, shared


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    settings = load_settings(CONFIG_PATH)
    processed_path = args.processed_path or PROJECT_ROOT / settings["storage"]["processed_path"]

    records = load_records(processed_path)
    kept, dropped, shared = split_by_source(records, set(args.source))
    print(f"{len(records)} records: {len(dropped)} to drop, {len(kept)} kept ({', '.join(sorted(args.source))})")
    for record in dropped:
        print(f"  drop: {record.start_date} {record.source} {record.title[:60]}")
    for record in shared:
        print(f"  kept, also from another source: {record.start_date} {record.source} {record.title[:60]}")

    if args.dry_run or not dropped:
        print("nothing written" if args.dry_run else "nothing to drop")
        return 0

    backup = processed_path.with_suffix(".before_drop.xlsx")
    shutil.copy2(processed_path, backup)
    save_records(kept, processed_path, workbook_kind="processed")
    print(f"workbook rewritten: {processed_path} (previous copy: {backup})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
