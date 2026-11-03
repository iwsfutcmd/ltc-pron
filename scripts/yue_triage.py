"""Sort the remaining gaps in the Cantonese predictions into three kinds.

Takes the per-part gaps from scripts/yue_misses.py (an MC category and a
change in onset, rhyme or tone, e.g. 眞三開 "an → eon") and tests each, on
characters with a single MC reading:

  conditioned   the change holds across the group, or across a sub-group
                (by MC initial for rhyme and tone gaps, by final for onset
                gaps): at least MIN_CHARS characters and 2:1 against the
                prediction  ->  a literary fix candidate
  layer         characters often have both forms, and words using the
                changed form are more vernacular  ->  a colloquial candidate
  exception     neither: word-by-word, leave as a mismatch

Run scripts/yue_misses.py first. Writes data/derived/yue_triage.json.

Usage: uv run python scripts/yue_triage.py [--top 40] [--min-common 6]
"""

import argparse
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

from ltcpron.chars import load_chars
from ltcpron.predict import LtcPron
from ltcpron.words import load_tokens

DERIVED = Path(__file__).resolve().parent.parent / "data" / "derived"
JYUTPING = re.compile(r"^(gw|kw|ng|[bpmfdtnlgkhwzcsj])?([a-z]+)([1-6])$")
FULLY_VOICED = {3, 7, 11, 15, 17, 20, 22, 25, 27, 30, 33}
SONORANT = {4, 8, 12, 31, 35, 36, 37, 38}
PARTS = ("onset", "rhyme", "tone")
MIN_CHARS = 5


def split_jp(s):
    m = JYUTPING.match(s)
    return [m.group(1) or "", m.group(2), m.group(3)] if m else None


def voicing(initial):
    return "voiced" if initial in FULLY_VOICED else "sonorant" if initial in SONORANT else "voiceless"


def main(top: int, min_common: int):
    p = LtcPron()
    chars = load_chars()
    tokens = load_tokens()
    gaps = json.loads((DERIVED / "yue_misses.json").read_text())["gaps"]

    # single-reading characters with their categories and literary prediction
    single = []
    for c in chars.values():
        if len(c.mc) == 1 and c.yue:
            r = c.mc[0]
            cat = p.categories(r)
            single.append((c, r, cat, p.yue(cat)))

    def group_key(part, r, cat):
        return {"onset": r[0], "rhyme": r[1:4], "tone": f"{r[5]} {voicing(cat.initial)}"}[part]

    def sub_key(part, r):
        # rhyme and tone gaps split by initial; onset gaps by final
        return r[1:4] + ("入" if r[5] == "入" else "") if part == "onset" else r[0]

    results = []
    for part in PARTS:
        i = PARTS.index(part)
        for gap in gaps[part]:
            if gap["common"] < min_common:
                continue
            old, new = (x.replace("∅", "") for x in gap["change"].split(" → "))
            show, keep = [], []
            sub = defaultdict(lambda: [0, 0])
            vern = {"changed": [0, 0], "predicted": [0, 0]}
            both = 0
            for c, r, cat, lit in single:
                if group_key(part, r, cat) != gap["group"]:
                    continue
                parts = split_jp(lit)
                if not parts or parts[i] != old:
                    continue
                changed = parts.copy()
                changed[i] = new
                changed = "".join(changed)
                att = {y.base for y in c.yue}
                has_c, has_p = changed in att, lit in att
                if not (has_c or has_p):
                    continue
                s = sub[sub_key(part, r)]
                if has_c:
                    show.append(c.char)
                    s[0] += 1
                if has_p:
                    keep.append(c.char)
                    s[1] += 1
                both += has_c and has_p
                for t in tokens.get(c.char, []):
                    side = "changed" if t.reading.base == changed else "predicted" if t.reading.base == lit else None
                    if side:
                        vern[side][0] += 1
                        vern[side][1] += t.vernacular
            if not show:
                continue
            strong_subs = sorted(
                ((k, v) for k, v in sub.items() if v[0] >= MIN_CHARS and v[0] >= 2 * v[1]),
                key=lambda kv: -kv[1][0])
            vs = {k: (v[1] / v[0] if v[0] else None) for k, v in vern.items()}
            whole = len(show) >= MIN_CHARS and len(show) >= 2 * len(keep)
            skew = (vs["changed"] is not None and vs["predicted"] is not None
                    and vern["changed"][0] >= 10 and vs["changed"] > 1.5 * vs["predicted"])
            if whole or strong_subs:
                kind = "conditioned"
            elif skew and both >= 3:
                kind = "layer"
            else:
                kind = "exception"
            results.append({
                "part": part, "group": gap["group"], "change": gap["change"], "common": gap["common"],
                "show": len(show), "keep": len(keep), "both": both,
                "strong_subs": [(k, v) for k, v in strong_subs], "vernacular": vs,
                "vern_tokens": {k: v[0] for k, v in vern.items()}, "kind": kind,
                "examples": show[:10],
            })

    results.sort(key=lambda x: -x["common"])
    kinds = Counter(x["kind"] for x in results)
    print(f"Gaps with at least {min_common} common characters: {len(results)}  {dict(kinds)}\n")
    for x in results[:top]:
        vs = x["vernacular"]
        v = (f"vern {vs['changed']:.0%}/{vs['predicted']:.0%}" if vs["changed"] is not None
             and vs["predicted"] is not None else "vern -")
        subs = " ".join(f"{k}:{a}/{b}" for k, (a, b) in x["strong_subs"][:4])
        print(f"{x['kind']:11} {x['part']:5} {x['group']:12} {x['change']:13} "
              f"changed {x['show']:3} kept {x['keep']:3} both {x['both']:2}  {v:16} {subs}")
        print(f"{'':11} e.g. {''.join(x['examples'])}")
    (DERIVED / "yue_triage.json").write_text(json.dumps(results, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--top", type=int, default=40)
    ap.add_argument("--min-common", type=int, default=6)
    args = ap.parse_args()
    main(args.top, args.min_common)
