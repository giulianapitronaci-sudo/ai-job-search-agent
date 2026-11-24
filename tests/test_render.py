"""Tests for documents/render.py.

These check the HTML the script builds, so they run in a second and do not
need Chrome. Run from the repository root:
    python3 -m unittest -v
"""
import json
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "documents"))
import render  # noqa: E402


def load_example(name):
    with open(os.path.join(ROOT, "examples", name)) as f:
        return json.load(f)


class CvHtml(unittest.TestCase):
    def setUp(self):
        self.cv = load_example("cv.example.json")
        self.html = render.cv_html(self.cv)

    def test_contains_name_and_every_section(self):
        self.assertIn("Alex Moreno", self.html)
        for section in self.cv["sections"]:
            self.assertIn(f"<h2>{section['title']}</h2>", self.html)

    def test_every_bullet_is_on_the_page(self):
        for section in self.cv["sections"]:
            for entry in section.get("entries", []):
                for bullet in entry.get("bullets", []):
                    self.assertIn(render.e(bullet), self.html)

    def test_no_photo_when_none_given(self):
        self.assertNotIn('class="photo"', self.html)

    def test_special_characters_are_escaped(self):
        cv = {"name": "Test", "sections": [{"title": "R&D", "entries": [
            {"role": "Chemist", "bullets": ["Cost <3 EUR/m3 & 97% removal"]}]}]}
        html = render.cv_html(cv)
        self.assertIn("R&amp;D", html)
        self.assertIn("&lt;3 EUR/m3 &amp; 97%", html)
        self.assertNotIn("<3 EUR", html)


class LetterHtml(unittest.TestCase):
    def setUp(self):
        self.letter = load_example("letter.example.json")
        self.html = render.letter_html(self.letter)

    def test_has_every_paragraph_in_order(self):
        positions = [self.html.index(render.e(p)) for p in self.letter["body"]]
        self.assertEqual(positions, sorted(positions))

    def test_default_closing(self):
        letter = dict(self.letter)
        letter.pop("closing")
        self.assertIn("Kind regards,", render.letter_html(letter))


class ExamplesStayFictional(unittest.TestCase):
    """The public examples must never contain a real person's details."""

    def test_examples_use_example_domains(self):
        for name in ("cv.example.json", "letter.example.json"):
            text = json.dumps(load_example(name))
            self.assertIn("example.com", text)
            self.assertNotIn("gmail", text.lower())


if __name__ == "__main__":
    unittest.main()
