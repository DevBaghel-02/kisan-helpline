"""
DATA LAYER: mandi prices ka database (SQLite).

Kya karta hai:
  1. CSV file (judges ki ya data.gov.in wali) padh ke SQLite table `prices` mein daalta hai.
  2. Column ke naam alag ho sakte hain ("Modal_Price", "modal price", "Price"...), isliye
     HEADER_ALIASES se har column ko ek standard naam pe map karte hain.
  3. Bot sirf yahan se numbers padhta hai. LLM / koi aur jagah se number kabhi nahi aata.
"""
import csv
import io
import re
import sqlite3
import threading
from datetime import date, datetime
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "kisan.db"

# Standard column naam  ->  CSV mein jo-jo naam ho sakte hain (lowercase, sirf a-z0-9)
HEADER_ALIASES = {
    "state": ["state", "statename"],
    "district": ["district", "districtname"],
    "market": ["market", "mandi", "marketname", "mandiname", "apmc"],
    "commodity": ["commodity", "crop", "commodityname", "cropname", "fasal"],
    "variety": ["variety"],
    "arrival_date": ["arrivaldate", "date", "pricedate", "reporteddate"],
    "min_price": ["minprice", "minimumprice", "minpricersquintal", "min"],
    "max_price": ["maxprice", "maximumprice", "maxpricersquintal", "max"],
    "modal_price": ["modalprice", "modalpricersquintal", "price", "modal"],
}
REQUIRED = ["market", "commodity", "arrival_date", "modal_price"]


_local = threading.local()


def connect() -> sqlite3.Connection:
    """Har thread ka apna ek connection, baar-baar khol-band nahi karte (fast + koi leak nahi)."""
    con = getattr(_local, "con", None)
    if con is not None:
        return con
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    _local.con = con
    con.execute(
        """CREATE TABLE IF NOT EXISTS prices (
            id INTEGER PRIMARY KEY,
            state TEXT, district TEXT, market TEXT NOT NULL, commodity TEXT NOT NULL,
            variety TEXT, arrival_date TEXT NOT NULL,           -- ISO format: 2026-11-19
            min_price REAL, max_price REAL, modal_price REAL NOT NULL
        )"""
    )
    # DUPLICATE ROKNA: ek mandi + fasal + variety + date ki sirf EK row ho sakti hai.
    # (Purane DB mein duplicate hon to pehle hata do, sabse nayi wali row rakho.)
    con.execute("""DELETE FROM prices WHERE id NOT IN (
                     SELECT MAX(id) FROM prices GROUP BY market, commodity, variety, arrival_date)""")
    con.execute("""CREATE UNIQUE INDEX IF NOT EXISTS one_price_per_day
                   ON prices (market, commodity, variety, arrival_date)""")
    con.commit()
    con.execute(
        """CREATE TABLE IF NOT EXISTS query_log (
            id INTEGER PRIMARY KEY, at TEXT, channel TEXT, heard TEXT,
            intent TEXT, crop TEXT, market TEXT, answered INTEGER, answer TEXT, total_ms INTEGER
        )"""
    )
    return con


def _clean_header(h: str) -> str:
    return re.sub(r"[^a-z0-9]", "", h.lower())


def _map_headers(headers: list[str]) -> dict[str, int]:
    """Har standard naam ke liye CSV ka column number dhoondo."""
    cleaned = [_clean_header(h) for h in headers]
    mapping = {}
    for std, aliases in HEADER_ALIASES.items():
        for i, h in enumerate(cleaned):
            if h in aliases:
                mapping[std] = i
                break
    return mapping


def parse_date(text: str) -> str | None:
    """'19/11/2026', '2026-11-19', '19-11-2026', '19-Nov-2026' -> '2026-11-19'."""
    text = text.strip()
    for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y", "%d-%b-%Y", "%d %b %Y", "%d/%m/%y"):
        try:
            return datetime.strptime(text, fmt).date().isoformat()
        except ValueError:
            pass
    return None


def _parse_price(text: str) -> float | None:
    text = re.sub(r"[^0-9.]", "", text or "")  # "₹2,480" -> "2480"
    return float(text) if text else None


def _clean_name(text: str) -> str:
    """'  AMRITSAR ' -> 'Amritsar', taaki 'Amritsar' aur 'AMRITSAR' do alag mandiyan na ban jaayein."""
    return re.sub(r"\s+", " ", text).strip().title()


def import_csv(content: str, replace: bool = True) -> dict:
    """
    CSV text ko database mein daalo. 2 modes:
      replace=True  : purana SAARA data hatao, sirf is file ka data rakho (judges ka dataset).
      replace=False : MERGE - purana data rakho. Same mandi+fasal+variety+date wali row aaye to
                      purani row UPDATE ho jaati hai (nayi price), duplicate nahi banti.
                      Roz ka data.gov.in fetch isi mode mein chalega.
    Report: kitni nayi rows, kitni update hui, kitni reject hui (aur kyun).
    """
    reader = csv.reader(io.StringIO(content.lstrip("﻿")))
    headers = next(reader, None)
    if not headers:
        return {"ok": False, "error": "CSV khaali hai"}
    cols = _map_headers(headers)
    missing = [c for c in REQUIRED if c not in cols]
    if missing:
        return {"ok": False, "error": f"Ye columns nahi mile: {missing}", "headers_seen": headers}

    good, rejected, valid_lines = {}, [], 0
    for line_no, row in enumerate(reader, start=2):
        if not any(cell.strip() for cell in row):
            continue                                            # khaali line, chhod do
        get = lambda k: row[cols[k]].strip() if k in cols and cols[k] < len(row) else ""
        d = parse_date(get("arrival_date"))
        modal = _parse_price(get("modal_price"))
        reason = ("mandi ka naam nahi" if not get("market") else "fasal ka naam nahi" if not get("commodity")
                  else f"date samajh nahi aayi: '{get('arrival_date')}'" if d is None
                  else "modal price nahi" if modal is None else None)
        if reason:
            rejected.append({"line": line_no, "reason": reason, "row": row})
            continue
        market, commodity = _clean_name(get("market")), _clean_name(get("commodity"))
        variety = _clean_name(get("variety")) or "Other"     # variety na ho to Agmarknet jaisa "Other"
        valid_lines += 1
        # Isi file mein ek hi row do baar ho to aakhri wali rakho (dict ki key = unique pehchaan)
        good[(market, commodity, variety, d)] = (
            _clean_name(get("state")), _clean_name(get("district")), market, commodity, variety, d,
            _parse_price(get("min_price")), _parse_price(get("max_price")), modal)

    con = connect()
    with con:
        if replace:
            con.execute("DELETE FROM prices")
        before = con.execute("SELECT COUNT(*) FROM prices").fetchone()[0]
        # UPSERT: nayi row ho to INSERT, pehle se ho to sirf price UPDATE
        con.executemany(
            """INSERT INTO prices (state,district,market,commodity,variety,arrival_date,min_price,max_price,modal_price)
               VALUES (?,?,?,?,?,?,?,?,?)
               ON CONFLICT (market, commodity, variety, arrival_date) DO UPDATE SET
                 min_price = excluded.min_price, max_price = excluded.max_price,
                 modal_price = excluded.modal_price, state = excluded.state, district = excluded.district""",
            list(good.values()))
        after = con.execute("SELECT COUNT(*) FROM prices").fetchone()[0]
    added = after - before
    return {"ok": True, "mode": "replace" if replace else "merge", "rows_in_file": valid_lines + len(rejected),
            "duplicates_in_file": valid_lines - len(good),
            "added": added, "updated": len(good) - added, "rejected": len(rejected),
            "rejected_rows": rejected[:20], "total_rows_now": after}


def summary() -> dict:
    """Database mein abhi kya hai (admin page ke liye)."""
    con = connect()
    r = con.execute("""SELECT COUNT(*) n, COUNT(DISTINCT market) markets, COUNT(DISTINCT commodity) crops,
                              MIN(arrival_date) first, MAX(arrival_date) last FROM prices""").fetchone()
    return {"rows": r["n"], "markets": r["markets"], "crops": r["crops"], "from": r["first"], "to": r["last"],
            "market_names": all_markets(), "crop_names": all_commodities()}


def all_markets() -> list[str]:
    return [r[0] for r in connect().execute("SELECT DISTINCT market FROM prices ORDER BY market")]


def all_commodities() -> list[str]:
    return [r[0] for r in connect().execute("SELECT DISTINCT commodity FROM prices ORDER BY commodity")]


def latest_prices(commodities: list[str], market: str | None = None, on_date: date | None = None) -> list[sqlite3.Row]:
    """
    Har (market, commodity) ki SABSE NAYI row do.
    on_date diya ho to us din ya usse pehle ki sabse nayi row.
    """
    if not commodities:
        return []
    q = f"""SELECT p.* FROM prices p
            JOIN (SELECT market, commodity, MAX(arrival_date) d FROM prices
                  WHERE commodity IN ({",".join("?" * len(commodities))})
                  {"AND market = ?" if market else ""}
                  {"AND arrival_date <= ?" if on_date else ""}
                  GROUP BY market, commodity) last
              ON p.market = last.market AND p.commodity = last.commodity AND p.arrival_date = last.d
            ORDER BY p.arrival_date DESC, p.modal_price DESC"""
    params = list(commodities) + ([market] if market else []) + ([on_date.isoformat()] if on_date else [])
    return connect().execute(q, params).fetchall()


def log_query(channel, heard, intent, crop, market, answered, answer, total_ms):
    con = connect()
    with con:
        con.execute("INSERT INTO query_log (at,channel,heard,intent,crop,market,answered,answer,total_ms)"
                    " VALUES (datetime('now','localtime'),?,?,?,?,?,?,?,?)",
                    (channel, heard, intent, crop, market, int(answered), answer, total_ms))


def recent_queries(limit=50):
    return [dict(r) for r in connect().execute("SELECT * FROM query_log ORDER BY id DESC LIMIT ?", (limit,))]


def ensure_sample_data():
    """Pehli baar chalaane pe agar DB khaali hai to sample CSV load kar do (sirf testing ke liye)."""
    if connect().execute("SELECT COUNT(*) FROM prices").fetchone()[0] == 0:
        sample = DB_PATH.parent / "sample_prices.csv"
        import_csv(sample.read_text(encoding="utf-8"))
