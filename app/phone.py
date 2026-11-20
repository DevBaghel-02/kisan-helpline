"""
PHONE CALL (keypad phone wale kisan ke liye) - Twilio ke through.

Call ka flow:
  1. /voice/incoming : "ਸਤ ਸ੍ਰੀ ਅਕਾਲ ਜੀ..." sunao, phir beep ke baad kisan ka sawaal RECORD karo.
  2. /voice/answer   : recording download karo -> wahi pipeline (ASR -> samjho -> DB -> TTS) -> jawab sunao.
                       Phir "hor sawaal?" aur dobara record. Aise call chalti rehti hai.
  3. Do baar awaaz samajh na aaye -> /voice/menu : KEYPAD menu ("ਕਣਕ ਲਈ 1 ਦਬਾਓ ...").
     Shor wali jagah se call ho to bhi kisan ko jawab mil jaata hai.

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

from fastapi import APIRouter, Depends, Form, Header, HTTPException, Request
from fastapi.responses import Response
from pydantic import BaseModel

from . import intent, pipeline, speech

PROMPTS = {
    "welcome": "ਸਤ ਸ੍ਰੀ ਅਕਾਲ ਜੀ। ਕਿਸਾਨ ਹੈਲਪਲਾਈਨ ਵਿੱਚ ਤੁਹਾਡਾ ਸਵਾਗਤ ਹੈ। ਬੀਪ ਤੋਂ ਬਾਅਦ ਫ਼ਸਲ ਅਤੇ ਮੰਡੀ ਦਾ ਨਾਮ ਲੈ ਕੇ ਭਾਅ ਪੁੱਛੋ।",
    "more": "ਹੋਰ ਕੁਝ ਪੁੱਛਣਾ ਹੈ ਤਾਂ ਬੀਪ ਤੋਂ ਬਾਅਦ ਬੋਲੋ। ਨਹੀਂ ਤਾਂ ਫ਼ੋਨ ਕੱਟ ਦਿਓ।",
    "menu_intro": "ਆਵਾਜ਼ ਸਾਫ਼ ਨਹੀਂ ਆ ਰਹੀ। ਹੁਣ ਬਟਨ ਦਬਾ ਕੇ ਫ਼ਸਲ ਚੁਣੋ।",
    "no_speech": "ਮਾਫ਼ ਕਰਨਾ, ਆਵਾਜ਼ ਸਾਫ਼ ਨਹੀਂ ਆਈ। ਕਿਰਪਾ ਕਰਕੇ ਦੁਬਾਰਾ ਬੋਲੋ।",
    "bye": "ਧੰਨਵਾਦ ਜੀ। ਸਤ ਸ੍ਰੀ ਅਕਾਲ।",
}
FAIL_KINDS = {"no_speech", "not_understood"}       # sirf inhi ko "fail" maano
TWILIO_MEDIA = "https://api.twilio.com/"


def _env(name: str) -> str | None:
    return os.environ.get(name) or None


def _base(request: Request) -> str:
    return (_env("PUBLIC_BASE_URL") or str(request.base_url)).rstrip("/")


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


def _record(request: Request, tries: int) -> str:
    # timeout=2: 2 second chup = sawaal khatam. maxLength=12: lamba sawaal bhi aa jaaye.
    return (f'<Record action="{_base(request)}/voice/answer?tries={tries}" method="POST" '
            f'maxLength="12" timeout="2" playBeep="true" trim="trim-silence"/>')


def _redirect(request: Request, path: str) -> str:
    return f'<Redirect method="POST">{_base(request)}{path}</Redirect>'


def _twiml(*parts: str) -> Response:
    xml = '<?xml version="1.0" encoding="UTF-8"?><Response>' + "".join(parts) + "</Response>"
    return Response(content=xml, media_type="application/xml")


def _menu_crops():
    return [(k, v) for k, v in intent.crop_info.items() if v["db"]][:9]


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
    return _twiml(_play(request, PROMPTS["welcome"]), _record(request, 0))


@voice.post("/answer")
def answer(request: Request, tries: int = 0, RecordingUrl: str = Form(None)):
    result = {"kind": "no_speech", "text": PROMPTS["no_speech"]}
    if RecordingUrl:
        try:
            r = pipeline.ask(wav=_download_recording(RecordingUrl), channel="phone")
            if r.get("ok"):
                result = r
        except Exception as e:              # download/ASR fail -> kisan ko "dobara bolo"
            print("phone answer error:", e)

    if result["kind"] in FAIL_KINDS:
        tries += 1
        if tries >= 2:
            return _twiml(_redirect(request, "/voice/menu"))
        return _twiml(_play(request, result["text"]), _record(request, tries))

    return _twiml(_play(request, result["text"]), _play(request, PROMPTS["more"]), _record(request, 0))


@voice.post("/menu")
def menu(request: Request):
    options = " ".join(f"{v['pa']} ਲਈ {i} ਦਬਾਓ।" for i, (k, v) in enumerate(_menu_crops(), start=1))
    gather = (f'<Gather input="dtmf" numDigits="1" timeout="8" action="{_base(request)}/voice/menu-choice" '
              f'method="POST">{_play(request, PROMPTS["menu_intro"])}{_play(request, options)}</Gather>')
    return _twiml(gather, _play(request, PROMPTS["bye"]))


@voice.post("/menu-choice")
def menu_choice(request: Request, Digits: str = Form("")):
    crops = _menu_crops()
    if not Digits.isdigit() or not 1 <= int(Digits) <= len(crops):
        return _twiml(_redirect(request, "/voice/menu"))
    key, info = crops[int(Digits) - 1]
    result = pipeline.ask(text=f"{info['pa']} ਦਾ ਭਾਅ", channel="phone-keypad")
    return _twiml(_play(request, result["text"]), _play(request, PROMPTS["more"]), _record(request, 0))


router.include_router(voice)


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
