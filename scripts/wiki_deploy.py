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
import html
import os
import shutil
import subprocess
import sys
import tempfile
import webbrowser
from pathlib import Path
from string import Template
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
            coll = 'title="colloquial"' in out
            print(f"  {page}: table OK" + (", with colloquial forms" if coll else ", literary only"))


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


def edit_url(title: str, summary: str | None = None) -> str:
    url = f"https://en.wiktionary.org/w/index.php?title={quote(title, safe=':/')}&action=edit"
    return url + (f"&summary={quote(summary, safe='')}" if summary else "")


def view_url(title: str) -> str:
    return f"https://en.wiktionary.org/wiki/{quote(title, safe=':/')}"


DEPLOY_PAGE = Template('''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Deploy ltc-pron to Wiktionary</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500&family=IBM+Plex+Sans:wght@400;500;600&display=swap" rel="stylesheet">
<style>
/* Layout: one narrow column of numbered steps; each step is a card with its two actions. */
:root {
  color-scheme: light;
  --paper: #f7f8f9; --surface: #ffffff; --ink: #15181d; --ink-2: #4a505a;
  --muted: #737983; --rule: #dfe2e6; --accent: #3348a8; --accent-ink: #ffffff;
  --done: #006300; --code-bg: #f0f2f4;
  --font-body: "IBM Plex Sans", system-ui, -apple-system, "Segoe UI", sans-serif;
  --font-mono: "IBM Plex Mono", ui-monospace, Menlo, monospace;
}
@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) {
    color-scheme: dark;
    --paper: #0f1114; --surface: #15171b; --ink: #e9ebee; --ink-2: #b4b9c2;
    --muted: #8a909a; --rule: #2a2e35; --accent: #6d84e0; --accent-ink: #0f1114;
    --done: #0ca30c; --code-bg: #1b1e23;
  }
}
:root[data-theme="dark"] {
  color-scheme: dark;
  --paper: #0f1114; --surface: #15171b; --ink: #e9ebee; --ink-2: #b4b9c2;
  --muted: #8a909a; --rule: #2a2e35; --accent: #6d84e0; --accent-ink: #0f1114;
  --done: #0ca30c; --code-bg: #1b1e23;
}
* { box-sizing: border-box; }
body { margin: 0; background: var(--paper); color: var(--ink); font-family: var(--font-body); font-size: 16px; line-height: 1.55; }
main { max-width: 760px; margin: 0 auto; padding: 40px 20px 72px; }
h1 { font-size: 1.7rem; font-weight: 600; margin: 0; text-wrap: balance; }
.lede { color: var(--ink-2); margin: 10px 0 0; }
code { font-family: var(--font-mono); font-size: 0.88em; background: var(--code-bg); padding: 1px 5px; border-radius: 4px; }
a { color: var(--accent); text-underline-offset: 2px; }
:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; border-radius: 4px; }
ol.steps { list-style: none; padding: 0; margin: 28px 0 0; display: grid; gap: 14px; counter-reset: step; }
ol.steps > li { counter-increment: step; background: var(--surface); border: 1px solid var(--rule); border-radius: 10px; padding: 18px 20px; display: grid; grid-template-columns: 34px 1fr; gap: 0 14px; }
ol.steps > li::before { content: counter(step); width: 28px; height: 28px; border-radius: 50%; border: 1px solid var(--rule); display: grid; place-items: center; font-family: var(--font-mono); font-size: 0.85rem; font-weight: 500; }
.title { font-family: var(--font-mono); font-size: 0.95rem; font-weight: 500; word-break: break-all; }
.meta { color: var(--muted); font-size: 0.85rem; margin-top: 2px; }
.actions { display: flex; flex-wrap: wrap; gap: 10px; margin-top: 14px; align-items: center; }
.btn { font: inherit; font-size: 0.92rem; font-weight: 500; border-radius: 6px; padding: 7px 14px; cursor: pointer; text-decoration: none; display: inline-flex; align-items: center; gap: 6px; }
.btn.primary { background: var(--accent); color: var(--accent-ink); border: 1px solid var(--accent); }
.btn.secondary { background: transparent; color: var(--ink); border: 1px solid var(--rule); }
.btn.secondary:hover { border-color: var(--ink-2); }
.status { font-size: 0.85rem; color: var(--done); min-height: 1.2em; }
.status.warn { color: var(--ink-2); }
details { margin-top: 12px; }
summary { cursor: pointer; color: var(--ink-2); font-size: 0.88rem; }
textarea { width: 100%; height: 260px; margin-top: 8px; font-family: var(--font-mono); font-size: 0.78rem; line-height: 1.5; background: var(--code-bg); color: var(--ink); border: 1px solid var(--rule); border-radius: 6px; padding: 10px 12px; resize: vertical; }
.final { margin-top: 22px; padding: 16px 20px; border-left: 3px solid var(--accent); background: var(--surface); border-radius: 0 10px 10px 0; }
.final p { margin: 6px 0 0; color: var(--ink-2); font-size: 0.92rem; }
.summary-line { margin-top: 18px; font-size: 0.88rem; color: var(--ink-2); }
@media (prefers-reduced-motion: reduce) { * { transition: none !important; } }
</style>
</head>
<body>
<main>
  <h1>Deploy ltc-pron to Wiktionary</h1>
  <p class="lede">Userspace copies for <b>$user</b>, built from <a href="$commit_url">$commit_label</a>. For each page in order: copy its contents, open its edit page, replace the whole edit box with what you copied, and save. The edit summary is already filled in.</p>
  <ol class="steps">
$steps
  </ol>
  <div class="final">
    <a class="btn primary" href="$test_url">Open the test page</a>
    <p>It renders the Middle Chinese table for $test_pages, each under a heading that links to the live entry.</p>
  </div>
  <p class="summary-line">Edit summary used: <code>$summary</code></p>
</main>
<script>
document.querySelectorAll("[data-copy]").forEach(function (button) {
  button.addEventListener("click", function () {
    var step = button.closest("li");
    var area = step.querySelector("textarea");
    var status = step.querySelector(".status");
    function copied() {
      status.className = "status";
      status.textContent = "Copied " + area.value.split("\\n").length + " lines";
    }
    function fallback() {
      step.querySelector("details").open = true;
      area.focus();
      area.select();
      status.className = "status warn";
      status.textContent = "Clipboard blocked: the text is selected below, press Ctrl+C";
    }
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(area.value).then(copied, fallback);
    } else {
      fallback();
    }
  });
});
</script>
</body>
</html>
''')

DEPLOY_STEP = Template('''    <li>
      <div>
        <div class="title">$title</div>
        <div class="meta">$lines lines · <code>$file</code></div>
        <div class="actions">
          <button class="btn primary" type="button" data-copy>Copy contents</button>
          <a class="btn secondary" href="$edit_url">Open edit page</a>
          <span class="status" aria-live="polite"></span>
        </div>
        <details>
          <summary>Show contents</summary>
          <textarea id="src-$n" readonly aria-label="Contents of $title">
$text</textarea>
        </details>
      </div>
    </li>''')


def deploy_page(user: str, built: dict[str, str], names: dict[str, str], summary: str,
                commit_url: str, pages: list[str]) -> str:
    steps = "\n".join(
        DEPLOY_STEP.substitute(
            n=i, title=html.escape(title), lines=text.count("\n") + 1,
            file=f"build/userspace/{names[title]}", edit_url=html.escape(edit_url(title, summary)),
            text=html.escape(text),
        )
        for i, (title, text) in enumerate(built.items(), 1)
    )
    return DEPLOY_PAGE.substitute(
        user=html.escape(user), steps=steps, summary=html.escape(summary),
        commit_url=html.escape(commit_url), commit_label=html.escape(commit_url.rsplit("/", 1)[-1]),
        test_url=html.escape(view_url(f"User:{user}/ltc-pron")),
        test_pages=html.escape(" ".join(pages)),
    )


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
    commit_url = ver.split(" ", 1)[0]
    (BUILD / "index.html").write_text(deploy_page(user, built, names, summary, commit_url, args.pages))

    if args.upload:
        password = os.environ.get("WIKTIONARY_BOT_PASSWORD")
        if not bot_user or not password:
            sys.exit("set WIKTIONARY_BOT_USER and WIKTIONARY_BOT_PASSWORD (see Special:BotPasswords)")
        wiki = Wiki(bot_user, password)
        for title, text in built.items():
            print(f"  {title}: {wiki.save(title, text, summary)}")
        print(f"Test page: https://en.wiktionary.org/wiki/User:{user}/ltc-pron")
        return

    print(f"\nDeploy page with copy buttons and edit links: {BUILD / 'index.html'}")
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
