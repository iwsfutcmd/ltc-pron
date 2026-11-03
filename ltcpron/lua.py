"""Run Wiktionary Scribunto modules locally under Lua 5.1 (via lupa).

Only the slice of the Scribunto API that the ltc-pron modules use is provided:
mw.ustring.{find,match,gsub,sub,len,char,codepoint}, mw.text.{split,gsplit},
mw.loadData, and "Module:string utilities" / "Module:load" stand-ins.
mw.ustring is implemented in Python, translating Lua patterns to `re`, so
that character classes like "[微泰廢]" match characters rather than bytes.
"""

import re
from functools import lru_cache
from pathlib import Path

from lupa import lua51

MODULES = Path(__file__).resolve().parent.parent / "modules"

# Lua %-classes -> regex, outside and inside [] sets.
_CLASSES = {
    "a": r"[^\W\d_]", "d": r"\d", "l": r"[a-z]", "u": r"[A-Z]",
    "s": r"\s", "w": r"[^\W_]", "x": r"[0-9A-Fa-f]", "p": r"[!-/:-@\[-`{-~]",
    "c": r"[\x00-\x1f\x7f]",
}
_SET_CLASSES = {
    "a": r"^\W\d_", "d": r"\d", "l": "a-z", "u": "A-Z", "s": r"\s",
    "w": r"^\W_", "x": "0-9A-Fa-f", "p": r"!-/:-@\[-`{-~", "c": r"\x00-\x1f\x7f",
}
_CLASSES.update({
    "A": r"[\W\d_]", "D": r"\D", "L": r"[^a-z]", "U": r"[^A-Z]", "S": r"\S",
    "W": r"[\W_]", "X": r"[^0-9A-Fa-f]", "P": r"[^!-/:-@\[-`{-~]",
    "C": r"[^\x00-\x1f\x7f]",
})


@lru_cache(maxsize=None)
def lua_pattern(pat: str) -> re.Pattern:
    """Translate a Lua pattern into a compiled Python regex (no %b, %f, ())."""
    out = []
    i, n = 0, len(pat)
    if pat.startswith("^"):
        out.append(r"\A")
        i = 1
    while i < n:
        c = pat[i]
        if c == "$" and i == n - 1:
            out.append(r"\Z")
            i += 1
            continue
        if c in "()":
            out.append(c)
            i += 1
            continue
        # single-character class
        if c == "%":
            d = pat[i + 1]
            if d in "bf":
                raise NotImplementedError(f"%{d} in Lua pattern {pat!r}")
            if d.isdigit():
                atom = "\\" + d
            else:
                atom = _CLASSES.get(d) or re.escape(d)
            i += 2
        elif c == "[":
            j = i + 1
            body = ""
            if j < n and pat[j] == "^":
                body += "^"
                j += 1
            if j < n and pat[j] == "]":
                body += r"\]"
                j += 1
            while pat[j] != "]":
                ch = pat[j]
                if ch == "%":
                    nxt = pat[j + 1]
                    body += _SET_CLASSES.get(nxt) or re.escape(nxt)
                    j += 2
                elif ch == "-" and body and pat[j + 1] != "]":
                    body += "-"
                    j += 1
                else:
                    body += re.escape(ch)
                    j += 1
            atom = "[" + body + "]"
            i = j + 1
        elif c == ".":
            atom = "."
            i += 1
        else:
            atom = re.escape(c)
            i += 1
        # quantifier
        if i < n and pat[i] in "*+-?":
            atom += {"*": "*", "+": "+", "-": "*?", "?": "?"}[pat[i]]
            i += 1
        out.append(atom)
    return re.compile("".join(out), re.DOTALL)


def _start(s: str, init) -> int:
    if init is None:
        return 0
    init = int(init)
    if init < 0:
        return max(len(s) + init, 0)
    return max(init - 1, 0)


def _lua_repl(repl: str):
    def expand(m: re.Match) -> str:
        def sub(mm: re.Match) -> str:
            k = mm.group(1)
            if k == "%":
                return "%"
            k = int(k)
            if k == 0 or m.re.groups == 0:
                return m.group(0)
            return m.group(k) or ""
        return re.sub(r"%([0-9%])", sub, repl)
    return expand


def _split(s: str, sep: str, plain=None) -> list[str]:
    """mw.text.split: an empty separator splits into characters."""
    if sep == "":
        return list(s)
    if plain:
        return s.split(sep)
    parts, last = [], 0
    for m in lua_pattern(sep).finditer(s):
        if m.end() == m.start():
            continue
        parts.append(s[last:m.start()])
        last = m.end()
    parts.append(s[last:])
    return parts


class Scribunto:
    """A Lua 5.1 runtime with enough of `mw` to load ltc-pron modules."""

    def __init__(self, modules_dir: Path = MODULES):
        self.modules_dir = modules_dir
        self.lua = lua51.LuaRuntime(unpack_returned_tuples=True)
        self._install_mw()

    # --- mw.ustring, in Python ---------------------------------------------

    def _ustring(self):
        lua = self.lua

        def captures(m: re.Match):
            return m.groups() if m.re.groups else (m.group(0),)

        def find(s, pattern, init=None, plain=None):
            start = _start(s, init)
            if plain:
                pos = s.find(pattern, start)
                return None if pos < 0 else (pos + 1, pos + len(pattern))
            m = lua_pattern(pattern).search(s, start)
            if not m:
                return None
            return (m.start() + 1, m.end()) + (m.groups() if m.re.groups else ())

        def match(s, pattern, init=None):
            m = lua_pattern(pattern).search(s, _start(s, init))
            return captures(m) if m else None

        def gsub(s, pattern, repl, n=None):
            rx = lua_pattern(pattern)
            if isinstance(repl, str):
                fn = _lua_repl(repl)
            else:
                lua_type = lua.globals().type(repl)

                def fn(m: re.Match) -> str:
                    key = captures(m)[0]
                    v = repl[key] if lua_type == "table" else repl(*captures(m))
                    return m.group(0) if v is None or v is False else str(v)
            out, count = rx.subn(fn, s, count=int(n) if n else 0)
            return out, count

        def sub(s, i=1, j=-1):
            n = len(s)
            i, j = int(i), int(j if j is not None else -1)
            if i < 0:
                i = max(n + i + 1, 1)
            elif i == 0:
                i = 1
            if j < 0:
                j = n + j + 1
            elif j > n:
                j = n
            return s[i - 1:j] if i <= j else ""

        def codepoint(s, i=1, j=None):
            chars = sub(s, i, i if j is None else j)
            return tuple(ord(c) for c in chars)

        def char(*cps):
            return "".join(chr(int(c)) for c in cps)

        return dict(find=find, match=match, gsub=gsub, sub=sub,
                    len=len, codepoint=codepoint, char=char,
                    upper=str.upper, lower=str.lower)

    def _install_mw(self):
        lua = self.lua
        g = lua.globals()
        g._py_ustring = lua.table_from(self._ustring())
        g._py_split = lambda s, sep, plain=None: lua.table_from(_split(s, sep, plain))
        g._py_module_path = self._module_path
        lua.execute(r"""
            local us = _py_ustring
            local ustring = {}
            for k, v in pairs(us) do ustring[k] = v end
            local text = {}
            function text.split(s, sep, plain) return _py_split(s, sep, plain) end
            function text.gsplit(s, sep, plain)
                local parts, i = _py_split(s, sep, plain), 0
                return function() i = i + 1; return parts[i] end
            end
            function text.trim(s) return (s:gsub("^%s+", ""):gsub("%s+$", "")) end
            mw = { ustring = ustring, text = text }
            function mw.loadData(name) return require(name) end

            -- Resolve "Module:Foo/bar" against modules/Foo/bar.lua.
            table.insert(package.loaders, 2, function(name)
                local path = _py_module_path(name)
                if not path then return nil end
                local chunk, err = loadfile(path)
                if not chunk then error(err) end
                return chunk
            end)

            package.preload["Module:string utilities"] = function()
                return {
                    codepoint = ustring.codepoint, gsub = ustring.gsub,
                    len = ustring.len, match = ustring.match,
                    find = ustring.find, sub = ustring.sub, char = ustring.char,
                }
            end
            package.preload["Module:load"] = function()
                return { safe_require = function(name)
                    local ok, m = pcall(require, name)
                    return ok and m or nil
                end }
            end
            -- Only used for display (pinyin tone marks); not needed here.
            package.preload["Module:cmn-pron"] = function()
                return { py_number_to_mark = function(s) return s end }
            end
        """)

    def _module_path(self, name: str):
        if not name.startswith("Module:"):
            return None
        path = self.modules_dir / f"{name.removeprefix('Module:')}.lua"
        return str(path) if path.exists() else None

    def require(self, name: str):
        return self.lua.globals().require(name)
