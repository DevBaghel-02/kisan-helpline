# Pitch: Kisan Helpline (H6, Voice Helpline for Farmers in Punjabi)

## 2-minute pitch
**Problem (20s)**
"Small farmers around Amritsar need to know today's mandi price before they sell. A wrong price means selling cheap. Many of them use basic keypad phones and can't read English, so apps and websites don't reach them. We chose H6: a voice helpline in Punjabi."

**Solution (40s)**
"A farmer just speaks in Punjabi or Hindi, for example 'ਅੰਮ੍ਰਿਤਸਰ ਮੰਡੀ ਵਿੱਚ ਕਣਕ ਦਾ ਭਾਅ?' ('What is the wheat price in Amritsar mandi?'), and hears the answer in Punjabi. There are two ways in:
1. **A phone call** that works on any keypad phone. If our system can't understand the voice twice because of noise, it switches to a keypad menu: press 1 for wheat, 2 for paddy.
2. **A very simple website** for smartphone users: one big mic button, crop pictures to tap, no login and no typing, and it loads on 2G."

**Our engineering (40s)**
"The statement warns that LLMs invent prices, so we kept the LLM out of the answer path completely.
- After speech-to-text, our own normaliser handles spelling and dialect variation. 'ਕਨਕ', 'kanak' and 'गेहूं' all map to wheat, using Gurmukhi skeletons, transliteration and fuzzy matching.
- Every number in the answer comes from a database row. Before we speak, a grounding checker verifies each number against its source row.
- If the data isn't there, the bot says 'ਮੇਰੇ ਕੋਲ ਨਹੀਂ ਹੈ' ('I don't have that'). It never guesses."

**Progress (20s)**
"The core works end to end. Punjabi voice in, Punjabi voice out, in about 2 seconds on average against a 6-second limit. We have 15 automated tests, including noisy-audio tests. The phone-call flow is built and secured, and tonight we test it on a real call."

## Demo (1 minute)
1. Website → mic → say "ਅੰਮ੍ਰਿਤਸਰ ਮੰਡੀ ਵਿੱਚ ਕਣਕ ਦਾ ਭਾਅ" → spoken answer.
2. Ask "ਸੇਬ ਦਾ ਭਾਅ" (apple, not in the data) → "I don't have that". This shows there are no made-up numbers.
3. `/admin` → per-stage timing, the source row, and the CSV upload for the judges' dataset.

## Likely questions and answers
| Question | Answer |
|---|---|
| How do you stop made-up prices? | There is no LLM in the answer path. Answers are fixed Punjabi templates filled from database rows, a grounding checker verifies every number before speaking, and a unit test proves out-of-dataset questions never get a number. |
| Why not use an LLM to understand the question? | Rule-based matching takes ~10 ms versus 1–2 s for an LLM, works without an API, can't hallucinate, and every decision is explainable. An LLM could be an optional fallback later, but only to fill slots, never to write numbers. |
| What about background noise? | Three layers: browser noise suppression, picking the best of several speech-recognition alternatives, and a keypad fallback on calls. |
| How do you hit 6 seconds? | Speech-to-text ~1.5 s, understanding ~10 ms, database ~1 ms, text-to-speech ~1 s. The TTS is fast because we synthesise sentences in parallel and cache them. Average is ~2 s. |
| What if our dataset has different columns? | Upload it at /admin. Column names are detected automatically, and new crops and mandis are added to the matcher automatically. |
| What if the farmer asks about a mandi you don't have? | The bot says it has no data for that mandi. It never answers with another mandi's price under the wrong name. |
| Where do real prices come from? | The data.gov.in Agmarknet API (free), fetched daily into our database. Weather from Open-Meteo; schemes from official pages. |
| Why a phone call? | The target users have keypad phones. In real life: a missed-call number (Exotel/Knowlarity), and the system calls back so the call is free for the farmer. |
| What doesn't work yet? | Phone-quality (8 kHz) audio sometimes mishears place names, so the bot then lists several mandis with their names. Weather and schemes are next. The speech service is a free endpoint; Bhashini is the planned replacement. |
| Which AI tools did you use? | Claude for generating code. The architecture, the decision to keep the LLM out of the answer path, the synonym data, the testing and the recordings are ours. |

## Questions to ask the mentors
1. What format will the judges' dataset be in (CSV? which columns?), and will it include schemes and weather?
2. Does a phone-call demo count, or should we focus on the web app?
3. Do answers need to be in Hindi too, or only Punjabi?
4. How will noise be tested: live speech, or recorded audio files?
5. How is the 6 seconds measured: from the end of speech to the start of the answer, or to the end of the answer?
6. Is code written before the event start allowed, given that AI use is declared?
