"""Render Module:ltc-pron's Middle Chinese table for a page, locally.

Runs export.ipa as {{zh-pron|mc=...}} does, with the page's characters'
data modules loaded from the extracted dump, and prints the table as text:
one line per row, cells separated by " | ". Use --wikitext for the raw
output.

Usage: uv run python scripts/ltc_table.py 生 重 [--wikitext]
"""

import argparse
import json
import re

from ltcpron.chars import EXTRACTED
from ltcpron.lua import Scribunto


def load_data_modules() -> dict[str, list[str]]:
    out, aliases = {}, {}
    with open(EXTRACTED / "ltc-pron.jsonl") as f:
        for line in f:
            rec = json.loads(line)
            if len(rec["char"]) != 1:
                continue
            if "alias" in rec:
                aliases[rec["char"]] = rec["alias"]
            else:
                out[rec["char"]] = rec["readings"]
    for ch, target in aliases.items():
        if target in out:
            out[ch] = out[target]
    return out


def plain(cell: str) -> str:
    cell = re.sub(r"\[\[(?:[^|\]]*\|)?([^\]]*)\]\]", r"\1", cell)
    cell = re.sub(r"<br\s*/?>", " ", cell)
    return re.sub(r"<[^>]+>", "", cell).strip()


def as_text(wikitext: str) -> str:
    lines = []
    for chunk in wikitext.split("\n|-\n")[1:]:
        chunk = chunk.removesuffix("\n|}")
        parts = re.split(r'\n\| style="[^"]*"\|', chunk)
        label = plain(parts[0].split("|", 1)[1])
        cells = [plain(c) for c in parts[1:]]
        lines.append(f"{label:32} {' | '.join(cells)}" if cells else f"== {label}")
    return "\n".join(lines)


def main(pages, wikitext):
    rt = Scribunto()
    data = load_data_modules()
    lua = rt.lua
    preload = lua.globals().package.preload
    for page in pages:
        for ch in page:
            if ch in data:
                preload[f"Module:zh/data/ltc-pron/{ch}"] = lua.eval(
                    "function(t) return function() return t end end")(lua.table_from(data[ch]))
        lua.globals().package.loaded["Module:headword/data"] = lua.table_from({"pagename": page})
    pron = rt.require("Module:ltc-pron")
    for page in pages:
        lua.globals().package.loaded["Module:headword/data"] = lua.table_from({"pagename": page})
        out = pron.ipa("y", page)
        print(f"\n# {page}")
        print(out if wikitext else as_text(out))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("pages", nargs="+")
    ap.add_argument("--wikitext", action="store_true")
    args = ap.parse_args()
    main(args.pages, args.wikitext)
