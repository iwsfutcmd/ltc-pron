"""Tally attested Cantonese outcomes for a slice of Middle Chinese.

Only characters with a single MC reading are used, so each attested
reading can be attributed. Filters match the fields of the reading
string; each accepts a set of characters (e.g. --initial 精清從心邪).

Usage:
  uv run python scripts/yue_tally.py --final 眞 --div 三 --open 開 --by initial --part rhyme
"""

import argparse
import re
from collections import Counter, defaultdict

from ltcpron.chars import load_chars
from ltcpron.predict import LtcPron

JYUTPING = re.compile(r"^(gw|kw|ng|[bpmfdtnlgkhwzcsj])?([a-z]+)([1-6])$")
PARTS = {"onset": 0, "rhyme": 1, "tone": 2}
FIELDS = {"initial": 0, "final": 1, "div": 2, "open": 3, "tone": 5}


def split_jp(s):
    m = JYUTPING.match(s)
    return (m.group(1) or "∅", m.group(2), m.group(3)) if m else None


def main(args):
    p = LtcPron()
    rows = defaultdict(Counter)
    preds = defaultdict(Counter)
    examples = defaultdict(lambda: defaultdict(list))
    for c in load_chars().values():
        if len(c.mc) != 1 or not c.yue:
            continue
        r = c.mc[0]
        if any(getattr(args, f) and r[i] not in getattr(args, f) for f, i in FIELDS.items()):
            continue
        key = r[FIELDS[args.by]] if args.by in FIELDS else "all"
        pred = split_jp(p.yue(p.categories(r)))
        preds[key][pred[PARTS[args.part]] if args.part in PARTS else "".join(pred)] += 1
        for y in {y.base for y in c.yue}:
            a = split_jp(y)
            if not a:
                continue
            out = a[PARTS[args.part]] if args.part in PARTS else y
            rows[key][out] += 1
            if len(examples[key][out]) < 6:
                examples[key][out].append(c.char)
    for key in sorted(rows, key=lambda k: -sum(rows[k].values())):
        print(f"{key}  predicted {dict(preds[key])}")
        print("   " + "  ".join(f"{o} {n} ({''.join(examples[key][o])})"
                                for o, n in rows[key].most_common(args.top)))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    for f in FIELDS:
        ap.add_argument(f"--{f}", default="")
    ap.add_argument("--by", default="initial", choices=[*FIELDS, "all"])
    ap.add_argument("--part", default="rhyme", choices=[*PARTS, "syllable"])
    ap.add_argument("--top", type=int, default=6)
    main(ap.parse_args())
