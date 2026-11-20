"""
SPEECH: awaaz -> text (ASR) aur text -> awaaz (TTS).

ASR: Google ka free speech endpoint (SpeechRecognition library), language "pa-IN".
     show_all=True se 3-5 "alternatives" milte hain (n-best). pipeline.py har alternative
     try karta hai aur jismein fasal/mandi samajh aaye wo chunta hai. Shor mein ye bahut kaam aata hai.
TTS: gTTS (Google Translate ki awaaz), lang "pa". Free hai, key nahi chahiye.
     Ek hi sentence dobara bole to cache se milta hai (data/tts_cache) -> 0 ms.

Dono "provider" alag functions mein hain. Baad mein Bhashini ya AI4Bharat lagana ho to
sirf yahi file badlegi, baaki code nahi.
"""
import hashlib
import io
import wave
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import speech_recognition as sr
from gtts import gTTS

CACHE = Path(__file__).resolve().parent.parent / "data" / "tts_cache"
CACHE.mkdir(parents=True, exist_ok=True)
_recognizer = sr.Recognizer()


class ASRError(Exception):
    pass


def transcribe(wav_bytes: bytes, language: str = "pa-IN") -> list[dict]:
    """WAV audio -> [{"text": ..., "confidence": ...}, ...] (sabse achha pehle). Kuch na samjhe to []."""
    try:
        with wave.open(io.BytesIO(wav_bytes)) as w:
            rate, width = w.getframerate(), w.getsampwidth()
            frames = w.readframes(w.getnframes())
    except wave.Error as e:
        raise ASRError(f"WAV file kharab hai: {e}")
    audio = sr.AudioData(frames, rate, width)
    try:
        result = _recognizer.recognize_google(audio, language=language, show_all=True)
    except sr.RequestError as e:
        raise ASRError(f"Speech service tak nahi pahunch paaye: {e}")
    if not result or not result.get("alternative"):
        return []
    alts = result["alternative"]
    return [{"text": a["transcript"], "confidence": a.get("confidence")} for a in alts]


def _cache_file(text: str, lang: str) -> Path:
    return CACHE / (hashlib.sha1(f"{lang}:{text}".encode()).hexdigest()[:16] + ".mp3")


def _one_sentence(text: str, lang: str) -> bytes:
    path = _cache_file(text, lang)
    if not path.exists():
        buf = io.BytesIO()
        gTTS(text, lang=lang).write_to_fp(buf)
        path.write_bytes(buf.getvalue())
    return path.read_bytes()


def transcribe_multi(wav_bytes: bytes, languages=("pa-IN", "hi-IN")) -> dict[str, list[dict]]:
    """
    Ek hi awaaz ko Punjabi aur Hindi dono ASR mein EK SAATH (parallel) bhejo -> time utna hi lagta hai.
    Kisan Hindi mein bole to Hindi ASR behtar likhta hai; pipeline.py dono mein se behtar chunta hai.
    Ek language fail ho jaaye to doosri se kaam chala lo; dono fail -> ASRError.
    """
    with ThreadPoolExecutor(max_workers=len(languages)) as pool:
        futures = {lang: pool.submit(transcribe, wav_bytes, lang) for lang in languages}
    out, errors = {}, []
    for lang, f in futures.items():
        try:
            out[lang] = f.result()
        except ASRError as e:
            errors.append(e)
    if not out:
        raise errors[0]
    return out


def tts_path(text: str, lang: str | None = None) -> Path:
    """
    Text ki MP3 file banao (ya cache se do). File ka path wapas karo.
    lang na diya ho to text se pehchaano: Devanagari -> Hindi awaaz, baaki -> Punjabi.
    SPEED TRICK: lamba jawab "।" pe sentences mein todo, har sentence ki awaaz EK SAATH
    (parallel threads mein) banao, phir MP3 tukde jod do. MP3 frames seedhe jod sakte hain.
    2 sentence ka jawab ~2.2s ki jagah ~1.3s mein ban jaata hai.
    """
    if lang is None:
        devanagari = sum("ऀ" <= ch <= "ॿ" for ch in text)
        lang = "hi" if devanagari > len(text) / 4 else "pa"
    path = _cache_file(text, lang)
    if path.exists():
        return path
    sentences = [s.strip() + "।" for s in text.split("।") if s.strip()]
    if len(sentences) <= 1:
        _one_sentence(text, lang)
        return path
    with ThreadPoolExecutor(max_workers=4) as pool:
        parts = list(pool.map(lambda s: _one_sentence(s, lang), sentences))
    path.write_bytes(b"".join(parts))
    return path
