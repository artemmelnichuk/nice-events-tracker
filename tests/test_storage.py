import tempfile
import unittest
from pathlib import Path

from core.deduplication import deduplicate_records
from core.models import EventRecord
from core.storage import add_untracked_records, load_records, merge_records, save_records


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

    def test_a_url_gaining_a_second_source_updates_instead_of_duplicating(self) -> None:
        # Regression test: a real event that was singleton on day 1 and picked
        # up by cross-source merging on day 2 (source string changes from
        # "explorenicecotedazur" to "explorenicecotedazur+songkick") must
        # update the existing row, not create an orphaned duplicate.
        day_one = [
            EventRecord(
                source="explorenicecotedazur",
                title="Liv del Estal",
                url="https://www.explorenicecotedazur.com/en/event/liv-del-estal/",
            )
        ]
        merged_once, counts_once = merge_records([], day_one)
        self.assertEqual(counts_once["new"], 1)

        day_two = [
            EventRecord(
                source="explorenicecotedazur+songkick",
                title="Liv del Estal",
                url="https://www.explorenicecotedazur.com/en/event/liv-del-estal/",
                venue="Frigo 16",
            )
        ]
        merged_twice, counts_twice = merge_records(merged_once, day_two)

        self.assertEqual(len(merged_twice), 1)
        self.assertEqual(counts_twice["updated"], 1)
        self.assertEqual(counts_twice["new"], 0)
        self.assertEqual(merged_twice[0].event_id, merged_once[0].event_id)
        self.assertEqual(merged_twice[0].venue, "Frigo 16")

    def test_a_richer_source_swapping_the_url_updates_instead_of_duplicating(self) -> None:
        # Regression test: when a new source joins an event and its (richer)
        # record becomes the merge base, the stored record's url changes. The
        # same normalized title on the same day must still find the old row.
        stored = [
            EventRecord(
                source="explorenicecotedazur",
                title="Liv del Estal",
                start_date="2026-10-10",
                url="https://www.explorenicecotedazur.com/en/event/liv-del-estal/",
            )
        ]
        merged_once, _ = merge_records([], stored)

        incoming = [
            EventRecord(
                source="explorenicecotedazur+panda_events",
                title="LIV DEL ESTAL",
                start_date="2026-10-10",
                url="https://www.panda-events.com/evenement/liv-del-estal/",
                price="à partir de 5 € + FL*",
            )
        ]
        merged_twice, counts = merge_records(merged_once, incoming)

        self.assertEqual(len(merged_twice), 1)
        self.assertEqual(counts["updated"], 1)
        self.assertEqual(counts["new"], 0)
        self.assertEqual(merged_twice[0].event_id, merged_once[0].event_id)
        self.assertEqual(merged_twice[0].price, "à partir de 5 € + FL*")

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


class AddUntrackedRecordsTests(unittest.TestCase):
    def test_adds_a_new_record_with_an_id(self) -> None:
        incoming = [EventRecord(source="manual_events", title="New Night", start_date="2026-10-01", url="https://x.example/new")]

        merged, added, skipped = add_untracked_records([], incoming)

        self.assertEqual(len(merged), 1)
        self.assertEqual(len(added), 1)
        self.assertEqual(skipped, [])
        self.assertTrue(added[0].event_id)

    def test_skips_and_never_overwrites_an_event_already_tracked(self) -> None:
        stored = [
            EventRecord(
                event_id="explorenicecotedazur_abc",
                source="explorenicecotedazur+songkick",
                title="Liv del Estal",
                start_date="2026-10-10",
                venue="Frigo 16",
                theme="DJ",
                url="https://www.explorenicecotedazur.com/en/event/liv-del-estal/",
            )
        ]
        # Same event typed in by hand: different url, different casing.
        incoming = [EventRecord(source="manual_events", title="LIV DEL ESTAL", start_date="2026-10-10", url="https://ra.co/events/1")]

        merged, added, skipped = add_untracked_records(stored, incoming)

        self.assertEqual(added, [])
        self.assertEqual(len(skipped), 1)
        self.assertEqual(len(merged), 1)
        self.assertEqual(merged[0].venue, "Frigo 16")
        self.assertEqual(merged[0].source, "explorenicecotedazur+songkick")

    def test_running_twice_adds_nothing_the_second_time(self) -> None:
        incoming = [EventRecord(source="manual_events", title="Once Only", start_date="2026-10-01", url="https://x.example/once")]

        merged, added_first, _ = add_untracked_records([], incoming)
        _, added_second, skipped_second = add_untracked_records(merged, [EventRecord(source="manual_events", title="Once Only", start_date="2026-10-01", url="https://x.example/once")])

        self.assertEqual(len(added_first), 1)
        self.assertEqual(added_second, [])
        self.assertEqual(len(skipped_second), 1)


if __name__ == "__main__":
    unittest.main()
