"""
PHONE CALL (keypad phone wale kisan ke liye) - Twilio ke through, ya PHONE SIMULATOR (website par).

Call ka flow:
  1. incoming : "ਸਤ ਸ੍ਰੀ ਅਕਾਲ ਜੀ..." sunao, phir beep ke baad kisan ka sawaal RECORD karo.
  2. answer   : recording -> wahi pipeline (ASR -> samjho -> DB -> TTS) -> jawab sunao.
                Phir "hor sawaal?" aur dobara record. Aise call chalti rehti hai.
  3. Do baar awaaz samajh na aaye -> menu : KEYPAD menu ("ਕਣਕ ਲਈ 1 ਦਬਾਓ ...").
     Shor wali jagah se call ho to bhi kisan ko jawab mil jaata hai.

EK HI FLOW, DO RAASTE:
  flow_*() functions decide karte hain ki call mein aage kya hoga, "steps" ki list ke roop mein:
      ("say", text)      -> ye Punjabi text bolo
      ("record", tries)  -> beep, phir kisan ki awaaz record karo
      ("menu", None)     -> keypad menu sunao aur ek button ka intezaar karo
  - Twilio ke liye: _twiml() in steps ko TwiML (XML) mein badalta hai -> /voice/...
  - Simulator ke liye: _sim_json() inhe JSON mein badalta hai -> /api/phone-sim/...
  Isliye simulator mein jo dikhta hai, asli call mein bhi bilkul wahi hoga.

SECURITY (server internet pe khula hai, isliye zaroori):
  - verify_twilio(): har /voice request pe Twilio ka signature (X-Twilio-Signature) check hota hai.
    Koi aur nakli request bheje to 403. Signature auth token se banta hai jo sirf Twilio aur hum jaante hain.
  - RecordingUrl sirf https://api.twilio.com/ se hi download hoti hai. Warna koi hacker apna URL
    bhej ke humse uski taraf request karwa sakta tha, aur saath mein humara Twilio password chala jaata.
  - /api/call-me ke liye ADMIN_TOKEN chahiye. Warna koi bhi humare credit se call karwa sakta tha.

Env variables (.env file mein): TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_NUMBER,
                                PUBLIC_BASE_URL, ADMIN_TOKEN
"""
import base64
import os
import re
import urllib.request

from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, Request, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel

from . import intent, phoneline, pipeline, speech

PROMPTS = {
    "welcome": "ਸਤ ਸ੍ਰੀ ਅਕਾਲ ਜੀ। ਕਿਸਾਨ ਹੈਲਪਲਾਈਨ ਵਿੱਚ ਤੁਹਾਡਾ ਸਵਾਗਤ ਹੈ। ਬੀਪ ਤੋਂ ਬਾਅਦ ਫ਼ਸਲ ਅਤੇ ਮੰਡੀ ਦਾ ਨਾਮ ਲੈ ਕੇ ਭਾਅ ਪੁੱਛੋ।",
    "more": "ਹੋਰ ਕੁਝ ਪੁੱਛਣਾ ਹੈ ਤਾਂ ਬੀਪ ਤੋਂ ਬਾਅਦ ਬੋਲੋ। ਨਹੀਂ ਤਾਂ ਫ਼ੋਨ ਕੱਟ ਦਿਓ।",
    "menu_intro": "ਆਵਾਜ਼ ਸਾਫ਼ ਨਹੀਂ ਆ ਰਹੀ। ਹੁਣ ਬਟਨ ਦਬਾ ਕੇ ਫ਼ਸਲ ਚੁਣੋ।",
    "no_speech": "ਮਾਫ਼ ਕਰਨਾ, ਆਵਾਜ਼ ਸਾਫ਼ ਨਹੀਂ ਆਈ। ਕਿਰਪਾ ਕਰਕੇ ਦੁਬਾਰਾ ਬੋਲੋ।",
    "bye": "ਧੰਨਵਾਦ ਜੀ। ਸਤ ਸ੍ਰੀ ਅਕਾਲ।",
}
FAIL_KINDS = {"no_speech", "not_understood"}       # sirf inhi ko "fail" maano
TWILIO_MEDIA = "https://api.twilio.com/"
MENU_WAIT_SECONDS = 8


def _env(name: str) -> str | None:
    return os.environ.get(name) or None


def _base(request: Request) -> str:
    return (_env("PUBLIC_BASE_URL") or str(request.base_url)).rstrip("/")


# ---------------------------------------------------------------------------
# CALL FLOW: aage kya hoga (Twilio aur simulator dono ke liye same)
# ---------------------------------------------------------------------------

def menu_crops():
    """Keypad menu ki fasalein: sirf wo jinka data hai, zyada se zyada 9 (button 1-9)."""
    return [(k, v) for k, v in intent.crop_info.items() if v["db"]][:9]


def menu_options_text() -> str:
    return " ".join(f"{v['pa']} ਲਈ {i} ਦਬਾਓ।" for i, (k, v) in enumerate(menu_crops(), start=1))


def flow_incoming():
    return [("say", PROMPTS["welcome"]), ("record", 0)]


def answer_from_wav(wav: bytes | None, channel: str) -> dict:
    """Recording se jawab. Kuch bhi galat ho (khaali recording, ASR fail) to "dobara bolo"."""
    if wav:
        try:
            r = pipeline.ask(wav=wav, channel=channel)
            if r.get("ok"):
                return r
        except Exception as e:
            print("phone answer error:", e)
    return {"kind": "no_speech", "answered": False, "text": PROMPTS["no_speech"]}


def flow_answer(result: dict, tries: int):
    if result["kind"] in FAIL_KINDS:
        tries += 1
        if tries >= 2:
            return [("menu", None)]                      # 2 baar fail -> keypad
        return [("say", result["text"]), ("record", tries)]
    return [("say", result["text"]), ("say", PROMPTS["more"]), ("record", 0)]


def flow_menu_choice(digits: str, channel: str):
    """Button dabaya -> us fasal ka bhaav. Galat button -> menu dobara. Returns (steps, result)."""
    crops = menu_crops()
    if not digits.isdigit() or not 1 <= int(digits) <= len(crops):
        return [("menu", None)], None
    key, info = crops[int(digits) - 1]
    result = pipeline.ask(text=f"{info['pa']} ਦਾ ਭਾਅ", channel=channel)
    return [("say", result["text"]), ("say", PROMPTS["more"]), ("record", 0)], result


# ---------------------------------------------------------------------------
# RAASTA 1: Twilio (asli phone call) -> TwiML
# ---------------------------------------------------------------------------

async def verify_twilio(request: Request):
    """Request sach mein Twilio se aayi hai? Auth token set na ho (local testing) to check skip."""
    token = _env("TWILIO_AUTH_TOKEN")
    if not token or _env("SKIP_TWILIO_SIGNATURE") == "1":
        return
    from twilio.request_validator import RequestValidator
    # Twilio ne jis public URL pe request bheji, signature usi URL se bana hai
    url = _base(request) + request.url.path + (f"?{request.url.query}" if request.url.query else "")
    form = dict(await request.form())
    if not RequestValidator(token).validate(url, form, request.headers.get("X-Twilio-Signature", "")):
        raise HTTPException(403, "Twilio signature galat hai")


router = APIRouter()
voice = APIRouter(prefix="/voice", dependencies=[Depends(verify_twilio)])


def _play(request: Request, text: str) -> str:
    return f"<Play>{_base(request)}/audio/{speech.tts_path(text).name}</Play>"


def _twiml(request: Request, steps) -> Response:
    base = _base(request)
    parts = []
    for kind, value in steps:
        if kind == "say":
            parts.append(_play(request, value))
        elif kind == "record":
            # timeout=2: 2 second chup = sawaal khatam. maxLength=12: lamba sawaal bhi aa jaaye.
            parts.append(f'<Record action="{base}/voice/answer?tries={value}" method="POST" '
                         f'maxLength="12" timeout="2" playBeep="true" trim="trim-silence"/>')
        elif kind == "menu":
            parts.append(f'<Gather input="dtmf" numDigits="1" timeout="{MENU_WAIT_SECONDS}" '
                         f'action="{base}/voice/menu-choice" method="POST">'
                         f'{_play(request, PROMPTS["menu_intro"])}{_play(request, menu_options_text())}</Gather>')
            parts.append(_play(request, PROMPTS["bye"]))   # koi button nahi dabaya -> alvida
    xml = '<?xml version="1.0" encoding="UTF-8"?><Response>' + "".join(parts) + "</Response>"
    return Response(content=xml, media_type="application/xml")


def _download_recording(url: str) -> bytes:
    if not url.startswith(TWILIO_MEDIA):
        raise ValueError("Recording sirf api.twilio.com se le sakte hain")
    req = urllib.request.Request(url + ".wav")
    sid, token = _env("TWILIO_ACCOUNT_SID"), _env("TWILIO_AUTH_TOKEN")
    if sid and token:
        req.add_header("Authorization", "Basic " + base64.b64encode(f"{sid}:{token}".encode()).decode())
    with urllib.request.urlopen(req, timeout=10) as r:
        return r.read()


# Note: ye functions "def" hain (async nahi). FastAPI inhe alag thread mein chalata hai,
# isliye ASR/TTS ke 2 second ke intezaar mein doosri calls ruki nahi rehti.

@voice.post("/incoming")
def incoming(request: Request):
    return _twiml(request, flow_incoming())


@voice.post("/answer")
def answer(request: Request, tries: int = 0, RecordingUrl: str = Form(None)):
    wav = None
    if RecordingUrl:
        try:
            wav = _download_recording(RecordingUrl)
        except Exception as e:
            print("recording download error:", e)
    return _twiml(request, flow_answer(answer_from_wav(wav, "phone"), tries))


@voice.post("/menu")
def menu(request: Request):
    return _twiml(request, [("menu", None)])


@voice.post("/menu-choice")
def menu_choice(request: Request, Digits: str = Form("")):
    steps, _ = flow_menu_choice(Digits, "phone-keypad")
    return _twiml(request, steps)


router.include_router(voice)


# ---------------------------------------------------------------------------
# RAASTA 2: PHONE SIMULATOR (website par keypad phone) -> JSON
# Asli phone number ke liye paid telecom account chahiye. Tab tak judges isse poora call flow
# chala ke dekh sakte hain. Awaaz phoneline.to_phone_quality() se phone jaisi 8 kHz banti hai.
# ---------------------------------------------------------------------------

sim = APIRouter(prefix="/api/phone-sim")


def _audio_url(text: str) -> str:
    return f"/audio/{speech.tts_path(text).name}"


def _sim_json(steps, result: dict | None = None, line_audio: bytes | None = None) -> dict:
    out = []
    for kind, value in steps:
        if kind == "say":
            out.append({"type": "say", "text": value, "audio": _audio_url(value)})
        elif kind == "record":
            out.append({"type": "record", "tries": value})
        elif kind == "menu":
            options = [{"digit": i, "pa": v["pa"], "icon": v["icon"]}
                       for i, (k, v) in enumerate(menu_crops(), start=1)]
            out.append({"type": "menu", "wait_seconds": MENU_WAIT_SECONDS,
                        "say": [{"text": t, "audio": _audio_url(t)}
                                for t in (PROMPTS["menu_intro"], menu_options_text())],
                        "options": options,
                        "timeout_say": {"text": PROMPTS["bye"], "audio": _audio_url(PROMPTS["bye"])}})
    body = {"steps": out}
    if result is not None:
        body["result"] = {k: result.get(k) for k in
                          ("heard", "alternatives", "kind", "answered", "text", "sources", "timings")}
    if line_audio is not None:
        # "Phone line ne aapki awaaz kaise suni" - website par sunne ke liye (disk par save nahi hoti)
        body["line_audio"] = "data:audio/wav;base64," + base64.b64encode(line_audio).decode()
    return body


@sim.post("/start")
def sim_start():
    return _sim_json(flow_incoming())


@sim.post("/answer")
async def sim_answer(tries: int = 0, phone_line: bool = True, audio: UploadFile = File(...)):
    wav = await audio.read()
    if len(wav) > 5_000_000:
        raise HTTPException(413, "Audio bahut lambi hai")
    if phone_line:
        try:
            wav = phoneline.to_phone_quality(wav)
        except (ValueError, EOFError) as e:
            raise HTTPException(400, f"Audio WAV nahi hai: {e}")
    from starlette.concurrency import run_in_threadpool      # ASR/TTS thread mein, server na ruke
    result = await run_in_threadpool(answer_from_wav, wav, "phone-sim")
    return _sim_json(flow_answer(result, tries), result, wav if phone_line else None)


class SimDigits(BaseModel):
    digits: str


@sim.post("/menu-choice")
def sim_menu_choice(body: SimDigits):
    steps, result = flow_menu_choice(body.digits, "phone-sim-keypad")
    return _sim_json(steps, result)


router.include_router(sim)


# ---------------------------------------------------------------------------
# "Missed call" demo: system khud kisan ko call karta hai (Twilio chahiye)
# ---------------------------------------------------------------------------

class CallMe(BaseModel):
    phone: str    # +91XXXXXXXXXX format


@router.post("/api/call-me")
def call_me(body: CallMe, request: Request, x_admin_token: str = Header("")):
    """'Missed call' ka demo: is number pe system khud call karega (call kisan ke liye free)."""
    admin = _env("ADMIN_TOKEN")
    if not admin or x_admin_token != admin:
        raise HTTPException(401, "Admin token galat hai")
    if not re.fullmatch(r"\+\d{10,15}", body.phone):
        raise HTTPException(400, "Number +91XXXXXXXXXX format mein do")
    sid, token, number = _env("TWILIO_ACCOUNT_SID"), _env("TWILIO_AUTH_TOKEN"), _env("TWILIO_NUMBER")
    if not (sid and token and number):
        raise HTTPException(503, "Twilio set nahi hai (.env mein TWILIO_ACCOUNT_SID / TWILIO_AUTH_TOKEN / TWILIO_NUMBER)")
    from twilio.base.exceptions import TwilioRestException
    from twilio.rest import Client
    try:
        call = Client(sid, token).calls.create(to=body.phone, from_=number, url=f"{_base(request)}/voice/incoming")
    except TwilioRestException as e:
        raise HTTPException(400, f"Twilio ne mana kiya: {e.msg}")
    return {"ok": True, "call_sid": call.sid}
