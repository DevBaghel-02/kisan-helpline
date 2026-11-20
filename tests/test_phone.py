"""
Phone call routes ka test, asli Twilio ke bina. Hum Twilio jaisi requests khud bana ke bhejte hain,
aur fake auth token se sahi "X-Twilio-Signature" bhi banate hain.
Chalao: python -m unittest tests.test_phone
"""
import os
import unittest
from pathlib import Path
from unittest import mock

from fastapi.testclient import TestClient
from twilio.request_validator import RequestValidator

FAKE = {"TWILIO_AUTH_TOKEN": "test-token-123", "TWILIO_ACCOUNT_SID": "ACtest",
        "PUBLIC_BASE_URL": "https://kisan.example.com", "ADMIN_TOKEN": "secret-admin"}


class Phone(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.env = mock.patch.dict(os.environ, FAKE)
        cls.env.start()
        from app import main, phone
        cls.phone = phone
        cls.client = TestClient(main.app)
        cls.client.__enter__()

    @classmethod
    def tearDownClass(cls):
        cls.client.__exit__(None, None, None)
        cls.env.stop()

    def post_signed(self, path, form=None):
        form = form or {}
        sig = RequestValidator(FAKE["TWILIO_AUTH_TOKEN"]).compute_signature(FAKE["PUBLIC_BASE_URL"] + path, form)
        return self.client.post(path, data=form, headers={"X-Twilio-Signature": sig})

    def test_unsigned_request_rejected(self):
        self.assertEqual(self.client.post("/voice/incoming").status_code, 403)

    def test_wrong_signature_rejected(self):
        r = self.client.post("/voice/incoming", headers={"X-Twilio-Signature": "nakli"})
        self.assertEqual(r.status_code, 403)

    def test_incoming_plays_welcome_and_records(self):
        r = self.post_signed("/voice/incoming", {"From": "+911234567890"})
        self.assertEqual(r.status_code, 200)
        self.assertIn("<Play>https://kisan.example.com/audio/", r.text)
        self.assertIn("/voice/answer?tries=0", r.text)

    def test_spoken_question_answered(self):
        wav = Path("tests/audio/s03_noisy.wav")
        if not wav.exists():
            self.skipTest("pehle: python scripts/benchmark.py --make-synthetic")
        with mock.patch.object(self.phone, "_download_recording", return_value=wav.read_bytes()):
            r = self.post_signed("/voice/answer?tries=0",
                                 {"RecordingUrl": "https://api.twilio.com/2010-04-01/Accounts/ACtest/Recordings/RE1"})
        self.assertEqual(r.text.count("<Play>"), 2)          # jawab + "hor sawaal?"
        self.assertIn("tries=0", r.text)

    def test_two_failures_go_to_keypad_menu(self):
        r1 = self.post_signed("/voice/answer?tries=0", {})
        self.assertIn("tries=1", r1.text)
        r2 = self.post_signed("/voice/answer?tries=1", {})
        self.assertIn("/voice/menu", r2.text)
        menu = self.post_signed("/voice/menu", {})
        self.assertIn('<Gather input="dtmf"', menu.text)

    def test_keypad_choice(self):
        r = self.post_signed("/voice/menu-choice", {"Digits": "1"})
        self.assertIn("<Play>", r.text)
        bad = self.post_signed("/voice/menu-choice", {"Digits": "#"})
        self.assertIn("/voice/menu", bad.text)

    def test_recording_url_must_be_twilio(self):
        with self.assertRaises(ValueError):
            self.phone._download_recording("https://evil.example.com/steal")

    def test_call_me_needs_admin_token(self):
        r = self.client.post("/api/call-me", json={"phone": "+911234567890"})
        self.assertEqual(r.status_code, 401)
        r = self.client.post("/api/call-me", json={"phone": "12345"}, headers={"X-Admin-Token": "secret-admin"})
        self.assertEqual(r.status_code, 400)


if __name__ == "__main__":
    unittest.main()
