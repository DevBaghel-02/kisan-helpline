"""
WEATHER: mandi/shehar ka aaj, kal, parson ka mausam - Open-Meteo se (free, koi API key nahi).

Grounding yahan bhi wahi hai: jawab ka har number (tapmaan, barish ki sambhavna) Open-Meteo ke
jawab se aata hai, aur check_grounded() use source se milaata hai.
Internet na ho / API fail ho to saaf bolte hain "abhi mausam nahi mil raha" - koi andaaza nahi.

Location: data/synonyms.json mein har mandi ka lat/lon. Mandi na boli ho to HOME district.
"""
import json
import time
import urllib.parse
import urllib.request
from datetime import date, timedelta

API = "https://api.open-meteo.com/v1/forecast"
SOURCE_NAMES = {"_open_meteo": "Open-Meteo", "_wttr": "wttr.in"}
WTTR = "https://wttr.in"     # backup jab Open-Meteo mana kare (429)
CACHE_SECONDS = 30 * 60          # mausam 30 minute tak dobara nahi mangte (fast + API pe bojh kam)
_cache: dict[tuple, tuple[float, dict]] = {}


class WeatherError(Exception):
    pass


def fetch(lat: float, lon: float) -> dict:
    """Agle 3 din ka mausam: {"2026-11-21": {"tmin", "tmax", "rain_prob", "rain_mm"}, ...}"""
    key = (round(lat, 3), round(lon, 3))
    hit = _cache.get(key)
    if hit and time.time() - hit[0] < CACHE_SECONDS:
        return hit[1]
    errors = []
    for source in (_open_meteo, _wttr):
        try:
            days = source(lat, lon)
            for d in days.values():
                d["provider"] = SOURCE_NAMES[source.__name__]
            break
        except Exception as e:          # 429 / network / format: agla source try karo
            errors.append(f"{source.__name__}: {e}")
    else:
        raise WeatherError("Mausam nahi mila: " + " | ".join(errors))
    _cache[key] = (time.time(), days)
    return days


def _get_json(url: str) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": "kisan-helpline/1.0 (hackathon demo)"})
    with urllib.request.urlopen(req, timeout=4) as r:
        return json.load(r)


def _open_meteo(lat: float, lon: float) -> dict:
    """Pehla source. Render free ka IP bahut log share karte hain, isliye kabhi kabhi 429 aata hai."""
    params = urllib.parse.urlencode({
        "latitude": lat, "longitude": lon, "timezone": "Asia/Kolkata", "forecast_days": 3,
        "daily": "temperature_2m_min,temperature_2m_max,precipitation_probability_max,precipitation_sum",
    })
    raw = _get_json(f"{API}?{params}")["daily"]
    return {d: {"tmin": raw["temperature_2m_min"][i], "tmax": raw["temperature_2m_max"][i],
                "rain_prob": raw["precipitation_probability_max"][i], "rain_mm": raw["precipitation_sum"][i]}
            for i, d in enumerate(raw["time"])}


def _wttr(lat: float, lon: float) -> dict:
    """Backup source (wttr.in, free, koi key nahi). 3-3 ghante ke 8 hisse: barish ki sambhavna = sabse zyada,
    barish mm = sab ka jod. Tareekh local (India) ki hoti hai."""
    raw = _get_json(f"{WTTR}/{lat},{lon}?format=j1")["weather"]
    return {w["date"]: {"tmin": float(w["mintempC"]), "tmax": float(w["maxtempC"]),
                        "rain_prob": max(int(h["chanceofrain"]) for h in w["hourly"]),
                        "rain_mm": round(sum(float(h["precipMM"]) for h in w["hourly"]), 1)}
            for w in raw}


def target_day(day_word: str | None, today: date) -> tuple[date, str]:
    """
    Sawaal ka din. Dhyaan do: Punjabi mein "ਕੱਲ੍ਹ" ka matlab beeta hua kal bhi hai aur aane wala kal bhi.
    Bhaav ke sawaal mein beeta hua (kal ka bhaav), mausam ke sawaal mein aane wala (kal barish hogi?).
    """
    if day_word in ("yesterday", "tomorrow"):
        return today + timedelta(days=1), "tomorrow"
    if day_word == "day_after":
        return today + timedelta(days=2), "day_after"
    return today, "today"


def forecast(lat: float, lon: float, day: date) -> dict | None:
    d = fetch(lat, lon).get(day.isoformat())
    if d is None or d["tmin"] is None or d["tmax"] is None:
        return None
    return {"tmin": round(d["tmin"]), "tmax": round(d["tmax"]),
            "rain_prob": round(d["rain_prob"]) if d["rain_prob"] is not None else None,
            "rain_mm": d["rain_mm"], "provider": d.get("provider", "Open-Meteo")}
