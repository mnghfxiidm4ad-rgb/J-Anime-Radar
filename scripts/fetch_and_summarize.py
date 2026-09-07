#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""J-Anime Radar builder: fetch season Top 20, summarize, emit static docs/."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.error import HTTPError, URLError

import requests

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover
    def load_dotenv(*_a, **_k):
        return False

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))

from editorial import GEMINI_PROMPT, compose_review  # noqa: E402
from legal_pages import page_specs  # noqa: E402
from supplement import daily_target, run_supplement_loop  # noqa: E402
from cms_wordpress import publish_post as wp_publish  # noqa: E402

DATA = ROOT / "data"
POSTS_JSON = DATA / "posts"
TRACKER_PATH = DATA / "anime_tracker.json"
DOCS = ROOT / "docs"
TEMPLATES = ROOT / "templates"
UA = "J-Anime-Radar/1.0 (editorial static generator; +https://github.com)"
TENRAI_DEFAULT = "https://api.tenrai.org/v1"
DESK_SIZE = 30
ARTICLE_PRIORITY = 20  # episode briefs: ranks 1-20; 21-30 are ranking-only unless the daily quota is short
RANKING_SOURCE_LABELS = {
    "tenrai": "MyAnimeList current-season listing via Tenrai (TV/ONA, continuing=true so 2-cour holdovers are included). Not a Japanese TV ratings chart.",
    "anilist": "AniList popularity among currently airing TV/ONA, including 2-cour titles that started last season. Not a Japanese TV ratings chart.",
    "jikan": "MyAnimeList current-season listing via Jikan (TV/ONA, continuing=true so 2-cour holdovers are included). Not a Japanese TV ratings chart.",
}


def current_season(now=None):
    now = now or datetime.now(timezone.utc)
    m = now.month
    if m in (1, 2, 3):
        season = "WINTER"
    elif m in (4, 5, 6):
        season = "SPRING"
    elif m in (7, 8, 9):
        season = "SUMMER"
    else:
        season = "FALL"
    return season, now.year


def previous_season(season: str, year: int):
    order = ["WINTER", "SPRING", "SUMMER", "FALL"]
    i = order.index(season)
    if i == 0:
        return "FALL", year - 1
    return order[i - 1], year


def public_score(raw):
    if raw is None or raw == "":
        return None
    try:
        s = float(raw)
    except (TypeError, ValueError):
        return None
    if s <= 10:
        return int(round(s * 10))
    return int(round(s))


def save_ranking(items, source: str) -> None:
    payload = {
        "source": source,
        "source_label": RANKING_SOURCE_LABELS.get(source, source),
        "desk_size": DESK_SIZE,
        "updated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "items": items,
    }
    (DATA / "ranking.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def load_ranking():
    path = DATA / "ranking.json"
    if not path.exists():
        return [], {}
    raw = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(raw, list):
        return raw, {}
    return list(raw.get("items") or []), raw


def log(msg: str) -> None:
    text = str(msg)
    try:
        print(text, flush=True)
    except UnicodeEncodeError:
        enc = getattr(sys.stdout, "encoding", None) or "utf-8"
        sys.stdout.buffer.write((text + "\n").encode(enc, errors="replace"))
        sys.stdout.flush()


def env(name: str, default: str = "") -> str:
    return (os.environ.get(name) or default).strip()


def site_url() -> str:
    return env("SITE_URL", "https://j-animeradar.net").rstrip("/")


def tenrai_base() -> str:
    return env("TENRAI_BASE", TENRAI_DEFAULT).rstrip("/")


def ranking_rows(catalog: List[dict]) -> List[dict]:
    rows = []
    for rank, anime in enumerate(catalog[:DESK_SIZE], 1):
        rows.append(
            {
                "rank": rank,
                "title": anime.get("title_english") or anime.get("title"),
                "score": public_score(anime.get("score")),
                "mal_id": anime.get("mal_id"),
                "latest": anime.get("latest_episode"),
                "origin": anime.get("origin"),
            }
        )
    return rows


def _error_body_detail(raw: bytes) -> str:
    if not raw:
        return ""
    text = raw.decode("utf-8", errors="replace").strip()
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return text[:300]
    if not isinstance(parsed, dict):
        return text[:300]
    errs = parsed.get("errors")
    if isinstance(errs, list) and errs:
        first = errs[0] if isinstance(errs[0], dict) else {}
        return str((first.get("message") if isinstance(first, dict) else first) or first)[:400]
    if parsed.get("message"):
        return str(parsed.get("message"))[:400]
    return text[:300]


def http_json(url: str, payload: Optional[dict] = None, timeout: int = 45) -> dict:
    headers = {"User-Agent": UA, "Accept": "application/json"}
    try:
        if payload is not None:
            res = requests.post(url, json=payload, headers=headers, timeout=timeout)
        else:
            res = requests.get(url, headers=headers, timeout=timeout)
    except requests.RequestException as e:
        raise URLError(str(e)) from e
    if res.status_code >= 400:
        detail = _error_body_detail(res.content or b"")
        reason = res.reason or "Error"
        if detail:
            reason = f"{reason}: {detail}"
        raise HTTPError(url, res.status_code, reason, res.headers, None)
    try:
        return res.json()
    except ValueError as e:
        raise json.JSONDecodeError(str(e), res.text or "", 0) from e


def with_retries(fn, tries: int = 4, sleep_s: float = 2.0, retry_http=(429, 500, 502, 503, 504)):
    last = None
    for i in range(tries):
        try:
            return fn()
        except HTTPError as e:
            last = e
            if e.code not in retry_http:
                raise
            wait = sleep_s * (2 ** i)
            if e.code == 429:
                wait = max(wait, 20)
            log(f"  HTTP {e.code} retry in {wait:.0f}s")
            time.sleep(wait)
        except (URLError, TimeoutError, json.JSONDecodeError) as e:
            last = e
            wait = sleep_s * (2 ** i)
            log(f"  {type(e).__name__} retry in {wait:.0f}s")
            time.sleep(wait)
    raise last


def slugify(text: str) -> str:
    text = (text or "").lower()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    return text.strip("-")[:80] or "episode"


def load_tracker() -> dict:
    if TRACKER_PATH.exists():
        return json.loads(TRACKER_PATH.read_text(encoding="utf-8"))
    return {"season": "", "updated_at": "", "anime": {}}


def save_tracker(tr: dict) -> None:
    tr["updated_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    TRACKER_PATH.parent.mkdir(parents=True, exist_ok=True)
    TRACKER_PATH.write_text(json.dumps(tr, ensure_ascii=False, indent=2), encoding="utf-8")


def already_done(tr: dict, mal_id: int, episode: int) -> bool:
    node = (tr.get("anime") or {}).get(str(mal_id), {})
    return str(episode) in (node.get("episodes") or {})


def mark_done(tr: dict, anime: dict, episode: int, slug: str, source: str) -> None:
    key = str(anime["mal_id"])
    tr.setdefault("anime", {}).setdefault(key, {"title": anime.get("title_english") or anime.get("title"), "episodes": {}})
    tr["anime"][key]["episodes"][str(episode)] = {
        "slug": slug,
        "source": source,
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }


def fetch_tenrai_season(limit: int = DESK_SIZE) -> List[dict]:
    rows = []
    page = 1
    base = tenrai_base()
    while len(rows) < limit and page <= 3:
        def _pull(p=page):
            return http_json(f"{base}/seasons/now?filter=tv&sfw=true&continuing=true&page={p}&limit=25")

        data = with_retries(_pull)
        batch = data.get("data") or []
        if not batch:
            break
        for a in batch:
            if (a.get("type") or "").upper() not in {"TV", "ONA", ""}:
                continue
            rows.append(normalize_jikan(a, origin="tenrai"))
            if len(rows) >= limit:
                break
        page += 1
        time.sleep(0.4)
    return rows[:limit]


def normalize_jikan(a: dict, origin: str = "tenrai") -> dict:
    genres = [g.get("name") for g in (a.get("genres") or []) if g.get("name")]
    studios = [s.get("name") for s in (a.get("studios") or []) if s.get("name")]
    img = ((a.get("images") or {}).get("jpg") or {})
    return {
        "mal_id": a.get("mal_id"),
        "anilist_id": None,
        "title": a.get("title"),
        "title_english": a.get("title_english") or a.get("title"),
        "title_romaji": a.get("title"),
        "title_native": (a.get("title_japanese") or ""),
        "score": a.get("score"),
        "members": a.get("members") or 0,
        "episodes": a.get("episodes"),
        "genres": genres,
        "studio": studios[0] if studios else "",
        "studios": studios,
        "image": img.get("large_image_url") or img.get("image_url") or "",
        "banner": "",
        "description": a.get("synopsis") or "",
        "source": a.get("source") or "",
        "site_url": (a.get("url") or ""),
        "watch": guess_watch([]),
        "cast": [],
        "next_episode": None,
        "latest_episode": None,
        "origin": origin,
    }


ANILIST_SEASON_QUERY = """
    query ($season: MediaSeason, $seasonYear: Int, $perPage: Int) {
      Page(page: 1, perPage: $perPage) {
        media(
          season: $season
          seasonYear: $seasonYear
          type: ANIME
          status: RELEASING
          format_in: [TV, ONA, TV_SHORT]
          sort: POPULARITY_DESC
        ) {
          id
          idMal
          format
          season
          seasonYear
          title { romaji english native }
          averageScore
          popularity
          episodes
          genres
          source
          description(asHtml: false)
          coverImage { extraLarge }
          bannerImage
          siteUrl
          studios(isMain: true) { nodes { name } }
          nextAiringEpisode { episode airingAt }
          externalLinks { site url type }
          characters(role: MAIN, perPage: 8) {
            edges {
              node { name { full native } }
              voiceActors(language: JAPANESE, sort: RELEVANCE) { name { full } }
            }
          }
        }
      }
    }
    """


def _anilist_row(m: dict) -> dict:
    nxt = m.get("nextAiringEpisode") or {}
    latest = (nxt.get("episode") or 1) - 1
    if latest < 1:
        latest = 1
    links = m.get("externalLinks") or []
    watch = guess_watch(links)
    cast = []
    for e in ((m.get("characters") or {}).get("edges") or []):
        nm = ((e.get("node") or {}).get("name") or {}).get("full")
        vas = e.get("voiceActors") or []
        va = ((vas[0].get("name") or {}).get("full") if vas else "")
        if nm:
            cast.append(f"{nm} / {va}" if va else nm)
    studios = [n.get("name") for n in ((m.get("studios") or {}).get("nodes") or []) if n.get("name")]
    return {
        "mal_id": m.get("idMal") or m.get("id"),
        "anilist_id": m.get("id"),
        "title": (m.get("title") or {}).get("romaji"),
        "title_english": (m.get("title") or {}).get("english") or (m.get("title") or {}).get("romaji"),
        "title_romaji": (m.get("title") or {}).get("romaji"),
        "title_native": (m.get("title") or {}).get("native") or "",
        "score": m.get("averageScore"),
        "members": m.get("popularity") or 0,
        "episodes": m.get("episodes"),
        "genres": m.get("genres") or [],
        "studio": studios[0] if studios else "",
        "studios": studios,
        "image": (m.get("coverImage") or {}).get("extraLarge") or "",
        "banner": m.get("bannerImage") or "",
        "description": m.get("description") or "",
        "source": m.get("source") or "",
        "site_url": m.get("siteUrl") or "",
        "watch": watch,
        "cast": cast,
        "next_episode": nxt.get("episode"),
        "next_airing_at": nxt.get("airingAt"),
        "latest_episode": latest,
        "origin": "anilist",
        "season_tag": m.get("season"),
        "season_year_tag": m.get("seasonYear"),
    }


def _fetch_anilist_window(season: str, year: int, per_page: int = 50) -> List[dict]:
    data = with_retries(
        lambda: http_json(
            "https://graphql.anilist.co",
            {
                "query": ANILIST_SEASON_QUERY,
                "variables": {"season": season, "seasonYear": year, "perPage": int(per_page)},
            },
        )
    )
    media = (((data.get("data") or {}).get("Page") or {}).get("media")) or []
    return [_anilist_row(m) for m in media]


def fetch_anilist_season(limit: int = DESK_SIZE) -> List[dict]:
    """Current cour plus previous cour still RELEASING (2-cour holdovers).

    AniList `season` is the start cour. A Spring-start 2-cour is tagged SPRING
    even while it is still broadcasting in Summer, so a current-season-only
    query drops those titles.
    """
    season, year = current_season()
    windows = [(season, year)]
    windows.append(previous_season(season, year))
    merged: Dict[str, dict] = {}
    for s, y in windows:
        log(f"  AniList window {s} {y}")
        for row in _fetch_anilist_window(s, y, per_page=50):
            key = str(row.get("anilist_id") or row.get("mal_id") or "")
            if not key:
                continue
            prev = merged.get(key)
            if prev is None or int(row.get("members") or 0) >= int(prev.get("members") or 0):
                merged[key] = row
    rows = sorted(merged.values(), key=lambda r: int(r.get("members") or 0), reverse=True)
    log(f"  AniList merged pool {len(rows)} (current+previous cour)")
    return rows[:limit]


def guess_watch(links: List[dict]) -> List[dict]:
    wanted = {
        "Crunchyroll": "https://www.crunchyroll.com/",
        "Netflix": "https://www.netflix.com/",
        "HIDIVE": "https://www.hidive.com/",
        "Amazon Prime Video": "https://www.primevideo.com/",
        "Disney Plus": "https://www.disneyplus.com/",
        "Hulu": "https://www.hulu.com/",
        "Bilibili TV": "https://www.bilibili.tv/",
    }
    found = []
    seen = set()
    for lk in links:
        if (lk.get("type") or "").upper() != "STREAMING":
            continue
        name = lk.get("site") or ""
        url = lk.get("url") or wanted.get(name)
        if name in seen or not url:
            continue
        if name in wanted or name.lower() in {"crunchyroll", "netflix", "hidive", "amazon prime video", "disney plus", "hulu"}:
            found.append({"name": name, "url": url})
            seen.add(name)
    if not found:
        found = [
            {"name": "Crunchyroll", "url": wanted["Crunchyroll"]},
            {"name": "Netflix", "url": wanted["Netflix"]},
            {"name": "HIDIVE", "url": wanted["HIDIVE"]},
            {"name": "Prime Video", "url": wanted["Amazon Prime Video"]},
        ]
    return found[:6]


def enrich_mal_episodes(anime: dict) -> dict:
    mal = anime.get("mal_id")
    if not mal:
        return anime
    base = tenrai_base()
    try:
        time.sleep(0.4)
        data = with_retries(lambda: http_json(f"{base}/anime/{mal}/full"), tries=2)
        body = data.get("data") or {}
        anime["score"] = anime.get("score") or body.get("score")
        anime["episodes"] = anime.get("episodes") or body.get("episodes")
        anime["description"] = anime.get("description") or body.get("synopsis") or ""
        streaming = body.get("streaming") or []
        if streaming:
            anime["watch"] = [{"name": s.get("name"), "url": s.get("url")} for s in streaming if s.get("name")]
        time.sleep(0.4)
        eps = with_retries(lambda: http_json(f"{base}/anime/{mal}/episodes?page=1"), tries=2)
        last = 0
        for ep in (eps.get("data") or []):
            n = ep.get("mal_id") or ep.get("episode") or 0
            try:
                last = max(last, int(n))
            except (TypeError, ValueError):
                pass
        if last:
            anime["latest_episode"] = last
    except Exception as e:
        log(f"  catalog enrich failed for {mal}: {e}")
    if not anime.get("latest_episode"):
        anime["latest_episode"] = 1
    return anime


def fetch_season(enrich: bool = True) -> Optional[List[dict]]:
    min_ok = max(15, DESK_SIZE // 2)
    log(f"Fetching season Top {DESK_SIZE} via Tenrai…")
    try:
        rows = fetch_tenrai_season(DESK_SIZE)
        if len(rows) >= min_ok:
            log(f"  Tenrai OK ({len(rows)})")
            if not enrich:
                for a in rows:
                    if not a.get("latest_episode"):
                        a["latest_episode"] = 1
                return rows
            out = []
            for i, a in enumerate(rows, 1):
                log(f"  enrich {i}/{len(rows)} {a.get('title_english')}")
                out.append(enrich_mal_episodes(a))
            return out
        log(f"  Tenrai returned too few rows ({len(rows)}); falling back")
    except Exception as e:
        log(f"  Tenrai unavailable ({e}); using AniList fallback")
    log(f"Fetching season Top {DESK_SIZE} via AniList…")
    try:
        rows = fetch_anilist_season(DESK_SIZE)
        if len(rows) >= min_ok:
            log(f"  AniList OK ({len(rows)})")
            return rows
        log(f"  AniList returned too few rows ({len(rows)})")
    except Exception as e:
        log(f"  AniList unavailable ({e})")
    return None


def gemini_review(anime: dict, episode: int) -> Optional[dict]:
    api_key = env("GEMINI_API_KEY")
    if not api_key:
        return None
    try:
        import google.generativeai as genai
    except ImportError:
        log("  google-generativeai missing; seed fallback")
        return None

    genai.configure(api_key=api_key)
    models = []
    preferred = env("GEMINI_MODEL", "gemini-1.5-flash")
    for m in [preferred, "gemini-1.5-flash", "gemini-2.0-flash", "gemini-2.5-flash", "gemini-flash-latest"]:
        if m and m not in models:
            models.append(m)

    user = {
        "title_english": anime.get("title_english"),
        "title_romaji": anime.get("title_romaji"),
        "title_native": anime.get("title_native"),
        "episode": episode,
        "episodes_total": anime.get("episodes"),
        "studio": anime.get("studio"),
        "genres": anime.get("genres"),
        "score": anime.get("score"),
        "source": anime.get("source"),
        "description": (anime.get("description") or "")[:900],
        "cast": anime.get("cast"),
        "licensed_platforms": anime.get("watch"),
    }
    prompt = GEMINI_PROMPT + "\n\nSERIES CONTEXT:\n" + json.dumps(user, ensure_ascii=False)

    last_err = None
    for model_name in models:
        for attempt in range(4):
            try:
                model = genai.GenerativeModel(model_name)
                resp = model.generate_content(
                    prompt,
                    generation_config={"temperature": 0.7, "max_output_tokens": 4096},
                )
                text = (resp.text or "").strip()
                text = re.sub(r"^```json\s*|\s*```$", "", text, flags=re.I | re.M)
                data = json.loads(text)
                if "episode_synopsis_analysis" not in data:
                    raise ValueError("missing keys")
                data.setdefault("where_to_watch", anime.get("watch") or [])
                log(f"  Gemini OK ({model_name})")
                time.sleep(8)
                return data
            except Exception as e:
                last_err = e
                msg = str(e).lower()
                if "429" in msg or "resource exhausted" in msg:
                    wait = 20 * (attempt + 1)
                    log(f"  Gemini 429 on {model_name}; sleep {wait}s")
                    time.sleep(wait)
                    continue
                log(f"  Gemini error on {model_name}: {e}")
                break
        time.sleep(2)
    log(f"  Gemini failed ({last_err}); using editorial seed")
    return None


def paragraphs(text: str) -> List[str]:
    text = (text or "").strip()
    if not text:
        return []
    parts = re.split(r"\n\s*\n", text)
    if len(parts) == 1 and len(text) > 420:
        mid = text.rfind(". ", 180, 420)
        if mid != -1:
            return [text[: mid + 1].strip(), text[mid + 1 :].strip()]
    return [p.strip() for p in parts if p.strip()]


def build_post_record(anime: dict, episode: int, review: dict, rank: int) -> dict:
    title = anime.get("title_english") or anime.get("title")
    slug = f"{slugify(title)}-ep{episode}"
    aired = "Summer 2026 broadcast week"
    ts = anime.get("next_airing_at")
    if ts:
        # next airing is the following episode; latest aired is roughly 7 days prior
        aired_dt = datetime.fromtimestamp(int(ts) - 7 * 24 * 3600, tz=timezone.utc)
        aired = aired_dt.strftime("%Y-%m-%d")
    watch = review.get("where_to_watch") or anime.get("watch") or []
    if watch and isinstance(watch[0], str):
        watch = [{"name": w, "url": "https://www.crunchyroll.com/"} for w in watch]
    reactions = review.get("japan_fan_reactions") or {}
    synopsis = review.get("episode_synopsis_analysis") or ""
    take = review.get("deep_dive_takeaway") or ""
    pull = (review.get("episode_vibe") or "Seasonal intel") + " — original briefing, not a recap."
    return {
        "slug": slug,
        "rank": rank,
        "mal_id": anime.get("mal_id"),
        "anime_title": title,
        "title_native": anime.get("title_native") or "",
        "episode": episode,
        "episode_total": anime.get("episodes"),
        "episode_title": review.get("episode_title") or f"Episode {episode}",
        "episode_vibe": review.get("episode_vibe") or "Seasonal Pressure Test",
        "aired": aired,
        "score": anime.get("score"),
        "studio": anime.get("studio") or "Unknown studio",
        "genres": anime.get("genres") or [],
        "image": anime.get("image") or "",
        "banner": anime.get("banner") or anime.get("image") or "",
        "watch": watch,
        "pullquote": pull,
        "synopsis_paragraphs": paragraphs(synopsis),
        "sakuga_paragraphs": paragraphs(reactions.get("sakuga_and_direction") or ""),
        "story_paragraphs": paragraphs(reactions.get("story_and_lore") or ""),
        "voice_paragraphs": paragraphs(reactions.get("voice_acting_highlights") or ""),
        "takeaway_paragraphs": paragraphs(take),
        "raw": review,
        "source": review.get("_source", "editorial"),
    }


def jinja_env():
    from jinja2 import Environment, FileSystemLoader, select_autoescape

    return Environment(
        loader=FileSystemLoader(str(TEMPLATES)),
        autoescape=select_autoescape(["html"]),
    )


def abs_url(path: str) -> str:
    return f"{site_url()}/{path.lstrip('/')}"


def default_og() -> str:
    return abs_url("assets/logo.svg")


def og_image_for(post: dict) -> str:
    img = (post.get("banner") or post.get("image") or "").strip()
    if img.startswith("http://") or img.startswith("https://"):
        return img
    if img.startswith("/"):
        return f"{site_url()}{img}"
    if img:
        return abs_url(img)
    return default_og()


def write_html(path: Path, html: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(html, encoding="utf-8", newline="\n")


def render_legal(envj) -> None:
    year = datetime.now().year
    contact_email = env("CONTACT_EMAIL", "editorial@example.com")
    form_embed = env("GOOGLE_FORM_EMBED_URL", 'https://docs.google.com/forms/d/e/1FAIpQLSfqzO3DXp5V8f8FdWfNxgAk_bgJMSXIcMlWHQiFvQkuTMMukA/viewform?embedded=true')
    for spec in page_specs():
        body_src = spec["body"]
        body = envj.from_string(body_src).render(contact_email=contact_email, form_embed=form_embed)
        page = envj.get_template("page.html")
        html = page.render(
            title=spec["title"],
            description=spec["description"],
            canonical=abs_url(spec["filename"]),
            og_type="website",
            og_image=default_og(),
            root="",
            nav=spec["nav"],
            year=year,
            kicker=spec["kicker"],
            heading=spec["heading"],
            updated=spec["updated"],
            body=body,
            json_ld=json.dumps(
                {
                    "@context": "https://schema.org",
                    "@type": "WebPage",
                    "name": spec["heading"],
                    "url": abs_url(spec["filename"]),
                    "isPartOf": {"@type": "WebSite", "name": "J-Anime Radar", "url": site_url()},
                },
                ensure_ascii=False,
            ),
        )
        write_html(DOCS / spec["filename"], html)


def render_post(envj, post: dict) -> None:
    year = datetime.now().year
    canonical = abs_url(f"posts/{post['slug']}.html")
    is_feature = (post.get("kind") == "feature")
    headline = post.get("headline") or post.get("episode_title") or post.get("anime_title")
    graph = [
        {
            "@type": "WebSite",
            "name": "J-Anime Radar",
            "url": site_url(),
            "description": "Seasonal Anime Intel, Episode Breakdowns & Japanese Fan Reactions",
        },
        {
            "@type": "Article",
            "headline": headline if is_feature else f"{post['anime_title']} Episode {post['episode']} — {post['episode_title']}",
            "description": headline,
            "image": og_image_for(post),
            "datePublished": post.get("aired"),
            "inLanguage": "en",
            "author": {"@type": "Organization", "name": "J-Anime Radar Editorial Project"},
            "publisher": {"@type": "Organization", "name": "J-Anime Radar", "url": site_url()},
            "mainEntityOfPage": canonical,
        },
    ]
    if not is_feature:
        graph.append(
            {
                "@type": "TVEpisode",
                "name": post["episode_title"],
                "episodeNumber": post["episode"],
                "partOfSeries": {"@type": "TVSeries", "name": post["anime_title"]},
            }
        )
    article_ld = {"@context": "https://schema.org", "@graph": graph}
    if is_feature:
        title = f"{headline} — J-Anime Radar"
        description = f"Original series guide: appeal, spoiler-light synopsis, watch points, and legal streaming notes for {post['anime_title']}."
    else:
        title = f"{post['anime_title']} Ep. {post['episode']} — J-Anime Radar"
        description = f"Original episode briefing: sakuga, Japanese fan reaction, and legal watch links for {post['anime_title']} episode {post['episode']}."
    html = envj.get_template("post.html").render(
        title=title,
        description=description,
        canonical=canonical,
        og_type="article",
        og_image=og_image_for(post),
        root="../",
        nav="home",
        year=year,
        post=post,
        json_ld=json.dumps(article_ld, ensure_ascii=False),
    )
    write_html(DOCS / "posts" / f"{post['slug']}.html", html)


def render_index(envj, posts: List[dict], ranking: List[dict], ranking_note: str = "") -> None:
    year = datetime.now().year
    genres = sorted({g for p in posts for g in (p.get("genres") or [])})
    website_ld = {
        "@context": "https://schema.org",
        "@type": "WebSite",
        "name": "J-Anime Radar",
        "url": site_url(),
        "description": "Seasonal Anime Intel, Episode Breakdowns & Japanese Fan Reactions",
        "inLanguage": "en",
        "publisher": {"@type": "Organization", "name": "J-Anime Radar Editorial Project"},
    }
    html = envj.get_template("index.html").render(
        title="J-Anime Radar — Seasonal Anime Intel, Episode Breakdowns & Japanese Fan Reactions",
        description="Original English briefings on this season’s Top 30 anime: sakuga analysis, Japanese fan reactions, seiyuu notes, and legal streaming links.",
        canonical=abs_url("index.html"),
        og_type="website",
        og_image=default_og(),
        root="",
        nav="home",
        year=year,
        season_label="Summer 2026",
        stats={"titles": len(ranking) or DESK_SIZE, "articles": len(posts), "season": "2026 S"},
        genres=genres,
        posts=posts,
        ranking=ranking,
        ranking_note=ranking_note or RANKING_SOURCE_LABELS["tenrai"],
        json_ld=json.dumps(website_ld, ensure_ascii=False),
    )
    write_html(DOCS / "index.html", html)


def write_extras(posts: List[dict]) -> None:
    (DOCS / "robots.txt").write_text(
        f"User-agent: *\nAllow: /\nSitemap: {abs_url('sitemap.xml')}\n",
        encoding="utf-8",
    )
    (DOCS / "ads.txt").write_text(
        "google.com, pub-2075840815269276, DIRECT, f08c47fec0942fa0\n",
        encoding="utf-8",
    )
    urls = ["index.html", "about.html", "privacy.html", "contact.html", "disclaimer.html"]
    urls += [f"posts/{p['slug']}.html" for p in posts]
    sm = ['<?xml version="1.0" encoding="UTF-8"?>', '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    for u in urls:
        sm.append(f"  <url><loc>{abs_url(u)}</loc></url>")
    sm.append("</urlset>")
    (DOCS / "sitemap.xml").write_text("\n".join(sm) + "\n", encoding="utf-8")
    (DOCS / "404.html").write_text(
        "<!DOCTYPE html><html lang='en'><head><meta charset='utf-8'><title>Not found — J-Anime Radar</title>"
        "<link rel='stylesheet' href='/css/style.css'></head><body><div class='legal'><h1>Signal lost</h1>"
        "<p>That briefing does not exist. Return to <a href='/index.html'>headquarters</a>.</p></div></body></html>\n",
        encoding="utf-8",
    )


def planned_episodes(anime: dict, rank: int, seed: bool) -> List[int]:
    latest = int(anime.get("latest_episode") or 1)
    latest = max(1, latest)
    eps = [latest]
    if seed and rank <= 5 and latest > 1:
        eps.append(latest - 1)
    return eps


def _aired_sort_key(post: dict):
    aired = str(post.get("aired") or "")
    date = aired[:10] if len(aired) >= 10 and aired[4:5] == "-" else "0000-00-00"
    episode = int(post.get("episode") or 0)
    slug = post.get("slug") or ""
    return (date, episode, slug)


def rebuild_from_json() -> List[dict]:
    posts = []
    if POSTS_JSON.exists():
        for fp in POSTS_JSON.glob("*.json"):
            posts.append(json.loads(fp.read_text(encoding="utf-8")))
    posts.sort(key=_aired_sort_key, reverse=True)
    return posts


def main() -> int:
    load_dotenv(ROOT / ".env")
    parser = argparse.ArgumentParser(description="Build J-Anime Radar static site")
    parser.add_argument("--rebuild-only", action="store_true", help="Do not call APIs; rewrite HTML from data/posts")
    parser.add_argument("--ranking-only", action="store_true", help="Refresh the Top 30 ranking sidebar without writing episode articles")
    parser.add_argument("--max-new", type=int, default=30, help="Max new Top-20 episode articles this run")
    parser.add_argument("--daily-target", type=int, default=None, help="Target total new posts per run (default DAILY_TARGET_COUNT or 3)")
    parser.add_argument("--skip-supplement", action="store_true", help="Do not generate complementary feature articles")
    parser.add_argument("--no-seed-extra", action="store_true", help="Only latest episode per title")
    args = parser.parse_args()
    target = args.daily_target if args.daily_target is not None else daily_target()

    DATA.mkdir(parents=True, exist_ok=True)
    POSTS_JSON.mkdir(parents=True, exist_ok=True)
    (DOCS / "posts").mkdir(parents=True, exist_ok=True)

    envj = jinja_env()
    tr = load_tracker()
    new_features: List[dict] = []

    if args.ranking_only:
        log(f"Refreshing Top {DESK_SIZE} ranking only")
        catalog = fetch_season(enrich=False)
        if not catalog:
            log("  live ranking unavailable; keeping existing ranking.json")
        else:
            ranking_meta = ranking_rows(catalog)
            source = (catalog[0].get("origin") if catalog else "tenrai") or "tenrai"
            save_ranking(ranking_meta, source)
            log(f"ranking rows: {len(ranking_meta)} source={source}")
    elif not args.rebuild_only:
        catalog = fetch_season()
        if not catalog:
            log("  live catalog unavailable; rebuilding site from existing posts/ranking")
        else:
            tr["season"] = "2026-SUMMER"
            created = 0
            ranking_meta = ranking_rows(catalog)
            for rank, anime in enumerate(catalog, 1):
                if rank > ARTICLE_PRIORITY:
                    continue
                seed = not args.no_seed_extra
                for ep in planned_episodes(anime, rank, seed=seed):
                    if already_done(tr, int(anime["mal_id"]), ep):
                        log(f"skip {anime.get('title_english')} ep{ep}")
                        continue
                    if created >= args.max_new:
                        continue
                    log(f"brief {anime.get('title_english')} ep{ep}")
                    review = gemini_review(anime, ep)
                    source = "gemini"
                    if review is None:
                        review = compose_review(anime, ep)
                        source = "editorial-seed"
                        review["_source"] = source
                        log(f"  editorial seed ({review.get('_word_count')} words)")
                    else:
                        review["_source"] = source
                    post = build_post_record(anime, ep, review, rank)
                    (POSTS_JSON / f"{post['slug']}.json").write_text(
                        json.dumps(post, ensure_ascii=False, indent=2), encoding="utf-8"
                    )
                    mark_done(tr, anime, ep, post["slug"], source)
                    created += 1
            desk_origin = (catalog[0].get("origin") if catalog else "tenrai") or "tenrai"
            save_ranking(ranking_meta, desk_origin)
            save_tracker(tr)
            log(f"new desk episode briefings this run: {created}")
            shortfall = max(0, int(target) - int(created))
            if not args.skip_supplement and shortfall > 0:
                try:
                    new_features = run_supplement_loop(shortfall, ranking_meta) or []
                except Exception as e:
                    log(f"  complementary features skipped ({e})")
                    new_features = []
            else:
                log(f"complementary features skipped (shortfall={shortfall})")
    posts = rebuild_from_json()
    ranking, ranking_doc = load_ranking()
    latest_by_mal = {}
    for p in posts:
        if p.get("kind") == "feature":
            continue
        mid = str(p.get("mal_id"))
        if mid not in latest_by_mal or int(p.get("episode") or 0) > int(latest_by_mal[mid].get("episode") or 0):
            latest_by_mal[mid] = p
    for row in ranking:
        p = latest_by_mal.get(str(row.get("mal_id")))
        row["href"] = f"posts/{p['slug']}.html" if p else "index.html#top30"

    if args.ranking_only:
        log(f"rendering index + legal with {len(ranking)} ranking rows")
    else:
        log(f"rendering {len(posts)} posts + legal + index")
        for post in posts:
            render_post(envj, post)
    render_index(envj, posts, ranking, ranking_note=(ranking_doc or {}).get("source_label") or "")
    render_legal(envj)
    write_extras(posts)
    for post in new_features:
        try:
            html_path = DOCS / "posts" / f"{post['slug']}.html"
            html = html_path.read_text(encoding="utf-8") if html_path.exists() else ""
            wp_publish(
                post,
                html,
                eyecatch={
                    "featured_media": post.get("featured_media") or 0,
                    "eyecatch_source": post.get("eyecatch_source"),
                },
            )
        except Exception as e:
            log(f"  WordPress post-render skipped: {e}")
    log("done")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
