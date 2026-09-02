# -*- coding: utf-8 -*-
"""Safe eyecatch resolution: official embeds first, then owned genre defaults. Never scrape, never abort."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parents[1]
GENRE_MEDIA_PATH = ROOT / "data" / "genre_media.json"

# First matching genre wins.
_GENRE_KEYS = (
    (("sci-fi", "sci fi", "mecha", "space", "cyberpunk"), "sf"),
    (("action", "adventure", "sports", "martial arts", "military"), "action"),
    (("romance", "josei", "shoujo"), "romance"),
    (("slice of life", "gourmet", "iyashikei", "kids"), "slice-of-life"),
    (("comedy", "gag humor"), "comedy"),
    (("fantasy", "supernatural", "isekai", "magic", "mythology"), "fantasy"),
)

_YT_ID_RE = re.compile(r"(?:youtu\.be/|v=|/embed/|/shorts/)([A-Za-z0-9_-]{11})")


def log(msg: str) -> None:
    print(msg, flush=True)


def env(name: str, default: str = "") -> str:
    return (os.environ.get(name) or default).strip()


def site_url() -> str:
    return env("SITE_URL", "https://j-animeradar.net").rstrip("/")


def load_genre_media() -> Dict[str, dict]:
    if GENRE_MEDIA_PATH.exists():
        return json.loads(GENRE_MEDIA_PATH.read_text(encoding="utf-8"))
    return {}


def genre_key_for(genres: Optional[List[str]]) -> str:
    names = [str(g or "").strip().lower() for g in (genres or [])]
    blob = " ".join(names)
    for needles, key in _GENRE_KEYS:
        if any(n in blob for n in needles):
            return key
    return "default"


def genre_record(genres: Optional[List[str]]) -> dict:
    table = load_genre_media()
    key = genre_key_for(genres)
    row = dict(table.get(key) or table.get("default") or {})
    if env(f"WP_GENRE_MEDIA_{key.upper().replace('-', '_')}"):
        try:
            row["featured_media"] = int(env(f"WP_GENRE_MEDIA_{key.upper().replace('-', '_')}"))
        except ValueError:
            pass
    row.setdefault("key", key)
    row.setdefault("asset", f"assets/eyecatch/{key}.svg")
    row.setdefault("featured_media", 0)
    return row


def asset_url(asset: str) -> str:
    asset = (asset or "").lstrip("/")
    return f"{site_url()}/{asset}"


def extract_youtube_id(anime: dict) -> Optional[str]:
    trailer = anime.get("trailer") or {}
    if isinstance(trailer, dict):
        site = str(trailer.get("site") or trailer.get("embed_url") or "").lower()
        tid = trailer.get("youtube_id") or trailer.get("id")
        if tid and (not site or "youtube" in site or "youtu" in site):
            tid = str(tid).strip()
            if re.fullmatch(r"[A-Za-z0-9_-]{11}", tid):
                return tid
        for field in ("url", "embed_url", "image_url"):
            m = _YT_ID_RE.search(str(trailer.get(field) or ""))
            if m:
                return m.group(1)
    for lk in anime.get("external_links") or anime.get("externalLinks") or []:
        if not isinstance(lk, dict):
            continue
        site = str(lk.get("site") or "").lower()
        url = str(lk.get("url") or "")
        if "youtube" in site or "youtu.be" in url or "youtube.com" in url:
            m = _YT_ID_RE.search(url)
            if m:
                return m.group(1)
    return None


def extract_official_x(anime: dict) -> Optional[str]:
    for lk in anime.get("external_links") or anime.get("externalLinks") or []:
        if not isinstance(lk, dict):
            continue
        site = str(lk.get("site") or "").lower()
        url = str(lk.get("url") or "")
        if site in {"twitter", "x"} or "twitter.com/" in url or "x.com/" in url:
            return url
    return None


def youtube_embed_html(video_id: str) -> str:
    vid = re.sub(r"[^A-Za-z0-9_-]", "", video_id)[:11]
    return (
        '<div class="official-embed">'
        f'<iframe title="Official trailer" src="https://www.youtube-nocookie.com/embed/{vid}" '
        'width="100%" height="360" loading="lazy" allow="accelerometer; autoplay; clipboard-write; '
        'encrypted-media; gyroscope; picture-in-picture; web-share" allowfullscreen></iframe>'
        '<p class="tiny">Official trailer via YouTube. Video remains the property of the rights holders.</p>'
        "</div>"
    )


def twitter_embed_html(url: str) -> str:
    return (
        '<p class="official-x">Official social: '
        f'<a href="{url}" rel="noopener noreferrer" target="_blank">Open the official X / Twitter post</a>'
        " (no scraping; link-out only).</p>"
    )


def resolve_eyecatch(anime: dict, *, is_archive: bool = False) -> Dict[str, Any]:
    """Step 1 official YouTube/X; Step 2 genre default; Step 3 never raise."""
    rec = genre_record(anime.get("genres") or [])
    fallback_url = asset_url(rec.get("asset") or "assets/eyecatch/default.svg")
    out: Dict[str, Any] = {
        "image": fallback_url,
        "banner": fallback_url,
        "featured_media": int(rec.get("featured_media") or 0),
        "eyecatch_key": rec.get("key") or "default",
        "eyecatch_source": "genre-default",
        "youtube_id": None,
        "twitter_url": None,
        "embed_html": "",
        "is_archive": bool(is_archive),
    }
    try:
        yid = extract_youtube_id(anime)
        xurl = extract_official_x(anime)
        blocks: List[str] = []
        if yid:
            out["youtube_id"] = yid
            blocks.append(youtube_embed_html(yid))
            if not is_archive:
                thumb = f"https://img.youtube.com/vi/{yid}/hqdefault.jpg"
                out["image"] = thumb
                out["banner"] = thumb
                out["eyecatch_source"] = "youtube-thumb"
        if xurl:
            out["twitter_url"] = xurl
            blocks.append(twitter_embed_html(xurl))
        out["embed_html"] = "\n".join(blocks)
        if is_archive:
            # Past titles: keep owned genre art as the featured image; still allow official embeds in body.
            out["image"] = fallback_url
            out["banner"] = fallback_url
            if yid:
                out["eyecatch_source"] = "genre-default+youtube-embed"
            else:
                out["eyecatch_source"] = "genre-default"
    except Exception as e:
        log(f"  eyecatch fallback ({type(e).__name__}): {e}")
        out["image"] = fallback_url
        out["banner"] = fallback_url
        out["eyecatch_source"] = "genre-default-error"
        out["embed_html"] = out.get("embed_html") or ""
    return out
