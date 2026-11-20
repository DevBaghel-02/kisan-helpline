"""
ANSWER ENGINE: grounded Punjabi jawab banana.

SABSE ZAROORI RULE: jawab mein har number database ki kisi row se aata hai.
  - Jawab fixed Punjabi templates se banta hai, numbers database row se bhare jaate hain.
  - check_grounded() bolne se pehle jawab ke har number ko source rows se milaata hai.
    Ek bhi number match na ho to jawab rok ke "ਮਾਫ਼ ਕਰਨਾ" bolte hain. Ye safety net hai.
  - Data na ho to saaf bolte hain "ਮੇਰੇ ਕੋਲ ਨਹੀਂ ਹੈ". Andaaza kabhi nahi.
"""
import re
from datetime import date, timedelta

from . import data, intent as I

HOME_DISTRICT = "Amritsar"   # mandi na boli ho to pehle is district ki mandiyan dikhao
MONTHS = ["ਜਨਵਰੀ", "ਫ਼ਰਵਰੀ", "ਮਾਰਚ", "ਅਪ੍ਰੈਲ", "ਮਈ", "ਜੂਨ", "ਜੁਲਾਈ", "ਅਗਸਤ", "ਸਤੰਬਰ", "ਅਕਤੂਬਰ", "ਨਵੰਬਰ", "ਦਸੰਬਰ"]


def _num(x) -> str:
    return str(int(x)) if x is not None and float(x).is_integer() else str(x)


def _day_phrase(iso: str, today: date) -> str:
    d = date.fromisoformat(iso)
    if d == today:
        return "ਅੱਜ"
    if d == today - timedelta(days=1):
        return "ਕੱਲ੍ਹ"
    return f"{d.day} {MONTHS[d.month - 1]} ਨੂੰ"


def _crop_pa(key):
    return I.crop_info[key]["pa"]


def _crop_of(key):
    """Punjabi grammar: 'ਝੋਨਾ' -> 'ਝੋਨੇ ਦਾ' ('ਦਾ' se pehle wala roop)."""
    return I.crop_info[key]["pa_of"]


def _market_pa(name):
    return I.market_info.get(name, {}).get("pa", name)


def _available_crops_text(market=None) -> str:
    keys = []
    for key, info in I.crop_info.items():
        if info["db"] and (market is None or data.latest_prices(info["db"], market)):
            keys.append(key)
    return ", ".join(_crop_pa(k) for k in keys[:8])


def _row_dict(r):
    return {"id": r["id"], "market": r["market"], "commodity": r["commodity"], "variety": r["variety"],
            "date": r["arrival_date"], "min": r["min_price"], "max": r["max_price"], "modal": r["modal_price"]}


def check_grounded(text: str, sources: list[dict]) -> bool:
    """Jawab ka har number kisi source row mein hona chahiye (price, ya date ka din/saal)."""
    allowed = set()
    for s in sources:
        for k in ("min", "max", "modal"):
            if s[k] is not None:
                allowed.add(_num(s[k]))
        d = date.fromisoformat(s["date"])
        allowed.update({str(d.day), str(d.year)})
    return all(n in allowed for n in re.findall(r"\d+(?:\.\d+)?", text))


def build_answer(q: dict, today: date | None = None) -> dict:
    today = today or date.today()
    result = {"answered": False, "kind": "", "text": "", "sources": []}

    if q["intent"] in ("weather", "scheme") and not q["crops"]:
        what = "ਮੌਸਮ" if q["intent"] == "weather" else "ਸਰਕਾਰੀ ਸਕੀਮਾਂ"
        result.update(kind="not_supported_yet",
                      text=f"{what} ਦੀ ਜਾਣਕਾਰੀ ਜਲਦੀ ਸ਼ੁਰੂ ਹੋਵੇਗੀ। ਹੁਣ ਮੈਂ ਮੰਡੀ ਦੇ ਭਾਅ ਦੱਸ ਸਕਦਾ ਹਾਂ।")
        return result

    if not q["crops"]:
        if q["intent"] is None and q["market"] is None:
            result.update(kind="not_understood",
                          text="ਮਾਫ਼ ਕਰਨਾ, ਮੈਨੂੰ ਸਮਝ ਨਹੀਂ ਆਇਆ। ਫ਼ਸਲ ਅਤੇ ਮੰਡੀ ਦਾ ਨਾਮ ਲੈ ਕੇ ਪੁੱਛੋ, "
                               "ਜਿਵੇਂ: ਅੰਮ੍ਰਿਤਸਰ ਮੰਡੀ ਵਿੱਚ ਕਣਕ ਦਾ ਭਾਅ।")
        else:
            result.update(kind="unknown_crop",
                          text="ਮਾਫ਼ ਕਰਨਾ, ਇਸ ਫ਼ਸਲ ਦਾ ਭਾਅ ਮੇਰੇ ਕੋਲ ਨਹੀਂ ਹੈ। ਮੇਰੇ ਕੋਲ ਇਹਨਾਂ ਫ਼ਸਲਾਂ ਦੇ ਭਾਅ ਹਨ: "
                               + _available_crops_text() + "।")
        return result

    market = q["market"]
    if not market and q.get("unknown_market"):
        result.update(kind="unknown_market",
                      text=f"ਮਾਫ਼ ਕਰਨਾ, {q['unknown_market']} ਮੰਡੀ ਦਾ ਡਾਟਾ ਮੇਰੇ ਕੋਲ ਨਹੀਂ ਹੈ।")
        return result
    if market and not I.market_info[market]["has_data"]:
        result.update(kind="unknown_market",
                      text=f"ਮਾਫ਼ ਕਰਨਾ, {_market_pa(market)} ਮੰਡੀ ਦਾ ਡਾਟਾ ਮੇਰੇ ਕੋਲ ਨਹੀਂ ਹੈ।")
        return result

    on_date = {"today": today, "yesterday": today - timedelta(days=1)}.get(q["day"])
    parts, sources = [], []
    for key in q["crops"]:
        db_names = I.crop_info[key]["db"]
        crop, crop_of = _crop_pa(key), _crop_of(key)
        rows = data.latest_prices(db_names, market, on_date) if db_names else []

        if rows and market:
            r = rows[0]
            parts.append(f"{_day_phrase(r['arrival_date'], today)} {_market_pa(market)} ਮੰਡੀ ਵਿੱਚ {crop_of} ਦਾ ਭਾਅ "
                         f"{_num(r['modal_price'])} ਰੁਪਏ ਕੁਇੰਟਲ ਰਿਹਾ। ਘੱਟੋ-ਘੱਟ {_num(r['min_price'])} "
                         f"ਅਤੇ ਵੱਧ ਤੋਂ ਵੱਧ {_num(r['max_price'])} ਰੁਪਏ।")
            sources.append(_row_dict(r))
            continue

        # Mandi nahi boli, ya us mandi mein ye fasal nahi -> doosri mandiyon ke bhaa (naam ke saath)
        others = data.latest_prices(db_names, None, on_date) if db_names else []
        if not others:
            parts.append(f"ਮਾਫ਼ ਕਰਨਾ, {crop_of} ਦਾ ਭਾਅ ਮੇਰੇ ਕੋਲ ਨਹੀਂ ਹੈ।")
            continue
        prefix = f"{_market_pa(market)} ਮੰਡੀ ਵਿੱਚ {crop_of} ਦਾ ਭਾਅ ਮੇਰੇ ਕੋਲ ਨਹੀਂ ਹੈ। " if market else ""
        home = [r for r in others if r["district"] == HOME_DISTRICT]
        home_ids = {r["id"] for r in home}
        picked = (home + [r for r in others if r["id"] not in home_ids])[:3]
        listing = ", ".join(f"{_market_pa(r['market'])} {_num(r['modal_price'])}" for r in picked)
        parts.append(f"{prefix}{_day_phrase(picked[0]['arrival_date'], today)} {crop_of} ਦਾ ਭਾਅ: {listing} "
                     f"ਰੁਪਏ ਕੁਇੰਟਲ।")
        sources.extend(_row_dict(r) for r in picked)

    text = " ".join(parts)
    if sources and not check_grounded(text, sources):     # safety net: kabhi fire nahi hona chahiye
        return {"answered": False, "kind": "grounding_failed", "sources": [],
                "text": "ਮਾਫ਼ ਕਰਨਾ, ਹੁਣ ਮੈਂ ਪੱਕਾ ਭਾਅ ਨਹੀਂ ਦੱਸ ਸਕਦਾ।"}
    result.update(answered=bool(sources), kind="price" if sources else "no_data", text=text, sources=sources)
    return result
