"""
WEB SERVER (FastAPI): website, admin panel aur phone call ke saare URLs yahan hain.

Chalaao:  python -m uvicorn app.main:app --port 8000
Website:  http://localhost:8000        (kisan wali screen)
Admin:    http://localhost:8000/admin  (CSV upload + query log)
Phone:    http://localhost:8000/phone  (keypad phone simulator: poora call flow, bina Twilio ke)
"""
import os
import re
from contextlib import asynccontextmanager
import threading
from pathlib import Path

from fastapi import FastAPI, File, Header, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .config import load_env

load_env()   # .env se Twilio keys etc. (phone.py import hone se pehle)

from . import data, intent, phone, pipeline, speech  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent

# Ye jawab hamesha same hote hain, inki awaaz pehle se bana ke rakh lo (cache) -> jaldi jawab
FIXED_PHRASES = [
    "ਮਾਫ਼ ਕਰਨਾ, ਆਵਾਜ਼ ਸਾਫ਼ ਨਹੀਂ ਆਈ। ਕਿਰਪਾ ਕਰਕੇ ਦੁਬਾਰਾ ਬੋਲੋ।",
    "ਮਾਫ਼ ਕਰਨਾ, ਮੈਨੂੰ ਸਮਝ ਨਹੀਂ ਆਇਆ। ਫ਼ਸਲ ਅਤੇ ਮੰਡੀ ਦਾ ਨਾਮ ਲੈ ਕੇ ਪੁੱਛੋ, ਜਿਵੇਂ: ਅੰਮ੍ਰਿਤਸਰ ਮੰਡੀ ਵਿੱਚ ਕਣਕ ਦਾ ਭਾਅ।",
    *phone.PROMPTS.values(),
]


@asynccontextmanager
async def lifespan(app):
    startup()
    yield


def startup():
    data.ensure_sample_data()
    intent.refresh()

    def warm():
        for p in FIXED_PHRASES + [phone.menu_options_text()]:
            try:
                speech.tts_path(p)
            except Exception:
                pass                      # internet na ho to bhi server chalta rahe
    threading.Thread(target=warm, daemon=True).start()


app = FastAPI(title="Kisan Helpline", lifespan=lifespan)
app.include_router(phone.router)


class TextQuestion(BaseModel):
    text: str


@app.post("/api/ask")
async def ask_audio(audio: UploadFile = File(...)):
    wav = await audio.read()
    if len(wav) > 5_000_000:
        raise HTTPException(413, "Audio bahut lambi hai")
    return pipeline.ask(wav=wav, channel="web")


@app.post("/api/ask-text")
def ask_text(q: TextQuestion):
    return pipeline.ask(text=q.text, channel="web-tap")


@app.get("/api/crops")
def crops():
    """Website ke photo-buttons ke liye: sirf wo fasalein aur mandiyan jinka data hai."""
    return {
        "crops": [{"key": k, "pa": v["pa"], "icon": v["icon"]} for k, v in intent.crop_info.items() if v["db"]],
        "markets": [{"name": m, "pa": v["pa"]} for m, v in intent.market_info.items() if v["has_data"]],
    }


@app.get("/audio/{name}")
def audio(name: str):
    if not re.fullmatch(r"[0-9a-f]{16}\.mp3", name):      # sirf apni cache files, aur kuch nahi
        raise HTTPException(404)
    path = speech.CACHE / name
    if not path.exists():
        raise HTTPException(404)
    return FileResponse(path, media_type="audio/mpeg")


def require_admin(request: Request, token: str):
    """
    Data badalne wale kaam (upload/reset) internet se aaye to ADMIN_TOKEN chahiye.
    Laptop pe seedha (localhost) khola ho to token nahi maangte - demo aasaan rahe.
    Cloudflare tunnel se aayi request mein 'Cf-Connecting-Ip' header hota hai, usi se pehchaante hain.
    """
    from_internet = "cf-connecting-ip" in request.headers or "x-forwarded-for" in request.headers
    if from_internet and (not os.environ.get("ADMIN_TOKEN") or token != os.environ["ADMIN_TOKEN"]):
        raise HTTPException(401, "Admin token chahiye")


@app.post("/api/upload-csv")
async def upload_csv(request: Request, file: UploadFile = File(...), mode: str = "replace",
                     x_admin_token: str = Header("")):
    """mode=replace: purana data hata ke sirf ye file. mode=merge: purana rakho, nayi rows jodo/update karo."""
    require_admin(request, x_admin_token)
    if mode not in ("replace", "merge"):
        raise HTTPException(400, "mode 'replace' ya 'merge' hona chahiye")
    content = (await file.read()).decode("utf-8-sig", errors="replace")
    report = data.import_csv(content, replace=(mode == "replace"))
    intent.refresh()                                       # nayi fasalein/mandiyan pehchaano
    return report


@app.get("/api/data-summary")
def data_summary():
    return data.summary()


@app.post("/api/reset-sample")
def reset_sample(request: Request, x_admin_token: str = Header("")):
    """Wapas sample (testing) data pe jao."""
    require_admin(request, x_admin_token)
    report = data.import_csv((ROOT / "data" / "sample_prices.csv").read_text(encoding="utf-8"), replace=True)
    intent.refresh()
    return report


@app.get("/api/log")
def log():
    return data.recent_queries()


@app.get("/")
def home():
    return FileResponse(ROOT / "static" / "index.html")


@app.get("/phone")
def phone_simulator():
    """Keypad phone simulator: asli call jaisa flow, bina Twilio number ke."""
    return FileResponse(ROOT / "static" / "phone.html")


@app.get("/admin")
def admin():
    return FileResponse(ROOT / "static" / "admin.html")


app.mount("/static", StaticFiles(directory=ROOT / "static"), name="static")
