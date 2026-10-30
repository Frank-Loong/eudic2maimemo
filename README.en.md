# eudic2maimemo

Look words up in Eudic, review them in MaiMemo. This handles the copying in between.

[中文](README.md)

[![CI](https://github.com/Frank-Loong/eudic2maimemo/actions/workflows/ci.yml/badge.svg)](https://github.com/Frank-Loong/eudic2maimemo/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

Start at step 1 for a fresh setup. Already configured and troubleshooting? Jump to **Troubleshooting**. No GitHub? See **Running without GitHub**.

## What it does

Eudic is good at looking words up: swap in a dictionary, trust the definitions. MaiMemo is good at scheduling reviews. Each keeps its own wordbook and the two don't talk, so anything you look up has to be retyped into MaiMemo, and nobody keeps that up.

Below, the Eudic side is called the *wordbook* and the MaiMemo side the *notepad*.

This closes the gap. It reads the Eudic wordbook, drops whatever the notepad already contains, and appends the rest grouped by the day it was added. Once it runs, you leave it alone.

The mechanics: fetch the Eudic wordbook, compare against the notepad, write back only the new entries, grouped by date in UTC+8. A full rebuild pages forward to the 5100-entry ceiling, then backwards to pick up the newest stretch, and takes the union, so a large wordbook doesn't lose recent words.

What it supports:

- Full import and daily incremental, which writes new words only
- Several wordbooks at once, merged and deduplicated
- Union of both paging directions for full syncs, past the per-direction cap
- Regex filters for phrases, Chinese terms and other entries MaiMemo can't turn into cards
- Push notifications on new words or failures
- A self-check command for config and coverage
- GitHub Actions, a long-running service, Docker, or systemd

## Before you start

You need:

- A Eudic account
- A MaiMemo account with the phone app installed
- A GitHub account, which holds the scheduled job

Everything is configured in the browser; nothing to install; about ten minutes for the first setup.

## Step 1 — get your Eudic authorization

1. Open https://my.eudic.net/OpenAPI/Authorization
2. Log in; you are returned to the same page
3. The page shows a string starting with `NIS ` — this is the Authorization value
4. Copy it in full, keeping `NIS` and the space after it

Keep it somewhere handy for step 4. If you aren't redirected back, reopen the link.

## Step 2 — get your MaiMemo token

Use the phone app. Tokens from the web page expire after seven days.

1. Open MaiMemo
2. Me → More settings → Experimental features → Open API
3. Copy the 64-character string

## Step 3 — fork the repo

Fork the repository into your own account; the scheduled job runs from that copy.

Make it private: Settings → Danger Zone → Change visibility → Make private. GitHub disables scheduled workflows in public repositories after 60 days without a commit; private repositories are exempt.

## Step 4 — add two secrets

1. In your fork, click **Settings**
2. Left sidebar: **Secrets and variables** → **Actions**
3. Click **New repository secret**
4. Name `EUDIC_API_KEY`, value from step 1
5. Click **Add secret**
6. Repeat: name `MOMO_API_KEY`, value from step 2

Names are case-sensitive and must match exactly. A typo shows up later as "missing secret".

Leave `MOMO_NOTEPAD_ID` for now.

## Step 5 — find your notepad id

MaiMemo can hold several cloud notepads. The tool needs to know which one.

1. Click **Actions**
2. Click **Doctor** in the left list
3. Click **Run workflow** on the right, then the green **Run workflow** button
4. Wait about thirty seconds, refresh, open the newest run
5. The **Summary** section lists every notepad, each ending with a long `np-...` id

Copy the id of the notepad you want. Go back to step 4 and add it as `MOMO_NOTEPAD_ID`.

No notepads at all? Create an empty one in the MaiMemo app first, then run Doctor again.

## Step 6 — first sync

1. **Actions** → click **Sync**
2. **Run workflow** → pick **full** → green button
3. Wait a minute or two. A green check means it worked
4. Open that notepad in MaiMemo. Your words should be there, grouped by date

Use `full` the first time so the whole history lands. The daily runs afterwards are incremental.

## Step 7 — ongoing operation

It runs daily at 22:30 UTC (06:30 Beijing). You only get a message when new words were added, assuming you set up notifications.

To change the time, edit `cron: "30 22 * * *"` in `.github/workflows/sync.yml`. It's UTC, eight hours behind Beijing.

## Troubleshooting

| Symptom | Cause | Action |
|---|---|---|
| Run marked as failed | a step errored | open the run, expand **Sync**, read the failing line |
| 401 in the log | token invalid or expired | regenerate it in the app, update the secret |
| 403 in the log | Eudic rate limit (30 per minute) | wait about an hour; avoid repeated retries |
| Missing secret message | secret name mismatch | compare character by character with step 4 |
| Notepad unchanged | no new entries in Eudic | expected |
| Entry present but MaiMemo won't study it | not in MaiMemo's dictionary | expected for phrases, acronyms and Chinese |

## Notifications (optional)

Results can be pushed to any endpoint that accepts GET or POST. WeCom is tested; DingTalk and Server Chan use the same request shape and should work as written, but haven't been verified one by one.

**WeCom group bot**: group settings → group bot → add → copy the webhook URL, then add two secrets:

| Variable | Value |
|---|---|
| `NOTIFY_URL` | `https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=YOUR_KEY` |
| `NOTIFY_BODY` | `{"msgtype":"text","text":{"content":"{content}"}}` |

DingTalk takes the same POST JSON, so `NOTIFY_BODY` is identical. If the bot uses signed requests, you'll need the signed URL instead.

**Server Chan** uses GET with `{content}` in the URL:

```dotenv
NOTIFY_URL=https://sctapi.ftqq.com/YOUR_KEY.send?title=words&desp={content}
```

Delivery: a summary when new words are written, the error reason on failure, silence otherwise unless `NOTIFY_ALWAYS` is set.

The message is a single summary line:

```text
已写入｜模式=incremental · 欧路匹配 12 · 新增 12 · 云词本共 6076 词 / 391 段 · 请求 3 次
```

A failed delivery never affects the sync; it only adds a warning to the log.

## Running without GitHub

Four options, all reading the same configuration: environment variables, or a `.env` file next to the program.

**1. One-off run.** Python 3.10 or newer.

```bash
pip install -r requirements.txt
cp .env.example .env                     # fill in the three required values
python -m eudic2maimemo doctor           # verify the configuration
python -m eudic2maimemo sync --full      # first import
python -m eudic2maimemo sync             # incremental afterwards
```

**2. Long-running service.** The program loops internally, so no external scheduler is involved.

```bash
python -m eudic2maimemo serve --interval 24
```

With systemd: copy `deploy/eudic2maimemo.service` to `/etc/systemd/system/`, adjust the working directory and user, then `systemctl daemon-reload && systemctl enable --now eudic2maimemo`.

**3. Docker.**

```bash
docker compose up -d                                   # uses .env, runs serve every 24 hours
docker compose run --rm eudic2maimemo sync --full      # one-off full import
```

The image is built locally; `docker compose up` handles it, or run `docker build -t eudic2maimemo .`.

**4. Prebuilt binary with a system scheduler.** Download the file for your platform from Releases, unpack it, and place a `.env` alongside it (or use environment variables).

cron on Linux and macOS:

```bash
0 7 * * * cd /opt/eudic2maimemo && ./eudic2maimemo sync
```

On Windows, Task Scheduler: create a basic task, trigger daily, action "Start a program", program = full path to `eudic2maimemo.exe`, arguments `sync`, start in = the program's directory.

Which to pick: use the first for debugging or a one-time import; prefer the second for unattended operation, since the interval is managed by the program and the log stays continuous; the third when you already run containers; the fourth when you'd rather not install Python.

## Configuration

Configuration comes from environment variables, or a `.env` file next to the program. On GitHub Actions, put keys in Secrets and non-sensitive options in Variables.

| Variable | Default | Notes |
|---|---|---|
| `EUDIC_API_KEY` | required | Starts with `NIS `; the token alone also works |
| `EUDIC_CATEGORY_ID` | `0` | Wordbook id, comma-separated for several |
| `EUDIC_LANGUAGE` | `en` | `en` Eudic, `fr` French, `de` German, `es` Spanish |
| `MOMO_API_KEY` | required | MaiMemo Open API token |
| `MOMO_NOTEPAD_ID` | required | Target notepad, `np-` prefixed |
| `IGNORE_PATTERNS` | empty | Regex filters, separated by `;` or newline |
| `MIN_STAR` | `0` | Skip entries below this rating; `0` means no limit |
| `EUDIC_ROUTES` | empty | Wordbook-to-notepad mapping |
| `KEEP_ORPHANS` | `0` | Keep hand-added entries on rebuild |
| `SYNC_INTERVAL_HOURS` | `24` | Interval for `serve` |
| `NOTIFY_URL` | empty | Notification endpoint |
| `NOTIFY_BODY` | empty | Request body template |
| `NOTIFY_ALWAYS` | `0` | Notify every run; default is only when new words appear |
| `MOMO_NOTEPAD_TITLE` | `欧路生词` | Used only when the notepad title is empty; existing titles are never overwritten |
| `MOMO_NOTEPAD_BRIEF` | `来自欧路词典的生词` | Same, for the description |

### Filtering out entries

MaiMemo only creates cards for entries in its own dictionary. Phrases, Chinese terms and proper nouns go in and do nothing. Filter them out with regex:

```dotenv
# skip phrases containing spaces, and anything with Chinese characters
IGNORE_PATTERNS=^\S*\s\S*$;[一-龥]
```

Or pass it ad hoc: `sync --ignore '\s'`. Separate patterns with a semicolon or newline; a match on any of them skips the entry.

### Splitting wordbooks across notepads

```dotenv
EUDIC_ROUTES=0=np-aaaa;133716565810649835=np-bbbb
```

Left is the wordbook id, right the notepad id. Wordbooks not listed still go to `MOMO_NOTEPAD_ID`. Existing notepad titles are preserved.

### Syncing only high-rated entries

```dotenv
MIN_STAR=4
```

Skipped counts are reported separately. `sync --min-star N` overrides it for one run.

### Keeping hand-added entries on rebuild

```dotenv
KEEP_ORPHANS=1
```

Entries in the notepad that Eudic doesn't have are collected into a trailing section instead of being dropped. Same as `sync --keep-orphans`.

### Waiting out a rate limit

```bash
python -m eudic2maimemo sync --wait-on-limit 3600
```

Eudic locks you out for about an hour; this sleeps and retries once. Meant for `serve` on your own machine. GitHub Actions caps jobs at 15 minutes, so don't use it there.

## Commands

| Command | Purpose |
|---|---|
| `sync` | Incremental, new words only |
| `sync --full` | Rebuild the notepad from Eudic |
| `sync --dry-run` | Preview, write nothing |
| `serve` | Run continuously at a fixed interval |
| `doctor` | Check config, list wordbooks and notepads |
| `doctor --deep` | Page through everything, report gaps |
| `doctor --dict` | Check which entries exist in MaiMemo's dictionary |
| `stats` | Wordbook breakdown: stars, gaps, recent months |
| `export` | Dump the wordbook; `--format` accepts `text`, `csv` or `json` |

Other flags are covered in their own sections: `--min-star`, `--keep-orphans`, `--wait-on-limit`, `--limit`, `--json`, `--quiet`.

## Limits

- 5100 entries per direction is an API cap; the union tops out near 10200, so very large wordbooks can't be fully covered
- MaiMemo replaces the notepad `content` wholesale, so every run sends the full text
- Deletions aren't synced
- `sync --full` drops entries the notepad has but Eudic doesn't unless `--keep-orphans` is set, and reports the count first; `--min-star` also applies during rebuilds
- Four languages only: English, French, German, Spanish

## Data safety

- Keys live only in your repo's Secrets, never in code or logs
- The program reads your Eudic wordbook and writes only the notepad you specified
- Nothing is deleted unless you run `--full`

## Development

```bash
pip install -r requirements.txt -r requirements-dev.txt
coverage run --source=eudic2maimemo -m unittest discover -s tests -t .
coverage report -m
```

137 tests; CI runs ruff and enforces an 80% coverage floor.

MIT
