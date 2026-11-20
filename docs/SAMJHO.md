# SAMJHO: poora project Hinglish mein (viva ki tayyari)

Har module ke liye 4 sawaal: **Input kya? Output kya? Andar kya hota hai? Aisa kyun?**
Har member ko sab modules ka overview aana chahiye. Owner ko apna module gehraai se.

---

## Bada picture (30 second mein samjhao)
Kisan bolta hai, server awaaz ko text banata hai, text se fasal/mandi/din nikaalta hai, database se
price uthata hai, fixed Punjabi sentence mein bharta hai, aur us sentence ki awaaz banake sunata hai.
**LLM use nahi kiya.** Isliye price bana ke bolne ka sawaal hi nahi uthta.

```
awaaz → [speech.py] → text → [normalise.py + intent.py] → {fasal, mandi, din}
      → [data.py: SQLite] → row → [answer.py: template + check] → Punjabi text → [speech.py] → awaaz
```
Website aur phone call, dono yahi ek `pipeline.ask()` use karte hain.

---

## 1. `app/data.py`: database (owner: C)
- **Input:** CSV file (judges ki ya Agmarknet ki).
- **Output:** SQLite table `prices`, aur functions jaise `latest_prices(["Wheat"], "Amritsar")`.
- **Andar:**
  1. CSV ke column naam saaf karo ("Modal Price (Rs/Quintal)" → "modalpricersquintal").
  2. `HEADER_ALIASES` se standard naam pe map karo.
  3. Date ke 6 formats try karo.
  4. "₹2,480" ko 2480 banao.
  5. Kharab rows reject karo, aur report do ki kaunsi reject hui.
- **Kyun:** judges apni CSV laayenge jiske column naam alag ho sakte hain. Code badle bina load honi chahiye.
- **Viva sawaal:** "Sabse nayi price kaise milti hai?" → SQL mein har (market, commodity) ka `MAX(arrival_date)` nikaal ke usi row ko JOIN karte hain.

## 2. `app/normalise.py`: spelling ki galtiyan (owner: B)
- **Input:** koi bhi text. **Output:** match hue shabd + score (0 se 1).
- **Andar, 3 tareeke:**
  1. `skeleton()`: chhote nishaan hatao (addak ੱ, nukta ਼, halant ੍), tippi = bindi. "ਕੱਲ੍ਹ" aur "ਕਲ੍ਹ" ek ho jaate hain.
  2. `to_roman()`: Gurmukhi/Hindi ko rough English mein badlo aur 'a' hata do. "ਕਣਕ" → "knk" aur "kanak" → "knk": dono same.
  3. `Matcher.find()`: sentence ke 1, 2 aur 3 shabd wale tukde banao, har jaane-pehchaane shabd se `difflib` ratio nikaalo. 0.82 se upar = match. 3 akshar se chhote shabd sirf exact.
- **Kyun:** ASR har baar ek jaisi spelling nahi likhta. Exact match se bot fail ho jaata.
- **Bug jo humne pakda (viva mein batao!):** regex ka `\w` Gurmukhi matra (ਾ ਿ ੋ) ko akshar nahi maanta tha. "ਹੈਲੋ" toot ke "ਹ ਲ" ban gaya aur galti se "ਆਲੂ" match ho gaya. Fix: `unicodedata.category()` se akshar (L), matra (M) aur number (N) rakhe.

## 3. `app/intent.py`: kisan ne kya poocha (owner: B)
- **Input:** "ਅੰਮ੍ਰਿਤਸਰ ਮੰਡੀ ਵਿੱਚ ਕਣਕ ਦਾ ਕੀ ਭਾਅ ਹੈ"
- **Output:** `{"intent": "price", "crops": ["wheat"], "market": "Amritsar", "day": None}`
- **Andar:** `data/synonyms.json` se 4 matchers banao (fasal, mandi, intent, din) aur sab pe `find()` chalao. Phir 3 rules:
  - Basmati + jhona dono mile → sirf basmati.
  - Sirf fasal boli → maan lo bhaa poocha hai.
  - "X ਮੰਡੀ" bola aur X humari list mein nahi → `unknown_market`. Isse bot kisi doosri mandi ka bhaa nahi batata.
- **`refresh()`:** CSV upload ke baad nayi fasalein/mandiyan apne aap jud jaati hain (English naam se).
- **Kyun rule-based, LLM kyun nahi?**
  1. ~10 ms mein ho jaata hai, LLM ko 1-2 second lagte.
  2. Internet/API key nahi chahiye.
  3. Har decision explain ho sakta hai.
  4. Price banane ka risk zero.

## 4. `app/answer.py`: grounded jawab (owner: C)
- **Input:** intent ka output. **Output:** Punjabi (ya Hindi) text + `sources` (jawab kahan se aaya).
- **Teen tarah ke sawaal:** bhaav (database), mausam (`weather.py`), sarkari scheme (`data/schemes.json`). Teeno ka har number `check_grounded()` se check hota hai.
- **Bhasha:** saare templates `T["pa"]` aur `T["hi"]` mein hain. Hindi sawaal → Hindi jawab, Hindi naam (गेहूं, अमृतसर).
- **Andar (bhaav):** case ke hisaab se fixed template:
  - Mandi + fasal → us mandi ka bhaa (modal, min, max).
  - Sirf fasal → 3 mandiyon ke bhaa (pehle Amritsar district ki).
  - Mandi mein fasal nahi → "us mandi mein nahi hai" + doosri mandiyan, naam ke saath.
  - Anjaan fasal/mandi → "ਮਾਫ਼ ਕਰਨਾ, ਮੇਰੇ ਕੋਲ ਨਹੀਂ ਹੈ".
  - Date hamesha boli jaati hai ("ਕੱਲ੍ਹ", "18 ਨਵੰਬਰ ਨੂੰ").
- **Safety net, `check_grounded()`:** bolne se pehle jawab ke har number ko source rows (price, date ka din, saal) se milaata hai. Ek bhi number bahar ka mila to jawab rok do.
- **Grammar:** "ਝੋਨਾ ਦਾ" galat hai, "ਝੋਨੇ ਦਾ" sahi. Isliye synonyms mein `pa_of` field rakha.
- CSV mein min/max price khaali ho to sirf modal bolte hain (pehle galti se "None" bolta tha, ab test hai).
- **Viva sawaal:** "LLM fake price kaise nahi bolega?" → LLM hai hi nahi. Numbers sirf DB row se aate hain, aur check_grounded() double-check karta hai. Test `test_never_invents_numbers` ye prove karta hai.

## 5. `app/speech.py`: awaaz (owner: A)
- **ASR (awaaz → text):** `speech_recognition` library, Google ka free endpoint, `show_all=True` (3-5 alternatives milte hain). Input WAV file hai.
  - `transcribe_multi()`: wahi awaaz **Punjabi (pa-IN) aur Hindi (hi-IN) dono** ko ek saath (parallel threads) bhejte hain, isliye time nahi badhta.
- **TTS (text → awaaz):** `gTTS`, output MP3. Text Devanagari mein ho to Hindi awaaz, warna Punjabi.
- **Speed tricks:**
  1. Jawab ko "।" pe sentences mein todo aur sab sentences ki awaaz parallel threads mein banao. Phir MP3 jod do.
  2. Har sentence cache hota hai (`data/tts_cache`), dobara bolne pe 0 ms.
  3. Fixed lines (welcome, "dobara bolo") server start hote hi pehle se bana lo.
- **Kyun ye tools:** free hain, key nahi chahiye, Punjabi support hai. Sab ek file mein hai, isliye Bhashini lagana ho to sirf yahi file badlegi.

## 6. `app/pipeline.py`: sab jodna (owner: A)
- `ask(text=...)` ya `ask(wav=...)`: steps chalao, har step ka time (ms) naapo, aur query log mein likho.
- **n-best trick, `_pick_best()`:** ASR ke har alternative ko score do (fasal/scheme mili = 2, mandi = 1, intent = 1) aur sabse achha chuno. Shor mein pehla guess galat ho to doosra kaam aa jaata hai.
- **Bhasha chunna, `_pick_language()`:** Punjabi aur Hindi ASR mein se jiski baat zyada samajh aayi (score), barabar ho to jispe ASR ko zyada bharosa (confidence), wo bhi barabar ho to Punjabi.
- **Hindi jo Gurmukhi mein likhi gayi:** Punjabi ASR Hindi awaaz ko bhi Gurmukhi mein likhta hai ("ਮੰਡੀ ਮੇਂ ਗੇਹੂੰ ਕਾ ਭਾਓ ਕਿਆ"). `intent.detect_lang()` "ਮੇਂ, ਕਾ, ਕਿਆ" jaise sirf-Hindi shabd ginta hai → jawab Hindi mein.

## 7. `app/phone.py`: keypad phone call (owner: D)
- Twilio ek "webhook" bhejta hai, hum XML (TwiML) wapas bhejte hain ki call mein kya karna hai:
  - `<Play>` awaaz sunao, `<Record>` kisan ko record karo, `<Gather>` keypad button padho.
- **Flow:**
  1. welcome → record
  2. jawab → "hor sawaal?" → record → ...
  3. 2 baar samajh nahi aaya → keypad menu ("ਕਣਕ ਲਈ 1 ਦਬਾਓ")
  4. Menu mein **0 = mausam**.
- **Ek flow, do raaste:** `flow_*()` functions decide karte hain aage kya hoga ("steps": say / record / menu). Twilio ke liye wahi steps TwiML (XML) bante hain (`/voice/*`), simulator ke liye JSON (`/api/phone-sim/*`). Isliye simulator = asli call ka logic.
- **Missed call:** `/api/call-me` se system kisan ko call karta hai, isliye kisan ka paisa nahi lagta.
- **Kyun keypad fallback:** khet mein shor hota hai. Awaaz fail ho tab bhi jawab milna chahiye.
- **Security, 3 cheezein:**
  1. Twilio signature check: nakli request aaye to 403.
  2. Recording sirf api.twilio.com se download hoti hai, isliye humara token kisi aur URL pe nahi jaata.
  3. call-me ke liye ADMIN_TOKEN chahiye.
  Setup ke steps: `docs/TWILIO_SETUP.md`.

## 8. `static/index.html`: website (owner: D)
- Ek bada mic button hai. Browser ki apni noise suppression ON hai.
- Chup hone ke 1.5 second baad recording apne aap ruk jaati hai. Awaaz browser mein hi 16 kHz WAV ban jaati hai, isliye file chhoti hai aur 2G pe upload ho jaati hai.
- Fasal ki photo pe tap karo to bina bole bhaa mil jaata hai.
- Jawab apne aap bajta hai, saath mein "ਦੁਬਾਰਾ ਸੁਣੋ" button hai.
- Neeche har step ka time aur source row dikhti hai. Ye judges ke liye hai.
- ਮੌਸਮ (ਅੱਜ / ਭਲਕੇ / ਪਰਸੋਂ) aur ਸਰਕਾਰੀ ਸਕੀਮਾਂ ke tiles bhi hain. Mandi chuni ho to usi ka mausam.

## 9. `app/weather.py`: mausam (owner: C)
- **Source:** Open-Meteo (free, koi API key nahi). Har mandi ki location (`lat`/`lon`) `data/synonyms.json` mein hai. Mandi na boli → Amritsar.
- **Din:** "ਕੱਲ੍ਹ" ke do matlab hain. Bhaav ke sawaal mein beeta hua kal, mausam ke sawaal mein aane wala kal. `target_day()` ye sambhalta hai. "ਭਲਕੇ" = kal, "ਪਰਸੋਂ" = parson.
- **Jawab:** tapmaan (min-max) + barish ki sambhavna. 50% se zyada ho to salah: "ਸਪਰੇਅ ਨਾ ਕਰੋ".
- **Cache:** 30 minute tak dobara API nahi bulate. API fail → "abhi mausam nahi mil raha", koi number nahi.

## 10. `data/schemes.json`: sarkari schemes (owner: C)
- 4 schemes: PM-KISAN, Fasal Bima (PMFBY), Kisan Credit Card, Parali machine subsidy (Punjab CRM).
- Har scheme mein: Punjabi + Hindi jawab, `numbers` (jawab ke saare number, grounding ke liye), `sources` (official link), `checked` (kab check kiya).
- Test `test_every_scheme_text_is_grounded` check karta hai ki koi number `numbers` list ke bahar na ho.
- Scheme badle to sirf ye file badlo, code nahi.

## 11. Phone simulator: `static/phone.html` + `app/phoneline.py` (owner: D)
- Twilio trial ab number kharidne nahi deta (paid account chahiye). Isliye `/phone` par keypad phone ka simulator banaya.
- Server ka **wahi** call flow chalta hai: greeting → beep → sawaal → jawab → 2 fail pe keypad menu.
- **Phone line effect (`phoneline.py`):** awaaz ko asli call jaisa banate hain: sirf 300–3400 Hz (FFT se), 8000 samples/second, 8-bit mu-law. Isliye simulator ki accuracy asli call ke kareeb hai, laptop mic jaisi badhiya nahi. Call log mein "Hear your voice as the phone line sent it" se sun bhi sakte ho.

---

## Viva ke pakke sawaal + jawab
| Sawaal | Jawab (short) |
|---|---|
| Fake price kaise roka? | LLM nahi hai. Number sirf DB row se aata hai, aur `check_grounded()` + unit test isse check karte hain. |
| Shor mein kya hota hai? | 3 layer: browser noise suppression, ASR ke n-best alternatives, aur 2 baar fail hone pe keypad menu. |
| 6 second kaise? | ASR ~0.6-1.4s (Punjabi + Hindi parallel) + samajhna ~10ms + DB ~1ms + TTS (parallel + cache). Benchmark average ~0.9s, max ~1.5s. |
| Mausam ke number kahan se? | Open-Meteo API ke jawab se. Wahi grounding check: jawab ka har number API ke jawab mein hona chahiye. |
| Schemes galat to nahi? | Har number official source se check kiya (link + date `schemes.json` mein). Jo pakka nahi (Punjab mein Fasal Bima lagu hai ya nahi), wo bot khud bolta hai "apne kheti daftar se poochho". |
| Hindi? | Hindi sawaal → Hindi jawab + Hindi awaaz. Punjabi aur Hindi ASR saath chalte hain. |
| Asli phone number kyun nahi? | Twilio trial number nahi deta, paid chahiye. Code Twilio ke liye tayyar aur tested hai; simulator wahi flow chalata hai. Real life mein Exotel ka missed-call number. |
| Judges ki CSV? | `/admin` pe upload karo. Column naam apne aap pehchaane jaate hain aur nayi fasal/mandi `refresh()` se jud jaati hai. |
| Dataset mein nahi hai to? | "ਮੇਰੇ ਕੋਲ ਨਹੀਂ ਹੈ". Anjaan mandi ("ਸਮਰਾਲਾ ਮੰਡੀ") bhi pakdi jaati hai. |
| Real prices kahan se? | data.gov.in ki Agmarknet API (free key). Roz ek cron job DB mein daalega. |
| Keypad phone? | Twilio call: record → jawab → keypad menu. Real life mein Exotel ka missed-call number. |

## Honest limits (presentation mein khud bolo)
- Free Google ASR unofficial hai aur rate-limited hai. Replacement ka plan Bhashini hai.
- Phone (8 kHz) awaaz pe mandi ke naam kabhi galat sune jaate hain (test mein "ਤਰਨ ਤਾਰਨ" → "17 17"). Tab bot kai mandiyon ke bhaa unke naam ke saath batata hai, galat mandi ke naam se kabhi nahi.
- Asli phone number nahi hai (Twilio paid chahiye). Demo phone simulator se hota hai.
- Schemes sirf 4 hain, aur unki jaankari haath se update karni padti hai (`checked` date dekho).
- Hindi bolne par kabhi-kabhi Punjabi mein jawab aa sakta hai, agar sawaal mein koi sirf-Hindi shabd na ho.
- Render free plan: 15 minute khaali rahe to server so jaata hai (pehli request ~1 minute), aur restart pe uploaded CSV chali jaati hai.

## AI declaration (submission form ke liye, apne hisaab se badlo)
> Claude (Anthropic) was used to generate the initial code for all modules. The team decided the architecture (rule-based NLU, no LLM in the answer path, DB-only numbers), built and verified the synonym dataset, recorded the test audio, and tested and modified the code.
