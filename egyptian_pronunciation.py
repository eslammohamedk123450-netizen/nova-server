"""Conservative Egyptian Arabic TTS text preparation.

The display text is never changed. Only the private text sent to TTS is
normalized and selectively vocalized. Keep this dictionary conservative:
incorrect tashkeel can be worse than leaving a word unvocalized.
"""
from __future__ import annotations

import re
import unicodedata

# Whole-word pronunciation hints for frequent Egyptian colloquial words.
# Values use Arabic diacritics to guide the Arabic neural voice.
WORD_PRONUNCIATIONS = {
    "النهارده": "النَّهارْدَه",
    "النهاردة": "النَّهارْدَه",
    "انهارده": "النَّهارْدَه",
    "انهاردة": "النَّهارْدَه",
    "دلوقتي": "دِلْوَقْتي",
    "دلوقت": "دِلْوَقْت",
    "إزاي": "إِزَّاي",
    "ازاي": "إِزَّاي",
    "إزيك": "إِزَّيَّك",
    "ازيك": "إِزَّيَّك",
    "عامل": "عامِل",
    "عاملة": "عامْلَه",
    "عايز": "عايِز",
    "عاوز": "عاوِز",
    "عايزة": "عايْزَه",
    "عاوزة": "عاوْزَه",
    "كده": "كِدَه",
    "كدا": "كِدَه",
    "ليه": "لِيه",
    "إيه": "إِيه",
    "ايه": "إِيه",
    "مش": "مِش",
    "معلش": "مَعْلِش",
    "معاك": "مَعاك",
    "معاكي": "مَعاكي",
    "هساعدك": "هَساعِدَك",
    "موجود": "مَوْجود",
    "موجودة": "مَوْجودَه",
    "أهلا": "أَهْلًا",
    "اهلا": "أَهْلًا",
    "أنا": "أَنا",
    "انا": "أَنا",
    # Brand/persona name: explicitly preserve the long final ee sound.
    "سولي": "سُولِي",
    "سولين": "سُولِين",
}

# Normalize common Unicode presentation differences without changing wording.
_DIACRITICS = re.compile(r"[\u064B-\u065F\u0670]")
_TOKEN = re.compile(r"[\u0621-\u064A\u066E-\u06D3]+")


def prepare_egyptian_speech_text(text: str) -> str:
    """Return a TTS-only version with conservative Egyptian pronunciation hints."""
    value = unicodedata.normalize("NFC", text)
    value = value.replace("\u0640", "")  # tatweel
    value = re.sub(r"[ \t\r\n]+", " ", value).strip()

    def replace_word(match: re.Match[str]) -> str:
        word = match.group(0)
        # Match dictionary entries regardless of pre-existing tashkeel.
        bare = _DIACRITICS.sub("", word)
        return WORD_PRONUNCIATIONS.get(bare, word)

    return _TOKEN.sub(replace_word, value)
