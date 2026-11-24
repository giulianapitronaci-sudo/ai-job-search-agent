"""Tests for tracker/tracker.py.

Run from the repository root:
    python3 -m unittest -v
"""
import io
import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stdout

import openpyxl

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tracker"))
import tracker  # noqa: E402


class TextHelpers(unittest.TestCase):
    def test_normalize_ignores_case_spaces_and_symbols(self):
        self.assertEqual(tracker.normalize("Novo Nordisk A/S"), "novonordiskas")

    def test_company_key_drops_brackets(self):
        self.assertEqual(tracker.company_key("Sanofi (Waterford)"), "sanofi")

    def test_title_words_drop_filler_words(self):
        self.assertEqual(tracker.title_words("Junior QC Analyst I"), {"analyst"})


class SameRole(unittest.TestCase):
    """The duplicate check that stops the agent proposing a job you already applied to."""

    def test_same_role_with_different_wording(self):
        self.assertTrue(tracker.same_role(
            "Sanofi", "MSAT Graduate Programme",
            "Sanofi", "Manufacturing Science and Technology (MSAT) Graduate"))

    def test_different_role_at_same_company(self):
        self.assertFalse(tracker.same_role(
            "Sanofi", "Automation Engineer",
            "Sanofi", "Manufacturing Science and Technology (MSAT) Graduate"))

    def test_same_title_at_different_company(self):
        self.assertFalse(tracker.same_role("Roche", "Graduate Chemist", "Bayer", "Graduate Chemist"))

    def test_company_name_with_suffix_still_matches(self):
        self.assertTrue(tracker.same_role(
            "Proxima Fusion GmbH", "CEO Office Associate", "Proxima Fusion", "CEO Office Associate"))


class ScoreColor(unittest.TestCase):
    def test_colors(self):
        self.assertEqual(tracker.score_color(9), tracker.GREEN)
        self.assertEqual(tracker.score_color(6), tracker.YELLOW)
        self.assertIsNone(tracker.score_color(5))


class AddCommand(unittest.TestCase):
    """End to end on a throw-away spreadsheet, never on a real one."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        d = self.tmp.name
        self.cfg = {
            "file": os.path.join(d, "jobs.xlsx"), "backup_dir": os.path.join(d, "backups"),
            "new_postings_sheet": "New postings", "applications_sheet": "Applications",
            "applications_first_row": 2, "company_column": "A", "role_column": "B",
        }
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Applications"
        ws.append(["Company", "Role"])
        ws.append(["Proxima Fusion", "CEO Office Associate"])
        wb.save(self.cfg["file"])

    def tearDown(self):
        self.tmp.cleanup()

    def add(self, postings):
        path = os.path.join(self.tmp.name, "postings.json")
        with open(path, "w") as f:
            json.dump(postings, f)
        out = io.StringIO()
        with redirect_stdout(out):
            tracker.cmd_add(self.cfg, path)
        return out.getvalue()

    def rows(self):
        ws = openpyxl.load_workbook(self.cfg["file"])["New postings"]
        return list(ws.iter_rows(min_row=2, values_only=True))

    def posting(self, id_, company, title, score=8):
        return {"id": id_, "score": score, "company": company, "title": title, "url": "https://example.com"}

    def test_adds_new_posting(self):
        self.add([self.posting("1", "TestCo", "Graduate Chemist")])
        self.assertEqual(len(self.rows()), 1)
        self.assertEqual(self.rows()[0][2], "TestCo")

    def test_skips_role_already_applied_to(self):
        output = self.add([self.posting("1", "Proxima Fusion", "CEO Office Associate")])
        self.assertIn("already applied", output)
        self.assertEqual(self.rows(), [])

    def test_same_posting_twice_is_added_once(self):
        self.add([self.posting("1", "TestCo", "Graduate Chemist")])
        self.add([self.posting("1", "TestCo", "Graduate Chemist")])
        self.assertEqual(len(self.rows()), 1)

    def test_best_scores_first(self):
        self.add([self.posting("1", "A", "Role one", score=5), self.posting("2", "B", "Role two", score=9)])
        self.assertEqual([r[1] for r in self.rows()], [9, 5])

    def test_makes_a_backup_before_writing(self):
        self.add([self.posting("1", "TestCo", "Graduate Chemist")])
        self.assertEqual(len(os.listdir(self.cfg["backup_dir"])), 1)

    def test_refuses_when_excel_has_the_file_open(self):
        open(os.path.join(self.tmp.name, "~$jobs.xlsx"), "w").close()
        with self.assertRaises(SystemExit):
            self.add([self.posting("1", "TestCo", "Graduate Chemist")])


if __name__ == "__main__":
    unittest.main()
