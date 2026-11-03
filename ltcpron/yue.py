"""Parse Cantonese readings out of extracted {{zh-pron}} parameters."""

import re
from dataclasses import dataclass

# A Jyutping syllable, optionally with a changed tone: "saang1", "saang1-4".
SYLLABLE = re.compile(r"^([a-z]+)([1-6])(?:-([1-6]))?$")


@dataclass(frozen=True)
class YueReading:
    base: str            # syllable with its base tone, e.g. "saang1"
    changed: str | None  # changed tone (變音), if marked, e.g. "4"

    @property
    def toneless(self) -> str:
        return self.base[:-1]


def parse_syllable(s: str) -> YueReading | None:
    m = SYLLABLE.match(s.strip())
    if not m:
        return None
    return YueReading(m.group(1) + m.group(2), m.group(3))


def readings(c_param: str) -> list[list[YueReading | None]]:
    """Split a c= value into readings, each a list of syllables.

    "saang1,sang1" -> [[saang1], [sang1]]; "sin1 saang1" -> [[sin1, saang1]].
    Unparseable syllables come back as None so callers can count them.
    """
    out = []
    for reading in c_param.split(","):
        reading = reading.strip()
        if reading:
            out.append([parse_syllable(s) for s in reading.split()])
    return out


_NOTE_PIECE = re.compile(r"^\s*([a-z1-6\-/, ]+?)\s+-\s+(.+?)\s*$")
_LABELS = ("colloquial", "literary")


def note_labels(c_note: str) -> dict[str, str]:
    """Map syllables to 'colloquial'/'literary' from a c_note value.

    "saang1 - colloquial; sang1 - literary" -> {"saang1": "colloquial", "sang1": "literary"}
    Pieces without either label are ignored. Keys keep the changed tone if given.
    """
    out = {}
    for piece in c_note.split(";"):
        m = _NOTE_PIECE.match(piece)
        if not m:
            continue
        label = next((l for l in _LABELS if m.group(2).lower().startswith(l)), None)
        if not label:
            continue
        for syl in re.split(r"[/,]", m.group(1)):
            if syl.strip():
                out[syl.strip()] = label
    return out
