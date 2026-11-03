"""How many more attested Cantonese readings does predict_yue_coll explain?

Compares coverage of attested c= readings by the literary predictions alone
with coverage by literary + colloquial, overall and per colloquial rule.
Writes a JSON summary to data/derived/yue_coll_coverage.json.

Usage: uv run python scripts/yue_coll_coverage.py
"""

import json
from collections import Counter, defaultdict
from pathlib import Path

from ltcpron.chars import load_chars
from ltcpron.predict import LtcPron
from ltcpron.rules import COLLOQUIAL_RULES as RULES
from ltcpron.rules import colloquial_rules as rules_for

OUT = Path(__file__).resolve().parent.parent / "data" / "derived"


def main():
    p = LtcPron()
    chars = load_chars()

    n = Counter()
    gained_by_rule = Counter()
    predicted_by_rule = Counter()
    attested_by_rule = Counter()
    examples = defaultdict(list)
    labelled = Counter()
    chars_fully = Counter()

    for c in chars.values():
        if not (c.mc and c.yue):
            continue
        lit, coll = {}, {}
        for r in c.mc:
            cat = p.categories(r)
            lit[p.yue(cat)] = cat
            form = p.yue_coll(cat)
            if form:
                coll[form] = cat
        att = {y.base for y in c.yue}

        n["chars"] += 1
        chars_fully["lit"] += att <= set(lit)
        chars_fully["lit+coll"] += att <= set(lit) | set(coll)

        for form, cat in coll.items():
            key = "+".join(rules_for(cat))
            predicted_by_rule[key] += 1
            if form in att:
                attested_by_rule[key] += 1

        for a in att:
            n["attested"] += 1
            in_lit, in_coll = a in lit, a in coll
            n["lit"] += in_lit
            n["lit+coll"] += in_lit or in_coll
            if in_coll and not in_lit:
                key = "+".join(rules_for(coll[a]))
                gained_by_rule[key] += 1
                if len(examples[key]) < 30:
                    lit_forms = [f for f, cat in lit.items() if cat == coll[a]]
                    examples[key].append(f"{c.char} {a}" + (f" ({lit_forms[0]})" if lit_forms else ""))
            label = c.labels.get(a)
            if label:
                labelled[(label, "lit" if in_lit else "coll" if in_coll else "none")] += 1

    total = n["attested"]
    print(f"Chars with MC + Cantonese readings: {n['chars']}")
    print(f"Attested readings: {total}")
    print(f"  matched by literary:              {n['lit']:6} ({n['lit'] / total:.1%})")
    print(f"  matched by literary + colloquial: {n['lit+coll']:6} ({n['lit+coll'] / total:.1%})")
    print(f"  gain:                             {n['lit+coll'] - n['lit']:6} "
          f"(+{(n['lit+coll'] - n['lit']) / total:.1%} points, "
          f"+{(n['lit+coll'] - n['lit']) / n['lit']:.1%} relative)")
    print(f"Chars with every reading explained: literary {chars_fully['lit']}, "
          f"literary + colloquial {chars_fully['lit+coll']}")

    print("\nBy rule:    gained   predicted  attested  (share of colloquial predictions attested)")
    for key in sorted(predicted_by_rule, key=lambda k: -gained_by_rule[k]):
        name = " + ".join(RULES[k] for k in key.split("+"))
        pred, attd = predicted_by_rule[key], attested_by_rule[key]
        print(f"  {name:42} {gained_by_rule[key]:5} {pred:8} {attd:8}  ({attd / pred:.0%})")

    print("\nc_note-labelled readings, matched by:")
    for label in ("literary", "colloquial"):
        row = {k: labelled[(label, k)] for k in ("lit", "coll", "none")}
        print(f"  {label:10} {row}")

    print()
    for key, ex in examples.items():
        print(key, ": ", " ".join(ex[:15]))

    OUT.mkdir(parents=True, exist_ok=True)
    summary = {
        "chars": n["chars"], "attested": total,
        "matched_lit": n["lit"], "matched_lit_coll": n["lit+coll"],
        "chars_fully_lit": chars_fully["lit"], "chars_fully_lit_coll": chars_fully["lit+coll"],
        "by_rule": {
            key: {"gained": gained_by_rule[key], "predicted": predicted_by_rule[key],
                  "attested": attested_by_rule[key], "examples": examples[key]}
            for key in predicted_by_rule
        },
        "labelled": {f"{l}/{k}": v for (l, k), v in labelled.items()},
    }
    (OUT / "yue_coll_coverage.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
