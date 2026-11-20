"""
NORMALISER: speech-to-text ki galtiyon ko sambhaalna.

Problem: ASR kabhi "ਕਣਕ" likhta hai, kabhi "ਕਨਕ", kabhi "kanak". Mandi "ਅੰਮ੍ਰਿਤਸਰ" bhi
"ਅਮ੍ਰਿਤਸਰ" ya "ਅੰਬਰਸਰ" ban jaati hai. Agar hum exact match karenge to bot fail ho jaayega.

Hal (3 steps):
  1. skeleton(): Gurmukhi ke chhote nishaan hata do (addak ੱ, nukta ਼, halant ੍), tippi ੰ = bindi ਂ.
     Isse "ਕੱਲ੍ਹ" aur "ਕਲ੍ਹ" ek jaise ho jaate hain.
  2. to_roman(): Gurmukhi/Hindi ko rough English letters mein badlo ("ਬਠਿੰਡਾ" -> "bathinda").
     Isse judges ki CSV ke English naam ("Bathinda") se bhi match ho jaata hai.
  3. Fuzzy match (difflib): 82% se zyada milta-julta shabd = match. Chhote shabd (<=3 akshar)
     sirf exact match honge, warna galat match ka khatra hai.
"""
import difflib
import re
import unicodedata

# --- Step 1: skeleton -------------------------------------------------------
_DROP = {"ੱ", "਼", "੍", "़", "्"}  # addak, nukta, halant (Gurmukhi + Hindi)
_SAME = {"ੰ": "ਂ", "ँ": "ं",            # tippi -> bindi, chandrabindu -> anusvara
         "ਸ਼": "ਸ", "ਖ਼": "ਖ", "ਗ਼": "ਗ", "ਜ਼": "ਜ", "ਫ਼": "ਫ"}  # ਸ਼ ਖ਼ ਗ਼ ਜ਼ ਫ਼ -> base


def skeleton(text: str) -> str:
    text = unicodedata.normalize("NFC", text.lower())
    out = []
    for ch in text:
        if ch in _DROP:
            continue
        # Akshar (L), matra (M) aur number (N) rakho; punctuation (।, ?, !) ko space bana do.
        # Dhyan do: regex ka \w matra (ਾ ਿ ੋ) ko akshar nahi maanta, isliye unicodedata use kiya.
        out.append(_SAME.get(ch, ch) if unicodedata.category(ch)[0] in "LMN" else " ")
    return re.sub(r"\s+", " ", "".join(out)).strip()


# --- Step 2: rough transliteration to Roman letters -------------------------
_ROMAN = {
    # Gurmukhi consonants
    "ਕ": "k", "ਖ": "kh", "ਗ": "g", "ਘ": "gh", "ਙ": "n", "ਚ": "ch", "ਛ": "chh", "ਜ": "j", "ਝ": "jh", "ਞ": "n",
    "ਟ": "t", "ਠ": "th", "ਡ": "d", "ਢ": "dh", "ਣ": "n", "ਤ": "t", "ਥ": "th", "ਦ": "d", "ਧ": "dh", "ਨ": "n",
    "ਪ": "p", "ਫ": "ph", "ਬ": "b", "ਭ": "bh", "ਮ": "m", "ਯ": "y", "ਰ": "r", "ਲ": "l", "ਵ": "v", "ੜ": "r",
    "ਸ": "s", "ਹ": "h",
    # Gurmukhi vowels / matras
    "ਅ": "a", "ਆ": "a", "ਇ": "i", "ਈ": "i", "ਉ": "u", "ਊ": "u", "ਏ": "e", "ਐ": "ai", "ਓ": "o", "ਔ": "au",
    "ੳ": "u", "ੲ": "i", "ਾ": "a", "ਿ": "i", "ੀ": "i", "ੁ": "u", "ੂ": "u", "ੇ": "e", "ੈ": "ai", "ੋ": "o", "ੌ": "au",
    "ਂ": "n",
    # Devanagari (Hindi) - same idea
    "क": "k", "ख": "kh", "ग": "g", "घ": "gh", "च": "ch", "छ": "chh", "ज": "j", "झ": "jh", "ट": "t", "ठ": "th",
    "ड": "d", "ढ": "dh", "ण": "n", "त": "t", "थ": "th", "द": "d", "ध": "dh", "न": "n", "प": "p", "फ": "ph",
    "ब": "b", "भ": "bh", "म": "m", "य": "y", "र": "r", "ल": "l", "व": "v", "स": "s", "श": "sh", "ह": "h",
    "अ": "a", "आ": "a", "इ": "i", "ई": "i", "उ": "u", "ऊ": "u", "ए": "e", "ऐ": "ai", "ओ": "o", "औ": "au",
    "ा": "a", "ि": "i", "ी": "i", "ु": "u", "ू": "u", "े": "e", "ै": "ai", "ो": "o", "ौ": "au", "ं": "n", "ृ": "ri",
}


def to_roman(text: str) -> str:
    text = "".join(_ROMAN.get(ch, ch) for ch in skeleton(text))
    # spelling ka farak kam karo: 'w'->'v', 'z'->'j', 'ee'->'i', 'oo'->'u', double letters ek.
    # 'a' poora hata do: Gurmukhi mein "ਕਣਕ" likhte waqt 'a' dikhta hi nahi ("knk"),
    # jabki English mein "kanak" likhte hain. Dono taraf 'a' hatane se dono "knk" ban jaate hain.
    text = text.replace("w", "v").replace("z", "j").replace("ee", "i").replace("oo", "u")
    text = text.replace("a", "")
    text = re.sub(r"(.)\1+", r"\1", text)
    return text


# --- Step 3: fuzzy matcher --------------------------------------------------
class Matcher:
    """
    Ek category (jaise saari fasalein) ke liye: {key: [shabd1, shabd2, ...]}.
    find(text) -> sabse achha (key, score, kaunsa hissa suna gaya) list.
    """

    THRESHOLD = 0.82

    def __init__(self, entries: dict[str, list[str]]):
        self.forms = []  # (key, skeleton form, roman form)
        for key, words in entries.items():
            for w in words:
                self.forms.append((key, skeleton(w), to_roman(w)))

    def _score(self, piece: str, piece_roman: str, form: str, form_roman: str) -> float:
        if piece == form or piece_roman == form_roman:
            return 1.0
        if len(form_roman) <= 3 or len(piece_roman) <= 3:
            return 0.0                                  # chhote shabd: sirf exact
        return max(difflib.SequenceMatcher(None, piece, form).ratio(),
                   difflib.SequenceMatcher(None, piece_roman, form_roman).ratio())

    def find(self, text: str) -> list[tuple[str, float, str]]:
        tokens = skeleton(text).split()
        best: dict[str, tuple[float, str]] = {}
        for n in (3, 2, 1):                             # pehle 3-shabd wale tukde ("ਤਰਨ ਤਾਰਨ"), phir chhote
            for i in range(len(tokens) - n + 1):
                piece = " ".join(tokens[i:i + n])
                piece_roman = to_roman(piece)
                for key, form, form_roman in self.forms:
                    if form.count(" ") != n - 1:
                        continue
                    s = self._score(piece, piece_roman, form, form_roman)
                    if s >= self.THRESHOLD and s > best.get(key, (0, ""))[0]:
                        best[key] = (s, piece)
        return sorted(((k, s, p) for k, (s, p) in best.items()), key=lambda x: -x[1])
