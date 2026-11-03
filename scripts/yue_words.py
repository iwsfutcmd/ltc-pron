"""Word-level evidence for colloquial layers.

For each colloquial rule in predict_yue_coll, and each candidate rule not
yet implemented, compares the words that use the literary form of a
character with the words that use the rule's form: how many there are,
and what share are vernacular (Cantonese reading but no Mandarin one).
A colloquial layer should show a higher vernacular share for its form.

Writes data/derived/yue_words.json.

Usage: uv run python scripts/yue_words.py
"""

import json
import re
from collections import defaultdict
from pathlib import Path

from ltcpron.chars import load_chars
from ltcpron.predict import LtcPron
from ltcpron.words import load_tokens

OUT = Path(__file__).resolve().parent.parent / "data" / "derived"
JYUTPING = re.compile(r"^(gw|kw|ng|[bpmfdtnlgkhwzcsj])?([a-z]+)([1-6])$")

FULLY_VOICED = {3, 7, 11, 15, 17, 20, 22, 25, 27, 30, 33}
GENG_2 = {109, 110, 113, 114, 117, 118, 119, 120}
GENG_34 = {111, 115, 121, 123, 125, 127}


def split_jp(s):
    m = JYUTPING.match(s)
    return (m.group(1) or "", m.group(2), m.group(3)) if m else None


def implemented_rule(cat) -> str | None:
    """Which predict_yue_coll rule(s) produce the colloquial form."""
    parts = []
    if cat.final in GENG_2:
        parts.append("梗二 -aang/-aak")
    if cat.final in GENG_34:
        parts.append("梗三四 -eng/-ek")
    if cat.tone == 2 and cat.initial in FULLY_VOICED:
        parts.append("全濁上 aspirate + 5")
    if cat.final == 15 and cat.initial == 16:
        parts.append("脂心 -ei")
    return " + ".join(parts) or None


def rhyme_swap(old, new, tone_map=None):
    def f(o, rh, t):
        if rh != old:
            return None
        return o + new + (tone_map or {}).get(t, t)
    return f


def onset_swap(old, new):
    return lambda o, rh, t: new + rh + t if o == old else None


# Candidate rules not (yet) in predict_yue_coll: eligibility on MC categories,
# and a transform on the literary prediction's (onset, rhyme, tone).
CANDIDATES = {
    "德 -ak → -aak": (lambda c: c.final == 131, rhyme_swap("ak", "aak")),
    "緝 -ap → -aap": (lambda c: c.final in (141, 142), rhyme_swap("ap", "aap", {"1": "3"})),
    "怗 -ip → -aap": (lambda c: c.final == 158, rhyme_swap("ip", "aap")),
    "咍 -oi → -aai": (lambda c: c.final == 41, rhyme_swap("oi", "aai")),
    "豪 -ou → -aau": (lambda c: c.final == 89, rhyme_swap("ou", "aau")),
    "蕭宵 -iu → -eu": (lambda c: c.final in (91, 92, 93), rhyme_swap("iu", "eu")),
    "歌戈 -o → -oe": (lambda c: c.final in (94, 95), rhyme_swap("o", "oe")),
    "日 j- → n-": (lambda c: c.initial == 38, onset_swap("j", "n")),
    "疑 j- → ng-": (lambda c: c.initial == 31, onset_swap("j", "ng")),
}


def main():
    p = LtcPron()
    chars = load_chars()
    tokens = load_tokens()

    all_tokens = [t for ts in tokens.values() for t in ts]
    base_share = sum(t.vernacular for t in all_tokens) / len(all_tokens)
    print(f"Tokens: {len(all_tokens)}; vernacular share overall {base_share:.1%}\n")

    # group -> char -> {"lit": [tokens], "rule": [tokens]}
    groups = defaultdict(lambda: defaultdict(lambda: {"lit": [], "rule": []}))
    page_attested = defaultdict(set)  # group -> chars attesting the rule form on their own page
    for c in chars.values():
        if not c.mc:
            continue
        page = {y.base for y in c.yue}
        lit_forms = set()
        rule_forms = defaultdict(set)
        for r in c.mc:
            cat = p.categories(r)
            lit = p.yue(cat)
            lit_forms.add(lit)
            coll = p.yue_coll(cat)
            if coll:
                rule_forms[implemented_rule(cat)].add(coll)
            parts = split_jp(lit)
            for name, (eligible, transform) in CANDIDATES.items():
                if parts and eligible(cat):
                    form = transform(*parts)
                    if form and form != lit:
                        rule_forms["candidate: " + name].add(form)
        for group, forms in rule_forms.items():
            forms -= lit_forms
            if not forms:
                continue
            if forms & page:
                page_attested[group].add(c.char)
            for t in tokens.get(c.char, []):
                if t.reading.base in forms:
                    groups[group][c.char]["rule"].append(t)
                elif t.reading.base in lit_forms:
                    groups[group][c.char]["lit"].append(t)

    def share(ts):
        return sum(t.vernacular for t in ts) / len(ts) if ts else None

    report = {"base_share": base_share, "groups": {}}
    header = (f"{'rule':30} {'page':>5} {'chars':>6} {'only':>5} {'both':>5} "
              f"{'lit tok':>8} {'vern':>6} {'rule tok':>9} {'vern':>6}  {'per-char >/<':>12}")
    print(header)
    for group in sorted(groups, key=lambda g: (g.startswith("candidate"), g)):
        per_char = groups[group]
        lit = [t for d in per_char.values() for t in d["lit"]]
        rule = [t for d in per_char.values() for t in d["rule"]]
        with_rule = [ch for ch, d in per_char.items() if d["rule"]]
        only = [ch for ch in with_rule if not per_char[ch]["lit"]]
        both = [ch for ch in with_rule if per_char[ch]["lit"]]
        higher = sum(share(per_char[ch]["rule"]) > share(per_char[ch]["lit"]) for ch in both)
        lower = sum(share(per_char[ch]["rule"]) < share(per_char[ch]["lit"]) for ch in both)
        vern_words = sorted({t.word for t in rule if t.vernacular}, key=len)[:12]
        ls, rs = share(lit), share(rule)
        print(f"{group:30} {len(page_attested[group]):5} {len(with_rule):6} {len(only):5} {len(both):5} "
              f"{len(lit):8} {(f'{ls:.1%}' if ls is not None else '-'):>6} {len(rule):9} "
              f"{(f'{rs:.1%}' if rs is not None else '-'):>6}  {higher:>5}/{lower:<5}")
        print(f"{'':30} e.g. {' '.join(vern_words)}")
        report["groups"][group] = {
            "page_attested": len(page_attested[group]), "chars_in_words": len(with_rule),
            "rule_only_chars": len(only), "both_chars": len(both),
            "lit_tokens": len(lit), "lit_vernacular": ls,
            "rule_tokens": len(rule), "rule_vernacular": rs,
            "per_char_higher": higher, "per_char_lower": lower,
            "rule_only_examples": only[:20], "vernacular_words": vern_words,
        }

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "yue_words.json").write_text(json.dumps(report, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
