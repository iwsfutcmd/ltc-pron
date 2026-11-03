"""What happens when two colloquial rules apply to the same MC reading?

predict_yue_coll applies every rule whose conditions a reading meets, so a
梗攝 reading with a fully voiced initial in the rising tone gets both the
rhyme change and the 全濁上 tone change ("stacking"). For each such reading
this script builds all four combinations:

  literary     neither layer          挺 ding6
  rhyme only   梗攝 vowel             挺 deng6
  tone only    全濁上 aspirate + 5     挺 ting5
  stacked      both                   挺 teng5

and counts which are attested on the character's page and in words. In the
rising tone the two changes do not interact (the tone does not depend on the
rhyme), so the single-layer forms are the literary form with either the
stacked rhyme or the stacked onset and tone.

It then compares coverage if predict_yue_coll returned the stacked form
(current), each single-layer form, or all three.

Writes data/derived/yue_stacking.json.

Usage: uv run python scripts/yue_stacking.py
"""

import json
import re
from collections import Counter
from pathlib import Path

from ltcpron.chars import load_chars
from ltcpron.predict import LtcPron
from ltcpron.rules import colloquial_rules
from ltcpron.words import load_tokens

OUT = Path(__file__).resolve().parent.parent / "data" / "derived"
JYUTPING = re.compile(r"^(gw|kw|ng|[bpmfdtnlgkhwzcsj])?([a-z]+)([1-6])$")
CELLS = ("literary", "rhyme only", "tone only", "stacked")


def split_jp(s):
    m = JYUTPING.match(s)
    return (m.group(1) or "", m.group(2), m.group(3)) if m else None


def main():
    p = LtcPron()
    chars = load_chars()
    tokens = load_tokens()

    rows = []
    for c in chars.values():
        for r in c.mc:
            cat = p.categories(r)
            if len(colloquial_rules(cat)) < 2:
                continue
            lit, stacked = p.yue(cat), p.yue_coll(cat)
            lo, lr, lt = split_jp(lit)
            so, sr, st = split_jp(stacked)
            forms = {
                "literary": lit,
                "rhyme only": lo + sr + lt,
                "tone only": so + lr + st,
                "stacked": stacked,
            }
            page = {y.base for y in c.yue}
            word = Counter(t.reading.base for t in tokens.get(c.char, []))
            rows.append({
                "char": c.char, "mc": r[:6], "rules": colloquial_rules(cat), "forms": forms,
                "page": {k: f in page for k, f in forms.items()},
                "words": {k: word[f] for k, f in forms.items()},
                "other_page": sorted(page - set(forms.values())),
            })

    with_page = [x for x in rows if chars[x["char"]].yue]
    print(f"MC readings where two colloquial rules apply: {len(rows)} "
          f"({len(with_page)} on characters with Cantonese readings)")
    page_hits = Counter(k for x in with_page for k in CELLS if x["page"][k])
    word_hits = Counter()
    for x in rows:
        word_hits.update(x["words"])
    any_attested = sum(any(x["page"].values()) for x in with_page)
    print(f"  with any of the four forms attested: {any_attested}")
    for k in CELLS:
        print(f"  {k:11} attested on {page_hits[k]:3} pages; {word_hits[k]:4} word tokens")

    print("\nReadings with an attested form:")
    for x in with_page:
        if any(x["page"].values()):
            cells = " ".join(f"{k}={x['forms'][k]}{'*' if x['page'][k] else ''}" for k in CELLS)
            print(f"  {x['char']} {x['mc']}  {cells}   other: {' '.join(x['other_page'])}")

    # Coverage under each option for what predict_yue_coll returns on overlaps.
    options = {
        "stacked (current)": ("stacked",),
        "rhyme layer only": ("rhyme only",),
        "tone layer only": ("tone only",),
        "no colloquial form": (),
        "one form per layer": ("rhyme only", "tone only"),
        "per layer + stacked": ("rhyme only", "tone only", "stacked"),
    }
    overlap = {(x["char"], x["mc"]): x for x in rows}
    coverage = {}
    for name, cells in options.items():
        matched = total = 0
        for c in chars.values():
            if not (c.mc and c.yue):
                continue
            forms = set()
            for r in c.mc:
                cat = p.categories(r)
                forms.add(p.yue(cat))
                x = overlap.get((c.char, r[:6]))
                if x:
                    forms.update(x["forms"][k] for k in cells)
                elif (coll := p.yue_coll(cat)):
                    forms.add(coll)
            for y in {y.base for y in c.yue}:
                total += 1
                matched += y in forms
        coverage[name] = matched
        print(f"\n{name:22} {matched} of {total} attested ({matched / total:.2%})")

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "yue_stacking.json").write_text(json.dumps({
        "rows": rows, "page_hits": page_hits, "word_hits": word_hits,
        "any_attested": any_attested, "with_page": len(with_page), "coverage": coverage,
    }, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
