"""
Chalao:  python -m unittest discover tests
Ye tests internet ke bina chalte hain (sirf samajhna + database + jawab).
Sabse zaroori test: dataset ke bahar wale sawaal pe jawab mein KOI number nahi hona chahiye.
"""
import re
from pathlib import Path
import unittest
from datetime import date

from app import answer, data, intent

TODAY = date(2026, 11, 20)


def ask(text):
    return answer.build_answer(intent.understand(text), TODAY)


class Core(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        data.import_csv((data.DB_PATH.parent / "sample_prices.csv").read_text(encoding="utf-8"))
        intent.refresh()

    def test_basic_price(self):
        a = ask("ਅੰਮ੍ਰਿਤਸਰ ਮੰਡੀ ਵਿੱਚ ਕਣਕ ਦਾ ਕੀ ਭਾਅ ਹੈ")
        self.assertTrue(a["answered"])
        self.assertIn("2480", a["text"])
        self.assertEqual(a["sources"][0]["market"], "Amritsar")

    def test_spelling_variants(self):
        for text in ["ਕਨਕ ਦਾ ਭਾ ਅੰਬਰਸਰ", "kanak da bhaa amritsar", "अमृतसर में गेहूं का भाव"]:
            q = intent.understand(text)
            self.assertEqual(q["crops"], ["wheat"], text)
            self.assertEqual(q["market"], "Amritsar", text)

    def test_basmati_beats_paddy(self):
        self.assertEqual(intent.understand("ਬਾਸਮਤੀ ਝੋਨੇ ਦਾ ਰੇਟ")["crops"], ["basmati"])

    def test_never_invents_numbers(self):
        for text in ["ਸੇਬ ਦਾ ਭਾਅ", "ਬਰਨਾਲਾ ਮੰਡੀ ਕਣਕ", "ਸਮਰਾਲਾ ਮੰਡੀ ਵਿੱਚ ਝੋਨਾ", "ਹੈਲੋ ਜੀ", "सेब का भाव"]:
            a = ask(text)
            self.assertFalse(a["answered"], text)
            self.assertEqual(re.findall(r"\d", a["text"]), [], f"number aa gaya: {text} -> {a['text']}")

    def test_every_number_is_from_db(self):
        for text in ["ਝੋਨੇ ਦਾ ਭਾਅ", "ਅਜਨਾਲਾ ਆਲੂ", "ਕਣਕ ਤੇ ਝੋਨਾ ਅੰਮ੍ਰਿਤਸਰ", "ਪੱਟੀ ਨਰਮਾ"]:
            a = ask(text)
            self.assertTrue(answer.check_grounded(a["text"], a["sources"]), text)

    def test_grounding_check_catches_fake_number(self):
        src = [{"min": 2450, "max": 2520, "modal": 2480, "date": "2026-11-19"}]
        self.assertTrue(answer.check_grounded("ਭਾਅ 2480 ਰੁਪਏ", src))
        self.assertFalse(answer.check_grounded("ਭਾਅ 2600 ਰੁਪਏ", src))

    def test_csv_with_different_headers(self):
        csv_text = "Mandi Name,Crop,Price Date,Modal Price (Rs/Quintal)\nSamrala,Wheat,2026-11-19,\"₹2,470\"\n"
        report = data.import_csv(csv_text, replace=False)
        self.assertEqual(report["added"], 1)
        intent.refresh()
        a = ask("samrala wheat")
        self.assertIn("2470", a["text"])
        # wapas sample data
        data.import_csv((data.DB_PATH.parent / "sample_prices.csv").read_text(encoding="utf-8"))
        intent.refresh()


class Import(unittest.TestCase):
    """Naya data: replace vs merge, aur duplicates."""

    SAMPLE = (data.DB_PATH.parent / "sample_prices.csv")
    JUDGES = Path(__file__).parent / "data" / "judges_style.csv"

    def setUp(self):
        data.import_csv(self.SAMPLE.read_text(encoding="utf-8"))

    tearDown = setUp

    def test_merge_adds_and_updates_without_duplicates(self):
        before = data.summary()["rows"]
        r = data.import_csv(self.JUDGES.read_text(encoding="utf-8"), replace=False)
        self.assertEqual((r["added"], r["updated"], r["duplicates_in_file"], r["rejected"]), (5, 1, 1, 2))
        self.assertEqual(r["total_rows_now"], before + 5)
        again = data.import_csv(self.JUDGES.read_text(encoding="utf-8"), replace=False)
        self.assertEqual(again["added"], 0)                      # dobara upload = koi nayi row nahi
        self.assertEqual(again["total_rows_now"], before + 5)

    def test_uppercase_market_is_same_market(self):
        data.import_csv(self.JUDGES.read_text(encoding="utf-8"), replace=False)
        self.assertNotIn("AMRITSAR", data.all_markets())

    def test_replace_keeps_only_new_file(self):
        r = data.import_csv(self.JUDGES.read_text(encoding="utf-8"), replace=True)
        self.assertEqual(r["total_rows_now"], 6)
        self.assertNotIn("Bathinda", data.all_markets())


if __name__ == "__main__":
    unittest.main()
