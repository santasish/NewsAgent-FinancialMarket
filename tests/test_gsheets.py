import unittest
from unittest.mock import MagicMock, patch

from briefing.deliver import gsheets


class AppendIssueTests(unittest.TestCase):
    def setUp(self):
        gsheets._issues_tab_id.cache_clear()

    def _mock_sheets(self, *, existing_sheets, updated_range):
        sheets = MagicMock()
        sheets.spreadsheets().get.return_value.execute.return_value = {
            "sheets": existing_sheets
        }
        sheets.spreadsheets().batchUpdate.return_value.execute.return_value = {
            "replies": [{"addSheet": {"properties": {"sheetId": 999}}}]
        }
        sheets.spreadsheets().values().append.return_value.execute.return_value = {
            "updates": {"updatedRange": updated_range}
        }
        return sheets

    @patch("briefing.deliver.gsheets.service")
    def test_creates_the_tab_when_it_does_not_exist_yet(self, service):
        service.return_value = self._mock_sheets(existing_sheets=[], updated_range="Issues!A2:C2")

        link = gsheets.append_issue("sheet123", date="2026-09-10", edition="Morning", text="hello")

        self.assertEqual(link, "https://docs.google.com/spreadsheets/d/sheet123/edit#gid=999&range=A2")
        service.return_value.spreadsheets().batchUpdate.assert_called_once()

    @patch("briefing.deliver.gsheets.service")
    def test_reuses_an_existing_tab_without_recreating_it(self, service):
        service.return_value = self._mock_sheets(
            existing_sheets=[{"properties": {"title": "Issues", "sheetId": 42}}],
            updated_range="Issues!A7:C7",
        )

        link = gsheets.append_issue("sheet123", date="2026-09-10", edition="Evening", text="hello")

        self.assertEqual(link, "https://docs.google.com/spreadsheets/d/sheet123/edit#gid=42&range=A7")
        service.return_value.spreadsheets().batchUpdate.assert_not_called()

    @patch("briefing.deliver.gsheets.service")
    def test_the_tab_lookup_is_cached_across_calls(self, service):
        service.return_value = self._mock_sheets(
            existing_sheets=[{"properties": {"title": "Issues", "sheetId": 42}}],
            updated_range="Issues!A2:C2",
        )

        gsheets.append_issue("sheet123", date="2026-09-10", edition="Morning", text="one")
        gsheets.append_issue("sheet123", date="2026-09-10", edition="Evening", text="two")

        service.return_value.spreadsheets().get.assert_called_once()

    @patch("briefing.deliver.gsheets.service")
    def test_overlong_text_is_truncated_to_fit_a_cell(self, service):
        mock = self._mock_sheets(
            existing_sheets=[{"properties": {"title": "Issues", "sheetId": 42}}],
            updated_range="Issues!A2:C2",
        )
        service.return_value = mock

        gsheets.append_issue("sheet123", date="2026-09-10", edition="Morning", text="x" * 60_000)

        written = mock.spreadsheets().values().append.call_args.kwargs["body"]["values"][0][2]
        self.assertLessEqual(len(written), gsheets.MAX_CELL_CHARS + len("\n[truncated]"))
        self.assertTrue(written.endswith("[truncated]"))


if __name__ == "__main__":
    unittest.main()
