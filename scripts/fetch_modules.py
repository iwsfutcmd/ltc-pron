"""Fetch Wiktionary Lua modules into modules/, mirroring their titles.

Module:ltc-pron/predict -> modules/ltc-pron/predict.lua

Usage: uv run scripts/fetch_modules.py [extra module titles...]
"""

import sys
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MODULES = ROOT / "modules"
UA = "ltc-pron-analysis/0.1"

DEFAULT = [
    "Module:ltc-pron",
    "Module:ltc-pron/predict",
    "Module:ltc-pron/data",
    "Module:ltc-pron/baxter",
    "Module:zh-pron",
]


def module_path(title: str) -> Path:
    name = title.removeprefix("Module:")
    return MODULES / f"{name}.lua"


def fetch(title: str) -> None:
    url = "https://en.wiktionary.org/w/index.php?" + urllib.parse.urlencode(
        {"title": title, "action": "raw"}
    )
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req) as resp:
        text = resp.read().decode("utf-8")
    path = module_path(title)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    print(f"{title} -> {path.relative_to(ROOT)} ({len(text.splitlines())} lines)")


if __name__ == "__main__":
    for title in DEFAULT + sys.argv[1:]:
        fetch(title)
