"""Extract Chinese pronunciation data from an enwiktionary pages-articles dump.

Writes JSONL files to data/extracted/:
  ltc-pron.jsonl   {"char", "readings"|"alias"}   Module:zh/data/ltc-pron/<char>
  dial-pron.jsonl  {"char", "rows"|"alias"}       Module:zh/data/dial-pron/<char>
  zh-pron.jsonl    {"title", "templates"}         {{zh-pron}} calls in main namespace

Module data is evaluated in an empty Lua environment, so it can only build
tables, not touch globals, io or os.

Usage: uv run python -m ltcpron.dump data/dump/enwiktionary-latest-pages-articles.xml.bz2
"""

import bz2
import html
import json
import re
import sys
from pathlib import Path

from lupa import lua51

OUT = Path(__file__).resolve().parent.parent / "data" / "extracted"

LTC_PREFIX = "Module:zh/data/ltc-pron/"
DIAL_PREFIX = "Module:zh/data/dial-pron/"

_TITLE = re.compile(r"<title>(.*)</title>")
_NS = re.compile(r"<ns>(\d+)</ns>")


def iter_pages(path: Path):
    """Yield (ns, title, text) from a pages-articles dump, line by line."""
    title = ns = None
    buf: list[str] | None = None
    with bz2.open(path, "rt", encoding="utf-8") as f:
        for line in f:
            if buf is not None:
                end = line.find("</text>")
                if end >= 0:
                    buf.append(line[:end])
                    yield ns, title, html.unescape("".join(buf))
                    buf = None
                else:
                    buf.append(line)
                continue
            s = line.lstrip()
            if s.startswith("<title>"):
                title = html.unescape(_TITLE.search(s).group(1))
            elif s.startswith("<ns>"):
                ns = int(_NS.search(s).group(1))
            elif s.startswith("<text") and ns in (0, 828):
                if s.rstrip().endswith("/>"):
                    continue
                body = s[s.index(">") + 1:]
                end = body.find("</text>")
                if end >= 0:
                    yield ns, title, html.unescape(body[:end])
                else:
                    buf = [body]


class LuaData:
    """Evaluate `return {...}` data modules in an empty environment."""

    def __init__(self):
        self.lua = lua51.LuaRuntime()
        self._eval = self.lua.eval("""
            function(src)
                local chunk, err = loadstring(src)
                if not chunk then return nil, err end
                -- Alias modules are `return require [[Module:...]]`.
                setfenv(chunk, { require = function(name) return { __alias = name } end })
                local ok, val = pcall(chunk)
                if not ok then return nil, val end
                return val
            end
        """)

    def load(self, src: str):
        val = self._eval(src)
        if isinstance(val, tuple):
            val, err = val
            if val is None:
                raise ValueError(err)
        return self._to_py(val)

    def _to_py(self, v):
        if lua51.lua_type(v) == "table":
            keys = list(v.keys())
            if keys == list(range(1, len(keys) + 1)):
                return [self._to_py(v[k]) for k in keys]
            return {str(k): self._to_py(v[k]) for k in keys}
        return v


def template_calls(text: str, name: str):
    """Yield the raw bodies of every {{name ...}} call, braces balanced."""
    opener = re.compile(r"\{\{\s*" + re.escape(name) + r"\s*(?=[|}])")
    for m in opener.finditer(text):
        depth, i = 0, m.start()
        while i < len(text) - 1:
            pair = text[i:i + 2]
            if pair == "{{":
                depth += 1
                i += 2
            elif pair == "}}":
                depth -= 1
                i += 2
                if depth == 0:
                    yield text[m.end():i - 2]
                    break
            else:
                i += 1


def split_params(body: str) -> dict[str, str]:
    """Split a template body on top-level pipes into named/positional params."""
    parts, depth, cur, i = [], 0, [], 0
    while i < len(body):
        two = body[i:i + 2]
        if two in ("{{", "[["):
            depth += 1
            cur.append(two)
            i += 2
        elif two in ("}}", "]]"):
            depth -= 1
            cur.append(two)
            i += 2
        elif body[i] == "|" and depth == 0:
            parts.append("".join(cur))
            cur = []
            i += 1
        else:
            cur.append(body[i])
            i += 1
    parts.append("".join(cur))
    params, pos = {}, 0
    for p in parts[1:]:  # parts[0] is whatever followed the name, normally ""
        if "=" in p:
            k, v = p.split("=", 1)
            params[k.strip()] = v.strip()
        else:
            pos += 1
            params[str(pos)] = p.strip()
    return params


def main(dump: Path) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    lua = LuaData()
    counts = {"ltc-pron": 0, "dial-pron": 0, "zh-pron": 0, "errors": 0}
    names = ["ltc-pron.jsonl", "dial-pron.jsonl", "zh-pron.jsonl", "errors.jsonl"]
    # Write to .partial files and rename at the end, so readers never see
    # half-written output.
    partial = {n: OUT / f"{n}.partial" for n in names}
    with (open(partial["ltc-pron.jsonl"], "w") as ltc,
          open(partial["dial-pron.jsonl"], "w") as dial,
          open(partial["zh-pron.jsonl"], "w") as zh,
          open(partial["errors.jsonl"], "w") as errs):
        for ns, title, text in iter_pages(dump):
            if ns == 828 and title.startswith((LTC_PREFIX, DIAL_PREFIX)):
                is_ltc = title.startswith(LTC_PREFIX)
                char = title.removeprefix(LTC_PREFIX if is_ltc else DIAL_PREFIX)
                if "/" in char:  # documentation and the like
                    continue
                try:
                    val = lua.load(text)
                except Exception as e:
                    counts["errors"] += 1
                    errs.write(json.dumps({"title": title, "error": str(e)}, ensure_ascii=False) + "\n")
                    continue
                if isinstance(val, dict) and "__alias" in val:
                    alias = val["__alias"].removeprefix(LTC_PREFIX if is_ltc else DIAL_PREFIX)
                    (ltc if is_ltc else dial).write(
                        json.dumps({"char": char, "alias": alias}, ensure_ascii=False) + "\n")
                    counts["ltc-pron" if is_ltc else "dial-pron"] += 1
                elif is_ltc:
                    ltc.write(json.dumps({"char": char, "readings": val}, ensure_ascii=False) + "\n")
                    counts["ltc-pron"] += 1
                else:
                    dial.write(json.dumps({"char": char, "rows": val}, ensure_ascii=False) + "\n")
                    counts["dial-pron"] += 1
            elif ns == 0 and "zh-pron" in text:
                templates = [split_params(b) for b in template_calls(text, "zh-pron")]
                if templates:
                    zh.write(json.dumps({"title": title, "templates": templates}, ensure_ascii=False) + "\n")
                    counts["zh-pron"] += 1
    for n, p in partial.items():
        p.replace(OUT / n)
    print(counts)


if __name__ == "__main__":
    main(Path(sys.argv[1]))
