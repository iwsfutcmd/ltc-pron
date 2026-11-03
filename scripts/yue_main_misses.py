"""Main readings of common characters that neither layer predicts.

A character is common if it appears in at least MIN_WORDS Wiktionary words
with an aligned Cantonese reading; its main reading is the one used in the
most of those words. Each missed main reading is put in the first category
that fits:

  changed tone     right syllable, tone 1 or 2 instead of the predicted
                   tone: 變音 in familiar words (貓 maau1)
  other tone       right syllable, another tone
  analogy          copies a reading of the phonetic or an IDS component
                   whose MC initial and final differ from the character's
  sporadic onset   only the onset differs, by a known word-by-word
                   alternation: aspiration (g/k, b/p, d/t, z/c), 溪 k-/h-,
                   s-/c-, n-/l-, ng-/none
  suspect MC data  Mandarin disagrees too: no Mandarin reading matches,
                   ignoring tone, the Mandarin predicted from any listed MC
                   reading, so the listed MC reading may be wrong or missing
  residual         the rest, tallied by MC category and change

Writes data/derived/yue_main_misses.json.

Usage: uv run python scripts/yue_main_misses.py [--min-words 3]
"""

import argparse
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

from ltcpron.chars import load_chars, load_components
from ltcpron.cmn import mandarin_readings, toneless
from ltcpron.predict import LtcPron
from ltcpron.words import load_tokens

OUT = Path(__file__).resolve().parent.parent / "data" / "derived"
JYUTPING = re.compile(r"^(gw|kw|ng|[bpmfdtnlgkhwzcsj])?([a-z]+)([1-6])$")
PARTS = ("onset", "rhyme", "tone")
SPORADIC = {frozenset(p) for p in [
    ("g", "k"), ("gw", "kw"), ("b", "p"), ("d", "t"), ("z", "c"),
    ("h", "k"), ("f", "kw"), ("h", "kw"), ("s", "c"), ("n", "l"), ("ng", ""),
]}
CATEGORIES = ("changed tone", "other tone", "analogy", "sporadic onset", "suspect MC data", "residual")


def split_jp(s):
    m = JYUTPING.match(s)
    return (m.group(1) or "", m.group(2), m.group(3)) if m else None


def main(min_words: int):
    p = LtcPron()
    chars = load_chars()
    tokens = load_tokens()
    components = load_components()
    mandarin = mandarin_readings()

    def mc_keys(ch):
        c = chars.get(ch)
        return {r[:4] for r in c.mc} if c else set()

    def analogous(ch, tl, comp):
        c = chars.get(comp)
        return bool(c and tl in {y.toneless for y in c.yue} and not (mc_keys(ch) & mc_keys(comp)))

    n_common = matched = 0
    by_cat = defaultdict(list)
    residual = defaultdict(list)
    for c in chars.values():
        if not (c.mc and c.yue):
            continue
        uses = Counter()
        words = defaultdict(set)
        for t in tokens.get(c.char, []):
            uses[t.reading.base] += 1
            words[t.reading.base].add(t.word)
        if len({t.word for t in tokens.get(c.char, [])}) < min_words or not uses:
            continue
        n_common += 1
        main_reading = uses.most_common(1)[0][0]
        preds = []  # (form, reading, layer)
        for r in c.mc:
            cat = p.categories(r)
            preds.append((p.yue(cat), r, "literary"))
            if coll := p.yue_coll(cat):
                preds.append((coll, r, "colloquial"))
        if main_reading in {f for f, *_ in preds}:
            matched += 1
            continue

        a = split_jp(main_reading)
        if not a:
            continue
        # nearest prediction
        best = min(((sum(x != y for x, y in zip(split_jp(f), a)), f, r) for f, r, _ in preds if split_jp(f)),
                   key=lambda t: t[0])
        b = split_jp(best[1])
        diff = tuple(part for part, x, y in zip(PARTS, b, a) if x != y)
        rec = {"char": c.char, "main": main_reading, "words": len(words[main_reading]),
               "examples": sorted(words[main_reading], key=len)[:4],
               "nearest": best[1], "mc": best[2][:6], "diff": "+".join(diff),
               "all_mc": [r[:6] for r in c.mc], "attested": sorted({y.base for y in c.yue}),
               "mandarin": sorted(mandarin.get(c.char, ())),
               "mandarin_predicted": sorted({p.cmn(p.categories(r)) for r in c.mc})}

        phon, ids = components.get(c.char, (set(), set()))
        tl = main_reading[:-1]
        if diff == ("tone",):
            cat = "changed tone" if a[2] in "12" else "other tone"
        elif any(analogous(c.char, tl, x) for x in sorted(phon) or sorted(ids)):
            cat = "analogy"
        elif diff == ("onset",) and frozenset((b[0], a[0])) in SPORADIC:
            cat = "sporadic onset"
        elif rec["mandarin"] and not ({toneless(m) for m in rec["mandarin"]}
                                      & {toneless(m) for m in rec["mandarin_predicted"]}):
            cat = "suspect MC data"
        else:
            cat = "residual"
            change = " ".join(f"{x or '∅'}→{y or '∅'}" for part, x, y in zip(PARTS, b, a) if x != y)
            residual[(best[2][1:4] + ("入" if best[2][5] == "入" else ""), change)].append(c.char)
        by_cat[cat].append(rec)

    missed = n_common - matched
    print(f"Common characters (≥{min_words} words): {n_common}; main reading predicted {matched} "
          f"({matched / n_common:.1%}); missed {missed}\n")
    for cat in CATEGORIES:
        recs = sorted(by_cat[cat], key=lambda r: -r["words"])
        print(f"{cat:16} {len(recs):4} ({len(recs) / missed:.0%})  " +
              "  ".join(f"{r['char']} {r['main']} (pred {r['nearest']})" for r in recs[:8]))

    print("\nResidual, by MC category and change (2+ characters):")
    for (group, change), chs in sorted(residual.items(), key=lambda kv: -len(kv[1])):
        if len(chs) >= 2:
            print(f"  {group:8} {change:22} {len(chs):3}  {''.join(chs[:12])}")

    print("\nSuspect MC data, most-used first:")
    for r in sorted(by_cat["suspect MC data"], key=lambda r: -r["words"])[:25]:
        print(f"  {r['char']} MC {' / '.join(r['all_mc'])}  predicted {r['nearest']} / "
              f"{','.join(r['mandarin_predicted'])}  attested {r['main']} / {','.join(r['mandarin'])}  "
              f"({r['words']} words: {' '.join(r['examples'])})")

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "yue_main_misses.json").write_text(json.dumps({
        "min_words": min_words, "common": n_common, "matched": matched,
        "categories": {k: sorted(v, key=lambda r: -r["words"]) for k, v in by_cat.items()},
        "residual": [{"group": g, "change": ch, "chars": chs}
                     for (g, ch), chs in sorted(residual.items(), key=lambda kv: -len(kv[1]))],
    }, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--min-words", type=int, default=3)
    main(ap.parse_args().min_words)
