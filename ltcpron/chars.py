"""Join extracted MC readings, Cantonese readings and dial-pron data by character."""

import json
from dataclasses import dataclass, field
from pathlib import Path

from .yue import YueReading, note_labels, readings

EXTRACTED = Path(__file__).resolve().parent.parent / "data" / "extracted"

GUANGZHOU = 31  # 0-based column in Module:zh/data/dial-pron rows


@dataclass
class Char:
    char: str
    mc: list[str] = field(default_factory=list)          # raw ltc-pron reading strings
    yue: list[YueReading] = field(default_factory=list)  # c= readings on the char's own page
    yue_unparsed: list[str] = field(default_factory=list)
    labels: dict[str, str] = field(default_factory=dict)  # c_note: syllable -> colloquial/literary
    c_notes: list[str] = field(default_factory=list)
    gz: list[str] = field(default_factory=list)           # dial-pron Guangzhou IPA, as listed


def _jsonl(name: str):
    with open(EXTRACTED / name) as f:
        for line in f:
            yield json.loads(line)


def load_chars() -> dict[str, Char]:
    chars: dict[str, Char] = {}

    def get(ch: str) -> Char:
        return chars.setdefault(ch, Char(ch))

    aliases = {}
    for rec in _jsonl("ltc-pron.jsonl"):
        # Skip the sharded copies (Module:zh/data/ltc-pron/003 etc.);
        # Module:ltc-pron reads the per-character modules.
        if len(rec["char"]) != 1:
            continue
        if "alias" in rec:
            aliases[rec["char"]] = rec["alias"]
        else:
            get(rec["char"]).mc = list(rec["readings"])
    for ch, target in aliases.items():
        if target in chars:
            get(ch).mc = list(chars[target].mc)

    for rec in _jsonl("zh-pron.jsonl"):
        title = rec["title"]
        if len(title) != 1:
            continue
        c = None
        for t in rec["templates"]:
            if "c" not in t:
                continue
            c = c or get(title)
            for reading in readings(t["c"]):
                if len(reading) == 1 and reading[0] is not None:
                    if reading[0] not in c.yue:
                        c.yue.append(reading[0])
                else:
                    c.yue_unparsed.append(t["c"])
            if t.get("c_note"):
                c.c_notes.append(t["c_note"])
                c.labels.update(note_labels(t["c_note"]))

    for rec in _jsonl("dial-pron.jsonl"):
        c = get(rec["char"])
        for row in rec.get("rows", []):
            cols = row[1] if isinstance(row, list) and len(row) > 1 else []
            if len(cols) > GUANGZHOU and cols[GUANGZHOU]:
                c.gz.extend(cols[GUANGZHOU].split("|"))

    return chars
