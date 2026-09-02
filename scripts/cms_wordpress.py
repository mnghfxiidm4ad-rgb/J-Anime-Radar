# -*- coding: utf-8 -*-
"""Optional WordPress REST publisher. Static docs/ remains the source of truth when WP_* is unset."""

from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
import base64


def env(name: str, default: str = "") -> str:
    return (os.environ.get(name) or default).strip()


def log(msg: str) -> None:
    print(msg, flush=True)


def _enabled() -> bool:
    return bool(env("WP_URL") and env("WP_USER") and env("WP_APP_PASSWORD"))


def _auth_header() -> str:
    token = base64.b64encode(f"{env('WP_USER')}:{env('WP_APP_PASSWORD')}".encode("utf-8")).decode("ascii")
    return f"Basic {token}"


def _int_env(name: str) -> Optional[int]:
    raw = env(name)
    if not raw:
        return None
    try:
        n = int(raw)
        return n if n > 0 else None
    except ValueError:
        return None


def build_wp_payload(post: dict, html: str, eyecatch: dict) -> Dict[str, Any]:
    """Map a Radar post to WP REST /wp/v2/posts fields, including featured_media fallback."""
    kind = post.get("kind") or "episode"
    title = post.get("headline") or (
        f"{post.get('anime_title')} Episode {post.get('episode')} — {post.get('episode_title')}"
    )
    cat = _int_env("WP_CATEGORY_FEATURE") if kind == "feature" else _int_env("WP_CATEGORY_EPISODE")
    tags: List[int] = []
    for key in (env("WP_TAG_IDS") or "").split(","):
        key = key.strip()
        if key.isdigit() and int(key) > 0:
            tags.append(int(key))
    payload: Dict[str, Any] = {
        "title": title,
        "content": html,
        "status": env("WP_STATUS", "draft") or "draft",
        "excerpt": (post.get("pullquote") or post.get("episode_title") or "")[:180],
        "meta": {
            "radar_slug": post.get("slug"),
            "radar_kind": kind,
            "radar_mal_id": post.get("mal_id"),
            "eyecatch_source": (eyecatch or {}).get("eyecatch_source") or post.get("eyecatch_source"),
        },
    }
    if cat:
        payload["categories"] = [cat]
    if tags:
        payload["tags"] = tags
    media_id = int((eyecatch or {}).get("featured_media") or post.get("featured_media") or 0)
    if media_id > 0:
        payload["featured_media"] = media_id
    return payload


def publish_post(post: dict, html: str, eyecatch: Optional[dict] = None) -> Optional[dict]:
    """Never raise into the daily pipeline. Missing WP config is a no-op."""
    if not _enabled():
        return None
    eyecatch = eyecatch or {
        "featured_media": post.get("featured_media") or 0,
        "eyecatch_source": post.get("eyecatch_source"),
    }
    base = env("WP_URL").rstrip("/")
    url = f"{base}/wp-json/wp/v2/posts"
    payload = build_wp_payload(post, html, eyecatch)
    body = json.dumps(payload).encode("utf-8")
    req = Request(
        url,
        data=body,
        method="POST",
        headers={
            "Authorization": _auth_header(),
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "J-Anime-Radar/1.0",
        },
    )
    try:
        with urlopen(req, timeout=45) as res:
            data = json.loads(res.read().decode("utf-8"))
        log(f"  WordPress OK id={data.get('id')} status={data.get('status')}")
        return data
    except HTTPError as e:
        log(f"  WordPress HTTP {e.code}; continuing without CMS abort")
        try:
            log(f"  {e.read()[:300]!r}")
        except Exception:
            pass
        return None
    except (URLError, TimeoutError, json.JSONDecodeError, Exception) as e:
        log(f"  WordPress skipped ({type(e).__name__}: {e})")
        return None
