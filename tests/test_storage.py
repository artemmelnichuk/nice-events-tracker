import tempfile
import unittest
from pathlib import Path

from core.deduplication import deduplicate_records
from core.models import EventRecord
from core.storage import load_records, merge_records, save_records


class SaveLoadRoundtripTests(unittest.TestCase):
    def test_save_then_load_preserves_records(self) -> None:
        records = [
            EventRecord(source="x", title="Jazz Night", url="https://example.com/a/", category="Concert"),
        ]
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "events.xlsx"
            deduplicate_records(records)
            save_records(records, path, workbook_kind="processed")
            loaded = load_records(path)

        self.assertEqual(len(loaded), 1)
        self.assertEqual(loaded[0].title, "Jazz Night")
        self.assertEqual(loaded[0].category, "Concert")


class MergeRecordsTests(unittest.TestCase):
    def test_rerunning_the_same_collection_does_not_duplicate(self) -> None:
        first_run = [EventRecord(source="x", title="Jazz Night", url="https://example.com/a/")]
        deduplicate_records(first_run)

        merged_once, counts_once = merge_records([], first_run)
        self.assertEqual(len(merged_once), 1)
        self.assertEqual(counts_once["new"], 1)

        second_run = [EventRecord(source="x", title="Jazz Night", url="https://example.com/a/")]
        deduplicate_records(second_run)

        merged_twice, counts_twice = merge_records(merged_once, second_run)
        self.assertEqual(len(merged_twice), 1)
        self.assertEqual(counts_twice["existing"], 1)
        self.assertEqual(merged_twice[0].event_id, merged_once[0].event_id)

    def test_changed_content_is_marked_updated_and_keeps_the_same_id(self) -> None:
        first_run = [EventRecord(source="x", title="Jazz Night", url="https://example.com/a/", venue="Old Venue")]
        deduplicate_records(first_run)
        merged_once, _ = merge_records([], first_run)

        second_run = [EventRecord(source="x", title="Jazz Night", url="https://example.com/a/", venue="New Venue")]
        deduplicate_records(second_run)
        merged_twice, counts = merge_records(merged_once, second_run)

        self.assertEqual(len(merged_twice), 1)
        self.assertEqual(counts["updated"], 1)
        self.assertEqual(merged_twice[0].event_id, merged_once[0].event_id)
        self.assertEqual(merged_twice[0].venue, "New Venue")


if __name__ == "__main__":
    unittest.main()
