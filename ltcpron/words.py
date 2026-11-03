"""Character-level Cantonese readings from multi-character {{zh-pron}} entries.

Each Cantonese reading of a word is aligned one syllable per character;
readings whose syllable count does not match the title are skipped. A word
counts as vernacular when its template has a Cantonese reading (c=) but no
Mandarin one (m=): Cantonese-specific vocabulary such as 生仔 or 揾食.
"""

import json
import re
from collections import defaultdict
from dataclasses import dataclass

from .chars import EXTRACTED
from .yue import YueReading, parse_syllable

_HAN = re.compile(r"^[㐀-鿿\U00020000-\U0003134f豈-﫿]+$")
_COMMENT = re.compile(r"<!--.*?(?:-->|$)", re.S)


@dataclass(frozen=True)
class Token:
    word: str
    index: int
    reading: YueReading
    vernacular: bool


def load_tokens() -> dict[str, list[Token]]:
    """char -> its readings in multi-character words, one Token per word reading."""
    tokens: dict[str, list[Token]] = defaultdict(list)
    with open(EXTRACTED / "zh-pron.jsonl") as f:
        for line in f:
            rec = json.loads(line)
            word = rec["title"]
            if len(word) < 2 or not _HAN.match(word):
                continue
            seen = set()
            for t in rec["templates"]:
                if not t.get("c"):
                    continue
                vernacular = "m" not in t
                for alt in _COMMENT.sub("", t["c"]).split(","):
                    sylls = alt.split()
                    if len(sylls) != len(word):
                        continue
                    for i, (ch, s) in enumerate(zip(word, sylls)):
                        y = parse_syllable(s)
                        if y and (ch, i, y.base) not in seen:
                            seen.add((ch, i, y.base))
                            tokens[ch].append(Token(word, i, y, vernacular))
    return tokens
