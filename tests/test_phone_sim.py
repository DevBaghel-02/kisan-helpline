"""
Phone simulator ka test (website wala keypad phone). Internet ke bina chalta hai:
ASR/TTS ko mock karte hain, sirf call flow aur phone-line effect check karte hain.
Chalao: python -m unittest tests.test_phone_sim
"""
import io
import math
import struct
import unittest
import wave
from unittest import mock

from fastapi.testclient import TestClient

from app import main, phone, phoneline, pipeline, speech


def make_wav(seconds=1.0, rate=16000, freqs=(100, 1000, 6000)):
    """Test ke liye WAV: 100 Hz (phone se kategi), 1000 Hz (bachegi), 6000 Hz (kategi)."""
    n = int(seconds * rate)
    samples = [sum(0.2 * math.sin(2 * math.pi * f * i / rate) for f in freqs) for i in range(n)]
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(rate)
        w.writeframes(b"".join(struct.pack("<h", int(s * 32767)) for s in samples))
    return buf.getvalue()


def power_at(wav_bytes, freq):
    import numpy as np
    x, rate = phoneline._read_wav(wav_bytes)
    spec = np.abs(np.fft.rfft(x))
    freqs = np.fft.rfftfreq(len(x), 1 / rate)
    return spec[np.argmin(np.abs(freqs - freq))]


class PhoneLine(unittest.TestCase):
    def test_becomes_8khz(self):
        out = phoneline.to_phone_quality(make_wav())
        with wave.open(io.BytesIO(out)) as w:
            self.assertEqual(w.getframerate(), 8000)
            self.assertEqual(w.getnchannels(), 1)
            self.assertAlmostEqual(w.getnframes(), 8000, delta=5)

    def test_cuts_outside_phone_band(self):
        out = phoneline.to_phone_quality(make_wav())
        kept = power_at(out, 1000)
        self.assertLess(power_at(out, 100), kept * 0.05)        # 100 Hz kat gaya

    def test_not_wav_rejected(self):
        with self.assertRaises(Exception):
            phoneline.to_phone_quality(b"not a wav")


FAKE_ANSWER = {"ok": True, "heard": "ਅੰਮ੍ਰਿਤਸਰ ਕਣਕ", "alternatives": ["ਅੰਮ੍ਰਿਤਸਰ ਕਣਕ"], "kind": "price",
               "answered": True, "text": "ਕਣਕ ਦਾ ਭਾਅ 2480 ਰੁਪਏ", "sources": [], "timings": {"total_ms": 900}}
NO_SPEECH = {"ok": True, "heard": "", "kind": "no_speech", "answered": False,
             "text": phone.PROMPTS["no_speech"], "sources": [], "timings": {"total_ms": 500}}


class Simulator(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # TTS (internet) ki jagah nakli file path
        cls.tts = mock.patch.object(speech, "tts_path", side_effect=lambda t: speech.CACHE / "0123456789abcdef.mp3")
        cls.tts.start()
        cls.client = TestClient(main.app)
        cls.client.__enter__()

    @classmethod
    def tearDownClass(cls):
        cls.client.__exit__(None, None, None)
        cls.tts.stop()

    def answer(self, tries, result):
        with mock.patch.object(pipeline, "ask", return_value=result) as ask:
            r = self.client.post(f"/api/phone-sim/answer?tries={tries}",
                                 files={"audio": ("q.wav", make_wav(0.5), "audio/wav")})
        return r, ask

    def test_page_served(self):
        r = self.client.get("/phone")
        self.assertEqual(r.status_code, 200)
        self.assertIn("/api/phone-sim/start", r.text)

    def test_start_greets_then_records(self):
        steps = self.client.post("/api/phone-sim/start").json()["steps"]
        self.assertEqual([s["type"] for s in steps], ["say", "record"])
        self.assertEqual(steps[0]["text"], phone.PROMPTS["welcome"])
        self.assertTrue(steps[0]["audio"].startswith("/audio/"))

    def test_answer_then_ask_more(self):
        r, ask = self.answer(0, FAKE_ANSWER)
        body = r.json()
        self.assertEqual([s["type"] for s in body["steps"]], ["say", "say", "record"])
        self.assertEqual(body["result"]["heard"], "ਅੰਮ੍ਰਿਤਸਰ ਕਣਕ")
        self.assertTrue(body["line_audio"].startswith("data:audio/wav;base64,"))
        sent = ask.call_args.kwargs["wav"]                      # ASR ko 8 kHz awaaz gayi?
        with wave.open(io.BytesIO(sent)) as w:
            self.assertEqual(w.getframerate(), 8000)

    def test_two_failures_open_keypad_menu(self):
        first, _ = self.answer(0, NO_SPEECH)
        self.assertEqual([s["type"] for s in first.json()["steps"]], ["say", "record"])
        self.assertEqual(first.json()["steps"][1]["tries"], 1)
        second, _ = self.answer(1, NO_SPEECH)
        menu = second.json()["steps"][0]
        self.assertEqual(menu["type"], "menu")
        self.assertGreater(len(menu["options"]), 0)
        self.assertEqual(menu["options"][0]["digit"], 1)

    def test_keypad_choice_and_bad_digit(self):
        with mock.patch.object(pipeline, "ask", return_value=FAKE_ANSWER):
            ok = self.client.post("/api/phone-sim/menu-choice", json={"digits": "1"}).json()
        self.assertEqual(ok["steps"][0]["type"], "say")
        bad = self.client.post("/api/phone-sim/menu-choice", json={"digits": "0"}).json()
        self.assertEqual(bad["steps"][0]["type"], "menu")

    def test_same_flow_as_twilio(self):
        """Simulator aur asli call ek hi flow function use karte hain."""
        self.assertEqual(phone.flow_answer(NO_SPEECH, 1), [("menu", None)])
        self.assertEqual([k for k, _ in phone.flow_answer(FAKE_ANSWER, 0)], ["say", "say", "record"])


if __name__ == "__main__":
    unittest.main()
