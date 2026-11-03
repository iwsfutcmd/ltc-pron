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

Before uploading, the built modules are run locally (via lupa) on the test
pages, so a broken build never reaches Wiktionary.

Credentials: create a bot password at Special:BotPasswords with the grants
"Edit existing pages" and "Create, edit, and move pages", then put it in
.env (gitignored) or the environment:

  WIKTIONARY_BOT_USER=YourName@ltc-pron
  WIKTIONARY_BOT_PASSWORD=...

Usage:
  uv run scripts/wiki_deploy.py --dry-run --user YourName   build + local check only
  uv run scripts/wiki_deploy.py                             build, check, upload
  uv run scripts/wiki_deploy.py --pages 生病 重 東           choose test pages
"""

import argparse
import os
import subprocess
import sys
import tempfile
from pathlib import Path

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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="build and check locally; no login or upload")
    ap.add_argument("--user", help="Wiktionary username (default: from WIKTIONARY_BOT_USER)")
    ap.add_argument("--pages", nargs="+", default=DEFAULT_PAGES, help="pages for the test page")
    args = ap.parse_args()

    load_env()
    bot_user = os.environ.get("WIKTIONARY_BOT_USER", "")
    user = args.user or bot_user.split("@", 1)[0]
    if not user:
        sys.exit("set WIKTIONARY_BOT_USER (in .env or the environment) or pass --user")

    ver = version()
    built = build(user)
    built[f"User:{user}/ltc-pron"] = test_page(user, args.pages, ver)

    BUILD.mkdir(parents=True, exist_ok=True)
    for title, text in built.items():
        ext = ".lua" if title.startswith("Module:") else ".wiki"
        (BUILD / (title.replace("/", "∕").replace(":", "꞉") + ext)).write_text(text)
    print(f"Built {len(built)} pages into {BUILD.relative_to(ROOT)}")

    print("Checking the built modules locally:")
    check_locally(user, built, args.pages)

    if args.dry_run:
        print("Dry run: nothing uploaded.")
        return

    password = os.environ.get("WIKTIONARY_BOT_PASSWORD")
    if not bot_user or not password:
        sys.exit("set WIKTIONARY_BOT_USER and WIKTIONARY_BOT_PASSWORD (see Special:BotPasswords)")
    wiki = Wiki(bot_user, password)
    summary = f"Sync from {ver}"
    for title, text in built.items():
        print(f"  {title}: {wiki.save(title, text, summary)}")
    print(f"Test page: https://en.wiktionary.org/wiki/User:{user}/ltc-pron")


if __name__ == "__main__":
    main()
