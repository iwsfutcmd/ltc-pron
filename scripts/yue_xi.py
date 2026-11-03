"""The 溪 initial in Cantonese: where does k- survive, and what should predict_yue do?

Builds two variants of the working predict module, one where 溪 becomes h-
before every final (upstream) and one where it never does (keeps k-, kw-
when rounded), so each 溪 reading has both candidate forms. Then:

- the attested onsets of 溪 characters (single MC reading), all and common
- per final type: attested k/kw vs h/f, and whether the current module keeps k-
- possible conditioning: openness, division, tone, frequency, and register
  (vernacular share of words using the k- form vs the h- form)
- literary coverage under several policies for which finals keep k-
- where the k- comes from:
  - Taishanese (c-t=) vs Guangzhou onsets for the same characters
  - whether k- characters more often have a velar-stop phonetic component
  - k-/h- doublets within one character, and which form the vernacular words use
  - in 梗/德/怗 finals, whether k- pairs with the literary rhyme and h- with
    the colloquial one, as a literary/colloquial split would predict

Writes data/derived/yue_xi.json.

Usage: uv run python scripts/yue_xi.py
"""

import json
import re
import shutil
import tempfile
from collections import Counter, defaultdict
from pathlib import Path

from ltcpron.chars import EXTRACTED, load_chars
from ltcpron.lua import MODULES, Scribunto
from ltcpron.predict import LtcPron
from ltcpron.rules import colloquial_rules
from ltcpron.words import load_tokens

OUT = Path(__file__).resolve().parent.parent / "data" / "derived"
JYUTPING = re.compile(r"^(gw|kw|ng|[bpmfdtnlgkhwzcsj])?([a-z]+)([1-6])$")
XI = 29
TABLE = re.compile(r"(local debuccalisation_inducing_yue = \{)(.*?)(\n\})", re.S)
K_SET, H_SET = {"k", "kw"}, {"h", "f"}


def split_jp(s):
    m = JYUTPING.match(s)
    return (m.group(1) or "", m.group(2), m.group(3)) if m else None


def variant(tmp: Path, name: str, finals) -> LtcPron:
    """A copy of modules/ whose debuccalisation table lists exactly `finals`."""
    root = tmp / name
    shutil.copytree(MODULES, root)
    path = root / "ltc-pron" / "predict.lua"
    body = "".join(f"\n\t[{f}] = true," for f in sorted(finals))
    path.write_text(TABLE.sub(lambda m: m.group(1) + body + m.group(3), path.read_text(), count=1))
    return LtcPron(Scribunto(root))


def current_finals() -> set[int]:
    src = (MODULES / "ltc-pron" / "predict.lua").read_text()
    return {int(n) for n in re.findall(r"\[(\d+)\] = true", TABLE.search(src).group(2))}


def stop_or_h(syllable: str) -> str | None:
    """'k' for a k-/kw- syllable, 'h' for h-, f- and the glides h- gives (j-, w-, none)."""
    onset = re.match(r"^([^aeiouy]*)", syllable).group(1)
    if onset in K_SET:
        return "k"
    if onset in H_SET | {"j", "w", ""}:
        return "h"
    return None


def taishanese_readings() -> dict[str, set[str]]:
    out = defaultdict(set)
    with open(EXTRACTED / "zh-pron.jsonl") as f:
        for line in f:
            rec = json.loads(line)
            if len(rec["title"]) != 1:
                continue
            for t in rec["templates"]:
                for alt in (t.get("c-t") or "").split(","):
                    if re.fullmatch(r"[a-z]+[0-9]+", alt.strip()):
                        out[rec["title"]].add(alt.strip())
    return out


def phonetic_components() -> dict[str, set[str]]:
    out = {}
    with open(EXTRACTED / "han.jsonl") as f:
        for line in f:
            rec = json.loads(line)
            out[rec["char"]] = {
                comp.get(k[1:], "").strip()
                for comp in rec["compounds"] for k, v in comp.items()
                if re.fullmatch(r"c\d+", k) and v.strip() == "p" and len(comp.get(k[1:], "").strip()) == 1
            }
    return out


def origin_tests(p: LtcPron, chars, tokens) -> dict:
    """Evidence on where 溪 k- comes from."""
    single = [c for c in chars.values()
              if len(c.mc) == 1 and c.mc[0][0] == "溪" and c.yue]

    def gz_class(c):
        found = {stop_or_h(y.base) for y in c.yue} - {None}
        return next(iter(found)) if len(found) == 1 else None

    # Taishanese vs Guangzhou
    ts = taishanese_readings()
    tais = Counter()
    tais_ex = defaultdict(list)
    for c in single:
        g = gz_class(c)
        t = {stop_or_h(s) for s in ts.get(c.char, ())} - {None}
        if g and len(t) == 1:
            key = f"{g}/{next(iter(t))}"
            tais[key] += 1
            tais_ex[key].append(c.char)

    # Velar-stop phonetic component
    phon = phonetic_components()
    ph = {"k": [0, 0], "h": [0, 0]}
    ph_ex = {"k": [], "h": []}
    for c in single:
        g = gz_class(c)
        comps = [x for x in phon.get(c.char, ()) if x in chars and chars[x].yue]
        if not g or not comps:
            continue
        onsets = {re.match(r"^([^aeiou]*)", y.base).group(1) for x in comps for y in chars[x].yue}
        stop = bool(onsets & {"g", "gw", "k", "kw"})
        ph[g][0] += 1
        ph[g][1] += stop
        if stop and len(ph_ex[g]) < 8:
            ph_ex[g].append(f"{c.char}←{''.join(comps)}")

    # Doublets within characters whose readings are all 溪
    xi_only = [c for c in chars.values() if c.mc and c.yue and all(r[0] == "溪" for r in c.mc)]
    counts = Counter()
    doublets = []
    for c in xi_only:
        forms = defaultdict(set)
        for y in {y.base for y in c.yue}:
            cls = stop_or_h(y)
            if cls:
                forms[cls].add(y)
        if forms["k"] and forms["h"]:
            counts["both"] += 1
            side = {}
            for cls in "kh":
                ts_ = [t for t in tokens.get(c.char, []) if t.reading.base in forms[cls]]
                side[cls] = {"forms": sorted(forms[cls]), "words": len(ts_),
                             "vernacular": sum(t.vernacular for t in ts_),
                             "vernacular_words": sorted({t.word for t in ts_ if t.vernacular})[:3]}
            if side["k"]["words"] and side["h"]["words"]:
                sk = side["k"]["vernacular"] / side["k"]["words"]
                sh = side["h"]["vernacular"] / side["h"]["words"]
                verdict = "k" if sk > sh else "h" if sh > sk else "same"
                counts[f"more vernacular: {verdict}"] += 1
                doublets.append({"char": c.char, **side, "more_vernacular": verdict})
        elif forms["k"]:
            counts["k only"] += 1
        elif forms["h"]:
            counts["h only"] += 1

    # Layering: onset vs rhyme layer in finals with a colloquial rhyme rule
    layer = Counter()
    layer_ex = defaultdict(list)
    for c in chars.values():
        if not (c.mc and c.yue):
            continue
        for r in c.mc:
            if r[0] != "溪":
                continue
            cat = p.categories(r)
            if not ({"geng2", "geng34", "de", "tie"} & set(colloquial_rules(cat))):
                continue
            lit = split_jp(p.yue(cat))
            coll = split_jp(p.yue_coll(cat) or p.yue(cat))
            for y in {y.base for y in c.yue}:
                parts = split_jp(y)
                cls = stop_or_h(y)
                if not parts or not cls:
                    continue
                rhyme = ("literary" if parts[1] == lit[1]
                         else "colloquial" if parts[1] == coll[1] else None)
                if rhyme:
                    layer[f"{cls}/{rhyme}"] += 1
                    if len(layer_ex[f"{cls}/{rhyme}"]) < 10:
                        layer_ex[f"{cls}/{rhyme}"].append(f"{c.char} {y}")

    return {
        "taishanese": dict(tais), "taishanese_examples": {k: v[:12] for k, v in tais_ex.items()},
        "phonetic": ph, "phonetic_examples": ph_ex,
        "doublet_counts": dict(counts), "doublets": doublets,
        "layering": dict(layer), "layering_examples": dict(layer_ex),
    }


def onset_class(onset: str) -> str:
    if onset in K_SET:
        return "k/kw"
    if onset in H_SET:
        return "h/f"
    if onset in ("g", "gw"):
        return "g/gw"
    if onset in ("j", "w", ""):
        return "j/w/∅"
    return "other"


def main():
    p = LtcPron()
    chars = load_chars()
    tokens = load_tokens()
    words = Counter()
    for ts in tokens.values():
        for t in ts:
            words[t.word] += 0  # touch
    n_words = Counter({ch: len({t.word for t in ts}) for ch, ts in tokens.items()})
    kept_now = set(range(1, 161)) - current_finals()

    with tempfile.TemporaryDirectory() as tmp:
        ph = variant(Path(tmp), "h", range(1, 161))
        pk = variant(Path(tmp), "k", ())

        xi = []  # one row per 溪 reading of a character with Cantonese readings
        for c in chars.values():
            if not (c.mc and c.yue):
                continue
            for r in c.mc:
                if r[0] != "溪":
                    continue
                cat = p.categories(r)
                xi.append({"char": c.char, "reading": r, "final": cat.final, "tone": cat.tone,
                           "group": r[1:4] + ("入" if cat.tone == 4 else ""),
                           "h": ph.yue(cat), "k": pk.yue(cat)})

        # Literary coverage under a policy: which finals keep k-.
        base = {}
        for c in chars.values():
            if c.mc and c.yue:
                base[c.char] = {p.yue(p.categories(r)) for r in c.mc if r[0] != "溪"}

        def coverage(keep: set[int]) -> int:
            forms = {ch: set(f) for ch, f in base.items()}
            for x in xi:
                forms[x["char"]].add(x["k"] if x["final"] in keep else x["h"])
            return sum(len({y.base for y in chars[ch].yue} & f) for ch, f in forms.items())

        def full_coverage(pp: LtcPron) -> int:
            return sum(len({y.base for y in c.yue} & {pp.yue(pp.categories(r)) for r in c.mc})
                       for c in chars.values() if c.mc and c.yue)

        # The module's 溪 -> j- rule (尤, 侵, 緝: 丘 jau1, 欽 jam1, 泣 jap1) sits after the
        # h- test, so it only fires for finals missing from the debuccalisation list.
        j_finals = {136, 139, 140, 141, 142}
        j_cov = {
            "upstream + j- rule": full_coverage(variant(Path(tmp), "hj", set(range(1, 161)) - j_finals)),
            "current + j- rule": full_coverage(variant(Path(tmp), "cj", current_finals() - j_finals)),
        }

    single = [x for x in xi if len(chars[x["char"]].mc) == 1]
    print(f"溪 readings on characters with Cantonese readings: {len(xi)} "
          f"({len(single)} on single-reading characters)")

    # 1. Attested onsets, single-reading characters.
    dist = {"all": Counter(), "common": Counter()}
    for x in single:
        for y in {y.base for y in chars[x["char"]].yue}:
            parts = split_jp(y)
            if not parts:
                continue
            cls = onset_class(parts[0])
            dist["all"][cls] += 1
            if n_words[x["char"]] >= 3:
                dist["common"][cls] += 1
    for k, d in dist.items():
        total = sum(d.values())
        print(f"\nAttested onsets ({k}, {total}): " +
              ", ".join(f"{o} {n} ({n / total:.0%})" for o, n in d.most_common()))

    # 2. Per final type.
    per_final = defaultdict(lambda: {"k": [], "h": [], "group": ""})
    for x in single:
        f = per_final[x["final"]]
        f["group"] = x["group"]
        for y in {y.base for y in chars[x["char"]].yue}:
            parts = split_jp(y)
            if parts and parts[0] in K_SET:
                f["k"].append(x["char"])
            elif parts and parts[0] in H_SET:
                f["h"].append(x["char"])
    rows = []
    for final, f in per_final.items():
        rows.append({"final": final, "group": f["group"], "k": len(f["k"]), "h": len(f["h"]),
                     "k_ex": sorted(set(f["k"]), key=lambda ch: -n_words[ch])[:8],
                     "h_ex": sorted(set(f["h"]), key=lambda ch: -n_words[ch])[:8],
                     "kept": final in kept_now})
    rows.sort(key=lambda r: (-(r["k"] - r["h"]), -r["k"]))
    print("\nPer final (k/kw vs h/f, single-reading chars):")
    for r in rows:
        if r["k"] + r["h"] >= 3:
            print(f"  {r['final']:4} {r['group']:6} {'KEEP' if r['kept'] else '    '} "
                  f"k {r['k']:3}  h {r['h']:3}   {''.join(r['k_ex'])} / {''.join(r['h_ex'])}")

    # 3. Conditioning factors: share of k/kw among k/kw + h/f attestations.
    def factor(key):
        t = defaultdict(Counter)
        for x in single:
            for y in {y.base for y in chars[x["char"]].yue}:
                parts = split_jp(y)
                if parts and parts[0] in K_SET | H_SET:
                    t[key(x)]["k" if parts[0] in K_SET else "h"] += 1
        return {k: dict(v) for k, v in sorted(t.items())}
    factors = {
        "openness": factor(lambda x: x["reading"][3]),
        "division": factor(lambda x: x["reading"][2]),
        "tone": factor(lambda x: x["reading"][5]),
        "frequency": factor(lambda x: "common (3+ words)" if n_words[x["char"]] >= 3 else "rare"),
    }
    for name, t in factors.items():
        print(f"\nk share by {name}: " + ", ".join(
            f"{k} {v.get('k', 0)}/{v.get('k', 0) + v.get('h', 0)} "
            f"({v.get('k', 0) / max(1, v.get('k', 0) + v.get('h', 0)):.0%})" for k, v in t.items()))

    # 4. Register: vernacular share of words using the k- form vs the h- form.
    reg = {"k": [0, 0], "h": [0, 0]}
    reg_words = {"k": Counter(), "h": Counter()}
    for x in xi:
        if x["h"] == x["k"]:
            continue
        for t in tokens.get(x["char"], []):
            for side in ("k", "h"):
                if t.reading.base == x[side]:
                    reg[side][0] += 1
                    reg[side][1] += t.vernacular
                    if t.vernacular:
                        reg_words[side][t.word] += 1
    for side in ("k", "h"):
        n, v = reg[side]
        print(f"\nWords using the {side}- form: {n} tokens, {v / max(1, n):.1%} vernacular; "
              f"e.g. {' '.join(list(reg_words[side])[:10])}")

    # 5. Policies.
    finals_with_xi = {x["final"] for x in xi}
    best = set()
    for final in finals_with_xi:
        keep = coverage({final}) - coverage(set())
        if keep > 0:
            best.add(final)
    rounded = {x["final"] for x in xi if x["reading"][3] == "合"}
    rounded_unrounded_vowel = {x["final"] for x in xi if x["reading"][3] == "合"
                               and not split_jp(x["k"])[1].startswith(("u", "o"))}
    policies = {
        "upstream: h- before every final": set(),
        "current: k- before 14 finals": kept_now,
        "rounded finals keep kw-": rounded,
        "rounded finals keep kw- unless the rhyme is u/o": rounded_unrounded_vowel,
        "best per final (ceiling)": best,
        "k- before every final": set(range(1, 161)),
    }
    cov = {name: coverage(keep) for name, keep in policies.items()}
    cov.update(j_cov)
    print("\nLiterary coverage (attested readings matched):")
    for name, n in cov.items():
        print(f"  {name:48} {n}  ({n - cov['upstream: h- before every final']:+d} vs upstream)")

    origin = origin_tests(p, chars, tokens)
    print("\nWhere k- comes from:")
    print("  Guangzhou/Taishanese onsets:", origin["taishanese"])
    for cls in "kh":
        n, s = origin["phonetic"][cls]
        print(f"  Guangzhou {cls}- characters with a velar-stop phonetic: {s}/{n} ({s / max(1, n):.0%})")
    print("  doublets:", origin["doublet_counts"])
    print("  onset by rhyme layer:", origin["layering"])

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "yue_xi.json").write_text(json.dumps({
        "origin": origin,
        "dist": {k: dict(v) for k, v in dist.items()}, "per_final": rows, "factors": factors,
        "register": reg, "register_words": {k: list(v) for k, v in reg_words.items()},
        "coverage": cov, "best": sorted(best), "kept_now": sorted(kept_now),
        "n_readings": len(xi), "n_single": len(single),
    }, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
