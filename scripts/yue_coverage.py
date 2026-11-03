"""How well does predict_yue (the literary system) cover attested Cantonese?

Usage: uv run python scripts/yue_coverage.py
"""

import re
from collections import Counter, defaultdict

from ltcpron.chars import load_chars
from ltcpron.predict import LtcPron

JYUTPING = re.compile(r"^(gw|kw|ng|[bpmfdtnlgkhwzcsj])?([a-z]+)([1-6])$")


def split_jp(s: str):
    m = JYUTPING.match(s)
    return (m.group(1) or "", m.group(2), m.group(3)) if m else None


def diff_kind(pred: str, att: str) -> str:
    p, a = split_jp(pred), split_jp(att)
    if not p or not a:
        return "unparsed"
    parts = [name for name, x, y in zip(("onset", "rhyme", "tone"), p, a) if x != y]
    return "+".join(parts) or "same"


def main():
    p = LtcPron()
    chars = load_chars()

    n = Counter()
    for c in chars.values():
        n["mc"] += bool(c.mc)
        n["yue"] += bool(c.yue)
        n["mc+yue"] += bool(c.mc and c.yue)
        n["labelled"] += bool(c.labels)
        n["mc+yue+labelled"] += bool(c.mc and c.yue and c.labels)
        n["gz dial-pron"] += bool(c.gz)
    print("Characters:")
    for k, v in n.items():
        print(f"  {k:18} {v:6}")

    # Exact and toneless coverage of attested readings by literary predictions.
    att_total = att_exact = att_toneless = 0
    label_hits = Counter()
    single = []  # (char, mc reading, categories, prediction, attested readings)
    errors = Counter()
    for c in chars.values():
        if not (c.mc and c.yue):
            continue
        preds = set()
        cats = []
        for r in c.mc:
            try:
                cat = p.categories(r)
            except Exception as e:
                errors[str(e)[:60]] += 1
                continue
            cats.append((r, cat))
            preds.add(p.yue(cat))
        if not preds:
            continue
        toneless = {x[:-1] for x in preds}
        for y in c.yue:
            att_total += 1
            att_exact += y.base in preds
            att_toneless += y.toneless in toneless
            label = c.labels.get(y.base) or (y.changed and c.labels.get(f"{y.base}-{y.changed}"))
            if label:
                label_hits[(label, y.base in preds)] += 1
        if len(cats) == 1:
            single.append((c.char, *cats[0], next(iter(preds)), c.yue))

    print(f"\nCategorisation errors: {sum(errors.values())}")
    for e, k in errors.most_common(5):
        print(f"  {k:5} {e}")

    print(f"\nAttested readings (chars with MC data): {att_total}")
    print(f"  equal to a literary prediction:     {att_exact:6} ({att_exact / att_total:.1%})")
    print(f"  same apart from tone:               {att_toneless:6} ({att_toneless / att_total:.1%})")

    print("\nc_note-labelled readings, by whether predict_yue produces them:")
    for label in ("literary", "colloquial"):
        hit, miss = label_hits[(label, True)], label_hits[(label, False)]
        print(f"  {label:10}  predicted {hit:5}   not predicted {miss:5}")

    # Single-MC-reading chars: what kind of mismatch, and where.
    kinds = Counter()
    by_group = defaultdict(Counter)
    for ch, r, cat, pred, yue in single:
        for y in yue:
            if y.base == pred:
                continue
            kind = diff_kind(pred, y.base)
            kinds[kind] += 1
            group = f"{r[1]}{r[2]}{r[3]} {r[5]}"  # final, division, openness, tone
            by_group[group][kind] += 1

    print(f"\nSingle-MC-reading chars: {len(single)}; unpredicted readings by mismatch:")
    for k, v in kinds.most_common():
        print(f"  {k:18} {v:5}")

    print("\nMC groups (final+division+openness tone) with most unpredicted readings:")
    for g, ks in sorted(by_group.items(), key=lambda kv: -sum(kv[1].values()))[:25]:
        print(f"  {g:10} {sum(ks.values()):4}  {dict(ks.most_common(3))}")


if __name__ == "__main__":
    main()
