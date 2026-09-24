import contextlib
import io
import tempfile
import unittest
from pathlib import Path

from core.models import EventRecord
from core.storage import load_records, save_records
from scripts.drop_source import main, split_by_source


def record(event_id: str, source: str) -> EventRecord:
    return EventRecord(event_id=event_id, source=source, title=f"Event {event_id}", start_date="2026-11-01", url=f"https://x/{event_id}")


def run(workbook: Path, *args: str) -> tuple[int, str]:
    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        code = main(["--processed-path", str(workbook), *args])
    return code, buffer.getvalue()


class SplitBySourceTests(unittest.TestCase):
    def test_drops_only_records_whose_every_source_is_named(self) -> None:
        records = [record("1", "antibes"), record("2", "antibes+songkick"), record("3", "songkick")]

        kept, dropped, shared = split_by_source(records, {"antibes"})

        self.assertEqual([r.event_id for r in dropped], ["1"])
        self.assertEqual([r.event_id for r in kept], ["2", "3"])
        self.assertEqual([r.event_id for r in shared], ["2"])

    def test_several_sources_can_be_named_at_once(self) -> None:
        records = [record("1", "antibes+menton"), record("2", "cannes")]

        _, dropped, _ = split_by_source(records, {"antibes", "menton"})

        self.assertEqual([r.event_id for r in dropped], ["1"])


class DropSourceCliTests(unittest.TestCase):
    def test_rewrites_the_workbook_and_keeps_a_copy(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workbook = Path(tmp) / "events.xlsx"
            save_records([record("1", "antibes"), record("2", "songkick")], workbook, workbook_kind="processed")

            code, output = run(workbook, "--source", "antibes")
            remaining = [r.event_id for r in load_records(workbook)]
            backup_exists = workbook.with_suffix(".before_drop.xlsx").exists()

        self.assertEqual(code, 0)
        self.assertEqual(remaining, ["2"])
        self.assertTrue(backup_exists)
        self.assertIn("1 to drop", output)

    def test_dry_run_writes_nothing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workbook = Path(tmp) / "events.xlsx"
            save_records([record("1", "antibes")], workbook, workbook_kind="processed")

            _, output = run(workbook, "--source", "antibes", "--dry-run")
            remaining = len(load_records(workbook))
            backup_exists = workbook.with_suffix(".before_drop.xlsx").exists()

        self.assertEqual(remaining, 1)
        self.assertFalse(backup_exists)
        self.assertIn("nothing written", output)

    def test_a_source_with_no_records_changes_nothing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workbook = Path(tmp) / "events.xlsx"
            save_records([record("1", "songkick")], workbook, workbook_kind="processed")

            _, output = run(workbook, "--source", "antibes")
            backup_exists = workbook.with_suffix(".before_drop.xlsx").exists()

        self.assertFalse(backup_exists)
        self.assertIn("nothing to drop", output)


if __name__ == "__main__":
    unittest.main()
