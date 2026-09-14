import unittest

from core.deduplication import merge_cross_source_duplicates
from core.ids import normalize_title_for_matching
from core.models import EventRecord


class NormalizeTitleForMatchingTests(unittest.TestCase):
    def test_strips_songkick_venue_suffix(self) -> None:
        self.assertEqual(
            normalize_title_for_matching("Djadja & Dinaz @ Palais Nikaïa"),
            normalize_title_for_matching("DJADJA & DINAZ"),
        )

    def test_folds_accents_and_punctuation(self) -> None:
        self.assertEqual(
            normalize_title_for_matching("Chopin – Récital de Piano"),
            normalize_title_for_matching("chopin recital de piano"),
        )


class MergeCrossSourceDuplicatesTests(unittest.TestCase):
    def test_merges_the_same_real_event_from_two_sources(self) -> None:
        explorenice = EventRecord(
            source="explorenicecotedazur",
            title="DJADJA & DINAZ",
            start_date="2026-10-03",
            theme="Rap, R&B, Soul",
            location="Nice",
            url="https://www.explorenicecotedazur.com/en/event/djadja-dinaz/",
        )
        songkick = EventRecord(
            source="songkick",
            title="Djadja & Dinaz @ Palais Nikaïa",
            start_date="2026-10-03",
            venue="Palais Nikaïa",
            location="Nice",
            url="https://www.songkick.com/concerts/42690969-djadja-and-dinaz-at-palais-nikaia",
        )

        result = merge_cross_source_duplicates([explorenice, songkick])

        self.assertEqual(result.merged_groups, 1)
        self.assertEqual(len(result.records), 1)
        merged = result.records[0]
        self.assertEqual(merged.venue, "Palais Nikaïa")
        self.assertEqual(merged.theme, "Rap, R&B, Soul")
        self.assertEqual(merged.source, "explorenicecotedazur+songkick")

    def test_does_not_merge_different_events_on_the_same_day(self) -> None:
        a = EventRecord(source="x", title="Concert A", start_date="2026-10-03")
        b = EventRecord(source="y", title="Concert B", start_date="2026-10-03")

        result = merge_cross_source_duplicates([a, b])

        self.assertEqual(result.merged_groups, 0)
        self.assertEqual(len(result.records), 2)

    def test_does_not_merge_the_same_title_on_different_dates(self) -> None:
        a = EventRecord(source="x", title="Chopin", start_date="2026-10-03")
        b = EventRecord(source="y", title="Chopin", start_date="2026-10-30")

        result = merge_cross_source_duplicates([a, b])

        self.assertEqual(result.merged_groups, 0)
        self.assertEqual(len(result.records), 2)

    def test_records_missing_title_or_date_never_merge(self) -> None:
        a = EventRecord(source="x", title="", start_date="2026-10-03")
        b = EventRecord(source="y", title="", start_date="2026-10-03")
        c = EventRecord(source="z", title="Concert C", start_date="")
        d = EventRecord(source="w", title="Concert C", start_date="")

        result = merge_cross_source_duplicates([a, b, c, d])

        self.assertEqual(result.merged_groups, 0)
        self.assertEqual(len(result.records), 4)


if __name__ == "__main__":
    unittest.main()
