import tempfile
import unittest
from datetime import date
from pathlib import Path

from briefing.dedup import headline_key, load_seen, record_seen


class HeadlineKeyTests(unittest.TestCase):
    def test_same_story_produces_the_same_key_despite_punctuation(self):
        a = {"headline": "RBI warns banks over shared tech providers"}
        b = {"headline": "RBI warns banks, over shared tech-providers!!"}
        self.assertEqual(headline_key(a), headline_key(b))

    def test_falls_back_to_subject_when_there_is_no_headline(self):
        item = {"subject": "Trading Window", "company": "Rays of Belief Limited"}
        self.assertEqual(headline_key(item), "tradingwindow")

    def test_empty_item_has_no_key(self):
        self.assertIsNone(headline_key({}))
        self.assertIsNone(headline_key({"headline": "   "}))


class SeenStateTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.state_dir = Path(self._tmp.name)
        self.day = date(2026, 9, 10)

    def tearDown(self):
        self._tmp.cleanup()

    def test_nothing_seen_before_any_record(self):
        self.assertEqual(load_seen(self.state_dir, self.day), set())

    def test_recorded_items_are_seen_afterwards(self):
        record_seen(self.state_dir, self.day, [{"headline": "Dilip Buildcon wins LOI"}])
        seen = load_seen(self.state_dir, self.day)
        self.assertIn(headline_key({"headline": "Dilip Buildcon wins LOI"}), seen)

    def test_recording_twice_merges_rather_than_overwrites(self):
        record_seen(self.state_dir, self.day, [{"headline": "Story A"}])
        record_seen(self.state_dir, self.day, [{"headline": "Story B"}])
        seen = load_seen(self.state_dir, self.day)
        self.assertIn(headline_key({"headline": "Story A"}), seen)
        self.assertIn(headline_key({"headline": "Story B"}), seen)

    def test_a_different_day_is_unaffected(self):
        record_seen(self.state_dir, self.day, [{"headline": "Story A"}])
        self.assertEqual(load_seen(self.state_dir, date(2026, 9, 11)), set())

    def test_items_with_no_headline_record_nothing(self):
        record_seen(self.state_dir, self.day, [{}, {"headline": "  "}])
        self.assertEqual(load_seen(self.state_dir, self.day), set())
        self.assertFalse((self.state_dir / "2026-09-10.json").exists())

    def test_corrupt_state_file_is_treated_as_empty(self):
        self.state_dir.mkdir(parents=True, exist_ok=True)
        (self.state_dir / "2026-09-10.json").write_text("not json", encoding="utf-8")
        self.assertEqual(load_seen(self.state_dir, self.day), set())


if __name__ == "__main__":
    unittest.main()
