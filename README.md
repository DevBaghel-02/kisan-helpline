# Kisan Helpline: Punjabi voice helpline for farmers (Code Fuzion 2026, H6)

A farmer asks for a mandi price in Punjabi (or Hindi) by voice, on a **keypad phone call** or on a simple website, and hears the answer in Punjabi. Every number in an answer comes from the price database; when the data isn't there, the bot says so instead of guessing.

> `data/sample_prices.csv` contains **made-up sample prices for testing only**. Real prices come from the judges' dataset (upload it at `/admin`) or from data.gov.in (Agmarknet).

## Run it locally
```powershell
pip install -r requirements.txt
python -m uvicorn app.main:app --port 8000
```
- Farmer page: http://localhost:8000
- Admin (CSV upload, query log, text test): http://localhost:8000/admin
- Phone call simulator (keypad phone, same call flow as Twilio): http://localhost:8000/phone

## Tests
```powershell
python -m unittest discover tests          # logic tests, no internet needed
python scripts/benchmark.py --make-synthetic   # voice tests: TTS questions + background noise
python scripts/benchmark.py                # after you add your own recordings in tests/audio/
```

## How it works
```
voice ─► speech.py (Google free ASR, pa-IN, n-best) ─► intent.py + normalise.py (crop/mandi/day, fuzzy)
      ─► answer.py (SQLite lookup, Punjabi template, grounding check) ─► speech.py (gTTS, parallel, cached) ─► voice
```
| File | Job |
|---|---|
| `app/data.py` | SQLite, CSV import with flexible column names, latest-price queries, query log |
| `app/normalise.py` | Gurmukhi "skeleton", rough transliteration, fuzzy matching |
| `app/intent.py` | Finds intent, crops, mandi and day (rule-based, ~10 ms) |
| `app/answer.py` | Builds the Punjabi answer from DB rows; `check_grounded()` blocks any number not in the source rows |
| `app/speech.py` | ASR + TTS providers (swap for Bhashini / AI4Bharat here only) |
| `app/pipeline.py` | Joins the steps, picks the best ASR alternative, times each stage |
| `app/phone.py` | Call flow: record → answer → repeat; keypad menu after 2 failures. One `flow_*` logic, two outputs: TwiML for Twilio (`/voice/*`) and JSON for the simulator (`/api/phone-sim/*`) |
| `app/phoneline.py` | Makes simulator audio sound like a real call (300–3400 Hz, 8 kHz, 8-bit mu-law) before ASR |
| `app/main.py` | FastAPI routes |
| `data/synonyms.json` | Crop/mandi words in Gurmukhi, Roman and Hindi. Edit this to teach the bot new words |

## Phone calls
**Without a phone number:** open `/phone`. It runs the same call flow (greeting, beep, question, answer, keypad menu after two failed tries), and passes your voice through a phone-line filter first, so recognition is tested at real call quality.

**Real calls (Twilio):** a Twilio trial account can no longer buy a number without upgrading, so this needs a paid account. Full step-by-step guide (Hinglish): [docs/TWILIO_SETUP.md](docs/TWILIO_SETUP.md). Short version:
1. Create a Twilio trial account, get a number, verify your phone, and turn on India in Geo Permissions.
2. Copy `.env.example` to `.env` and fill in your values.
3. Run the server, then `cloudflared tunnel --url http://localhost:8000`, and put that URL in `PUBLIC_BASE_URL`.
4. Run `python scripts/twilio_setup.py --apply` (checks everything, sets the webhook), then `--call +91…`.

Security: `/voice/*` checks the Twilio signature, recordings are fetched only from api.twilio.com, and `/api/call-me` needs `ADMIN_TOKEN`.

## Deploy (Render free tier)
- Build command: `pip install -r requirements.txt`
- Start command: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`

## Known limits (be honest in the demo)
- ASR uses Google's free, unofficial endpoint. It is good but rate-limited; Bhashini is the planned replacement.
- On 8 kHz phone audio, place names are sometimes misheard (e.g. "ਤਰਨ ਤਾਰਨ" → "17 17"). The bot then lists prices from several mandis with their names, so it never pins a price to the wrong mandi.
- Weather and schemes are not in the MVP yet; the bot says "coming soon".
