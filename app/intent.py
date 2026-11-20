"""
INTENT + SLOTS: kisan ne kya poochha?

Input : ek sentence, jaise "ਅੰਮ੍ਰਿਤਸਰ ਮੰਡੀ ਵਿੱਚ ਕਣਕ ਦਾ ਕੀ ਭਾਅ ਹੈ"
Output: {"intent": "price", "crops": ["wheat"], "market": "Amritsar", "day": None}

Ye RULE-BASED hai (LLM nahi), 3 wajah se:
  - Fast: 5-10 ms, network nahi chahiye  -> 6 second ke budget mein bahut time bachta hai.
  - Kabhi number nahi banata: ye sirf shabd pehchaanta hai, jawab answer.py database se banata hai.
  - Samjhaana aasaan: viva mein har line explain ho sakti hai.

Judges ki CSV mein koi nayi fasal/mandi ho jo synonyms.json mein nahi hai, to refresh()
use database se padh ke apne aap jod deta hai (English naam se match).
"""
import json
from pathlib import Path

from . import data
from .normalise import Matcher, skeleton

_MANDI_WORDS = {skeleton(w) for w in ["ਮੰਡੀ", "ਮੰਡੀਓਂ", "ਮੰਡੀਚ", "mandi", "मंडी"]}

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
SYN = json.loads((DATA_DIR / "synonyms.json").read_text(encoding="utf-8"))
SCHEMES = json.loads((DATA_DIR / "schemes.json").read_text(encoding="utf-8"))["schemes"]

crop_info: dict[str, dict] = {}     # "wheat" -> {"pa": "ਕਣਕ", "hi": "गेहूं", "icon": ..., "db": ["Wheat"]}
market_info: dict[str, dict] = {}   # "Amritsar" -> {"pa": "ਅੰਮ੍ਰਿਤਸਰ", "hi": "अमृतसर", "lat": .., "lon": ..}
_crop_matcher = _market_matcher = None
_intent_matcher = Matcher(SYN["intents"])
_time_matcher = Matcher(SYN["time"])
_scheme_matcher = Matcher({k: s["words"] for k, s in SCHEMES.items()})


# Punjabi ASR Hindi awaaz ko bhi Gurmukhi mein likh deta hai: "ਅੰਮ੍ਰਿਤਸਰ ਮੰਡੀ ਮੇਂ ਗੇਹੂੰ ਕਾ ਭਾਓ ਕਿਆ ਹੈ".
# Ye shabd sirf Hindi mein bolte hain (Punjabi mein "ਵਿੱਚ", "ਦਾ", "ਕੀ"). Inse pata chalta hai kisan Hindi bol raha hai.
_HINDI_IN_GURMUKHI = {skeleton(w) for w in ["ਮੇਂ", "ਕਾ", "ਕਿਆ", "ਕਯਾ", "ਹੋਗੀ", "ਹੋਗਾ", "ਬਤਾਓ", "ਬਤਾਈਏ",
                                             "ਕਿਤਨਾ", "ਕਿਤਨੇ", "ਹੈਂ", "ਮੁਝੇ", "ਆਜ"]}
_PUNJABI_ONLY = {skeleton(w) for w in ["ਦਾ", "ਦੀ", "ਦੇ", "ਵਿੱਚ", "ਵਿਚ", "ਦੱਸੋ", "ਕਿੰਨਾ", "ਨੂੰ", "ਅੱਜ", "ਪਵੇਗਾ"]}


def detect_lang(text: str) -> str:
    """
    Kis bhasha mein jawab dein? Devanagari mein likha -> Hindi. Gurmukhi mein Hindi ke shabd
    (ਮੇਂ, ਕਾ, ਕਿਆ) zyada hon Punjabi ke shabdon (ਵਿੱਚ, ਦਾ) se -> Hindi. Baaki sab Punjabi (humara main user).
    """
    devanagari = sum("ऀ" <= ch <= "ॿ" for ch in text)
    gurmukhi = sum("਀" <= ch <= "੿" for ch in text)
    if devanagari > gurmukhi:
        return "hi"
    tokens = skeleton(text).split()
    hindi = sum(t in _HINDI_IN_GURMUKHI for t in tokens)
    punjabi = sum(t in _PUNJABI_ONLY for t in tokens)
    return "hi" if hindi > punjabi else "pa"


def _db_names_for(crop: dict, commodities: list[str]) -> list[str]:
    """synonyms.json ke match_db/exclude_db se database ke Commodity naam dhoondo."""
    out = []
    for c in commodities:
        low = c.lower()
        if any(m in low for m in crop["match_db"]) and not any(x in low for x in crop["exclude_db"]):
            out.append(c)
    return out


def refresh():
    """Database badalne ke baad (CSV upload) matchers dobara banao."""
    global _crop_matcher, _market_matcher
    commodities, markets = data.all_commodities(), data.all_markets()
    crop_info.clear()
    market_info.clear()
    crop_words, market_words = {}, {}

    covered = set()
    for key, c in SYN["crops"].items():
        db_names = _db_names_for(c, commodities)
        crop_info[key] = {"pa": c["pa"], "pa_of": c.get("pa_of", c["pa"]), "hi": c.get("hi", c["pa"]),
                          "icon": c.get("icon", "🌿"), "db": db_names}
        crop_words[key] = c["words"]
        covered.update(db_names)
    for c in commodities:                       # nayi fasal jo synonyms mein nahi hai
        if c not in covered:
            base = c.split("(")[0].strip()
            crop_info[c] = {"pa": c, "pa_of": c, "hi": c, "icon": "🌿", "db": [c]}
            crop_words[c] = [c, base]

    # Jo mandiyan synonyms.json mein hain, unhe bhi pehchaano chahe data na ho.
    # Warna kisan "ਬਠਿੰਡਾ" bole aur hum na pehchaanein, to galti se doosri mandi ka bhaa bata denge.
    for m, info in SYN["markets"].items():
        market_info[m] = {"pa": info["pa"], "hi": info.get("hi", m), "has_data": m in markets}
        if "lat" in info:
            market_info[m].update(lat=info["lat"], lon=info["lon"])
        market_words[m] = info["words"] + [m] + ([info["hi"]] if "hi" in info else [])
    for m in markets:                           # nayi mandi jo synonyms mein nahi hai
        if m not in market_info:
            market_info[m] = {"pa": m, "hi": m, "has_data": True}
            market_words[m] = [m]

    _crop_matcher = Matcher(crop_words)
    _market_matcher = Matcher(market_words)


def understand(text: str) -> dict:
    if _crop_matcher is None:
        refresh()
    crops = _crop_matcher.find(text)
    markets = _market_matcher.find(text)
    intents = _intent_matcher.find(text)
    times = _time_matcher.find(text)

    crop_keys = [k for k, _, _ in crops]
    # "ਬਾਸਮਤੀ ਝੋਨਾ" bola ho to sirf basmati (zyada specific) rakho
    if "basmati" in crop_keys and "paddy" in crop_keys:
        crop_keys.remove("paddy")
    crop_keys = crop_keys[:2]                    # ek sawaal mein max 2 fasalein

    schemes = _scheme_matcher.find(text)

    # Kaunsa sawaal hai? Priority: scheme ka naam > mausam > bhaav.
    # "ਮੰਡੀ" bhaav wala shabd bhi hai, isliye "ਅੰਮ੍ਰਿਤਸਰ ਮੰਡੀ ਦਾ ਮੌਸਮ" ko mausam hi maano.
    intent_keys = {k for k, _, _ in intents}
    real_price_word = any(k == "price" and p not in _MANDI_WORDS for k, _, p in intents)
    if schemes and not crop_keys:
        intent = "scheme"
    elif "weather" in intent_keys and not (crop_keys and real_price_word):
        intent = "weather"
    elif "scheme" in intent_keys and not crop_keys:
        intent = "scheme"
    elif crop_keys or "price" in intent_keys:
        intent = "price"                         # sirf fasal ka naam bola -> zyaadatar bhaa hi poochte hain
    else:
        intent = None

    # Anjaan mandi: "ਸਮਰਾਲਾ ਮੰਡੀ" jaisa naam jo humari list mein nahi hai.
    # "ਮੰਡੀ" se pehle wala shabd utha lo, taaki bot bole "us mandi ka data nahi" -
    # galti se kisi doosri mandi ka bhaa na bata de.
    unknown_market = None
    if not markets:
        tokens = skeleton(text).split()
        crop_pieces = {p for _, _, p in crops}
        for i, t in enumerate(tokens):
            if t in _MANDI_WORDS and i > 0 and tokens[i - 1] not in crop_pieces and len(tokens[i - 1]) > 2:
                unknown_market = tokens[i - 1]
                break

    return {
        "intent": intent,
        "crops": crop_keys,
        "market": markets[0][0] if markets else None,
        "unknown_market": unknown_market,
        "day": times[0][0] if times else None,
        "scheme": schemes[0][0] if schemes else None,
        "lang": detect_lang(text),
        "evidence": {                            # debugging/viva ke liye: kaunsa shabd suna gaya
            "crops": [(k, round(s, 2), p) for k, s, p in crops],
            "markets": [(k, round(s, 2), p) for k, s, p in markets],
            "intents": [(k, round(s, 2), p) for k, s, p in intents],
            "schemes": [(k, round(s, 2), p) for k, s, p in schemes],
        },
    }
