"""Bulk quotes from a spreadsheet: the shapes people actually export, and nothing dropped without a reason."""
import base64
import os
import tempfile
import unittest

os.environ.setdefault("ACS_DATA_DIR", tempfile.mkdtemp())

from app.content import split_author  # noqa: E402
from app.errors import UserError  # noqa: E402
from app.quotes_csv import MAX_QUOTES, from_csv  # noqa: E402


class QuotesCsv(unittest.TestCase):
    def test_header_with_quote_and_author_columns_in_any_order(self):
        r = from_csv(text='author,quote\nSeneca,"We suffer more in imagination than in reality."\n,Begin anyway.\n')
        self.assertTrue(r["header"])
        self.assertEqual(r["quotes"], ["We suffer more in imagination than in reality. — Seneca", "Begin anyway."])
        self.assertEqual(r["authors"], 1)

    def test_no_header_two_columns_of_quote_and_name(self):
        r = from_csv(text='"Life has no script. Live it.",Anonymous\n"Waste no more time arguing.",Marcus Aurelius\n')
        self.assertEqual(r["quotes"][1], "Waste no more time arguing. — Marcus Aurelius")

    def test_quotes_alone_even_when_they_contain_commas(self):
        r = from_csv(text="Life has no script, live it.\nYour comfort zone will kill you.\nRest, then go again.\n")
        self.assertEqual(r["quotes"], ["Life has no script, live it.", "Your comfort zone will kill you.",
                                       "Rest, then go again."])
        self.assertEqual(r["authors"], 0)

    def test_semicolon_and_tab_files_and_excel_encoding(self):
        self.assertEqual(from_csv(text="Quote;Author\nStay hungry.;Someone\n")["quotes"], ["Stay hungry. — Someone"])
        self.assertEqual(from_csv(text="text\tby\nKeep going.\tA. Person\n")["quotes"], ["Keep going. — A. Person"])
        raw = "quote,author\n“Don’t wait.”,Seneca\n".encode("cp1252")
        self.assertEqual(from_csv(data_b64=base64.b64encode(raw).decode())["quotes"], ["Don’t wait. — Seneca"])

    def test_skipped_rows_say_why(self):
        long = "x" * 200
        r = from_csv(text=f"quote\nKeep going.\n{long}\nkeep going\nok\n,\n")
        self.assertEqual(r["quotes"], ["Keep going."])
        reasons = {s["row"]: s["reason"] for s in r["skipped"]}
        self.assertIn("over 180", reasons[3])
        self.assertEqual(reasons[4], "repeats row 2")
        self.assertEqual(reasons[5], "too short")

    def test_limit_and_empty_files(self):
        r = from_csv(text="\n".join(f"Quote number {i}." for i in range(MAX_QUOTES + 5)))
        self.assertEqual(len(r["quotes"]), MAX_QUOTES)
        self.assertEqual(len(r["skipped"]), 5)
        with self.assertRaises(UserError):
            from_csv(text="\n\n")

    def test_author_split_never_eats_a_hyphenated_line(self):
        self.assertEqual(split_author("Work hard - play hard"), ("Work hard - play hard", None))
        self.assertEqual(split_author("Be kind - Seneca"), ("Be kind", "Seneca"))
        self.assertEqual(split_author("Begin. — marcus aurelius"), ("Begin.", "marcus aurelius"))

    def test_a_pasted_csv_row_splits_into_quote_and_author(self):
        self.assertEqual(split_author('"He who is brave is free.","Seneca"'), ("He who is brave is free.", "Seneca"))
        self.assertEqual(split_author('"Small steps, taken daily, still count.",'), ("Small steps, taken daily, still count.", None))
        self.assertEqual(split_author('"Begin.";Marcus Aurelius'), ("Begin.", "Marcus Aurelius"))
        self.assertEqual(split_author('"Quoted, but alone."'), ('"Quoted, but alone."', None))


if __name__ == "__main__":
    unittest.main()
