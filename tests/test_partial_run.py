import contextlib
import io
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from collectors.base import CollectorResult
from core.models import EventRecord
from core.storage import load_records, merge_records, save_records
from scripts import collector


def stored_three_source_row() -> EventRecord:
    # Merged by an earlier full run: explorenice gave the theme, Songkick the
    # venue, Panda the price and url.
    return EventRecord(
        event_id="panda_events_acid",
        source="explorenicecotedazur+panda_events+songkick",
        title="Acid Pauli",
        theme="Electronic music",
        start_date="2099-12-04",
        venue="Le 109",
        price="25 EUR",
        url="https://www.panda-events.com/evenement/acid-pauli/",
    )


def panda_only_record() -> EventRecord:
    # The same event as a `--source panda_events` run sees it on its own.
    return EventRecord(
        source="panda_events",
        title="ACID PAULI",
        start_date="2099-12-04",
        price="25 EUR",
        url="https://www.panda-events.com/evenement/acid-pauli/",
    )


class PartialRunMergeTests(unittest.TestCase):
    def test_a_single_source_run_keeps_what_the_other_sources_contributed(self) -> None:
        merged, counts = merge_records([stored_three_source_row()], [panda_only_record()], run_sources={"panda_events"})

        self.assertEqual(len(merged), 1)
        row = merged[0]
        self.assertEqual(row.theme, "Electronic music")
        self.assertEqual(row.venue, "Le 109")
        self.assertEqual(row.title, "Acid Pauli")
        self.assertEqual(row.source, "explorenicecotedazur+panda_events+songkick")
        self.assertEqual(row.event_id, "panda_events_acid")
        self.assertEqual(counts["existing"], 1)

    def test_the_run_still_refreshes_fields_its_source_reports(self) -> None:
        incoming = panda_only_record()
        incoming.price = "30 EUR"
        incoming.availability = "Complet"

        merged, counts = merge_records([stored_three_source_row()], [incoming], run_sources={"panda_events"})

        self.assertEqual(merged[0].price, "30 EUR")
        self.assertEqual(merged[0].availability, "Complet")
        self.assertEqual(merged[0].theme, "Electronic music")
        self.assertEqual(counts["updated"], 1)

    def test_a_run_covering_every_source_of_the_row_still_replaces_it(self) -> None:
        # Each source was collected and only Panda still lists the event, so
        # the others' contributions are no longer vouched for.
        run = {"explorenicecotedazur", "panda_events", "songkick"}

        merged, _ = merge_records([stored_three_source_row()], [panda_only_record()], run_sources=run)

        self.assertEqual(merged[0].source, "panda_events")
        self.assertEqual(merged[0].theme, "")
        self.assertEqual(merged[0].venue, "")

    def test_without_run_sources_the_old_replace_behaviour_is_unchanged(self) -> None:
        merged, _ = merge_records([stored_three_source_row()], [panda_only_record()])

        self.assertEqual(merged[0].source, "panda_events")
        self.assertEqual(merged[0].theme, "")


class FakeCollector:
    def __init__(self, records: list[EventRecord]) -> None:
        self.records = records

    def collect(self, session, limit=None) -> CollectorResult:
        return CollectorResult(source="panda_events", records=[EventRecord(**r.to_dict()) for r in self.records], found=len(self.records))


class CollectorCliPartialRunTests(unittest.TestCase):
    def test_source_flag_does_not_wipe_theme_and_venue_of_a_merged_row(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            processed = Path(tmp) / "processed.xlsx"
            save_records([stored_three_source_row()], processed)
            settings = {
                "storage": {"raw_path": str(Path(tmp) / "raw.xlsx"), "processed_path": str(processed)},
                "sources": ["explorenicecotedazur", "songkick", "panda_events"],
            }

            with (
                mock.patch.object(collector, "load_settings", return_value=settings),
                mock.patch.object(collector, "build_collector", return_value=FakeCollector([panda_only_record()])),
                contextlib.redirect_stdout(io.StringIO()),
            ):
                self.assertEqual(collector.main(["--source", "panda_events"]), 0)

            [row] = load_records(processed)
            self.assertEqual(row.theme, "Electronic music")
            self.assertEqual(row.venue, "Le 109")
            self.assertEqual(row.source, "explorenicecotedazur+panda_events+songkick")


if __name__ == "__main__":
    unittest.main()
