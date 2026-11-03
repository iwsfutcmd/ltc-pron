"""Test candidate colloquial Cantonese sound changes against attested readings.

Each hypothesis is a transform on the literary prediction, applied to chars
with a single MC reading. For eligible chars we report how often the
transformed form is attested, and whether the literary form is attested too.

Usage: uv run python scripts/yue_coll_hypotheses.py [-v]
"""

import re
import sys
from collections import Counter

from ltcpron.chars import load_chars
from ltcpron.predict import LtcPron

JYUTPING = re.compile(r"^(gw|kw|ng|[bpmfdtnlgkhwzcsj])?([a-z]+)([1-6])$")

FULLY_VOICED = {3, 7, 11, 15, 17, 20, 22, 25, 27, 30, 33}
ASPIRATE = {"b": "p", "d": "t", "z": "c", "g": "k", "gw": "kw"}


def split_jp(s):
    m = JYUTPING.match(s)
    return (m.group(1) or "", m.group(2), int(m.group(3))) if m else None


def jp(onset, rhyme, tone):
    return f"{onset}{rhyme}{tone}"


# --- hypotheses: (name, eligible(reading, cats), transform(onset, rhyme, tone)) ---

def h_voiced_rising(r, c):
    return c.tone == 2 and c.initial in FULLY_VOICED


def t_voiced_rising(o, rh, t):
    return jp(ASPIRATE.get(o, o), rh, 5)


def h_geng_34(r, c):
    return r[1] in "庚陌清昔青錫" and r[2] in "三四"


def t_geng_34(o, rh, t):
    rh2 = {"ing": "eng", "ik": "ek", "wing": "weng"}.get(rh)
    if not rh2:
        return None
    return jp(o, rh2, 3 if t == 1 else t)


def h_geng_2(r, c):
    return r[1] in "庚陌耕麥" and r[2] == "二"


def t_geng_2(o, rh, t):
    rh2 = {"ang": "aang", "ak": "aak"}.get(rh)
    if not rh2:
        return None
    return jp(o, rh2, 3 if (t == 1 and rh == "ak") else t)


def h_zhi(r, c):
    return r[1] in "支脂之微" and r[3] == "開"


def t_zhi(o, rh, t):
    return jp(o, "ei", t) if rh == "i" else None


HYPOTHESES = [
    ("全濁上: aspirated + tone 5", h_voiced_rising, t_voiced_rising),
    ("梗三四: -ing/-ik > -eng/-ek", h_geng_34, t_geng_34),
    ("梗二: -ang/-ak > -aang/-aak", h_geng_2, t_geng_2),
    ("止開: -i > -ei", h_zhi, t_zhi),
]


def main(verbose=False):
    p = LtcPron()
    chars = [c for c in load_chars().values() if len(c.mc) == 1 and c.yue]
    for name, eligible, transform in HYPOTHESES:
        n = Counter()
        examples = []
        for c in chars:
            r = c.mc[0]
            cats = p.categories(r)
            if not eligible(r, cats):
                continue
            lit = p.yue(cats)
            parts = split_jp(lit)
            coll = transform(*parts) if parts else None
            if not coll or coll == lit:
                n["no distinct form"] += 1
                continue
            att = {y.base for y in c.yue}
            n["eligible"] += 1
            has_lit, has_coll = lit in att, coll in att
            n[("coll attested" if has_coll else "coll not attested")
              + (", lit attested" if has_lit else ", lit not attested")] += 1
            if has_coll:
                label = c.labels.get(coll)
                if label:
                    n[f"coll c_note={label}"] += 1
                examples.append(f"{c.char}{coll}" + ("" if not has_lit else f"/{lit}"))
        print(f"\n{name}")
        for k in ["eligible", "no distinct form",
                  "coll attested, lit attested", "coll attested, lit not attested",
                  "coll not attested, lit attested", "coll not attested, lit not attested",
                  "coll c_note=colloquial", "coll c_note=literary"]:
            if n[k]:
                print(f"  {k:38} {n[k]:5}")
        shown = examples if verbose else examples[:40]
        print("  e.g. " + " ".join(shown))


if __name__ == "__main__":
    main("-v" in sys.argv)
