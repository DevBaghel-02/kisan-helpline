"""
Mausam, sarkari schemes aur Hindi jawab ke tests. Internet nahi chahiye (Open-Meteo mock hai).
Chalao: python -m unittest tests.test_more
"""
import re
import unittest
from datetime import date
from unittest import mock

from app import answer, data, intent, pipeline, weather

TODAY = date(2026, 11, 20)
FAKE_WEATHER = {"2026-11-20": {"tmin": 8.6, "tmax": 23.4, "rain_prob": 10, "rain_mm": 0},
                "2026-11-21": {"tmin": 9.2, "tmax": 21.0, "rain_prob": 70, "rain_mm": 4.2},
                "2026-11-22": {"tmin": 7.0, "tmax": 20.0, "rain_prob": None, "rain_mm": None}}


def ask(text):
    return answer.build_answer(intent.understand(text), TODAY)


class Base(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        data.import_csv((data.DB_PATH.parent / "sample_prices.csv").read_text(encoding="utf-8"))
        intent.refresh()


class Weather(Base):
    def setUp(self):
        self.patch = mock.patch.object(weather, "fetch", return_value=FAKE_WEATHER)
        self.fetch = self.patch.start()

    def tearDown(self):
        self.patch.stop()

    def test_today_default_place_is_home(self):
        a = ask("ਅੱਜ ਮੌਸਮ ਕਿਵੇਂ ਹੈ")
        self.assertEqual(a["kind"], "weather")
        self.assertIn("ਅੰਮ੍ਰਿਤਸਰ", a["text"])
        self.assertIn("9 ਤੋਂ 23", a["text"])                      # rounded from 8.6 / 23.4
        self.assertTrue(answer.check_grounded(a["text"], a["sources"]))

    def test_kal_means_tomorrow_for_weather(self):
        a = ask("ਕੱਲ੍ਹ ਮੀਂਹ ਪਵੇਗਾ ਲੁਧਿਆਣਾ")
        self.assertIn("ਭਲਕੇ", a["text"])
        self.assertEqual(a["sources"][0]["date"], "2026-11-21")
        self.assertIn("ਸਪਰੇਅ ਨਾ ਕਰੋ", a["text"])                  # 70% -> salah
        lat, lon = self.fetch.call_args.args
        self.assertAlmostEqual(lat, 30.901, places=2)               # Ludhiana ki location

    def test_mandi_word_does_not_make_it_price(self):
        self.assertEqual(intent.understand("ਅੰਮ੍ਰਿਤਸਰ ਮੰਡੀ ਦਾ ਮੌਸਮ")["intent"], "weather")
        self.assertEqual(intent.understand("ਅੰਮ੍ਰਿਤਸਰ ਮੰਡੀ ਕਣਕ ਦਾ ਭਾਅ")["intent"], "price")

    def test_missing_rain_value_not_spoken(self):
        a = ask("ਪਰਸੋਂ ਦਾ ਮੌਸਮ")
        self.assertNotIn("ਮੀਂਹ ਦੀ ਸੰਭਾਵਨਾ", a["text"])
        self.assertNotIn("None", a["text"])

    def test_api_down_no_numbers(self):
        self.fetch.side_effect = weather.WeatherError("down")
        a = ask("ਅੱਜ ਮੌਸਮ")
        self.assertEqual(a["kind"], "weather_failed")
        self.assertEqual(re.findall(r"\d", a["text"]), [])

    def test_hindi_weather(self):
        a = ask("कल बारिश होगी क्या")
        self.assertEqual(a["lang"], "hi")
        self.assertIn("बारिश की संभावना 70 प्रतिशत", a["text"])


class Schemes(Base):
    def test_each_scheme_found_and_grounded(self):
        for text, key in [("ਪੀਐਮ ਕਿਸਾਨ ਦੀ ਕਿਸ਼ਤ ਕਦੋਂ ਆਊ", "pm_kisan"), ("ਫ਼ਸਲ ਬੀਮਾ", "pmfby"),
                          ("ਕਿਸਾਨ ਕ੍ਰੈਡਿਟ ਕਾਰਡ ਤੇ ਲੋਨ", "kcc"), ("ਪਰਾਲੀ ਵਾਲੀ ਮਸ਼ੀਨ ਤੇ ਸਬਸਿਡੀ", "crm_subsidy"),
                          ("पीएम किसान", "pm_kisan")]:
            a = ask(text)
            self.assertEqual(a["kind"], "scheme", text)
            self.assertEqual(a["sources"][0]["id"], key, text)
            self.assertTrue(answer.check_grounded(a["text"], a["sources"]), text)

    def test_every_scheme_text_is_grounded(self):
        """schemes.json mein koi number 'numbers' list ke bahar na ho (dono bhashaon mein)."""
        for key, s in intent.SCHEMES.items():
            for lang in ("pa", "hi"):
                src = [{"numbers": s["numbers"]}]
                self.assertTrue(answer.check_grounded(s["text"][lang], src), f"{key}/{lang}")
            self.assertTrue(s["sources"] and s["checked"], key)

    def test_general_question_lists_schemes(self):
        a = ask("ਸਰਕਾਰੀ ਸਕੀਮਾਂ ਦੱਸੋ")
        self.assertEqual(a["kind"], "scheme_list")
        self.assertIn("ਪੀਐਮ ਕਿਸਾਨ", a["text"])

    def test_crop_question_is_not_scheme(self):
        self.assertEqual(intent.understand("ਕਣਕ ਦਾ ਭਾਅ")["intent"], "price")


class Hindi(Base):
    def test_hindi_question_hindi_answer(self):
        a = ask("अमृतसर मंडी में गेहूं का भाव")
        self.assertEqual(a["lang"], "hi")
        self.assertIn("अमृतसर मंडी में गेहूं का भाव 2480", a["text"])
        self.assertTrue(answer.check_grounded(a["text"], a["sources"]))

    def test_hindi_speech_written_in_gurmukhi(self):
        """Punjabi ASR Hindi awaaz ko Gurmukhi mein likhta hai - phir bhi jawab Hindi mein."""
        a = ask("ਅੰਮ੍ਰਿਤਸਰ ਮੰਡੀ ਮੇਂ ਗੇਹੂੰ ਕਾ ਭਾਓ ਕਿਆ ਹੈ")
        self.assertEqual(a["lang"], "hi")
        self.assertIn("गेहूं", a["text"])
        self.assertEqual(intent.understand("ਅੰਮ੍ਰਿਤਸਰ ਮੰਡੀ ਵਿੱਚ ਕਣਕ ਦਾ ਕੀ ਭਾਅ ਹੈ")["lang"], "pa")

    def test_punjabi_and_roman_stay_punjabi(self):
        self.assertEqual(ask("ਕਣਕ ਦਾ ਭਾਅ")["lang"], "pa")
        self.assertEqual(ask("kanak da bhaa amritsar")["lang"], "pa")

    def test_missing_min_max_not_spoken(self):
        csv_text = "Market,Commodity,Arrival_Date,Modal_Price\nMoga,Wheat,2026-11-20,2490\n"
        data.import_csv(csv_text, replace=False)
        intent.refresh()
        try:
            a = ask("ਮੋਗਾ ਮੰਡੀ ਕਣਕ")
            self.assertIn("2490", a["text"])
            self.assertNotIn("None", a["text"])
            self.assertNotIn("ਘੱਟੋ-ਘੱਟ", a["text"])
        finally:
            data.import_csv((data.DB_PATH.parent / "sample_prices.csv").read_text(encoding="utf-8"))
            intent.refresh()


class LanguagePick(Base):
    """Punjabi aur Hindi ASR dono ka jawab aaye to sahi wala chuno."""

    def test_better_understood_wins(self):
        by_lang = {"pa-IN": [{"text": "ਹੈਲੋ ਜੀ", "confidence": 0.9}],
                   "hi-IN": [{"text": "अमृतसर में गेहूं का भाव", "confidence": 0.7}]}
        self.assertEqual(pipeline._pick_language(by_lang)[0]["text"], "अमृतसर में गेहूं का भाव")

    def test_tie_goes_to_confidence_then_punjabi(self):
        pa = [{"text": "ਕਣਕ ਦਾ ਭਾਅ", "confidence": 0.8}]
        hi = [{"text": "गेहूं का भाव", "confidence": 0.6}]
        self.assertEqual(pipeline._pick_language({"pa-IN": pa, "hi-IN": hi}), pa)
        hi_sure = [{"text": "गेहूं का भाव", "confidence": 0.95}]
        self.assertEqual(pipeline._pick_language({"pa-IN": pa, "hi-IN": hi_sure}), hi_sure)
        same = [{"text": "गेहूं का भाव", "confidence": 0.8}]
        self.assertEqual(pipeline._pick_language({"pa-IN": pa, "hi-IN": same}), pa)

    def test_one_language_empty(self):
        pa = [{"text": "ਕਣਕ ਦਾ ਭਾਅ", "confidence": 0.8}]
        self.assertEqual(pipeline._pick_language({"pa-IN": pa, "hi-IN": []}), pa)
        self.assertEqual(pipeline._pick_language({"pa-IN": [], "hi-IN": []}), [])


if __name__ == "__main__":
    unittest.main()
