import unittest

from core.models import EventRecord
from core.storage import merge_records


class CoveredStoredRowTests(unittest.TestCase):
    def test_a_stored_row_survives_a_title_and_url_change_with_its_id(self) -> None:
        # Regression: "Acid Pauli @ Le 109" (songkick) gets merged with Panda's
        # "ACID PAULI x REF SESSION #18"; neither the url nor the normalized
        # title match the stored row any more, so it used to be left behind
        # as a duplicate with a fresh id.
        stored = [
            EventRecord(
                event_id="songkick_e1978ec17ddf",
                source="songkick",
                title="Acid Pauli @ Le 109",
                start_date="2026-12-04",
                venue="Le 109",
                url="https://www.songkick.com/concerts/43315218-acid-pauli-at-le-109",
            )
        ]
        incoming = [
            EventRecord(
                source="panda_events+songkick",
                title="ACID PAULI x REF SESSION #18",
                start_date="2026-12-04",
                venue="Frigo 16",
                url="https://www.panda-events.com/evenement/acid-pauli/",
            )
        ]

        merged, counts = merge_records(stored, incoming)

        self.assertEqual(len(merged), 1)
        self.assertEqual(counts["updated"], 1)
        self.assertEqual(counts["new"], 0)
        self.assertEqual(merged[0].event_id, "songkick_e1978ec17ddf")
        self.assertEqual(merged[0].source, "panda_events+songkick")

    def test_extra_stored_duplicates_covered_by_the_merge_are_absorbed(self) -> None:
        stored = [
            EventRecord(event_id="songkick_a", source="songkick", title="Paranormal 2026 @ Le 109", start_date="2026-10-31", venue="Le 109", url="https://sk/a"),
            EventRecord(event_id="songkick_b", source="songkick", title="PARANORMAL FESTIVAL - Acte VI @ Le 109", start_date="2026-10-31", venue="Le 109", url="https://sk/b"),
        ]
        incoming = [
            EventRecord(source="panda_events+songkick", title="PARANORMAL FESTIVAL", start_date="2026-10-31", venue="Le 109", url="https://panda/p")
        ]

        merged, counts = merge_records(stored, incoming)

        self.assertEqual(len(merged), 1)
        self.assertEqual(counts["absorbed"], 1)
        self.assertEqual(merged[0].event_id, "songkick_a")

    def test_a_stored_duplicate_is_absorbed_even_when_the_record_matched_another_row_exactly(self) -> None:
        # The real Paranormal case: the incoming record matches one Songkick
        # row by title and date, the other Songkick listing is left over.
        stored = [
            EventRecord(event_id="songkick_a", source="songkick", title="Paranormal 2026 @ Le 109", start_date="2026-10-31", venue="Le 109", url="https://sk/a"),
            EventRecord(event_id="songkick_b", source="songkick", title="PARANORMAL FESTIVAL - Acte VI @ Le 109", start_date="2026-10-31", venue="Le 109", url="https://sk/b"),
        ]
        incoming = [
            EventRecord(source="panda_events+songkick", title="PARANORMAL FESTIVAL - Acte VI", start_date="2026-10-31", venue="Le 109", url="https://sk/b")
        ]

        merged, counts = merge_records(stored, incoming)

        self.assertEqual([record.event_id for record in merged], ["songkick_b"])
        self.assertEqual(counts["absorbed"], 1)

    def test_an_unrelated_stored_row_is_left_alone(self) -> None:
        stored = [EventRecord(event_id="songkick_x", source="songkick", title="Other Band @ Le 109", start_date="2026-12-04", venue="Le 109", url="https://sk/x")]
        incoming = [EventRecord(source="panda_events+songkick", title="ACID PAULI", start_date="2026-12-04", venue="Frigo 16", url="https://panda/a")]

        merged, counts = merge_records(stored, incoming)

        self.assertEqual(len(merged), 2)
        self.assertEqual(counts["new"], 1)
        self.assertEqual(counts["absorbed"], 0)

    def test_a_row_from_an_unrelated_source_is_not_claimed(self) -> None:
        # Same day and title overlap, but no source in common: the stored row
        # is a separate listing, not the older form of the incoming record.
        stored = [EventRecord(event_id="opera_1", source="opera_de_nice", title="Ninho", start_date="2027-03-18", url="https://opera/1")]
        incoming = [EventRecord(source="explorenicecotedazur+songkick", title="Ninho – Quatro Tour", start_date="2027-03-18", url="https://ex/n")]

        merged, counts = merge_records(stored, incoming)

        self.assertEqual(len(merged), 2)
        self.assertEqual(counts["new"], 1)


if __name__ == "__main__":
    unittest.main()
