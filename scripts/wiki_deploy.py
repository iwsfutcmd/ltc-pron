"""Deploy the working modules to your Wiktionary userspace for live testing.

Builds userspace copies of the modules this repo changes:

  modules/ltc-pron/predict.lua -> Module:User:<you>/ltc-pron/predict
  modules/ltc-pron.lua         -> Module:User:<you>/ltc-pron
  (test page)                  -> User:<you>/ltc-pron

Module:ltc-pron/data and /baxter are unchanged, so the copies use the live
ones. Two edits are made to the userspace ltc-pron only: it requires the
userspace predict, and it gets a show() entry point, because ipa() takes
the page title from the page being viewed:

  {{#invoke:User:<you>/ltc-pron|show|生病}}      table for 生病, expanded
  {{#invoke:User:<you>/ltc-pron|show|重|2}}      only reading 2

The test page invokes show() for each test page, under a heading linking to
the live entry for comparison.

The built pages are run locally (via lupa) on the test pages first, so a
broken build never reaches Wiktionary. Then, by default, the script writes
them to build/userspace/ and prints each page's title, edit link and file,
for pasting by hand. Paste them in order: predict, ltc-pron, test page.

  uv run scripts/wiki_deploy.py --user YourName          build, check, list
  uv run scripts/wiki_deploy.py --user YourName --copy   also walk through them:
      each page's text goes to the clipboard and its edit page opens in the
      browser; paste over the whole edit box, save, press Enter for the next
  uv run scripts/wiki_deploy.py --user YourName --pages 生病 重 東

The username can also come from WIKTIONARY_USER in .env (gitignored).

--upload saves the pages through the API instead, with a bot password from
Special:BotPasswords (grants "Edit existing pages" and "Create, edit, and
move pages") in .env:

  WIKTIONARY_BOT_USER=YourName@ltc-pron
  WIKTIONARY_BOT_PASSWORD=...
"""

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
import webbrowser
from pathlib import Path
from urllib.parse import quote

import requests

from ltcpron.chars import load_chars
from ltcpron.lua import MODULES, Scribunto

ROOT = MODULES.parent
BUILD = ROOT / "build" / "userspace"
API = "https://en.wiktionary.org/w/api.php"
REPO = "https://github.com/iwsfutcmd/ltc-pron"
UA = f"ltc-pron-deploy/0.1 ({REPO})"

DEFAULT_PAGES = ["生病", "重", "白", "石", "黑", "疊", "四", "艇", "鄰", "區", "東"]

SHOW = '''
-- Userspace testing only, added by scripts/wiki_deploy.py: render the Middle
-- Chinese table for another page, expanded.
--   {{#invoke:User:USER/ltc-pron|show|生病}}
--   {{#invoke:User:USER/ltc-pron|show|重|2}}   (reading indices as in {{zh-pron|mc=}})
function export.show(frame)
	local page = mw.text.trim(frame.args[1] or "")
	local index = frame.args[2] or "y"
	export._pagename = page
	local preview = export.retrieve_pron(page, false, index, true) or ""
	local out = export.ipa(index, preview)
	export._pagename = nil
	return (out:gsub("mw%-collapsed", ""))
end
'''


def replace_once(src: str, old: str, new: str) -> str:
    n = src.count(old)
    if n != 1:
        sys.exit(f"build: expected exactly one {old!r} in modules/ltc-pron.lua, found {n}")
    return src.replace(old, new)


def build(user: str) -> dict[str, str]:
    """Page title -> content for everything to upload."""
    predict = (MODULES / "ltc-pron" / "predict.lua").read_text()

    pron = (MODULES / "ltc-pron.lua").read_text()
    pron = replace_once(pron, 'require("Module:ltc-pron/predict")',
                        f'require("Module:User:{user}/ltc-pron/predict")')
    pron = replace_once(pron, 'local titlechar = mw.loadData("Module:headword/data").pagename',
                        'local titlechar = export._pagename or mw.loadData("Module:headword/data").pagename')
    body, tail = pron.rstrip().rsplit("\n", 1)
    if tail != "return export":
        sys.exit("build: modules/ltc-pron.lua does not end with `return export`")
    pron = body + "\n" + SHOW.replace("USER", user) + "\nreturn export\n"

    return {
        f"Module:User:{user}/ltc-pron/predict": predict,
        f"Module:User:{user}/ltc-pron": pron,
    }


def test_page(user: str, pages: list[str], version: str) -> str:
    lines = [
        f"Live test of [[Module:User:{user}/ltc-pron]] and [[Module:User:{user}/ltc-pron/predict]], "
        f"synced from {version}. Each heading links to the live entry for comparison.",
        "",
    ]
    for page in pages:
        lines += [f"== [[{page}#Chinese|{page}]] ==", f"{{{{#invoke:User:{user}/ltc-pron|show|{page}}}}}", ""]
    return "\n".join(lines)


def check_locally(user: str, built: dict[str, str], pages: list[str]) -> None:
    """Run the built userspace modules on the test pages with lupa."""
    chars = load_chars()
    with tempfile.TemporaryDirectory() as tmp:
        for title, text in built.items():
            if not title.startswith("Module:"):
                continue
            path = Path(tmp) / f"{title.removeprefix('Module:')}.lua"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text)
        # live modules the userspace copy still requires
        for name in ("ltc-pron/data", "ltc-pron/baxter"):
            path = Path(tmp) / f"{name}.lua"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text((MODULES / f"{name}.lua").read_text())
        rt = Scribunto(Path(tmp))
        lua = rt.lua
        make_loader = lua.eval("function(t) return function() return t end end")
        for page in pages:
            for ch in page:
                if ch in chars and chars[ch].mc:
                    lua.globals().package.preload[f"Module:zh/data/ltc-pron/{ch}"] = \
                        make_loader(lua.table_from(chars[ch].mc))
        mod = rt.require(f"Module:User:{user}/ltc-pron")
        for page in pages:
            frame = lua.table_from({"args": lua.table_from([page])})
            out = mod.show(frame)
            if "Expected" not in out:
                sys.exit(f"local check: no table rendered for {page}")
            coll = "Colloquial" in out
            print(f"  {page}: table OK" + (", colloquial row" if coll else ", no colloquial row"))


def load_env() -> None:
    path = ROOT / ".env"
    if path.exists():
        for line in path.read_text().splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip("'\""))


def version() -> str:
    sha = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True,
                         text=True, check=True).stdout.strip()
    dirty = subprocess.run(["git", "status", "--porcelain", "modules"], cwd=ROOT,
                           capture_output=True, text=True, check=True).stdout.strip()
    return f"{REPO}/commit/{sha[:7]}" + (" plus uncommitted changes" if dirty else "")


class Wiki:
    def __init__(self, bot_user: str, password: str):
        self.s = requests.Session()
        self.s.headers["User-Agent"] = UA
        token = self.get(action="query", meta="tokens", type="login")["query"]["tokens"]["logintoken"]
        r = self.post(action="login", lgname=bot_user, lgpassword=password, lgtoken=token)
        if r["login"]["result"] != "Success":
            sys.exit(f"login failed: {r['login'].get('reason', r['login']['result'])}")
        self.csrf = self.get(action="query", meta="tokens")["query"]["tokens"]["csrftoken"]

    def get(self, **params):
        r = self.s.get(API, params={**params, "format": "json", "formatversion": "2"}, timeout=60)
        r.raise_for_status()
        return r.json()

    def post(self, **data):
        r = self.s.post(API, data={**data, "format": "json", "formatversion": "2"}, timeout=60)
        r.raise_for_status()
        return r.json()

    def current(self, title: str) -> str | None:
        page = self.get(action="query", prop="revisions", rvprop="content", rvslots="main",
                        titles=title)["query"]["pages"][0]
        if page.get("missing"):
            return None
        return page["revisions"][0]["slots"]["main"]["content"]

    def save(self, title: str, text: str, summary: str) -> str:
        if self.current(title) == text.rstrip("\n"):
            return "unchanged"
        # "assert" is a Python keyword, hence the dict
        r = self.post(action="edit", title=title, text=text, summary=summary,
                      token=self.csrf, **{"assert": "user"})
        if "error" in r:
            sys.exit(f"edit of {title} failed: {r['error'].get('info', r['error'])}")
        result = r["edit"]
        if result.get("result") != "Success":
            sys.exit(f"edit of {title} did not succeed: {result}")
        return "created" if result.get("new") else "updated"


CLIPBOARD_COMMANDS = [
    ["wl-copy"],
    ["xclip", "-selection", "clipboard"],
    ["xsel", "--clipboard", "--input"],
    ["pbcopy"],
]


def copy_to_clipboard(text: str) -> bool:
    for cmd in CLIPBOARD_COMMANDS:
        if shutil.which(cmd[0]):
            subprocess.run(cmd, input=text, text=True, check=True)
            return True
    return False


def edit_url(title: str) -> str:
    return f"https://en.wiktionary.org/w/index.php?title={quote(title, safe=':/')}&action=edit"


def file_names(built: dict[str, str]) -> dict[str, str]:
    """Title -> file name in build/userspace, numbered in paste order."""
    names = {}
    for i, title in enumerate(built, 1):
        if title.endswith("/predict"):
            names[title] = f"{i}-predict.lua"
        elif title.startswith("Module:"):
            names[title] = f"{i}-ltc-pron.lua"
        else:
            names[title] = f"{i}-test-page.wiki"
    return names


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--user", help="your Wiktionary username (default: WIKTIONARY_USER in .env)")
    ap.add_argument("--pages", nargs="+", default=DEFAULT_PAGES, help="pages for the test page")
    ap.add_argument("--copy", action="store_true",
                    help="copy each page to the clipboard and open its edit page, one at a time")
    ap.add_argument("--upload", action="store_true", help="save through the API with a bot password")
    args = ap.parse_args()

    load_env()
    bot_user = os.environ.get("WIKTIONARY_BOT_USER", "")
    user = args.user or os.environ.get("WIKTIONARY_USER") or bot_user.split("@", 1)[0]
    if not user:
        sys.exit("pass --user YourName, or set WIKTIONARY_USER in .env")

    ver = version()
    summary = f"Sync from {ver}"
    built = build(user)
    built[f"User:{user}/ltc-pron"] = test_page(user, args.pages, ver)

    print("Checking the built modules locally:")
    check_locally(user, built, args.pages)

    if BUILD.exists():
        shutil.rmtree(BUILD)
    BUILD.mkdir(parents=True)
    names = file_names(built)
    for title, text in built.items():
        (BUILD / names[title]).write_text(text)

    if args.upload:
        password = os.environ.get("WIKTIONARY_BOT_PASSWORD")
        if not bot_user or not password:
            sys.exit("set WIKTIONARY_BOT_USER and WIKTIONARY_BOT_PASSWORD (see Special:BotPasswords)")
        wiki = Wiki(bot_user, password)
        for title, text in built.items():
            print(f"  {title}: {wiki.save(title, text, summary)}")
        print(f"Test page: https://en.wiktionary.org/wiki/User:{user}/ltc-pron")
        return

    print(f"\nBuilt {len(built)} pages in {BUILD.relative_to(ROOT)}. Paste each over the whole")
    print(f"edit box, in this order, with the edit summary:\n  {summary}\n")
    for title in built:
        print(f"  {title}")
        print(f"    edit: {edit_url(title)}")
        print(f"    file: {(BUILD / names[title]).relative_to(ROOT)}")

    if args.copy:
        print()
        for i, (title, text) in enumerate(built.items(), 1):
            if not copy_to_clipboard(text):
                sys.exit("no clipboard tool found (wl-copy, xclip, xsel or pbcopy)")
            webbrowser.open(edit_url(title))
            input(f"[{i}/{len(built)}] {title} is on the clipboard and its edit page is open. "
                  "Paste, save, then press Enter… ")
    print(f"\nTest page: https://en.wiktionary.org/wiki/User:{user}/ltc-pron")


if __name__ == "__main__":
    main()
