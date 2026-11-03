"""Break down attested Cantonese readings that neither predict_yue nor
predict_yue_coll produces.

Each miss is classified as
  phonetic   matches (ignoring tone) a reading of the character's phonetic
             component ({{Han compound}} c?=p) or, failing that, of an IDS
             component: likely 有邊讀邊 or analogy
  otherwise  by which parts differ from the nearest prediction
             (onset / rhyme / tone)
and split by whether the character is common (appears in at least
COMMON_WORDS multi-character Wiktionary entries).

Non-phonetic misses are then tallied per part, keyed by the MC category
that conditions that part, to surface systematic gaps:
  onset  by MC initial          e.g. 溪 h -> k
  rhyme  by MC final/div/open   e.g. 庚二開 ak -> aak
  tone   by MC tone + voicing   e.g. 上 voiceless 2 -> 1

Writes data/derived/yue_misses.json.

Usage: uv run python scripts/yue_misses.py [--min-words N]
"""

import argparse
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

from ltcpron.chars import EXTRACTED, load_chars
from ltcpron.predict import LtcPron

OUT = Path(__file__).resolve().parent.parent / "data" / "derived"

JYUTPING = re.compile(r"^(gw|kw|ng|[bpmfdtnlgkhwzcsj])?([a-z]+)([1-6])$")
IDS_OPERATORS = re.compile(r"[⿰-⿿㇯？?]")

FULLY_VOICED = {3, 7, 11, 15, 17, 20, 22, 25, 27, 30, 33}
SONORANT = {4, 8, 12, 31, 35, 36, 37, 38}

PARTS = ("onset", "rhyme", "tone")


def split_jp(s):
    m = JYUTPING.match(s)
    return (m.group(1) or "", m.group(2), m.group(3)) if m else None


def voicing(initial: int) -> str:
    if initial in FULLY_VOICED:
        return "voiced"
    if initial in SONORANT:
        return "sonorant"
    return "voiceless"


def load_components():
    """char -> (phonetic components, IDS components)."""
    out = {}
    path = EXTRACTED / "han.jsonl"
    if not path.exists():
        return out
    with open(path) as f:
        for line in f:
            rec = json.loads(line)
            phon = set()
            for comp in rec["compounds"]:
                for k, v in comp.items():
                    if re.fullmatch(r"c\d+", k) and v.strip() == "p":
                        part = comp.get(k[1:], "").strip()
                        if len(part) == 1:
                            phon.add(part)
            ids = set()
            for s in rec["ids"]:
                ids.update(ch for ch in IDS_OPERATORS.sub("", s) if ch != rec["char"])
            out[rec["char"]] = (phon, ids)
    return out


def word_counts():
    """char -> number of multi-character zh-pron entries containing it."""
    n = Counter()
    with open(EXTRACTED / "zh-pron.jsonl") as f:
        for line in f:
            title = json.loads(line)["title"]
            if len(title) > 1:
                n.update(set(title))
    return n


def main(min_words: int):
    p = LtcPron()
    chars = load_chars()
    components = load_components()
    words = word_counts()

    def toneless_readings(ch):
        c = chars.get(ch)
        return {y.toneless for y in c.yue} if c else set()

    summary = Counter()
    by_class = defaultdict(Counter)       # class -> common/rare counts
    examples = defaultdict(list)
    gaps = {part: defaultdict(lambda: {"chars": set(), "common": set()}) for part in PARTS}
    population = {part: defaultdict(set) for part in PARTS}

    for c in chars.values():
        if not (c.mc and c.yue):
            continue
        preds = []  # (form, reading, categories, layer)
        for r in c.mc:
            cat = p.categories(r)
            preds.append((p.yue(cat), r, cat, "lit"))
            coll = p.yue_coll(cat)
            if coll:
                preds.append((coll, r, cat, "coll"))
            # populations for gap rates: characters whose readings fall in each key
            population["onset"][r[0]].add(c.char)
            population["rhyme"][r[1:4]].add(c.char)
            population["tone"][(r[5], voicing(cat.initial))].add(c.char)
        forms = {f for f, *_ in preds}
        common = words[c.char] >= min_words
        freq = "common" if common else "rare"

        # Same base reading with and without a changed tone counts once.
        for y in {y.base: y for y in c.yue}.values():
            summary["attested"] += 1
            if y.base in forms:
                summary["matched"] += 1
                continue
            summary["missed"] += 1
            summary[f"missed {freq}"] += 1

            phon, ids = components.get(c.char, (set(), set()))
            phon_hit = next((x for x in phon if y.toneless in toneless_readings(x)), None)
            ids_hit = None if phon_hit else next(
                (x for x in sorted(ids) if y.toneless in toneless_readings(x)), None)
            if phon_hit or ids_hit:
                cls = "phonetic (marked)" if phon_hit else "component (IDS)"
                by_class[cls][freq] += 1
                if len(examples[cls]) < 25 and common:
                    examples[cls].append(f"{c.char} {y.base} ← {phon_hit or ids_hit}")
                continue

            a = split_jp(y.base)
            if not a:
                by_class["unparsed"][freq] += 1
                continue
            best = None
            for form, r, cat, layer in preds:
                b = split_jp(form)
                if not b:
                    continue
                diff = tuple(part for part, x, z in zip(PARTS, b, a) if x != z)
                key = (len(diff), layer != "lit")
                if best is None or key < best[0]:
                    best = (key, diff, b, r, cat)
            if best is None:
                by_class["unparsed"][freq] += 1
                continue
            _, diff, b, r, cat = best
            cls = "+".join(diff)
            by_class[cls][freq] += 1
            if len(examples[cls]) < 25 and common:
                examples[cls].append(f"{c.char} {y.base} (pred {''.join(b)})")

            for part in diff:
                i = PARTS.index(part)
                change = f"{b[i] or '∅'} → {a[i] or '∅'}"
                group = {"onset": r[0], "rhyme": r[1:4],
                         "tone": (r[5], voicing(cat.initial))}[part]
                g = gaps[part][(group, change)]
                g["chars"].add(c.char)
                if common:
                    g["common"].add(c.char)

    total = summary["attested"]
    print(f"Attested readings: {total}; matched {summary['matched']}; missed {summary['missed']} "
          f"({summary['missed'] / total:.1%})")
    print(f"Common = in >= {min_words} multi-character entries. "
          f"Missed: common {summary['missed common']}, rare {summary['missed rare']}\n")

    print(f"{'class':22} {'common':>7} {'rare':>7} {'total':>7}")
    order = sorted(by_class, key=lambda k: -sum(by_class[k].values()))
    for cls in order:
        cc, rr = by_class[cls]["common"], by_class[cls]["rare"]
        print(f"{cls:22} {cc:7} {rr:7} {cc + rr:7}")

    print()
    for cls in order:
        if examples[cls]:
            print(f"{cls}: " + "  ".join(examples[cls][:12]))

    report = {"summary": dict(summary), "min_words": min_words,
              "classes": {k: dict(v) for k, v in by_class.items()},
              "examples": dict(examples), "gaps": {}}
    for part in PARTS:
        rows = []
        for (group, change), g in gaps[part].items():
            pop = population[part][group]
            rows.append({
                "group": group if isinstance(group, str) else " ".join(group),
                "change": change,
                "chars": len(g["chars"]), "common": len(g["common"]),
                "population": len(pop),
                "examples": sorted(g["common"] or g["chars"],
                                   key=lambda ch: -words[ch])[:12],
            })
        rows.sort(key=lambda row: (-row["common"], -row["chars"]))
        report["gaps"][part] = rows
        print(f"\nTop {part} gaps (chars with that change among common chars / all chars / chars in group)")
        for row in rows[:20]:
            print(f"  {row['group']:14} {row['change']:14} {row['common']:4} {row['chars']:5} "
                  f"{row['population']:6}   {''.join(row['examples'])}")

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "yue_misses.json").write_text(json.dumps(report, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--min-words", type=int, default=3)
    main(ap.parse_args().min_words)
