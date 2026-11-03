"""Find predicted Cantonese syllables that do not exist in the language.

Builds the inventory of attested toneless syllables (character pages and
word tokens), then lists literary and colloquial predictions whose syllable
is attested fewer than RARE times, grouped by syllable, with the MC
categories behind them and what is attested instead. A prediction outside
the inventory is wrong by construction, and a cluster of them usually marks
a missing phonotactic condition (見 + -yut gives kyut, never *gyut).

Usage: uv run python scripts/yue_phonotactics.py [--rare 3] [--top 30]
"""

import argparse
from collections import Counter, defaultdict

from ltcpron.chars import load_chars
from ltcpron.predict import LtcPron
from ltcpron.words import load_tokens


def main(rare: int, top: int):
    p = LtcPron()
    chars = load_chars()
    tokens = load_tokens()

    inventory = Counter()
    for c in chars.values():
        for y in {y.base for y in c.yue}:
            inventory[y[:-1]] += 1
    for ts in tokens.values():
        for t in ts:
            inventory[t.reading.base[:-1]] += 1

    found = {"literary": defaultdict(list), "colloquial": defaultdict(list)}
    for c in chars.values():
        for r in c.mc:
            cat = p.categories(r)
            for layer, form in (("literary", p.yue(cat)), ("colloquial", p.yue_coll(cat))):
                if form and inventory[form[:-1]] < rare:
                    found[layer][form[:-1]].append((c.char, r[:6], sorted({y.base for y in c.yue})))

    for layer, by_syll in found.items():
        n = sum(map(len, by_syll.values()))
        print(f"\n{layer.capitalize()} predictions with a syllable attested fewer than {rare} times: "
              f"{n} readings, {len(by_syll)} syllables")
        for syll, xs in sorted(by_syll.items(), key=lambda kv: -len(kv[1]))[:top]:
            mc = Counter(x[1][:5] for x in xs).most_common(3)
            instead = Counter(a[:-1] for x in xs for a in x[2]).most_common(3)
            print(f"  {syll:8} ×{len(xs):3} (attested {inventory[syll]})  MC {mc}  "
                  f"attested instead {instead}  e.g. {''.join(x[0] for x in xs[:8])}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--rare", type=int, default=3)
    ap.add_argument("--top", type=int, default=30)
    args = ap.parse_args()
    main(args.rare, args.top)
