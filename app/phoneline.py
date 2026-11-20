"""
PHONE LINE EFFECT: laptop ke mic ki saaf awaaz ko asli phone call jaisi "kharab" awaaz banana.

Asli phone call (keypad phone / 2G) mein awaaz aise badalti hai:
  1. Sirf 300-3400 Hz ki awaaz jaati hai (bahut mota aur bahut patla sur kat jaata hai)
  2. 8000 samples/second (website par hum 16000 bhejte hain, yani aadhi quality)
  3. 8-bit mu-law encoding (phone network ka standard G.711), thoda "khar-khar" add hota hai

Simulator mein hum yahi teen cheezein karke awaaz ASR ko bhejte hain. Isse demo imaandaar rehta hai:
jo accuracy simulator mein dikhe, wo asli call ke kareeb hogi, laptop mic jaisi badhiya nahi.
"""
import io
import wave

import numpy as np

PHONE_RATE = 8000
LOW_HZ, HIGH_HZ = 300, 3400
MU = 255


def _read_wav(wav_bytes: bytes) -> tuple[np.ndarray, int]:
    with wave.open(io.BytesIO(wav_bytes)) as w:
        if w.getsampwidth() != 2:
            raise ValueError("Sirf 16-bit WAV chahiye")
        rate, channels = w.getframerate(), w.getnchannels()
        samples = np.frombuffer(w.readframes(w.getnframes()), dtype="<i2").astype(np.float64) / 32768
    if channels > 1:
        samples = samples.reshape(-1, channels).mean(axis=1)    # stereo -> mono
    return samples, rate


def _write_wav(samples: np.ndarray, rate: int) -> bytes:
    pcm = (np.clip(samples, -1, 1) * 32767).astype("<i2")
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(pcm.tobytes())
    return buf.getvalue()


def to_phone_quality(wav_bytes: bytes) -> bytes:
    """16-bit WAV (koi bhi rate) -> phone jaisi 8 kHz WAV."""
    x, rate = _read_wav(wav_bytes)
    if len(x) == 0:
        return _write_wav(x, PHONE_RATE)

    # 1. Band-pass 300-3400 Hz: FFT karke us range ke bahar ki frequencies zero
    spectrum = np.fft.rfft(x)
    freqs = np.fft.rfftfreq(len(x), d=1 / rate)
    spectrum[(freqs < LOW_HZ) | (freqs > HIGH_HZ)] = 0
    x = np.fft.irfft(spectrum, n=len(x))

    # 2. 8000 samples/second pe le aao
    n_out = int(len(x) * PHONE_RATE / rate)
    x = np.interp(np.linspace(0, len(x) - 1, n_out), np.arange(len(x)), x)

    # 3. mu-law: 8-bit mein compress karo, phir wapas kholo (jaise phone network karta hai)
    x = np.clip(x, -1, 1)
    encoded = np.sign(x) * np.log1p(MU * np.abs(x)) / np.log1p(MU)
    encoded = np.round(encoded * 127) / 127                       # 8 bit = sirf 256 levels
    x = np.sign(encoded) * np.expm1(np.abs(encoded) * np.log1p(MU)) / MU

    return _write_wav(x, PHONE_RATE)
