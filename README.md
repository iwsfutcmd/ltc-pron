# ltc-pron

Analysis of modern reflexes of Middle Chinese using Wiktionary's
[Module:ltc-pron](https://en.wiktionary.org/wiki/Module:ltc-pron) and
[Module:ltc-pron/predict](https://en.wiktionary.org/wiki/Module:ltc-pron/predict),
run locally, and changes to them: a colloquial Cantonese layer
(`predict_yue_coll`) and fixes to the literary one. The write-up is in
[docs/predict-yue-colloquial.html](docs/predict-yue-colloquial.html).

## Setup

```sh
uv sync
```

`modules/` mirrors Wiktionary module titles (`Module:ltc-pron/predict` →
`modules/ltc-pron/predict.lua`). The first commit holds the unmodified upstream
modules, so `git diff 23f28e6 -- modules/` shows every change made here.
`scripts/fetch_modules.py` refreshes them from Wiktionary; it overwrites the
working copies, so commit first and use `git diff` to see what changed upstream.

The modules run under Lua 5.1 through [lupa](https://github.com/scoder/lupa)
with a small Python stand-in for the Scribunto `mw` library (`ltcpron/lua.py`).

## Data

```sh
mkdir -p data/dump
curl -L -o data/dump/enwiktionary-latest-pages-articles.xml.bz2 \
  https://dumps.wikimedia.org/enwiktionary/latest/enwiktionary-latest-pages-articles.xml.bz2
uv run python -m ltcpron.dump data/dump/enwiktionary-latest-pages-articles.xml.bz2
```

This writes `data/extracted/`: Middle Chinese readings, dial-pron data,
`{{zh-pron}}` parameters and character components (about 5 minutes).

## Scripts

| Script | What it does |
|---|---|
| `yue_coll_coverage.py` | attested Cantonese readings matched by each layer and rule |
| `yue_words.py` | vernacular share of words using literary vs colloquial forms |
| `yue_misses.py` | breakdown of attested readings neither layer predicts |
| `yue_stacking.py` | readings where two colloquial rules apply |
| `yue_compare.py [REV]` | working-tree modules vs a revision: readings gained and lost |
| `yue_tally.py` | attested outcomes for a slice of Middle Chinese |
| `ltc_table.py PAGE…` | renders the Middle Chinese table for a page locally |
| `wiki_deploy.py` | builds the modules for your Wiktionary userspace |

Run them with `uv run python scripts/<name>`.

## Testing live on Wiktionary

`scripts/wiki_deploy.py` builds userspace copies of the changed modules, to
paste into Wiktionary by hand:

- `Module:User:<you>/ltc-pron/predict`
- `Module:User:<you>/ltc-pron`, which requires the userspace predict and adds a
  `show` entry point: `{{#invoke:User:<you>/ltc-pron|show|生病}}`
- `User:<you>/ltc-pron`, a test page rendering the table for a list of pages

```sh
uv run scripts/wiki_deploy.py --user YourName
```

checks the built modules locally on the test pages, writes them to
`build/userspace/` (`1-predict.lua`, `2-ltc-pron.lua`, `3-test-page.wiki`) and
prints each page's edit link and the edit summary to use. Paste each file over
the whole edit box, in that order, and save. Add `--copy` to be walked through
them: each page's text goes to the clipboard and its edit page opens in the
browser, and Enter moves to the next. `--pages 生 重 …` chooses the test pages;
`WIKTIONARY_USER=YourName` in `.env` saves passing `--user`.

To save through the API instead, create a bot password at
[Special:BotPasswords](https://en.wiktionary.org/wiki/Special:BotPasswords)
(grants "Edit existing pages" and "Create, edit, and move pages"), put
`WIKTIONARY_BOT_USER=YourName@ltc-pron` and `WIKTIONARY_BOT_PASSWORD=...` in
`.env`, and add `--upload`.
