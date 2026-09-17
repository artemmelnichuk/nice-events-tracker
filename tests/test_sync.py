import unittest

from core.models import EventRecord
from core.sync import compute_sync_batches


def make_record(**overrides) -> EventRecord:
    defaults = dict(
        event_id="explorenicecotedazur_abc123",
        source="explorenicecotedazur",
        title="Jazz Night",
        description="",
        category="Concert",
        theme="Jazz and blues",
        start_date="2026-10-01",
        end_date="2026-10-01",
        venue="Le 109",
        location="Nice",
        price="",
        url="https://example.com/event/jazz-night/",
        availability="",
    )
    defaults.update(overrides)
    return EventRecord(**defaults)


class ComputeSyncBatchesTests(unittest.TestCase):
    def test_record_missing_from_live_becomes_a_set(self) -> None:
        record = make_record()

        batches = compute_sync_batches([record], {})

        self.assertEqual(len(batches), 1)
        self.assertEqual(len(batches[0]), 1)
        write = batches[0][0]
        self.assertEqual(write["op"], "set")
        self.assertEqual(write["doc_id"], "explorenicecotedazur_abc123")
        self.assertEqual(write["data"]["title"], "Jazz Night")
        self.assertEqual(write["data"]["sort_date"], "2026-10-01")
        self.assertNotIn("if_version", write)

    def test_changed_field_becomes_update_with_only_that_field(self) -> None:
        record = make_record(venue="Nouveau Théâtre")
        live_snapshot = {
            "explorenicecotedazur_abc123": {
                "version": 3,
                "source": "explorenicecotedazur",
                "title": "Jazz Night",
                "description": "",
                "category": "Concert",
                "theme": "Jazz and blues",
                "start_date": "2026-10-01",
                "end_date": "2026-10-01",
                "venue": "Le 109",
                "location": "Nice",
                "price": "",
                "url": "https://example.com/event/jazz-night/",
                "availability": "",
                "sort_date": "2026-10-01",
                "rating": "like",
                "ratedAt": "2026-09-16T10:00:00.000Z",
            }
        }

        batches = compute_sync_batches([record], live_snapshot)

        self.assertEqual(len(batches), 1)
        write = batches[0][0]
        self.assertEqual(write["op"], "update")
        self.assertEqual(write["if_version"], 3)
        self.assertEqual(write["data"], {"venue": "Nouveau Théâtre"})

    def test_unchanged_record_produces_no_write(self) -> None:
        record = make_record()
        live_snapshot = {
            "explorenicecotedazur_abc123": {
                "version": 1,
                **{field: getattr(record, field) for field in (
                    "source", "title", "description", "category", "theme",
                    "start_date", "end_date", "venue", "location", "price",
                    "url", "availability",
                )},
                "sort_date": record.start_date,
                "rating": "dislike",
            }
        }

        batches = compute_sync_batches([record], live_snapshot)

        self.assertEqual(batches, [])

    def test_rating_is_never_written_even_when_other_fields_change(self) -> None:
        record = make_record(price="de 10 € à 20 €")
        live_snapshot = {
            "explorenicecotedazur_abc123": {
                "version": 2,
                "source": "explorenicecotedazur",
                "title": "Jazz Night",
                "description": "",
                "category": "Concert",
                "theme": "Jazz and blues",
                "start_date": "2026-10-01",
                "end_date": "2026-10-01",
                "venue": "Le 109",
                "location": "Nice",
                "price": "",
                "url": "https://example.com/event/jazz-night/",
                "availability": "",
                "sort_date": "2026-10-01",
                "rating": "like",
                "ratedAt": "2026-09-16T10:00:00.000Z",
            }
        }

        batches = compute_sync_batches([record], live_snapshot)

        write = batches[0][0]
        self.assertNotIn("rating", write["data"])
        self.assertNotIn("ratedAt", write["data"])
        self.assertEqual(write["data"], {"price": "de 10 € à 20 €"})

    def test_chunks_writes_into_batches_of_fifty(self) -> None:
        records = [make_record(event_id=f"explorenicecotedazur_{i}") for i in range(120)]

        batches = compute_sync_batches(records, {})

        self.assertEqual(len(batches), 3)
        self.assertEqual([len(batch) for batch in batches], [50, 50, 20])


if __name__ == "__main__":
    unittest.main()
