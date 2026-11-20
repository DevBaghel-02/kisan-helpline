"""
ANSWER ENGINE: grounded jawab banana (Punjabi, ya Hindi sawaal ho to Hindi).

SABSE ZAROORI RULE: jawab mein har number kisi SOURCE se aata hai.
  - Bhaav   : database ki price row
  - Mausam  : Open-Meteo ka jawab (weather.py)
  - Schemes : data/schemes.json (official sources ke link ke saath)
  Jawab fixed templates se banta hai, numbers source se bhare jaate hain.
  - check_grounded() bolne se pehle jawab ke har number ko sources se milaata hai.
    Ek bhi number match na ho to jawab rok ke "ਮਾਫ਼ ਕਰਨਾ" bolte hain. Ye safety net hai.
  - Data na ho to saaf bolte hain "ਮੇਰੇ ਕੋਲ ਨਹੀਂ ਹੈ". Andaaza kabhi nahi.
"""
import re
from datetime import date, datetime, timedelta, timezone

from . import data, intent as I, weather

HOME_DISTRICT = "Amritsar"   # mandi na boli ho to pehle is district ki mandiyan / iska mausam

MONTHS = {
    "pa": ["ਜਨਵਰੀ", "ਫ਼ਰਵਰੀ", "ਮਾਰਚ", "ਅਪ੍ਰੈਲ", "ਮਈ", "ਜੂਨ", "ਜੁਲਾਈ", "ਅਗਸਤ", "ਸਤੰਬਰ", "ਅਕਤੂਬਰ", "ਨਵੰਬਰ", "ਦਸੰਬਰ"],
    "hi": ["जनवरी", "फ़रवरी", "मार्च", "अप्रैल", "मई", "जून", "जुलाई", "अगस्त", "सितंबर", "अक्टूबर", "नवंबर", "दिसंबर"],
}

# Saare jawab ke templates. {..} mein sirf source se aaye naam/number bhare jaate hain.
T = {
    "pa": {
        "today": "ਅੱਜ", "yesterday": "ਕੱਲ੍ਹ", "on_date": "{d} {month} ਨੂੰ",
        "tomorrow": "ਭਲਕੇ", "day_after": "ਪਰਸੋਂ",
        "price": "{day} {market} ਮੰਡੀ ਵਿੱਚ {crop_of} ਦਾ ਭਾਅ {modal} ਰੁਪਏ ਕੁਇੰਟਲ ਰਿਹਾ।",
        "range": " ਘੱਟੋ-ਘੱਟ {min} ਅਤੇ ਵੱਧ ਤੋਂ ਵੱਧ {max} ਰੁਪਏ।",
        "no_crop_price": "ਮਾਫ਼ ਕਰਨਾ, {crop_of} ਦਾ ਭਾਅ ਮੇਰੇ ਕੋਲ ਨਹੀਂ ਹੈ।",
        "not_in_market": "{market} ਮੰਡੀ ਵਿੱਚ {crop_of} ਦਾ ਭਾਅ ਮੇਰੇ ਕੋਲ ਨਹੀਂ ਹੈ। ",
        "price_list": "{day} {crop_of} ਦਾ ਭਾਅ: {listing} ਰੁਪਏ ਕੁਇੰਟਲ।",
        "not_understood": "ਮਾਫ਼ ਕਰਨਾ, ਮੈਨੂੰ ਸਮਝ ਨਹੀਂ ਆਇਆ। ਫ਼ਸਲ ਅਤੇ ਮੰਡੀ ਦਾ ਨਾਮ ਲੈ ਕੇ ਪੁੱਛੋ, "
                          "ਜਿਵੇਂ: ਅੰਮ੍ਰਿਤਸਰ ਮੰਡੀ ਵਿੱਚ ਕਣਕ ਦਾ ਭਾਅ।",
        "unknown_crop": "ਮਾਫ਼ ਕਰਨਾ, ਇਸ ਫ਼ਸਲ ਦਾ ਭਾਅ ਮੇਰੇ ਕੋਲ ਨਹੀਂ ਹੈ। ਮੇਰੇ ਕੋਲ ਇਹਨਾਂ ਫ਼ਸਲਾਂ ਦੇ ਭਾਅ ਹਨ: {crops}।",
        "unknown_market": "ਮਾਫ਼ ਕਰਨਾ, {market} ਮੰਡੀ ਦਾ ਡਾਟਾ ਮੇਰੇ ਕੋਲ ਨਹੀਂ ਹੈ।",
        "grounding_failed": "ਮਾਫ਼ ਕਰਨਾ, ਹੁਣ ਮੈਂ ਪੱਕਾ ਜਵਾਬ ਨਹੀਂ ਦੱਸ ਸਕਦਾ।",
        "weather": "{day} {place} ਵਿੱਚ ਤਾਪਮਾਨ {tmin} ਤੋਂ {tmax} ਡਿਗਰੀ ਰਹੇਗਾ।",
        "rain": " ਮੀਂਹ ਦੀ ਸੰਭਾਵਨਾ {p} ਪ੍ਰਤੀਸ਼ਤ ਹੈ।",
        "rain_advice": " ਮੀਂਹ ਪੈ ਸਕਦਾ ਹੈ, ਸਪਰੇਅ ਨਾ ਕਰੋ ਅਤੇ ਵੱਢੀ ਹੋਈ ਫ਼ਸਲ ਢੱਕ ਕੇ ਰੱਖੋ।",
        "weather_no_place": "ਮਾਫ਼ ਕਰਨਾ, {place} ਦਾ ਮੌਸਮ ਮੇਰੇ ਕੋਲ ਨਹੀਂ ਹੈ।",
        "weather_failed": "ਮਾਫ਼ ਕਰਨਾ, ਹੁਣ ਮੌਸਮ ਦੀ ਜਾਣਕਾਰੀ ਨਹੀਂ ਮਿਲ ਰਹੀ। ਥੋੜ੍ਹੀ ਦੇਰ ਬਾਅਦ ਪੁੱਛੋ।",
        "scheme_list": "ਮੇਰੇ ਕੋਲ ਇਹਨਾਂ ਸਕੀਮਾਂ ਦੀ ਜਾਣਕਾਰੀ ਹੈ: {names}। ਸਕੀਮ ਦਾ ਨਾਮ ਲੈ ਕੇ ਪੁੱਛੋ।",
    },
    "hi": {
        "today": "आज", "yesterday": "कल", "on_date": "{d} {month} को",
        "tomorrow": "कल", "day_after": "परसों",
        "price": "{day} {market} मंडी में {crop_of} का भाव {modal} रुपये क्विंटल रहा।",
        "range": " कम से कम {min} और ज़्यादा से ज़्यादा {max} रुपये।",
        "no_crop_price": "माफ़ कीजिए, {crop_of} का भाव मेरे पास नहीं है।",
        "not_in_market": "{market} मंडी में {crop_of} का भाव मेरे पास नहीं है। ",
        "price_list": "{day} {crop_of} का भाव: {listing} रुपये क्विंटल।",
        "not_understood": "माफ़ कीजिए, मुझे समझ नहीं आया। फसल और मंडी का नाम लेकर पूछें, "
                          "जैसे: अमृतसर मंडी में गेहूं का भाव।",
        "unknown_crop": "माफ़ कीजिए, इस फसल का भाव मेरे पास नहीं है। मेरे पास इन फसलों के भाव हैं: {crops}।",
        "unknown_market": "माफ़ कीजिए, {market} मंडी का डेटा मेरे पास नहीं है।",
        "grounding_failed": "माफ़ कीजिए, अभी मैं पक्का जवाब नहीं बता सकता।",
        "weather": "{day} {place} में तापमान {tmin} से {tmax} डिग्री रहेगा।",
        "rain": " बारिश की संभावना {p} प्रतिशत है।",
        "rain_advice": " बारिश हो सकती है, छिड़काव न करें और कटी हुई फसल ढककर रखें।",
        "weather_no_place": "माफ़ कीजिए, {place} का मौसम मेरे पास नहीं है।",
        "weather_failed": "माफ़ कीजिए, अभी मौसम की जानकारी नहीं मिल रही। थोड़ी देर बाद पूछें।",
        "scheme_list": "मेरे पास इन योजनाओं की जानकारी है: {names}। योजना का नाम लेकर पूछें।",
    },
}
RAIN_ADVICE_FROM = 50     # itne % se zyada barish ki sambhavna ho to spray na karne ki salah


def _num(x) -> str:
    return str(int(x)) if x is not None and float(x).is_integer() else str(x)


IST = timezone(timedelta(hours=5, minutes=30))


def india_today() -> date:
    """Aaj ki tareekh India ke time se. Server (Render) UTC pe chalta hai: raat 12 se subah 5:30 tak
    UTC mein kal ki tareekh hoti hai, aur mausam ke din / "aaj ka bhaav" galat ho jaate the."""
    return datetime.now(IST).date()


def _day_phrase(iso: str, today: date, lang: str) -> str:
    d = date.fromisoformat(iso)
    if d == today:
        return T[lang]["today"]
    if d == today - timedelta(days=1):
        return T[lang]["yesterday"]
    return T[lang]["on_date"].format(d=d.day, month=MONTHS[lang][d.month - 1])


def _crop_name(key, lang):
    return I.crop_info[key]["hi" if lang == "hi" else "pa"]


def _crop_of(key, lang):
    """Punjabi grammar: 'ਝੋਨਾ' -> 'ਝੋਨੇ ਦਾ' ('ਦਾ' se pehle wala roop). Hindi mein zaroorat nahi."""
    return I.crop_info[key]["hi" if lang == "hi" else "pa_of"]


def _market_name(name, lang):
    info = I.market_info.get(name, {})
    return info.get("hi" if lang == "hi" else "pa", name)


def _available_crops_text(lang, market=None) -> str:
    keys = []
    for key, info in I.crop_info.items():
        if info["db"] and (market is None or data.latest_prices(info["db"], market)):
            keys.append(key)
    return ", ".join(_crop_name(k, lang) for k in keys[:8])


def _row_dict(r):
    return {"type": "price", "id": r["id"], "market": r["market"], "commodity": r["commodity"],
            "variety": r["variety"], "date": r["arrival_date"], "min": r["min_price"], "max": r["max_price"],
            "modal": r["modal_price"], "label": f"{r['market']} / {r['commodity']} / {r['arrival_date']}"}


def check_grounded(text: str, sources: list[dict]) -> bool:
    """Jawab ka har number kisi source mein hona chahiye (price/date, mausam, ya scheme ke numbers)."""
    allowed = set()
    for s in sources:
        if "numbers" in s:                               # mausam / scheme
            allowed.update(_num(n) for n in s["numbers"] if n is not None)
            continue
        for k in ("min", "max", "modal"):                # mandi price row
            if s[k] is not None:
                allowed.add(_num(s[k]))
        d = date.fromisoformat(s["date"])
        allowed.update({str(d.day), str(d.year)})
    return all(n in allowed for n in re.findall(r"\d+(?:\.\d+)?", text))


def _done(result, text, sources, kind, lang):
    if sources and not check_grounded(text, sources):     # safety net: kabhi fire nahi hona chahiye
        return {"answered": False, "kind": "grounding_failed", "sources": [], "lang": lang,
                "text": T[lang]["grounding_failed"]}
    result.update(answered=bool(sources), kind=kind if sources else "no_data", text=text, sources=sources)
    return result


# ---------------------------------------------------------------------------

def build_answer(q: dict, today: date | None = None) -> dict:
    today = today or india_today()
    lang = q.get("lang", "pa")
    t = T[lang]
    result = {"answered": False, "kind": "", "text": "", "sources": [], "lang": lang}

    if q["intent"] == "scheme":
        return _scheme_answer(q, lang, result)
    if q["intent"] == "weather":
        return _weather_answer(q, lang, today, result)

    if not q["crops"]:
        if q["intent"] is None and q["market"] is None:
            result.update(kind="not_understood", text=t["not_understood"])
        else:
            result.update(kind="unknown_crop", text=t["unknown_crop"].format(crops=_available_crops_text(lang)))
        return result

    market = q["market"]
    if not market and q.get("unknown_market"):
        result.update(kind="unknown_market", text=t["unknown_market"].format(market=q["unknown_market"]))
        return result
    if market and not I.market_info[market]["has_data"]:
        result.update(kind="unknown_market", text=t["unknown_market"].format(market=_market_name(market, lang)))
        return result

    on_date = {"today": today, "yesterday": today - timedelta(days=1)}.get(q["day"])
    parts, sources = [], []
    for key in q["crops"]:
        db_names = I.crop_info[key]["db"]
        crop_of = _crop_of(key, lang)
        rows = data.latest_prices(db_names, market, on_date) if db_names else []

        if rows and market:
            r = rows[0]
            text = t["price"].format(day=_day_phrase(r["arrival_date"], today, lang),
                                     market=_market_name(market, lang), crop_of=crop_of, modal=_num(r["modal_price"]))
            if r["min_price"] is not None and r["max_price"] is not None:   # CSV mein min/max na ho to mat bolo
                text += t["range"].format(min=_num(r["min_price"]), max=_num(r["max_price"]))
            parts.append(text)
            sources.append(_row_dict(r))
            continue

        # Mandi nahi boli, ya us mandi mein ye fasal nahi -> doosri mandiyon ke bhaa (naam ke saath)
        others = data.latest_prices(db_names, None, on_date) if db_names else []
        if not others:
            parts.append(t["no_crop_price"].format(crop_of=crop_of))
            continue
        prefix = t["not_in_market"].format(market=_market_name(market, lang), crop_of=crop_of) if market else ""
        home = [r for r in others if r["district"] == HOME_DISTRICT]
        home_ids = {r["id"] for r in home}
        picked = (home + [r for r in others if r["id"] not in home_ids])[:3]
        listing = ", ".join(f"{_market_name(r['market'], lang)} {_num(r['modal_price'])}" for r in picked)
        parts.append(prefix + t["price_list"].format(day=_day_phrase(picked[0]["arrival_date"], today, lang),
                                                     crop_of=crop_of, listing=listing))
        sources.extend(_row_dict(r) for r in picked)

    return _done(result, " ".join(parts), sources, "price", lang)


def _weather_answer(q, lang, today, result):
    t = T[lang]
    place = q["market"] or HOME_DISTRICT
    if not q["market"] and q.get("unknown_market"):
        result.update(kind="weather_no_place", text=t["weather_no_place"].format(place=q["unknown_market"]))
        return result
    info = I.market_info.get(place, {})
    if "lat" not in info:
        result.update(kind="weather_no_place", text=t["weather_no_place"].format(place=_market_name(place, lang)))
        return result
    day, day_key = weather.target_day(q.get("day"), today)
    try:
        f = weather.forecast(info["lat"], info["lon"], day)
    except weather.WeatherError as e:
        print(e)
        f = None
    if f is None:
        result.update(kind="weather_failed", text=t["weather_failed"])
        return result

    text = t["weather"].format(day=t[day_key], place=_market_name(place, lang), tmin=f["tmin"], tmax=f["tmax"])
    if f["rain_prob"] is not None:
        text += t["rain"].format(p=f["rain_prob"])
        if f["rain_prob"] >= RAIN_ADVICE_FROM:
            text += t["rain_advice"]
    source = {"type": "weather", "place": place, "date": day.isoformat(), "provider": "Open-Meteo",
              **f, "numbers": [f["tmin"], f["tmax"], f["rain_prob"]],
              "label": f"Open-Meteo / {place} / {day.isoformat()}"}
    return _done(result, text, [source], "weather", lang)


def _scheme_answer(q, lang, result):
    key = q.get("scheme")
    if not key:                                   # "ਕਿਹੜੀਆਂ ਸਕੀਮਾਂ ਹਨ?" -> list sunao
        names = ", ".join(s["name"][lang] for s in I.SCHEMES.values())
        result.update(answered=True, kind="scheme_list", text=T[lang]["scheme_list"].format(names=names))
        return result
    s = I.SCHEMES[key]
    source = {"type": "scheme", "id": key, "name": s["name"][lang], "numbers": s["numbers"],
              "links": s["sources"], "checked": s["checked"], "label": f"{s['name']['hi']} / checked {s['checked']}"}
    return _done(result, s["text"][lang], [source], "scheme", lang)
