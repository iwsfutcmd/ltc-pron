"""Compare predict_yue / predict_yue_coll in the working tree against a git revision.

Reports how many MC readings change prediction, and which attested
Cantonese readings are gained or lost, for the literary layer alone and for
literary + colloquial.

Usage: uv run python scripts/yue_compare.py [REV]   (default HEAD)
"""

import shutil
import subprocess
import sys
import tempfile
from collections import Counter
from pathlib import Path

from ltcpron.chars import load_chars
from ltcpron.lua import MODULES, Scribunto
from ltcpron.predict import LtcPron

ROOT = MODULES.parent


def modules_at(rev: str, tmp: Path) -> Path:
    """A copy of modules/ with every tracked module file as of rev."""
    out = tmp / "modules"
    shutil.copytree(MODULES, out)
    files = subprocess.run(["git", "ls-tree", "-r", "--name-only", rev, "modules"],
                           cwd=ROOT, capture_output=True, text=True, check=True).stdout.split()
    for f in files:
        src = subprocess.run(["git", "show", f"{rev}:{f}"], cwd=ROOT,
                             capture_output=True, check=True).stdout
        (tmp / f).write_bytes(src)
    return out


def predictions(p: LtcPron, chars):
    out = {}
    for c in chars:
        lit, coll = set(), set()
        for r in c.mc:
            cat = p.categories(r)
            lit.add(p.yue(cat))
            form = p.yue_coll(cat)
            if form:
                coll.add(form)
        out[c.char] = (lit, coll)
    return out


def main(rev: str):
    chars = [c for c in load_chars().values() if c.mc]
    with tempfile.TemporaryDirectory() as tmp:
        old_p = LtcPron(Scribunto(modules_at(rev, Path(tmp))))
        new_p = LtcPron()

        changed = []
        for c in chars:
            for r in c.mc:
                cat = new_p.categories(r)
                a, b = old_p.yue(cat), new_p.yue(cat)
                if a != b:
                    changed.append((c.char, r, a, b))
        old = predictions(old_p, [c for c in chars if c.yue])
        new = predictions(new_p, [c for c in chars if c.yue])

    print(f"MC readings with a changed literary prediction: {len(changed)}")
    transitions = Counter((a.rstrip("123456")[-3:], b.rstrip("123456")[-3:]) for *_, a, b in changed)
    print("  most common changes (end of syllable):",
          ", ".join(f"{a}→{b} ×{n}" for (a, b), n in transitions.most_common(6)))

    for label, idx in (("literary", (0,)), ("literary + colloquial", (0, 1))):
        gained, lost = [], []
        n_old = n_new = total = 0
        for c in chars:
            if not c.yue:
                continue
            o = set().union(*(old[c.char][i] for i in idx))
            n = set().union(*(new[c.char][i] for i in idx))
            for y in {y.base for y in c.yue}:
                total += 1
                n_old += y in o
                n_new += y in n
                if y in n and y not in o:
                    gained.append(f"{c.char}{y}")
                elif y in o and y not in n:
                    lost.append(f"{c.char}{y}")
        print(f"\n{label}: {n_old} → {n_new} of {total} attested "
              f"({n_old / total:.2%} → {n_new / total:.2%}); +{len(gained)} −{len(lost)}")
        print("  gained:", " ".join(gained[:40]) + (" …" if len(gained) > 40 else ""))
        print("  lost:  ", " ".join(lost[:40]) + (" …" if len(lost) > 40 else ""))


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "HEAD")
