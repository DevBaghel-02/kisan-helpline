"""
BENCHMARK: recorded sawaalon pe system kitna sahi aur kitna tez hai.

Use:
  1. Doston se Punjabi sawaal record karwao, WAV files ko tests/audio/ mein rakho.
  2. tests/audio/expected.csv banao:  file,crop,market      (jaise: q01.wav,wheat,Amritsar)
     Jo sawaal dataset ke bahar hai uske liye crop khaali chhodo -> "pata nahi" expected hai.
  3. Chalao:  python scripts/benchmark.py
  Output: har file ka result + accuracy + average/max time. Ye table presentation mein dikhao.

--make-synthetic : bina recording ke test karne ke liye, TTS se sawaal bana ke unpe shor (noise) milata hai.
"""
import csv
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from app import data, intent, pipeline, speech  # noqa: E402

AUDIO = ROOT / "tests" / "audio"

SYNTHETIC = [  # (file, question, crop, market)
    ("s01", "ਅੰਮ੍ਰਿਤਸਰ ਮੰਡੀ ਵਿੱਚ ਕਣਕ ਦਾ ਕੀ ਭਾਅ ਹੈ", "wheat", "Amritsar"),
    ("s02", "ਤਰਨ ਤਾਰਨ ਬਾਸਮਤੀ ਦਾ ਰੇਟ ਦੱਸੋ", "basmati", "Tarn Taran"),
    ("s03", "ਬਠਿੰਡੇ ਨਰਮੇ ਦਾ ਭਾਅ ਕੀ ਚੱਲ ਰਿਹਾ", "cotton", "Bathinda"),
    ("s04", "ਝੋਨੇ ਦਾ ਭਾਅ", "paddy", ""),
    ("s05", "ਲੁਧਿਆਣਾ ਮੰਡੀ ਸਰ੍ਹੋਂ ਦਾ ਰੇਟ", "mustard", "Ludhiana"),
    ("s06", "ਸੇਬ ਦਾ ਭਾਅ ਕੀ ਹੈ", "", ""),
]


def make_synthetic():
    AUDIO.mkdir(parents=True, exist_ok=True)
    rows = []
    for name, q, crop, market in SYNTHETIC:
        mp3 = speech.tts_path(q)
        for tag, noise in (("clean", None), ("noisy", 0.08)):
            out = AUDIO / f"{name}_{tag}.wav"
            cmd = ["ffmpeg", "-loglevel", "error", "-y", "-i", str(mp3)]
            if noise:   # brown noise milao (fan/tractor jaisa shor)
                cmd += ["-f", "lavfi", "-i", f"anoisesrc=color=brown:amplitude={noise}",
                        "-filter_complex", "[0][1]amix=inputs=2:duration=first:normalize=0"]
            cmd += ["-ar", "16000", "-ac", "1", str(out)]
            subprocess.run(cmd, check=True)
            rows.append((out.name, crop, market))
    with open(AUDIO / "expected.csv", "w", newline="", encoding="utf-8") as f:
        csv.writer(f).writerows([("file", "crop", "market"), *rows])
    print(f"{len(rows)} synthetic files bani: {AUDIO}")


def run():
    data.ensure_sample_data()
    intent.refresh()
    rows = list(csv.DictReader(open(AUDIO / "expected.csv", encoding="utf-8")))
    correct, times = 0, []
    print(f"{'file':<18}{'ok':<4}{'ms':>6}  heard -> answer")
    for r in rows:
        res = pipeline.ask(wav=(AUDIO / r["file"]).read_bytes(), channel="benchmark")
        u = res.get("understood") or {}
        got_crop = (u.get("crops") or [""])[0]
        got_market = u.get("market") or ""
        if r["crop"]:
            ok = got_crop == r["crop"] and (not r["market"] or got_market == r["market"]) and res["answered"]
        else:
            ok = not res["answered"]            # dataset ke bahar: jawab NAHI dena chahiye
        correct += ok
        times.append(res["timings"]["total_ms"])
        print(f"{r['file']:<18}{'✓' if ok else '✗':<4}{res['timings']['total_ms']:>6}  {res.get('heard')} -> {res['text'][:60]}")
    print(f"\nAccuracy: {correct}/{len(rows)} = {100 * correct / len(rows):.0f}%")
    print(f"Time: average {sum(times) / len(times) / 1000:.2f}s, max {max(times) / 1000:.2f}s (target < 6s)")


if __name__ == "__main__":
    if "--make-synthetic" in sys.argv:
        make_synthetic()
    run()
