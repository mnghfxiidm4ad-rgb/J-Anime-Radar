# -*- coding: utf-8 -*-
"""Daily shortfall fill-ins: off-rank (21-50) then archive classics. 30-day de-dupe."""

from __future__ import annotations

import json
import os
import re
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from eyecatch import resolve_eyecatch, site_url
from feature_editorial import compose_feature_review, gemini_feature_review

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
POSTS_JSON = DATA / "posts"
TRACKER_PATH = DATA / "anime_tracker.json"
SUPPLEMENT_LOG = DATA / "supplement_log.json"
ARCHIVE_CATALOG = DATA / "archive_catalog.json"
OFFRANK_START = 31  # desk is Top 30; complementary offrank starts here
UA = "J-Anime-Radar/1.0 (editorial static generator; +https://github.com)"


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


def daily_target() -> int:
    try:
        n = int(env("DAILY_TARGET_COUNT", "3") or 3)
    except ValueError:
        n = 3
    return max(0, n)


def lookback_days() -> int:
    try:
        n = int(env("SUPPLEMENT_LOOKBACK_DAYS", "30") or 30)
    except ValueError:
        n = 30
    return max(1, n)


def http_json(url: str, payload: Optional[dict] = None, timeout: int = 45) -> dict:
    headers = {"User-Agent": UA, "Accept": "application/json"}
    data = None
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = Request(url, data=data, headers=headers)
    with urlopen(req, timeout=timeout) as res:
        return json.loads(res.read().decode("utf-8"))


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
    return text.strip("-")[:70] or "feature"


def current_season(now: Optional[datetime] = None):
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
    for lk in links or []:
        ltype = (lk.get("type") or "").upper()
        if ltype and ltype != "STREAMING":
            continue
        name = lk.get("site") or lk.get("name") or ""
        url = lk.get("url") or wanted.get(name)
        if name in seen or not url:
            continue
        lname = name.lower()
        if name in wanted or lname in {
            "crunchyroll",
            "netflix",
            "hidive",
            "amazon prime video",
            "disney plus",
            "hulu",
        }:
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


def _parse_dt(raw: str) -> Optional[datetime]:
    raw = (raw or "").strip()
    if not raw:
        return None
    try:
        if raw.endswith("Z"):
            return datetime.strptime(raw, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
        if len(raw) >= 10 and raw[4] == "-":
            return datetime.strptime(raw[:10], "%Y-%m-%d").replace(tzinfo=timezone.utc)
    except ValueError:
        return None
    return None


def load_supplement_log() -> dict:
    if SUPPLEMENT_LOG.exists():
        return json.loads(SUPPLEMENT_LOG.read_text(encoding="utf-8"))
    return {"entries": []}


def save_supplement_log(logdoc: dict) -> None:
    cutoff = datetime.now(timezone.utc) - timedelta(days=lookback_days())
    kept = []
    for e in logdoc.get("entries") or []:
        dt = _parse_dt(e.get("posted_at") or "")
        if dt and dt >= cutoff:
            kept.append(e)
    logdoc["entries"] = kept
    logdoc["updated_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    SUPPLEMENT_LOG.write_text(json.dumps(logdoc, ensure_ascii=False, indent=2), encoding="utf-8")


def recent_mal_ids(posts: Optional[List[dict]] = None) -> Set[int]:
    """Any title posted in the lookback window (episode or feature) is blocked."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=lookback_days())
    ids: Set[int] = set()
    rows = posts
    if rows is None:
        rows = []
        if POSTS_JSON.exists():
            for fp in POSTS_JSON.glob("*.json"):
                try:
                    rows.append(json.loads(fp.read_text(encoding="utf-8")))
                except Exception:
                    continue
    for p in rows:
        try:
            mid = int(p.get("mal_id") or 0)
        except (TypeError, ValueError):
            continue
        if not mid:
            continue
        dt = _parse_dt(str(p.get("generated_at") or p.get("aired") or ""))
        if dt is None or dt >= cutoff:
            ids.add(mid)
    logdoc = load_supplement_log()
    for e in logdoc.get("entries") or []:
        try:
            mid = int(e.get("mal_id") or 0)
        except (TypeError, ValueError):
            continue
        dt = _parse_dt(e.get("posted_at") or "")
        if mid and (dt is None or dt >= cutoff):
            ids.add(mid)
    return ids


def normalize_anilist(m: dict, rank: Optional[int] = None) -> dict:
    nxt = m.get("nextAiringEpisode") or {}
    links = m.get("externalLinks") or []
    studios = [n.get("name") for n in ((m.get("studios") or {}).get("nodes") or []) if n.get("name")]
    start = m.get("startDate") or {}
    year = start.get("year") or m.get("seasonYear")
    trailer = m.get("trailer") or {}
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
        "watch": guess_watch(links),
        "external_links": links,
        "trailer": trailer,
        "season_year": year,
        "rank": rank,
        "origin": "anilist",
        "next_episode": nxt.get("episode"),
    }


def fetch_anilist_offrank() -> List[dict]:
    season, year = current_season()
    query = """
    query ($season: MediaSeason, $seasonYear: Int) {
      Page(page: 2, perPage: 30) {  # page 1 is Top 30
        media(season: $season, seasonYear: $seasonYear, type: ANIME, status: RELEASING, format_in: [TV, ONA, TV_SHORT], sort: POPULARITY_DESC) {
          id
          idMal
          title { romaji english native }
          averageScore
          popularity
          episodes
          genres
          source
          seasonYear
          startDate { year }
          description(asHtml: false)
          coverImage { extraLarge }
          bannerImage
          siteUrl
          trailer { id site }
          studios(isMain: true) { nodes { name } }
          nextAiringEpisode { episode airingAt }
          externalLinks { site url type }
        }
      }
    }
    """
    data = with_retries(
        lambda: http_json(
            "https://graphql.anilist.co",
            {"query": query, "variables": {"season": season, "seasonYear": year}},
        )
    )
    media = (((data.get("data") or {}).get("Page") or {}).get("media")) or []
    out = []
    for i, m in enumerate(media, OFFRANK_START):
        row = normalize_anilist(m, rank=i)
        if row.get("mal_id"):
            out.append(row)
        if len(out) >= 30:
            break
    return out


def fetch_jikan_offrank() -> List[dict]:
    def _pull():
        return http_json("https://api.jikan.moe/v4/seasons/now?filter=tv&sfw=true&continuing=true&page=2&limit=25")

    data = with_retries(_pull, tries=2)
    rows = []
    rank = 21
    for a in data.get("data") or []:
        if (a.get("type") or "").upper() not in {"TV", "ONA", ""}:
            continue
        genres = [g.get("name") for g in (a.get("genres") or []) if g.get("name")]
        studios = [s.get("name") for s in (a.get("studios") or []) if s.get("name")]
        trailer = a.get("trailer") or {}
        rows.append(
            {
                "mal_id": a.get("mal_id"),
                "title": a.get("title"),
                "title_english": a.get("title_english") or a.get("title"),
                "title_romaji": a.get("title"),
                "title_native": a.get("title_japanese") or "",
                "score": a.get("score"),
                "genres": genres,
                "studio": studios[0] if studios else "",
                "studios": studios,
                "description": a.get("synopsis") or "",
                "source": a.get("source") or "",
                "site_url": a.get("url") or "",
                "watch": guess_watch([]),
                "external_links": [],
                "trailer": trailer,
                "rank": rank,
                "origin": "jikan",
            }
        )
        rank += 1
        if len(rows) >= 30:
            break
        time.sleep(0.35)
    return rows


def hydrate_mal(mal_id: int) -> Optional[dict]:
    query = """
    query ($id: Int) {
      Media(idMal: $id, type: ANIME) {
        id
        idMal
        title { romaji english native }
        averageScore
        popularity
        episodes
        genres
        source
        seasonYear
        startDate { year }
        description(asHtml: false)
        coverImage { extraLarge }
        bannerImage
        siteUrl
        trailer { id site }
        studios(isMain: true) { nodes { name } }
        externalLinks { site url type }
      }
    }
    """
    try:
        data = with_retries(
            lambda: http_json("https://graphql.anilist.co", {"query": query, "variables": {"id": int(mal_id)}}),
            tries=2,
        )
        m = ((data.get("data") or {}).get("Media")) or None
        if not m:
            return None
        return normalize_anilist(m, rank=None)
    except Exception as e:
        log(f"  archive hydrate {mal_id} failed: {e}")
        return None


def load_archive_catalog() -> List[dict]:
    if not ARCHIVE_CATALOG.exists():
        return []
    doc = json.loads(ARCHIVE_CATALOG.read_text(encoding="utf-8"))
    rows = list(doc.get("titles") or [])
    rows.sort(key=lambda r: int(r.get("priority") or 0), reverse=True)
    return rows


def select_targets(shortfall: int, ranking: List[dict], posts: Optional[List[dict]] = None) -> List[dict]:
    blocked = recent_mal_ids(posts)
    for row in ranking or []:
        try:
            blocked.add(int(row.get("mal_id") or 0))
        except (TypeError, ValueError):
            pass
    blocked.discard(0)
    picks: List[dict] = []

    offrank: List[dict] = []
    try:
        log("Fetching off-rank seasonal titles (approx. 21–50)…")
        offrank = fetch_anilist_offrank()
        if len(offrank) < 8:
            log("  AniList offrank thin; trying Jikan page 2")
            offrank = offrank + fetch_jikan_offrank()
    except Exception as e:
        log(f"  offrank fetch failed ({e}); archive-only")
        try:
            offrank = fetch_jikan_offrank()
        except Exception as e2:
            log(f"  Jikan offrank failed ({e2})")
            offrank = []

    seen: Set[int] = set()
    for anime in offrank:
        if len(picks) >= shortfall:
            break
        try:
            mid = int(anime.get("mal_id") or 0)
        except (TypeError, ValueError):
            continue
        if not mid or mid in blocked or mid in seen:
            continue
        anime["feature_kind"] = "offrank"
        anime["is_archive"] = False
        picks.append(anime)
        seen.add(mid)

    if len(picks) < shortfall:
        log("Selecting archive catalog titles...")
        for row in load_archive_catalog():
            if len(picks) >= shortfall:
                break
            try:
                mid = int(row.get("mal_id") or 0)
            except (TypeError, ValueError):
                continue
            if not mid or mid in blocked or mid in seen:
                continue
            hydrated = hydrate_mal(mid)
            if not hydrated:
                continue
            hydrated["feature_kind"] = "archive"
            hydrated["is_archive"] = True
            hydrated["archive_reason"] = row.get("reason") or "archive"
            picks.append(hydrated)
            seen.add(mid)
            time.sleep(0.4)
    return picks[:shortfall]


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


def rights_credit(anime: dict, review: dict) -> str:
    studio = anime.get("studio") or ""
    hint = (review.get("credit_hint") or "").strip()
    holder = hint or studio or "the original rights holders"
    origin = "AniList" if anime.get("origin") == "anilist" else ("MyAnimeList/Jikan" if anime.get("origin") == "jikan" else "public catalog metadata")
    return f"© {holder} / Source: {origin}. Key visuals and footage remain the property of the production committee and licensors. J-Anime Radar does not claim those assets."


def build_feature_record(anime: dict, review: dict, eyecatch: dict) -> dict:
    title = anime.get("title_english") or anime.get("title")
    kind = anime.get("feature_kind") or "archive"
    slug = f"recommended-{slugify(title)}"
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    watch = review.get("where_to_watch") or anime.get("watch") or []
    if watch and isinstance(watch[0], str):
        watch = [{"name": w, "url": "https://www.crunchyroll.com/"} for w in watch]
    headline = review.get("headline") or f"【Recommended Anime】The Appeal of 『{title}』 — Synopsis, Highlights, and Watch Guide"
    credit = rights_credit(anime, review)
    return {
        "kind": "feature",
        "feature_kind": kind,
        "slug": slug,
        "rank": anime.get("rank") or 0,
        "mal_id": anime.get("mal_id"),
        "anime_title": title,
        "title_native": anime.get("title_native") or "",
        "episode": 0,
        "episode_total": anime.get("episodes"),
        "episode_title": headline,
        "headline": headline,
        "episode_vibe": review.get("vibe") or "Recommended Anime",
        "aired": today,
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "score": anime.get("score"),
        "studio": anime.get("studio") or "Unknown studio",
        "genres": anime.get("genres") or [],
        "image": eyecatch.get("image") or "",
        "banner": eyecatch.get("banner") or eyecatch.get("image") or "",
        "featured_media": eyecatch.get("featured_media") or 0,
        "eyecatch_source": eyecatch.get("eyecatch_source"),
        "eyecatch_key": eyecatch.get("eyecatch_key"),
        "embed_html": eyecatch.get("embed_html") or "",
        "watch": watch,
        "pullquote": (review.get("recommended_for") or "")[:280],
        "recommended_for": review.get("recommended_for") or "",
        "intro_paragraphs": paragraphs(review.get("intro") or ""),
        "synopsis_paragraphs": paragraphs(review.get("spoiler_free_synopsis") or ""),
        "highlights": review.get("highlights") or [],
        "close_paragraphs": paragraphs(review.get("platforms_and_close") or ""),
        "rights_credit": credit,
        "sakuga_paragraphs": [],
        "story_paragraphs": [],
        "voice_paragraphs": [],
        "takeaway_paragraphs": paragraphs(review.get("platforms_and_close") or ""),
        "raw": review,
        "source": review.get("_source", "editorial"),
        "site_url": site_url(),
    }


def unique_slug(slug: str) -> str:
    path = POSTS_JSON / f"{slug}.json"
    if not path.exists():
        return slug
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d")
    alt = f"{slug}-{stamp}"
    n = 2
    while (POSTS_JSON / f"{alt}.json").exists():
        alt = f"{slug}-{stamp}-{n}"
        n += 1
    return alt


def run_supplement_loop(shortfall: int, ranking: List[dict], posts: Optional[List[dict]] = None) -> List[dict]:
    if shortfall <= 0:
        return []
    log(f"Daily shortfall={shortfall} (target {daily_target()}); generating complementary features")
    made: List[dict] = []
    try:
        targets = select_targets(shortfall, ranking, posts=posts)
    except Exception as e:
        log(f"supplement selection aborted: {e}")
        return []
    if not targets:
        log("no supplement targets after 30-day de-dupe")
        return []

    logdoc = load_supplement_log()
    for anime in targets:
        title = anime.get("title_english") or anime.get("title")
        try:
            log(f"feature {title} ({anime.get('feature_kind')})")
            is_archive = bool(anime.get("is_archive") or anime.get("feature_kind") == "archive")
            review = gemini_feature_review(anime, feature_kind=anime.get("feature_kind") or "archive")
            if review is None:
                review = compose_feature_review(anime, feature_kind=anime.get("feature_kind") or "archive")
                log(f"  editorial feature seed ({review.get('_word_count')} words)")
            eyecatch = resolve_eyecatch(anime, is_archive=is_archive)
            post = build_feature_record(anime, review, eyecatch)
            post["slug"] = unique_slug(post["slug"])
            (POSTS_JSON / f"{post['slug']}.json").write_text(
                json.dumps(post, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            logdoc.setdefault("entries", []).append(
                {
                    "mal_id": post.get("mal_id"),
                    "slug": post["slug"],
                    "kind": post.get("feature_kind"),
                    "posted_at": post.get("generated_at"),
                }
            )
            made.append(post)
        except Exception as e:
            log(f"  supplement skipped for {title}: {e}")
            continue
    save_supplement_log(logdoc)
    log(f"complementary features this run: {len(made)}")
    return made
