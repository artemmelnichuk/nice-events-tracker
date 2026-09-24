import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from core.models import EventRecord
from core.storage import save_records
from core.sync import compute_sync_batches, load_snapshot, unpinned_updates
from scripts.sync_diff import main, without_sources


def record(event_id: str, source: str = "songkick", title: str = "Jazz Night", **fields) -> EventRecord:
    return EventRecord(event_id=event_id, source=source, title=title, start_date="2026-11-01", url=f"https://x/{event_id}", **fields)


class Workspace:
    """A temp workbook plus a temp live-database dump."""

    def __init__(self, tmp: str, local: list[EventRecord], live: dict[str, dict]) -> None:
        self.root = Path(tmp)
        self.workbook = self.root / "events.xlsx"
        self.snapshot = self.root / "snapshot"
        self.out = self.root / "batches.json"
        save_records(local, self.workbook, workbook_kind="processed")
        (self.snapshot / "events").mkdir(parents=True)
        for doc_id, doc in live.items():
            (self.snapshot / "events" / f"{doc_id}.json").write_text(json.dumps(doc), encoding="utf-8")

    def run(self, *extra: str) -> tuple[int, str]:
        argv = ["--snapshot-dir", str(self.snapshot), "--processed-path", str(self.workbook), "--out", str(self.out), *extra]
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            code = main(argv)
        return code, buffer.getvalue()

    def written(self) -> list[dict]:
        """The writes, each with its document loaded back from the referenced file as `data`."""
        entries = [write for batch in json.loads(self.out.read_text(encoding="utf-8")) for write in batch]
        for entry in entries:
            assert "data" not in entry, "batches must reference documents by file_path, not inline"
            entry["data"] = json.loads(Path(entry["file_path"]).read_text(encoding="utf-8"))
        return entries


class LoadSnapshotTests(unittest.TestCase):
    def test_reads_documents_and_attaches_known_versions(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Workspace(tmp, [], {"a": {"title": "A", "rating": "like"}, "b": {"title": "B"}})

            snapshot = load_snapshot(workspace.snapshot, {"a": 3})

        self.assertEqual(snapshot["a"]["version"], 3)
        self.assertEqual(snapshot["a"]["rating"], "like")
        self.assertEqual(snapshot["b"]["version"], 0)


class UnpinnedUpdatesTests(unittest.TestCase):
    def test_flags_only_updates_without_a_version(self) -> None:
        batches = [[
            {"op": "set", "doc_id": "new"},
            {"op": "update", "doc_id": "unpinned", "if_version": 0},
            {"op": "update", "doc_id": "pinned", "if_version": 4},
        ]]

        self.assertEqual(unpinned_updates(batches), ["unpinned"])


class WithoutSourcesTests(unittest.TestCase):
    def test_holds_back_only_records_whose_every_source_is_excluded(self) -> None:
        records = [record("1", "antibes"), record("2", "antibes+songkick"), record("3", "songkick")]

        kept, held = without_sources(records, {"antibes"})

        self.assertEqual([r.event_id for r in held], ["1"])
        self.assertEqual([r.event_id for r in kept], ["2", "3"])

    def test_nothing_is_held_when_nothing_is_excluded(self) -> None:
        kept, held = without_sources([record("1")], set())

        self.assertEqual((len(kept), held), (1, []))


class SyncDiffCliTests(unittest.TestCase):
    def test_a_new_record_becomes_a_set_and_the_batches_are_written(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Workspace(tmp, [record("new1")], {})

            code, output = workspace.run()
            writes = workspace.written()

        self.assertEqual(code, 0)
        self.assertEqual([(w["op"], w["doc_id"]) for w in writes], [("set", "new1")])
        self.assertIn("1 set, 0 update", output)

    def test_a_changed_document_needs_a_version_before_anything_is_written(self) -> None:
        live = {"e1": {"source": "songkick", "title": "Old Title", "start_date": "2026-11-01", "rating": "like"}}
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Workspace(tmp, [record("e1", title="New Title")], live)

            code, output = workspace.run()
            wrote_anything = workspace.out.exists()

        self.assertEqual(code, 2)
        self.assertFalse(wrote_anything)
        self.assertIn("no version for 1 update", output)
        self.assertIn("'Old Title' -> 'New Title'", output)

    def test_a_pinned_update_carries_the_version_and_never_the_rating(self) -> None:
        live = {"e1": {"source": "songkick", "title": "Old Title", "start_date": "2026-11-01", "rating": "like", "ratedAt": "2026-09-17"}}
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Workspace(tmp, [record("e1", title="New Title")], live)
            versions = workspace.root / "versions.json"
            versions.write_text(json.dumps({"e1": 7}), encoding="utf-8")

            code, _ = workspace.run("--versions", str(versions))
            writes = workspace.written()

        self.assertEqual(code, 0)
        self.assertEqual(writes[0]["op"], "update")
        self.assertEqual(writes[0]["if_version"], 7)
        self.assertNotIn("rating", writes[0]["data"])
        self.assertNotIn("ratedAt", writes[0]["data"])

    def test_a_live_only_document_is_reported_and_never_deleted(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Workspace(tmp, [], {"gone": {"title": "Gone", "rating": "dislike"}})

            code, output = workspace.run()
            writes = workspace.written()

        self.assertEqual(code, 0)
        self.assertEqual(writes, [])
        self.assertIn("gone", output)
        self.assertIn("nothing will be deleted", output)

    def test_an_excluded_source_is_held_back_and_listed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Workspace(tmp, [record("a1", "antibes", "Held Concert"), record("s1")], {})

            code, output = workspace.run("--exclude-source", "antibes")
            writes = workspace.written()

        self.assertEqual(code, 0)
        self.assertEqual([w["doc_id"] for w in writes], ["s1"])
        self.assertIn("held back (antibes)", output)
        self.assertIn("Held Concert", output)

    def test_a_held_back_record_is_not_reported_as_a_live_orphan(self) -> None:
        # Already pushed earlier, now held: it must not look like a stray document.
        live = {"a1": {"source": "antibes", "title": "Held"}}
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Workspace(tmp, [record("a1", "antibes", "Held")], live)

            _, output = workspace.run("--exclude-source", "antibes")

        self.assertNotIn("needs a human decision", output)

    def test_document_text_reaches_the_file_exactly_including_invisible_characters(self) -> None:
        # Regression: retyping "« Exsultate »" turned its non-breaking spaces into ordinary ones.
        title = "Concert « Exsultate » – Orchestre"
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Workspace(tmp, [record("nb1", title=title)], {})

            workspace.run()
            entry = json.loads(workspace.out.read_text(encoding="utf-8"))[0][0]
            stored = json.loads(Path(entry["file_path"]).read_text(encoding="utf-8"))

        self.assertEqual(stored["title"], title)
        self.assertNotIn("data", entry)
        self.assertTrue(Path(entry["file_path"]).is_absolute())

    def test_stale_document_files_from_an_earlier_run_are_cleared(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Workspace(tmp, [record("only")], {})
            stale = workspace.root / "sync_docs" / "old.json"
            stale.parent.mkdir()
            stale.write_text("{}", encoding="utf-8")

            workspace.run()

            self.assertFalse(stale.exists())
            self.assertTrue((workspace.root / "sync_docs" / "only.json").exists())

    def test_an_unchanged_document_produces_no_writes(self) -> None:
        local = record("e1")
        live = {"e1": {field: getattr(local, field) for field in ("source", "title", "description", "category", "theme", "start_date", "end_date", "venue", "location", "price", "url", "availability")}}
        live["e1"]["sort_date"] = local.start_date
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Workspace(tmp, [local], live)

            code, output = workspace.run()

        self.assertEqual(code, 0)
        self.assertIn("0 set, 0 update", output)


if __name__ == "__main__":
    unittest.main()
