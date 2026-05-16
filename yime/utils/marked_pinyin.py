from __future__ import annotations

ACCENTED_VOWEL_MAP: dict[str, tuple[str, int]] = {
    "ā": ("a", 1),
    "á": ("a", 2),
    "ǎ": ("a", 3),
    "à": ("a", 4),
    "ē": ("e", 1),
    "é": ("e", 2),
    "ě": ("e", 3),
    "è": ("e", 4),
    "ê": ("e", 1),
    "ḗ": ("e", 2),
    "ế": ("e", 2),
    "ề": ("e", 4),
    "ī": ("i", 1),
    "í": ("i", 2),
    "ǐ": ("i", 3),
    "ì": ("i", 4),
    "ō": ("o", 1),
    "ó": ("o", 2),
    "ǒ": ("o", 3),
    "ò": ("o", 4),
    "ū": ("u", 1),
    "ú": ("u", 2),
    "ǔ": ("u", 3),
    "ù": ("u", 4),
    "ǖ": ("ü", 1),
    "ǘ": ("ü", 2),
    "ǚ": ("ü", 3),
    "ǜ": ("ü", 4),
    "ń": ("n", 2),
    "ň": ("n", 3),
    "ǹ": ("n", 4),
    "ḿ": ("m", 2),
}


def marked_syllable_to_numeric(syllable: str) -> str:
    tone = 5
    base_chars: list[str] = []
    for char in syllable:
        mapped = ACCENTED_VOWEL_MAP.get(char)
        if mapped is None:
            base_chars.append(char)
            continue
        base, tone = mapped
        base_chars.append(base)

    base_syllable = "".join(base_chars).lower().replace("u:", "ü")
    if not base_syllable:
        return base_syllable
    return f"{base_syllable}{tone}"


def marked_pinyin_to_numeric(marked_pinyin: str) -> str:
    syllables = [segment for segment in marked_pinyin.strip().split() if segment]
    return " ".join(marked_syllable_to_numeric(segment) for segment in syllables)
