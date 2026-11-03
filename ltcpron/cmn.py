"""Mandarin readings from {{zh-pron}} m=, as numbered pinyin like predict_cmn's."""

import json
import re
import unicodedata
from collections import defaultdict

from .chars import EXTRACTED

_MARKS = {"̄": "1", "́": "2", "̌": "3", "̀": "4"}
_SYLLABLE = re.compile(r"^[a-zü]+[1-5]?$")


def numbered(pinyin: str) -> str | None:
    """'lüè' -> 'lüe4', 'shēng' -> 'sheng1', neutral 'de' -> 'de'."""
    tone = ""
    out = []
    for ch in unicodedata.normalize("NFD", pinyin.strip().lower()):
        if ch in _MARKS:
            tone = _MARKS[ch]
        elif ch == "̈":  # combining diaeresis: rebuild ü
            out[-1] = "ü"
        else:
            out.append(ch)
    syl = unicodedata.normalize("NFC", "".join(out)) + tone
    return syl if _SYLLABLE.match(syl) else None


def toneless(syl: str) -> str:
    return syl.rstrip("12345")


def mandarin_readings() -> dict[str, set[str]]:
    """char -> numbered Mandarin readings from m= on its own page."""
    out = defaultdict(set)
    with open(EXTRACTED / "zh-pron.jsonl") as f:
        for line in f:
            rec = json.loads(line)
            if len(rec["title"]) != 1:
                continue
            for t in rec["templates"]:
                for part in (t.get("m") or "").split(","):
                    if "=" not in part and (syl := numbered(part)):
                        out[rec["title"]].add(syl)
    return out
