import unittest

from briefing.deliver.telegram import LIMIT, render_html, split_on_sections
from briefing.layout import is_heading, split_sections

SAMPLE = """Evening Briefing for Thursday, 10 September 2026

HOW THE DAY WENT

Nifty 50 closed at 23,451.25, up 0.08%.

WHAT HAPPENED TODAY

RBI warns banks over shared technology providers
The Reserve Bank told banks they cannot outsource the consequences of a failure.

SOURCES

- NSE Provisional Equity Reports: NSE Daily Market Activity https://www.nseindia.com/x
"""


class HeadingTests(unittest.TestCase):
    def test_capital_lines_with_two_words_are_headings(self):
        self.assertTrue(is_heading("HOW THE DAY WENT"))
        self.assertTrue(is_heading("OVERNIGHT: WHAT COULD MOVE THINGS BEFORE TOMORROW"))
        self.assertTrue(is_heading("YESTERDAY'S WINNERS AND LOSERS"))

    def test_prose_and_single_words_are_not_headings(self):
        self.assertFalse(is_heading("Nifty 50 closed at 23,451.25, up 0.08%."))
        self.assertFalse(is_heading("SOURCES"))  # one word: the template uses none
        self.assertFalse(is_heading("BANDHANBNK"))
        self.assertFalse(is_heading("- SAIL"))
        self.assertFalse(is_heading(""))

    def test_sections_split_at_headings(self):
        sections = split_sections(SAMPLE)
        self.assertEqual(sections[0], "Evening Briefing for Thursday, 10 September 2026")
        self.assertTrue(sections[1].startswith("HOW THE DAY WENT"))
        self.assertTrue(sections[2].startswith("WHAT HAPPENED TODAY"))


class SplitTests(unittest.TestCase):
    def test_short_body_is_one_part(self):
        self.assertEqual(split_on_sections("just a line"), ["just a line"])

    def test_every_part_is_within_the_message_limit(self):
        long_body = SAMPLE * 40
        for part in split_on_sections(long_body):
            self.assertLessEqual(len(part), LIMIT)

    def test_nothing_is_lost_in_the_split(self):
        body = SAMPLE * 40
        rejoined = "".join(split_on_sections(body))
        squash = lambda s: "".join(s.split())
        self.assertEqual(squash(rejoined), squash(body))

    def test_breaks_land_on_headings_where_possible(self):
        section = "FIRST SECTION\n\n" + ("x" * 1000) + "\n\n"
        body = section * 12
        parts = split_on_sections(body)
        self.assertGreater(len(parts), 1)
        for part in parts[1:]:
            self.assertTrue(part.startswith("FIRST SECTION"), part[:40])

    def test_an_oversized_single_section_is_still_cut(self):
        parts = split_on_sections("y" * (LIMIT * 2 + 50))
        self.assertGreater(len(parts), 1)
        for part in parts:
            self.assertLessEqual(len(part), LIMIT)


class RenderTests(unittest.TestCase):
    def test_headings_are_bold_and_text_is_escaped(self):
        html = render_html("HOW THE DAY WENT\nOil & gas rose <fast>.")
        self.assertIn("<b>HOW THE DAY WENT</b>", html)
        self.assertIn("Oil &amp; gas rose &lt;fast&gt;.", html)
