import unittest
from datetime import date
from unittest.mock import patch

from briefing import deliver as deliver_module
from briefing.config import Config


class NotesHyperlinkTests(unittest.TestCase):
    """The archive row's Notes column must be a clickable link to the full issue.

    A plain "label: https://..." string doesn't reliably render as a link once it's
    part of a longer cell, so it's written as a =HYPERLINK() formula instead.
    """

    def config(self):
        return Config(data={"google": {"sheet_id": "sheet123"}}, root=None)

    @patch("briefing.deliver.append_row")
    @patch("briefing.deliver.append_issue")
    @patch("briefing.deliver.create_event")
    def test_notes_is_a_hyperlink_formula_when_nothing_else_failed(
        self, create_event, append_issue, append_row
    ):
        append_issue.return_value = "https://docs.google.com/spreadsheets/d/sheet123/edit#gid=1&range=A2"

        deliver_module.deliver(
            self.config(),
            prompt_name="morning",
            day=date(2026, 9, 10),
            body="issue text",
            degraded=False,
            verification_ok=True,
            verification_summary="ok",
            failed_sources=[],
        )

        notes = append_row.call_args.kwargs["notes"]
        self.assertEqual(
            notes,
            '=HYPERLINK("https://docs.google.com/spreadsheets/d/sheet123/edit#gid=1&range=A2", "Full issue")',
        )

    @patch("briefing.deliver.append_row")
    @patch("briefing.deliver.append_issue")
    @patch("briefing.deliver.create_event")
    def test_failed_sources_are_kept_in_the_hyperlink_label(
        self, create_event, append_issue, append_row
    ):
        append_issue.return_value = "https://docs.google.com/spreadsheets/d/sheet123/edit#gid=1&range=A2"

        deliver_module.deliver(
            self.config(),
            prompt_name="morning",
            day=date(2026, 9, 10),
            body="issue text",
            degraded=True,
            verification_ok=True,
            verification_summary="ok",
            failed_sources=["nse.announcements"],
        )

        notes = append_row.call_args.kwargs["notes"]
        self.assertEqual(
            notes,
            '=HYPERLINK("https://docs.google.com/spreadsheets/d/sheet123/edit#gid=1&range=A2", '
            '"nse.announcements | Full issue")',
        )

    @patch("briefing.deliver.append_row")
    @patch("briefing.deliver.append_issue", side_effect=RuntimeError("boom"))
    @patch("briefing.deliver.create_event")
    def test_plain_notes_kept_when_the_full_issue_link_fails(
        self, create_event, append_issue, append_row
    ):
        deliver_module.deliver(
            self.config(),
            prompt_name="morning",
            day=date(2026, 9, 10),
            body="issue text",
            degraded=True,
            verification_ok=True,
            verification_summary="ok",
            failed_sources=["nse.announcements"],
        )

        notes = append_row.call_args.kwargs["notes"]
        self.assertEqual(notes, "nse.announcements")
        self.assertNotIn("HYPERLINK", notes)


if __name__ == "__main__":
    unittest.main()
