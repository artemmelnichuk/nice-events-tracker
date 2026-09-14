import unittest

from core.deduplication import deduplicate_records
from core.models import EventRecord


class DeduplicateRecordsTests(unittest.TestCase):
    def test_keeps_first_and_counts_duplicates(self) -> None:
        records = [
            EventRecord(source="x", url="https://example.com/a/", title="A"),
            EventRecord(source="x", url="https://example.com/a/", title="A duplicate"),
            EventRecord(source="x", url="https://example.com/b/", title="B"),
        ]
        result = deduplicate_records(records)
        self.assertEqual(len(result.records), 2)
        self.assertEqual(result.duplicates, 1)
        self.assertEqual(result.records[0].title, "A")

    def test_assigns_event_id_when_missing(self) -> None:
        records = [EventRecord(source="x", url="https://example.com/a/")]
        result = deduplicate_records(records)
        self.assertTrue(result.records[0].event_id)


if __name__ == "__main__":
    unittest.main()
