# 🤖 Automated Bot

> A production-ready Python automation project that sends a **daily weather + news digest email** via Gmail and **auto-syncs GitHub repositories** to a portfolio website — all powered by **GitHub Actions**.

---

## ✨ Features

| Feature | Description |
|---|---|
| 🌤️ **Weather Alerts** | Fetches live weather for Thiruvananthapuram via OpenWeatherMap API. Includes an alert banner if temp > 35°C or rain is predicted. |
| 📰 **News Digest** | Pulls top headlines from 3 RSS feeds: Manorama Online, The Hindu, and Mathrubhumi. |
| 📧 **One Combined Email** | Weather + news are bundled into a single beautiful HTML email sent every morning at 7:00 AM IST. |
| 🔄 **Portfolio Sync** | Fetches your public GitHub repos via the API, generates `projects.json`, and auto-pushes it to your portfolio site. |

---

## 📁 Project Structure

```
automated-email-bot/
│
├── bot.py               ← Daily email bot (weather + news)
├── sync_projects.py     ← GitHub repo sync → portfolio update
├── projects.json        ← Auto-generated list of your repos
├── requirements.txt     ← Python dependencies
├── README.md            ← This file
│
└── .github/
    └── workflows/
        ├── daily.yml          ← Sends the daily email at 7:00 AM IST
        └── sync-projects.yml  ← Syncs repos on push + midnight IST
```

---

## 🚀 Quick Start

### Step 1 — Clone the repo

```bash
git clone https://github.com/r4hulee/automated-email-bot.git
cd automated-email-bot
```

### Step 2 — Install dependencies locally

```bash
pip install -r requirements.txt
```

### Step 3 — Create a `.env` file for local testing

Create a file named `.env` in the project root. **Never commit this file to GitHub.**

```env
# OpenWeatherMap API key (get free at openweathermap.org)
OPENWEATHER_API_KEY=your_openweathermap_api_key_here

# Gmail App Password (NOT your Gmail login password)
APP_PASSWORD=xxxx xxxx xxxx xxxx

# Personal Access Token for pushing to your portfolio repo
PORTFOLIO_PAT=your_github_pat_here
```

> 💡 `.env` is already handled by `python-dotenv`. When running in GitHub Actions, these values come from **Secrets** instead.

### Step 4 — Test locally

```bash
# Test the daily email bot
python bot.py

# Test the portfolio sync
python sync_projects.py
```

---

## 🔐 GitHub Secrets Setup

> Go to: `GitHub → automated-email-bot repo → Settings → Secrets and variables → Actions → New repository secret`

Add these **4 secrets**:

| Secret Name | What It Is | Where to Get It |
|---|---|---|
| `OPENWEATHER_API_KEY` | OpenWeatherMap API key | [openweathermap.org/api](https://openweathermap.org/api) → sign up free |
| `APP_PASSWORD` | Gmail App Password (16 chars) | Google Account → Security → App Passwords |
| `PORTFOLIO_PAT` | GitHub Personal Access Token | See instructions below |

### How to get a Gmail App Password

1. Go to [myaccount.google.com](https://myaccount.google.com)
2. Click **Security** → enable **2-Step Verification** (required)
3. Search for **"App Passwords"**
4. Select app: **Mail**, device: **Other** (type "Automated Bot")
5. Copy the 16-character password → paste as `APP_PASSWORD` secret

### How to create a PORTFOLIO_PAT

1. Go to GitHub → Profile icon → **Settings**
2. Click **Developer settings** → **Personal access tokens** → **Fine-grained tokens**
3. Click **Generate new token**
4. Set name: `portfolio-sync`
5. **Repository access**: Only select `r4hulee/portfolio`
6. **Permissions** → **Contents** → **Read and write**
7. Click **Generate token** → copy it
8. Add it as secret `PORTFOLIO_PAT` in the **automated-email-bot** repo

---

## ⚙️ GitHub Actions Workflows

### `daily.yml` — Daily Email Digest

| Setting | Value |
|---|---|
| **Schedule** | Every day at 7:00 AM IST (1:30 AM UTC) |
| **Cron expression** | `30 1 * * *` |
| **What it runs** | `bot.py` |
| **Manual trigger** | Yes — go to Actions tab → "Run workflow" |

**Flow:**
```
GitHub Actions (cron) → checkout repo → install deps → run bot.py
  → fetch weather (OpenWeatherMap API)
  → fetch news (3 RSS feeds)
  → build HTML + plain email
  → send via Gmail SMTP
```

### `sync-projects.yml` — Portfolio Sync

| Setting | Value |
|---|---|
| **Triggers** | Push to `main` + daily at midnight IST |
| **Cron expression** | `30 18 * * *` |
| **What it runs** | `sync_projects.py` |
| **Manual trigger** | Yes |

**Flow:**
```
Push to main (or cron) → checkout repo → install deps → run sync_projects.py
  → fetch all public repos (GitHub API, paginated)
  → format: name, description, url, language, topics, homepage
  → sort by most recently updated
  → push projects.json to r4hulee/portfolio via GitHub Contents API
  → commit local copy of projects.json to this repo
```

---

## 🌐 Portfolio Integration

### How it works end-to-end

The portfolio sync connects three things together:

```
automated-email-bot            r4hulee/portfolio
─────────────────────          ──────────────────────────
sync_projects.py               projects.json   ←──── auto-updated by sync script
      │                        script.js       ←──── reads projects.json dynamically
      │  GitHub API (PUT)            │
      └──────────────────────────────┘
                                     │
                                     ↓
                              Portfolio website
                          (renders GitHub repos as cards)
```

**Step-by-step:**

1. **Trigger**: Every push to `main` in `automated-email-bot` OR every midnight IST via cron
2. **Fetch**: `sync_projects.py` calls `https://api.github.com/users/r4hulee/repos`
3. **Format**: Extracts `name`, `description`, `url`, `language`, `topics`, `homepage` from each public repo
4. **Sort**: Orders by `updated_at` — most recently active repos appear first
5. **Push**: Uses the GitHub Contents API (PUT request) to update `projects.json` in `r4hulee/portfolio`
6. **Render**: The portfolio's `script.js` fetches `./projects.json` on page load and renders each repo as a project card using the same card HTML structure and CSS classes
7. **Filter**: New cards use `data-category` derived from the repo's primary language (`Python → code`, `JavaScript → web`, etc.), so they integrate automatically with the existing filter buttons

### What the portfolio `script.js` does

The `script.js` in the portfolio repo includes a **Section 5** that:
- Fetches `./projects.json` using the browser's `fetch()` API
- Renders each project as an `<article class="card reveal">` with the same structure as hardcoded cards
- Skips repos that are already shown as hardcoded cards (by matching card title text)
- Re-registers new cards with the `IntersectionObserver` so scroll animations work
- Refreshes the filter system so filter buttons work on all cards (static + dynamic)

### To add a repo to the portfolio manually (optional)

If you want a specific repo to appear with custom content (like Figma embeds), just hardcode it in `index.html` with the same `<article class="card">` structure. The script will detect it by name and skip adding a duplicate from JSON.

---

## 📰 News RSS Feeds

| Source | Language | RSS URL |
|---|---|---|
| Manorama Online | Malayalam | `https://www.manoramaonline.com/news/kerala.rss` |
| The Hindu | English | `https://www.thehindu.com/feeder/default.rss` |
| Mathrubhumi | Malayalam | `https://www.mathrubhumi.com/polopoly_fs/rss/kerala.rss` |

> ⚠️ **Note**: RSS feed URLs can change when sites update. If a feed stops working, check the site's footer for their RSS link, or search `site:manoramaonline.com rss`.

---

## 🛠️ Troubleshooting

### Email not sending

| Symptom | Fix |
|---|---|
| `SMTPAuthenticationError` | Re-check `APP_PASSWORD` secret — must be the 16-char App Password, not Gmail password |
| Email sent but not received | Check spam/junk folder |
| `APP_PASSWORD is not set` | Add the secret in repo Settings → Secrets → Actions |

### Weather not working

| Symptom | Fix |
|---|---|
| `OPENWEATHER_API_KEY is not set` | Add the secret in repo Settings → Secrets → Actions |
| HTTP 401 error | Your API key is invalid — get a new one at openweathermap.org |
| City not found | The city name in `bot.py` must exactly match OpenWeatherMap's database |

### Portfolio sync not working

| Symptom | Fix |
|---|---|
| `PORTFOLIO_PAT is not set` | Add the secret in **automated-email-bot** repo Settings → Secrets |
| HTTP 403 from GitHub API | PAT doesn't have `Contents: Write` on the portfolio repo — recreate it |
| HTTP 404 when pushing | Check `PORTFOLIO_REPO` and `GITHUB_USERNAME` in `sync_projects.py` |
| `projects.json` not updating on website | Hard-refresh browser (Ctrl+Shift+R) — browser may have cached the old file |

### Workflow not running on schedule

GitHub Actions can sometimes delay scheduled workflows by up to 15 minutes during high-traffic periods. You can always trigger a manual run from the **Actions** tab → select the workflow → **Run workflow**.

---

## 🧩 Dependencies

```
requests>=2.31.0    # HTTP calls to APIs
feedparser>=6.0.10  # Parse RSS news feeds
python-dotenv>=1.0.0 # Load .env file for local development
```

> `smtplib` and `email` are part of Python's standard library — no installation needed.

---

## 👤 Author

**Rahul P** — [github.com/r4hulee](https://github.com/r4hulee)

Built as part of the **ZERO2DEV** learning challenge.

---

*Generated and maintained by Automated Bot 🤖*
