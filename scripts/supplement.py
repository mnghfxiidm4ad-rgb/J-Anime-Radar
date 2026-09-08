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

import requests

from eyecatch import resolve_eyecatch, site_url
from feature_editorial import compose_feature_review, gemini_feature_review

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
POSTS_JSON = DATA / "posts"
TRACKER_PATH = DATA / "anime_tracker.json"
SUPPLEMENT_LOG = DATA / "supplement_log.json"
ARCHIVE_CATALOG = DATA / "archive_catalog.json"
ARTICLE_PRIORITY = 20
OFFRANK_START = 21  # ranks 21-30 plus further offrank, then archive, fill the daily quota
UA = "J-Anime-Radar/1.0 (editorial static generator; +https://github.com)"
TENRAI_DEFAULT = "https://api.tenrai.org/v1"


class HttpStatusError(URLError):
    def __init__(self, url: str, code: int, reason: str):
        super().__init__(f"HTTP {code} {reason}")
        self.code = code
        self.url = url
        self.reason = reason


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


def tenrai_base() -> str:
    return env("TENRAI_BASE", TENRAI_DEFAULT).rstrip("/")


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
        raise HttpStatusError(url, res.status_code, reason)
    try:
        return res.json()
    except ValueError as e:
        raise json.JSONDecodeError(str(e), res.text or "", 0) from e


def with_retries(fn, tries: int = 4, sleep_s: float = 2.0, retry_http=(429, 500, 502, 503, 504)):
    last = None
    for i in range(tries):
        try:
            return fn()
        except (HTTPError, HttpStatusError) as e:
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


def previous_season(season: str, year: int):
    order = ["WINTER", "SPRING", "SUMMER", "FALL"]
    i = order.index(season)
    if i == 0:
        return "FALL", year - 1
    return order[i - 1], year


def season_window_keys(now: Optional[datetime] = None):
    season, year = current_season(now)
    prev_season, prev_year = previous_season(season, year)
    return {(season.lower(), year), (prev_season.lower(), prev_year)}


def in_desk_window(row: dict, now: Optional[datetime] = None) -> bool:
    season = (row.get("season") or row.get("season_tag") or "").lower()
    year = row.get("year") if row.get("year") not in (None, "") else row.get("season_year")
    try:
        year = int(year) if year not in (None, "") else None
    except (TypeError, ValueError):
        year = None
    if not season or year is None:
        return False
    return (season, year) in season_window_keys(now)


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


def fetch_tenrai_seasonal_pool(limit: int = 80) -> List[dict]:
    pool: List[dict] = []
    seen: Set[int] = set()
    page = 1
    base = tenrai_base()
    while page <= 6:
        def _pull(p=page):
            return http_json(f"{base}/seasons/now?filter=tv&sfw=true&continuing=true&page={p}&limit=25")

        data = with_retries(_pull, tries=2)
        batch = data.get("data") or []
        if not batch:
            break
        for a in batch:
            if (a.get("type") or "").upper() not in {"TV", "ONA", ""}:
                continue
            try:
                mid = int(a.get("mal_id") or 0)
            except (TypeError, ValueError):
                mid = 0
            if not mid or mid in seen:
                continue
            genres = [g.get("name") for g in (a.get("genres") or []) if g.get("name")]
            studios = [s.get("name") for s in (a.get("studios") or []) if s.get("name")]
            trailer = a.get("trailer") or {}
            row = {
                "mal_id": mid,
                "title": a.get("title"),
                "title_english": a.get("title_english") or a.get("title"),
                "title_romaji": a.get("title"),
                "title_native": a.get("title_japanese") or "",
                "score": a.get("score"),
                "members": a.get("members") or 0,
                "genres": genres,
                "studio": studios[0] if studios else "",
                "studios": studios,
                "description": a.get("synopsis") or "",
                "source": a.get("source") or "",
                "site_url": a.get("url") or "",
                "watch": guess_watch([]),
                "external_links": [],
                "trailer": trailer,
                "image": ((a.get("images") or {}).get("jpg") or {}).get("large_image_url") or "",
                "year": a.get("year"),
                "season": (a.get("season") or "").lower(),
                "origin": "tenrai",
            }
            if not in_desk_window(row):
                continue
            seen.add(mid)
            pool.append(row)
        page += 1
        time.sleep(0.35)
    pool.sort(key=lambda r: int(r.get("members") or 0), reverse=True)
    log(f"  Tenrai seasonal pool {len(pool)} (off-rank uses ranks {ARTICLE_PRIORITY + 1}+)")
    return pool[:limit]


def fetch_tenrai_offrank() -> List[dict]:
    pool = fetch_tenrai_seasonal_pool(limit=60)
    out = []
    for rank, row in enumerate(pool, 1):
        if rank <= ARTICLE_PRIORITY:
            continue
        row = dict(row)
        row["rank"] = rank
        out.append(row)
        if len(out) >= 30:
            break
    return out


def hydrate_tenrai(mal_id: int) -> Optional[dict]:
    base = tenrai_base()
    try:
        data = with_retries(lambda: http_json(f"{base}/anime/{int(mal_id)}/full"), tries=2)
        a = data.get("data") or {}
        if not a:
            return None
        genres = [g.get("name") for g in (a.get("genres") or []) if g.get("name")]
        studios = [s.get("name") for s in (a.get("studios") or []) if s.get("name")]
        img = ((a.get("images") or {}).get("jpg") or {})
        return {
            "mal_id": a.get("mal_id") or mal_id,
            "title": a.get("title"),
            "title_english": a.get("title_english") or a.get("title"),
            "title_romaji": a.get("title"),
            "title_native": a.get("title_japanese") or "",
            "score": a.get("score"),
            "episodes": a.get("episodes"),
            "genres": genres,
            "studio": studios[0] if studios else "",
            "studios": studios,
            "description": a.get("synopsis") or "",
            "source": a.get("source") or "",
            "site_url": a.get("url") or "",
            "watch": guess_watch([]),
            "external_links": [],
            "trailer": a.get("trailer") or {},
            "image": img.get("large_image_url") or img.get("image_url") or "",
            "banner": "",
            "origin": "tenrai",
        }
    except Exception as e:
        log(f"  tenrai hydrate {mal_id} failed: {e}")
        return None


def hydrate_mal(mal_id: int) -> Optional[dict]:
    row = hydrate_tenrai(mal_id)
    if row:
        return row
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
        if m:
            return normalize_anilist(m, rank=None)
    except Exception as e:
        log(f"  archive hydrate AniList {mal_id} failed: {e}")
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
            rank = int(row.get("rank") or 0)
            mid = int(row.get("mal_id") or 0)
        except (TypeError, ValueError):
            continue
        if mid and rank and rank <= ARTICLE_PRIORITY:
            blocked.add(mid)
    blocked.discard(0)
    picks: List[dict] = []
    seen: Set[int] = set()

    tail = []
    for row in ranking or []:
        try:
            rank = int(row.get("rank") or 0)
            mid = int(row.get("mal_id") or 0)
        except (TypeError, ValueError):
            continue
        if mid and rank > ARTICLE_PRIORITY:
            tail.append(row)
    tail.sort(key=lambda r: int(r.get("rank") or 0))
    if tail:
        log(f"Filling shortfall from ranking ranks {ARTICLE_PRIORITY + 1}+ first")
    for row in tail:
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
        hydrated["feature_kind"] = "offrank"
        hydrated["is_archive"] = False
        hydrated["rank"] = row.get("rank")
        picks.append(hydrated)
        seen.add(mid)
        time.sleep(0.4)

    offrank: List[dict] = []
    if len(picks) >= shortfall:
        return picks[:shortfall]
    try:
        log("Fetching further off-rank seasonal titles…")
        offrank = fetch_tenrai_offrank()
        if len(offrank) < 8:
            log("  Tenrai offrank thin; trying AniList page 2")
            try:
                offrank = offrank + fetch_anilist_offrank()
            except Exception as e:
                log(f"  AniList offrank failed ({e})")
    except Exception as e:
        log(f"  Tenrai offrank failed ({e}); trying AniList")
        try:
            offrank = fetch_anilist_offrank()
        except Exception as e2:
            log(f"  AniList offrank failed ({e2})")
            offrank = []

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
    origin = "AniList" if anime.get("origin") == "anilist" else (
        "MyAnimeList/Tenrai" if anime.get("origin") in {"tenrai", "jikan"} else "public catalog metadata"
    )
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
