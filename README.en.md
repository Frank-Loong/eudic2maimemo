# eudic2maimemo

Look words up in Eudic, review them in MaiMemo. This handles the copying in between.

[中文](README.md)

[![CI](https://github.com/Frank-Loong/eudic2maimemo/actions/workflows/ci.yml/badge.svg)](https://github.com/Frank-Loong/eudic2maimemo/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

## What it does

Eudic is good at looking words up: swap in a dictionary, trust the definitions. MaiMemo is good at scheduling reviews. Each keeps its own wordbook and the two don't talk, so anything you look up has to be retyped into MaiMemo, and nobody keeps that up.

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

Any endpoint that accepts GET or POST works. WeCom, DingTalk and Server Chan are all verified.

| Variable | Required | Description |
|---|---|---|
| `NOTIFY_URL` | yes | webhook URL |
| `NOTIFY_BODY` | no | POST body template; `{content}` is replaced with the message. Omit it to send a GET with a `content` query parameter |
| `NOTIFY_ALWAYS` | no | set to `1` to be notified every run; by default only runs with new words notify |

Delivery: a summary when new words are written, the error reason on failure, silence otherwise.

**WeCom group bot**: group settings → group bot → add → copy the webhook URL.

| Variable | Value |
|---|---|
| `NOTIFY_URL` | `https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=YOUR_KEY` |
| `NOTIFY_BODY` | `{"msgtype":"text","text":{"content":"{content}"}}` |

DingTalk uses the same POST JSON shape, so `NOTIFY_BODY` is identical.

**Server Chan** uses GET with `{content}` in the URL:

```
NOTIFY_URL=https://sctapi.ftqq.com/YOUR_KEY.send?title=words&desp={content}
```

The message is one summary line:

```
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

## Commands

| Command | Purpose |
|---|---|
| `sync` | Incremental, new words only |
| `sync --full` | Rebuild the notepad from Eudic |
| `sync --dry-run` | Preview, write nothing |
| `doctor` | Check config, list wordbooks and notepads |
| `doctor --deep` | Page through everything, report gaps |
| `stats` | Wordbook breakdown: stars, gaps, recent months |
| `export --out words.csv --format csv` | Dump the full wordbook |

## Limits

- 5100 entries per direction is an API cap; union tops out near 10200
- MaiMemo only replaces the notepad `content` wholesale
- Deletions aren't synced
- `--full` drops words you added to the notepad by hand; it tells you how many first
- Eudic's four languages only: English, French, German, Spanish

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

107 tests, CI enforces an 80% coverage floor.

MIT
