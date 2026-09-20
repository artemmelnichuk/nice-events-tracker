import unittest

from core.deduplication import merge_cross_source_duplicates
from core.models import EventRecord


class SecondPassSimilarityTests(unittest.TestCase):
    def test_a_third_source_still_joins_an_exactly_matched_pair(self) -> None:
        # Regression: explorenice and Panda agree on the title exactly, which
        # merged them and used to take the pair out of the prefix pass -- so
        # Songkick's "Henrik Schwarz @ Le 109" stayed a separate duplicate.
        records = [
            EventRecord(source="explorenicecotedazur", title="Henrik Schwarz X Ref Session #16", start_date="2026-10-16"),
            EventRecord(source="panda_events", title="HENRIK SCHWARZ x REF SESSION #16", start_date="2026-10-16", venue="Frigo 16"),
            EventRecord(source="songkick", title="Henrik Schwarz @ Le 109", start_date="2026-10-16", venue="Le 109"),
        ]

        result = merge_cross_source_duplicates(records)

        self.assertEqual(len(result.records), 1)
        self.assertEqual(result.records[0].source, "explorenicecotedazur+panda_events+songkick")

    def test_same_names_in_a_different_order_are_one_event(self) -> None:
        records = [
            EventRecord(source="explorenicecotedazur", title="Isha & Limsa", start_date="2026-10-28"),
            EventRecord(source="panda_events", title="LIMSA + ISHA", start_date="2026-10-28"),
        ]

        self.assertEqual(len(merge_cross_source_duplicates(records).records), 1)

    def test_a_co_headliner_listed_alone_joins_the_double_bill_by_venue(self) -> None:
        # Songkick lists each co-headliner as its own event at the same hall:
        # "Isha" links to the double bill by prefix, "Limsa d'Aulnay" only by
        # sharing the hall and the lead word.
        hall = "Théâtre Lino Ventura"
        records = [
            EventRecord(source="explorenicecotedazur", title="Isha & Limsa", start_date="2026-10-28"),
            EventRecord(source="panda_events", title="LIMSA + ISHA", start_date="2026-10-28", venue=hall),
            EventRecord(source="songkick", title=f"Limsa d'Aulnay @ {hall}", start_date="2026-10-28", venue=hall),
            EventRecord(source="songkick", title=f"Isha @ {hall}", start_date="2026-10-28", venue=hall),
        ]

        self.assertEqual(len(merge_cross_source_duplicates(records).records), 1)

    def test_a_festival_listed_twice_by_one_source_collapses_once_another_lists_it(self) -> None:
        records = [
            EventRecord(source="panda_events", title="PARANORMAL FESTIVAL", start_date="2026-10-31", venue="Le 109"),
            EventRecord(source="songkick", title="Paranormal 2026 @ Le 109", start_date="2026-10-31", venue="Le 109"),
            EventRecord(
                source="songkick",
                title="PARANORMAL FESTIVAL - PARANORMAL FESTIVAL - Acte VI @ Le 109",
                start_date="2026-10-31",
                venue="Le 109",
            ),
        ]

        self.assertEqual(len(merge_cross_source_duplicates(records).records), 1)

    def test_same_venue_and_lead_word_on_different_days_stay_apart(self) -> None:
        records = [
            EventRecord(source="panda_events", title="LIMSA + ISHA", start_date="2026-10-28", venue="Le 109"),
            EventRecord(source="songkick", title="Limsa d'Aulnay @ Le 109", start_date="2026-10-29", venue="Le 109"),
        ]

        self.assertEqual(len(merge_cross_source_duplicates(records).records), 2)

    def test_different_venues_and_unrelated_titles_stay_apart(self) -> None:
        records = [
            EventRecord(source="panda_events", title="Frigo Nights", start_date="2027-06-03", venue="Frigo 16"),
            EventRecord(source="songkick", title="Frigorifik @ Le 109", start_date="2027-06-03", venue="Le 109"),
        ]

        self.assertEqual(len(merge_cross_source_duplicates(records).records), 2)

    def test_a_generic_lead_word_is_not_enough(self) -> None:
        records = [
            EventRecord(source="panda_events", title="Festival Bounce", start_date="2026-10-03", venue="Le 109"),
            EventRecord(source="songkick", title="Festival Gospel @ Le 109", start_date="2026-10-03", venue="Le 109"),
        ]

        self.assertEqual(len(merge_cross_source_duplicates(records).records), 2)

    def test_two_listings_from_one_source_do_not_merge_by_venue(self) -> None:
        # The venue rule is for cross-source matches like the prefix rule.
        records = [
            EventRecord(source="songkick", title="Limsa d'Aulnay @ Le 109", start_date="2026-10-28", venue="Le 109"),
            EventRecord(source="songkick", title="Limsa Live Set @ Le 109", start_date="2026-10-28", venue="Le 109"),
        ]

        self.assertEqual(len(merge_cross_source_duplicates(records).records), 2)

    def test_merged_title_avoids_an_all_caps_base(self) -> None:
        records = [
            EventRecord(source="songkick", title="Danyl @ Théâtre Lino Ventura", start_date="2026-11-20"),
            EventRecord(
                source="panda_events",
                title="DANYL",
                start_date="2026-11-20",
                venue="Théâtre Lino Ventura",
                price="À partir de 19 € + FL*",
                url="https://www.panda-events.com/evenement/danyl/",
            ),
        ]

        result = merge_cross_source_duplicates(records)

        self.assertEqual(len(result.records), 1)
        self.assertEqual(result.records[0].title, "Danyl")
        self.assertEqual(result.records[0].price, "À partir de 19 € + FL*")

    def test_merged_source_lists_each_source_once(self) -> None:
        records = [
            EventRecord(source="explorenicecotedazur", title="Les Wampas", start_date="2026-10-17"),
            EventRecord(source="panda_events", title="LES WAMPAS", start_date="2026-10-17"),
            EventRecord(source="songkick", title="Les Wampas @ Le 109", start_date="2026-10-17"),
        ]

        merged = merge_cross_source_duplicates(records).records

        self.assertEqual(len(merged), 1)
        self.assertEqual(merged[0].source, "explorenicecotedazur+panda_events+songkick")


if __name__ == "__main__":
    unittest.main()
