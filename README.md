# J-Anime Radar

Overseas English desk for the current Japanese TV season. Tagline: Seasonal Anime Intel, Episode Breakdowns & Japanese Fan Reactions.

Python builds static HTML into docs/ for GitHub Pages or Cloudflare Pages. AdSense-oriented legal pages (Privacy, About, Contact, Disclaimer) ship on day one, along with 20+ long-form episode briefings for the live Top 20.

## What it does

- Tracks the season Top 20 via Jikan (AniList fallback)
- Calls Gemini gemini-1.5-flash only for new episodes; skips existing ones using data/anime_tracker.json
- Structures sakuga notes, Japanese reception, seiyuu talk, and legal watch links
- GitHub Actions daily at 11:00 JST (cron 0 2 * * *)

## Setup

    python -m pip install -r requirements.txt
    copy .env.example .env

Edit GEMINI_API_KEY, SITE_URL, CONTACT_EMAIL, GOOGLE_FORM_EMBED_URL.

    python scripts/fetch_and_summarize.py
    python scripts/fetch_and_summarize.py --rebuild-only

## GitHub Pages

Publish the docs/ folder. Set secret GEMINI_API_KEY and variable SITE_URL. Replace pub-XXXXXXXXXXXXXXXX in docs/ads.txt.

Japanese notes for the operator: 固定ページは docs/ 配下の英文です。問い合わせは Contact の Google Form または CONTACT_EMAIL。著作権者からの削除依頼は Contact の Rights holders 節。
