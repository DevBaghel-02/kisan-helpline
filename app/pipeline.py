"""
PIPELINE: saare tukde jodna + har step ka time naapna.

  awaaz --(speech.transcribe)--> text alternatives
        --(intent.understand)--> {intent, crops, market}
        --(answer.build_answer)--> Punjabi jawab + source rows
        --(speech.tts_path)--> MP3

Website aur phone call, dono yahi function use karte hain. Isliye logic ek hi jagah hai.
"""
import time

from . import answer, data, intent, speech


def _pick_best(alternatives: list[dict]) -> tuple[str, dict]:
    """
    ASR ke n-best alternatives mein se wo chuno jisse sabse zyada samajh aaye.
    Score: fasal mili = +2, mandi mili = +1, intent mila = +1. Barabar ho to ASR ka pehla wala.
    Example: shor mein pehla alternative "ਕਰਨ ਦਾ ਭਾਅ" ho aur doosra "ਕਣਕ ਦਾ ਭਾਅ",
    to doosra chuna jaayega kyunki usmein fasal mili.
    """
    best_text, best_q, best_score = alternatives[0]["text"], None, -1
    for alt in alternatives:
        q = intent.understand(alt["text"])
        score = 2 * bool(q["crops"]) + bool(q["market"] or q["unknown_market"]) + bool(q["intent"])
        if score > best_score:
            best_text, best_q, best_score = alt["text"], q, score
    return best_text, best_q


def ask(*, text: str | None = None, wav: bytes | None = None, channel: str = "web", speak: bool = True) -> dict:
    timings = {}
    t0 = time.perf_counter()

    alternatives = []
    if wav is not None:
        try:
            alternatives = speech.transcribe(wav)
        except speech.ASRError as e:
            return {"ok": False, "error": str(e), "heard": None}
        timings["asr_ms"] = int((time.perf_counter() - t0) * 1000)
        if not alternatives:
            return _finish({"ok": True, "heard": "", "kind": "no_speech", "answered": False,
                            "text": "ਮਾਫ਼ ਕਰਨਾ, ਆਵਾਜ਼ ਸਾਫ਼ ਨਹੀਂ ਆਈ। ਕਿਰਪਾ ਕਰਕੇ ਦੁਬਾਰਾ ਬੋਲੋ।",
                            "sources": [], "understood": None}, timings, t0, channel, speak)
    else:
        alternatives = [{"text": text or "", "confidence": None}]

    t1 = time.perf_counter()
    heard, q = _pick_best(alternatives)
    timings["understand_ms"] = int((time.perf_counter() - t1) * 1000)

    t2 = time.perf_counter()
    a = answer.build_answer(q)
    timings["answer_ms"] = int((time.perf_counter() - t2) * 1000)

    out = {"ok": True, "heard": heard, "alternatives": [x["text"] for x in alternatives],
           "understood": {k: q[k] for k in ("intent", "crops", "market", "unknown_market", "day")},
           "evidence": q["evidence"], **a}
    return _finish(out, timings, t0, channel, speak)


def _finish(out, timings, t0, channel, speak):
    if speak:
        t3 = time.perf_counter()
        out["audio_file"] = speech.tts_path(out["text"]).name
        timings["tts_ms"] = int((time.perf_counter() - t3) * 1000)
    timings["total_ms"] = int((time.perf_counter() - t0) * 1000)
    out["timings"] = timings
    u = out.get("understood") or {}
    data.log_query(channel, out.get("heard"), u.get("intent"), ",".join(u.get("crops") or []),
                   u.get("market") or u.get("unknown_market"), out.get("answered", False), out["text"],
                   timings["total_ms"])
    return out
