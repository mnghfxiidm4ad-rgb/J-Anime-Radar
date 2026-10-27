# -*- coding: utf-8 -*-
"""Source-sales radar for the current cour.

The watch list lives in data/targets.json and is rebuilt per season.
Manual jp_title, track_formats, enabled, and rakuten_keyword survive the rebuild.

  python scripts/anime_radar_pipeline.py --sync-targets
  python scripts/anime_radar_pipeline.py --fetch
  python scripts/anime_radar_pipeline.py --generate
  python scripts/anime_radar_pipeline.py --all
  python scripts/anime_radar_pipeline.py --generate --title "Blue Box" --ep 2
"""

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

import requests

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover
    def load_dotenv(*_a, **_k):
        return False

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
POSTS = DATA / "posts"
TARGETS = DATA / "targets.json"
RADAR = DATA / "manga_sales_radar.json"
BRIEFINGS = ROOT / "content" / "briefings"
RAKUTEN_URL = "https://app.rakuten.co.jp/services/api/BooksBook/Search/20170404"
GENRES = {"manga": "001001", "light_novel": "001017"}
FORMAT_LABEL = {"manga": "Manga", "light_novel": "Light novel"}

# Applied only when a title has no saved override yet.
FORMAT_HINTS = (
    ("apothecary diaries", ["manga", "light_novel"], "薬屋のひとりごと"),
    ("blue box", ["manga"], "アオのハコ"),
    ("bleach", ["manga"], "BLEACH"),
    ("reincarnated aristocrat", ["manga", "light_novel"], "転生貴族、鑑定スキルで成り上がる"),
    ("overgeared", ["manga"], "テムパル〜アイテムの力〜"),
)

HOW_TO_UPDATE = (
    "When the cour changes, run: python scripts/anime_radar_pipeline.py --sync-targets. "
    "The previous season stays in seasons[]. The active list is rebuilt from the current Top 20. "
    "jp_title, track_formats, enabled, and rakuten_keyword you already set are kept. "
    "Set enabled to false to stop tracking a title without deleting that choice."
)


def env(name: str, default: str = "") -> str:
    return (os.environ.get(name) or default).strip()


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def season_of(moment: Optional[datetime] = None) -> tuple:
    moment = moment or datetime.now()
    month = moment.month
    year = moment.year
    if month <= 3:
        return f"{year}-winter", f"{year} Winter", f"{year} W"
    if month <= 6:
        return f"{year}-spring", f"{year} Spring", f"{year} Sp"
    if month <= 9:
        return f"{year}-summer", f"{year} Summer", f"{year} Su"
    return f"{year}-fall", f"{year} Fall", f"{year} F"


def season_clock() -> tuple:
    """Label for the site header. Prefers the active season stored in targets.json."""
    doc = load_targets()
    active = doc.get("active_season") or ""
    for season in doc.get("seasons") or []:
        if season.get("id") == active and season.get("label"):
            short = {
                "winter": "W",
                "spring": "Sp",
                "summer": "Su",
                "fall": "F",
            }
            tail = active.split("-")[-1] if "-" in active else ""
            year = active.split("-")[0]
            return season["label"], f"{year} {short.get(tail, tail[:1].upper())}"
    sid, label, short = season_of()
    return label, short


def norm(text: str) -> str:
    text = (text or "").lower()
    text = re.sub(r"[^a-z0-9\u3040-\u30ff\u4e00-\u9fff]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def clean_native(title: str) -> str:
    title = (title or "").strip()
    title = re.sub(r"\s*第\s*\d+\s*期.*$", "", title)
    title = re.sub(r"\s*(season|シーズン)\s*\d+.*$", "", title, flags=re.I)
    return title.strip() or (title or "").strip()


def load_json(path: Path, fallback: Any) -> Any:
    if not path.exists():
        return fallback
    return json.loads(path.read_text(encoding="utf-8"))


def save_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def load_targets() -> dict:
    doc = load_json(TARGETS, {})
    if not isinstance(doc, dict):
        doc = {}
    doc.setdefault("overrides", {})
    doc.setdefault("seasons", [])
    doc.setdefault("how_to_update", HOW_TO_UPDATE)
    return doc


def active_titles(doc: Optional[dict] = None) -> List[dict]:
    doc = doc or load_targets()
    active = doc.get("active_season")
    for season in doc.get("seasons") or []:
        if season.get("id") == active:
            return [row for row in (season.get("titles") or []) if row.get("enabled", True)]
    return []


def latest_native_by_mal() -> Dict[str, str]:
    found: Dict[str, tuple] = {}
    if not POSTS.exists():
        return {}
    for path in POSTS.glob("*.json"):
        try:
            post = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if post.get("kind") == "feature":
            continue
        mal = str(post.get("mal_id") or "")
        native = clean_native(post.get("title_native") or "")
        if not mal or not native:
            continue
        episode = int(post.get("episode") or 0)
        prev = found.get(mal)
        if prev is None or episode >= prev[0]:
            found[mal] = (episode, native)
    return {mal: native for mal, (_ep, native) in found.items()}


def hint_for(title: str) -> tuple:
    lowered = (title or "").lower()
    for needle, formats, jp in FORMAT_HINTS:
        if needle in lowered:
            return formats, jp
    return ["manga"], ""


def override_key(mal_id: Any, title: str) -> str:
    if mal_id:
        return str(mal_id)
    return "title:" + norm(title)


PRIORITY_PROFILES = (
    {
        "needle": "apothecary diaries",
        "jp_title": "薬屋のひとりごと",
        "track_formats": ["manga", "light_novel"],
        "cour_info": {"is_multi_cour": True, "current_cour": 2, "total_cours": 2, "label": "Cour 2/2"},
        "priority": 1,
    },
    {
        "needle": "blue box",
        "jp_title": "アオのハコ",
        "track_formats": ["manga"],
        "cour_info": {"is_multi_cour": True, "current_cour": 2, "total_cours": 2, "label": "Cour 2/2"},
        "priority": 2,
    },
    {
        "needle": "bleach",
        "jp_title": "BLEACH",
        "track_formats": ["manga"],
        "cour_info": {"is_multi_cour": True, "current_cour": 3, "total_cours": 4, "label": "Cour 3/4"},
        "priority": 3,
    },
    {
        "needle": "steel ball run",
        "jp_title": "スティール・ボール・ラン",
        "track_formats": ["manga"],
        "cour_info": {"is_multi_cour": True, "current_cour": 2, "total_cours": 3, "label": "Cour 2/3"},
        "priority": 4,
    },
    {
        "needle": "reincarnated aristocrat",
        "jp_title": "転生貴族、鑑定スキルで成り上がる",
        "track_formats": ["manga", "light_novel"],
        "cour_info": {"is_multi_cour": False, "current_cour": 1, "total_cours": 1, "label": "Single Cour"},
        "priority": 5,
    },
)

SINGLE_COUR = {"is_multi_cour": False, "current_cour": 1, "total_cours": 1, "label": "Single Cour"}


def profile_for(title: str) -> Optional[dict]:
    lowered = (title or "").lower()
    for profile in PRIORITY_PROFILES:
        if profile["needle"] in lowered:
            return profile
    return None


def fold_overrides(doc: dict) -> None:
    """Treat the current season list as the latest manual edits."""
    overrides = doc.setdefault("overrides", {})
    for season in doc.get("seasons") or []:
        if season.get("id") != doc.get("active_season"):
            continue
        for row in season.get("titles") or []:
            key = override_key(row.get("mal_id"), row.get("en_title") or "")
            overrides[key] = {
                "jp_title": row.get("jp_title") or "",
                "track_formats": row.get("track_formats") or ["manga"],
                "enabled": bool(row.get("enabled", True)),
                "rakuten_keyword": row.get("rakuten_keyword") or row.get("jp_title") or "",
                "cour_info": row.get("cour_info") or SINGLE_COUR,
                "priority": row.get("priority") or 100,
            }


def sync_targets() -> dict:
    ranking = load_json(DATA / "ranking.json", {})
    items = [row for row in (ranking.get("items") or []) if int(row.get("rank") or 99) <= 20]
    natives = latest_native_by_mal()
    doc = load_targets()
    fold_overrides(doc)
    sid, label, _short = season_of()
    titles = []
    for row in items:
        title = row.get("title") or ""
        mal = row.get("mal_id")
        key = override_key(mal, title)
        saved = (doc.get("overrides") or {}).get(key) or {}
        formats, hinted_jp = hint_for(title)
        jp = saved.get("jp_title") or natives.get(str(mal)) or hinted_jp
        if not saved and hinted_jp:
            jp = hinted_jp
        formats = saved.get("track_formats") or formats
        profile = profile_for(title)
        if profile:
            jp = profile["jp_title"]
            formats = list(profile["track_formats"])
        cour = (profile or {}).get("cour_info") or saved.get("cour_info") or SINGLE_COUR
        priority = (profile or {}).get("priority") or saved.get("priority") or (100 + int(row.get("rank") or 99))
        titles.append(
            {
                "en_title": title,
                "jp_title": jp,
                "mal_id": mal,
                "rank": row.get("rank"),
                "track_formats": formats,
                "rakuten_keyword": jp,
                "cour_info": cour,
                "priority": priority,
                "enabled": saved.get("enabled", True) if saved else True,
            }
        )
    seasons = [season for season in (doc.get("seasons") or []) if season.get("id") != sid]
    seasons.append(
        {
            "id": sid,
            "label": label,
            "updated_at": now_iso(),
            "titles": titles,
        }
    )
    seasons.sort(key=lambda season: season.get("id") or "")
    doc["active_season"] = sid
    doc["updated_at"] = now_iso()
    doc["how_to_update"] = HOW_TO_UPDATE
    doc["seasons"] = seasons
    save_json(TARGETS, doc)
    print(f"targets {sid}: {len(titles)} titles")
    return doc


def enabled_targets() -> List[dict]:
    rows = active_titles()
    if not rows and TARGETS.exists():
        raw = load_json(TARGETS, [])
        if isinstance(raw, list):
            return [row for row in raw if row.get("enabled", True)]
    return rows


def pick_item(items: List[dict], keyword: str) -> Optional[dict]:
    key = norm(keyword)
    if not key:
        return None
    for item in items:
        if key in norm(item.get("title") or ""):
            return item
    return None


def volume_of(title: str) -> str:
    match = re.search(r"(?:第?\s*)(\d{1,3})\s*(?:巻|vol\.?)", title or "", flags=re.I)
    if match:
        return match.group(1)
    tail = re.search(r"(\d{1,3})\s*$", title or "")
    return tail.group(1) if tail else ""


def search_rakuten(keyword: str, genre_id: str, app_id: str, affiliate: str) -> Optional[dict]:
    params = {
        "applicationId": app_id,
        "format": "json",
        "booksGenreId": genre_id,
        "keyword": keyword,
        "sort": "sales",
        "hits": 5,
    }
    if affiliate:
        params["affiliateId"] = affiliate
    response = requests.get(RAKUTEN_URL, params=params, timeout=30)
    if response.status_code == 429:
        time.sleep(2)
        response = requests.get(RAKUTEN_URL, params=params, timeout=30)
    response.raise_for_status()
    items = [row.get("Item") or {} for row in (response.json().get("Items") or [])]
    chosen = pick_item(items, keyword)
    if not chosen:
        return None
    url = chosen.get("affiliateUrl") or chosen.get("itemUrl") or ""
    title = chosen.get("title") or ""
    return {
        "title": title,
        "volume": volume_of(title),
        "price": chosen.get("itemPrice"),
        "review_average": chosen.get("reviewAverage") or "",
        "review_count": int(chosen.get("reviewCount") or 0),
        "image": chosen.get("largeImageUrl") or chosen.get("mediumImageUrl") or "",
        "url": url,
    }


def leading_format(books: Dict[str, Optional[dict]], formats: List[str]) -> str:
    present = [name for name in formats if books.get(name)]
    if present == ["manga"]:
        return "manga_driven"
    if present == ["light_novel"]:
        return "novel_driven"
    if len(present) < 2:
        return "manga_driven" if "manga" in present else "novel_driven"
    manga_count = int((books.get("manga") or {}).get("review_count") or 0)
    novel_count = int((books.get("light_novel") or {}).get("review_count") or 0)
    if manga_count >= novel_count * 1.5 and manga_count > novel_count:
        return "manga_driven"
    if novel_count >= manga_count * 1.5 and novel_count > manga_count:
        return "novel_driven"
    return "balanced"


def badge_for(row: dict) -> str:
    books = row.get("books") or {}
    formats = row.get("track_formats") or []
    lead = row.get("leading_format") or ""
    dual = "manga" in formats and "light_novel" in formats and books.get("manga") and books.get("light_novel")
    if dual and lead == "balanced":
        return "Dual Surge (Manga & LN)"
    if dual and lead == "novel_driven":
        return "LN Driven"
    if dual and lead == "manga_driven":
        return "Manga Driven"
    book = books.get("light_novel") if lead == "novel_driven" else books.get("manga") or books.get("light_novel")
    if not book:
        return ""
    kind = "LN" if book is books.get("light_novel") and lead == "novel_driven" else "Manga"
    if book is books.get("light_novel") and not books.get("manga"):
        kind = "LN"
    vol = book.get("volume") or ""
    suffix = f" (Vol.{vol})" if vol else ""
    return f"{kind} Spike{suffix}"


def factual_line(row: dict) -> str:
    books = row.get("books") or {}
    bits = []
    for key in ("manga", "light_novel"):
        book = books.get(key)
        if not book:
            continue
        label = FORMAT_LABEL[key]
        vol = f" vol.{book['volume']}" if book.get("volume") else ""
        reviews = int(book.get("review_count") or 0)
        stars = book.get("review_average") or "n/a"
        bits.append(f"{label}{vol} is the current Rakuten mover ({stars} stars, {reviews} reviews)")
    if not bits:
        return ""
    lead = {
        "manga_driven": "The comic side is pulling the shelf.",
        "novel_driven": "The light novel side is pulling the shelf.",
        "balanced": "Comic and light novel are sharing the shelf.",
    }.get(row.get("leading_format") or "", "")
    return " ".join(bits) + ". " + lead


def fetch_sales(only_title: str = "") -> dict:
    app_id = env("RAKUTEN_APP_ID")
    if not app_id:
        raise SystemExit("STOP missing RAKUTEN_APP_ID")
    affiliate = env("RAKUTEN_AFFILIATE_ID")
    targets = enabled_targets()
    if only_title:
        needle = only_title.lower()
        targets = [row for row in targets if needle in (row.get("en_title") or "").lower() or needle in (row.get("jp_title") or "")]
    sid, label, _short = season_of()
    payload_titles = []
    for index, target in enumerate(targets):
        keyword = target.get("rakuten_keyword") or target.get("jp_title") or target.get("en_title")
        books: Dict[str, Optional[dict]] = {}
        for fmt in target.get("track_formats") or ["manga"]:
            genre = GENRES.get(fmt)
            if not genre or not keyword:
                continue
            try:
                books[fmt] = search_rakuten(keyword, genre, app_id, affiliate)
            except requests.RequestException as exc:
                print(f"  rakuten {target.get('en_title')} {fmt}: {exc.__class__.__name__}")
                books[fmt] = None
            time.sleep(1.1)
        row = {
            "en_title": target.get("en_title"),
            "jp_title": target.get("jp_title"),
            "mal_id": target.get("mal_id"),
            "track_formats": target.get("track_formats") or ["manga"],
            "books": books,
        }
        row["leading_format"] = leading_format(books, row["track_formats"])
        row["badge"] = badge_for(row)
        row["market_line"] = factual_line(row)
        payload_titles.append(row)
        print(f"[{index + 1}/{len(targets)}] {row['en_title']} -> {row['badge'] or 'no hit'}")
    payload = {
        "season": sid,
        "season_label": label,
        "fetched_at": now_iso(),
        "titles": payload_titles,
    }
    save_json(RADAR, payload)
    return payload


def load_radar() -> dict:
    doc = load_json(RADAR, {})
    return doc if isinstance(doc, dict) else {}


def sales_lookup() -> Dict[str, dict]:
    found: Dict[str, dict] = {}
    for row in (load_radar().get("titles") or []):
        prepared = dict(row)
        prepared["book_list"] = book_list(row)
        if row.get("mal_id"):
            found["mal:" + str(row["mal_id"])] = prepared
        if row.get("en_title"):
            found["title:" + norm(row["en_title"])] = prepared
    return found


def match_sales(record: dict, lookup: Dict[str, dict]) -> Optional[dict]:
    mal = record.get("mal_id")
    if mal and ("mal:" + str(mal)) in lookup:
        return lookup["mal:" + str(mal)]
    title = record.get("anime_title") or record.get("title") or record.get("en_title") or ""
    return lookup.get("title:" + norm(title))


def book_list(row: dict) -> List[dict]:
    out = []
    for key in ("manga", "light_novel"):
        book = (row.get("books") or {}).get(key)
        if not book or not book.get("url"):
            continue
        price = book.get("price")
        price_label = f"¥{int(price):,}" if isinstance(price, (int, float)) else ""
        out.append(
            {
                "format_label": FORMAT_LABEL[key],
                "title": book.get("title") or "",
                "volume": book.get("volume") or "",
                "price": price_label,
                "review_average": book.get("review_average") or "",
                "review_count": book.get("review_count") or 0,
                "image": book.get("image") or "",
                "url": book.get("url") or "",
            }
        )
    return out


def attach_sales(posts: List[dict], ranking: List[dict]) -> dict:
    lookup = sales_lookup()
    for post in posts:
        post["sales"] = match_sales(post, lookup)
    for row in ranking:
        row["sales"] = match_sales(row, lookup)
    doc = load_targets()
    sid = doc.get("active_season")
    season = next((item for item in (doc.get("seasons") or []) if item.get("id") == sid), None)
    if not season:
        return {}
    titles = []
    for row in season.get("titles") or []:
        if not row.get("enabled", True):
            continue
        sales = match_sales(row, lookup)
        formats = row.get("track_formats") or []
        titles.append(
            {
                "en_title": row.get("en_title"),
                "jp_title": row.get("jp_title"),
                "format_label": " + ".join(FORMAT_LABEL.get(fmt, fmt) for fmt in formats),
                "cour_label": (row.get("cour_info") or {}).get("label") or "",
                "dual": "manga" in formats and "light_novel" in formats,
                "badge": (sales or {}).get("badge") or "",
                "priority": row.get("priority") or 100,
            }
        )
    by_mal = {str(row.get("mal_id")): row for row in (season.get("titles") or [])}
    for row in ranking:
        target = by_mal.get(str(row.get("mal_id")))
        if not target:
            continue
        formats = target.get("track_formats") or []
        row["cour_label"] = (target.get("cour_info") or {}).get("label") or ""
        row["dual"] = "manga" in formats and "light_novel" in formats
    return {"label": season.get("label") or sid, "titles": titles}


def market_context_block(anime: dict) -> str:
    sales = match_sales(anime or {}, sales_lookup())
    if not sales or not sales.get("market_line"):
        return ""
    dual = ""
    books = sales.get("books") or {}
    if books.get("manga") and books.get("light_novel"):
        dual = (
            "\nIn Domestic Radar, add a Dual-Market Pulse (Manga vs. Light Novel Dynamics): "
            "comic shelves pulling in a wider crowd versus the light novel holding the core readers. "
            "Use only the numbers above."
        )
    return (
        "\n\nMARKET CONTEXT (Rakuten Books, this cour only; do not invent extra chart facts):\n"
        + sales["market_line"]
        + "\nleading_format: "
        + str(sales.get("leading_format") or "")
        + dual
    )


def polish_lines(payload: dict) -> None:
    """One optional pass so the shelf line sounds like the desk. Numbers stay from Rakuten."""
    key = env("OPENAI_API_KEY") or env("GEMINI_API_KEY")
    if not key:
        return
    facts = [
        {
            "en_title": row.get("en_title"),
            "leading_format": row.get("leading_format"),
            "fact": row.get("market_line"),
        }
        for row in payload.get("titles") or []
        if row.get("market_line")
    ]
    if not facts:
        return
    instruction = (
        "Rewrite each fact as one spoken English sentence a Tokyo fan would text a friend. "
        "Keep every number. Do not add ranks, print runs, or shops. "
        "Return JSON array of {en_title, market_line}."
    )
    text = ""
    if env("OPENAI_API_KEY"):
        response = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {env('OPENAI_API_KEY')}", "Content-Type": "application/json"},
            json={
                "model": env("OPENAI_MODEL", "gpt-4o"),
                "temperature": 0.7,
                "messages": [
                    {"role": "system", "content": instruction},
                    {"role": "user", "content": json.dumps(facts, ensure_ascii=False)},
                ],
            },
            timeout=90,
        )
        if response.ok:
            text = (((response.json().get("choices") or [{}])[0].get("message") or {}).get("content") or "")
    elif env("GEMINI_API_KEY"):
        model = env("GEMINI_MODEL", "gemini-flash-latest")
        response = requests.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
            headers={"x-goog-api-key": env("GEMINI_API_KEY"), "Content-Type": "application/json"},
            json={
                "contents": [{"role": "user", "parts": [{"text": instruction + "\n" + json.dumps(facts, ensure_ascii=False)}]}],
                "generationConfig": {"temperature": 0.7, "responseMimeType": "application/json"},
            },
            timeout=90,
        )
        if response.ok:
            parts = (((response.json().get("candidates") or [{}])[0].get("content") or {}).get("parts") or [])
            text = "\n".join(part.get("text") or "" for part in parts)
    if not text:
        print("market lines left as Rakuten facts")
        return
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip(), flags=re.I)
    try:
        rewritten = json.loads(text)
    except json.JSONDecodeError:
        print("market lines left as Rakuten facts")
        return
    by_title = {norm(item.get("en_title") or ""): item.get("market_line") or "" for item in rewritten if isinstance(item, dict)}
    for row in payload.get("titles") or []:
        line = by_title.get(norm(row.get("en_title") or ""))
        if line:
            row["market_line"] = line
    save_json(RADAR, payload)


def slugify(text: str) -> str:
    text = (text or "").lower()
    text = re.sub(r"[^a-z0-9]+", "-", text).strip("-")
    return text or "briefing"


def find_post(title: str, episode: int) -> Optional[dict]:
    needle = norm(title)
    best = None
    for path in POSTS.glob("*.json"):
        try:
            post = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if norm(post.get("anime_title") or "") != needle and needle not in norm(post.get("anime_title") or ""):
            continue
        if int(post.get("episode") or 0) != episode:
            continue
        best = post
    return best


def sales_for_title(title: str) -> Optional[dict]:
    needle = (title or "").lower()
    for row in (load_radar().get("titles") or []):
        if needle and needle in (row.get("en_title") or "").lower():
            return row
    return None


def markdown_briefing(title: str, episode: int, post: dict, sales: Optional[dict]) -> str:
    subtitle = post.get("episode_title") or "Breakdown"
    quick = post.get("quick_take") or post.get("pullquote") or ""
    hook = "\n\n".join(post.get("synopsis_paragraphs") or [])
    hood = "\n\n".join((post.get("sakuga_paragraphs") or []) + (post.get("voice_paragraphs") or []))
    domestic = list(post.get("story_paragraphs") or [])
    if sales and sales.get("market_line"):
        domestic.append(sales["market_line"])
    books = (sales or {}).get("books") or {}
    if books.get("manga") and books.get("light_novel"):
        domestic.append(
            "Dual-Market Pulse (Manga vs. Light Novel Dynamics): "
            + (sales.get("market_line") or "Both formats are on the shelf this cour.")
        )
    score = post.get("desk_score") or post.get("score") or "Unscored"
    verdict = post.get("one_sentence_verdict") or quick
    streaming = post.get("licensed_streaming") or ", ".join(
        item.get("name") for item in (post.get("watch") or []) if isinstance(item, dict) and item.get("name")
    )
    lines = [
        f"# {title} – Episode {episode} Breakdown: {subtitle}",
        "",
        f"> **The Quick Take:** {quick}",
        "",
        "### 1. The Hook: What Made This Episode Unmissable",
        "",
        hook,
        "",
        "### 2. Under the Hood: Direction & Craft That Stole the Show",
        "",
        hood,
        "",
        "### 3. Domestic Radar: What Japanese Fans Are Screaming About",
        "",
        "\n\n".join(domestic),
        "",
        "### Verdict & Intel",
        "",
        f"- **Score:** {score} / 100",
        f"- **One-Sentence Verdict:** {verdict}",
        f"- **Streaming:** {streaming or 'Check a licensed platform in your region.'}",
        "",
    ]
    return "\n".join(lines).strip() + "\n"


def write_briefing(title: str, episode: int, post: Optional[dict] = None) -> Path:
    post = post if post is not None else (find_post(title, episode) or {})
    sales = sales_for_title(title)
    slug = post.get("slug") or f"{slugify(title)}-ep{episode}"
    BRIEFINGS.mkdir(parents=True, exist_ok=True)
    path = BRIEFINGS / f"{slug}.md"
    path.write_text(markdown_briefing(title, episode, post, sales), encoding="utf-8")
    print(f"wrote {path.relative_to(ROOT)}")
    return path


def latest_episode_on_desk(title: str, mal_id: Any) -> int:
    ranking = load_json(DATA / "ranking.json", {})
    for row in ranking.get("items") or []:
        if mal_id and str(row.get("mal_id")) == str(mal_id):
            return int(row.get("latest") or 0)
        if norm(row.get("title") or "") == norm(title):
            return int(row.get("latest") or 0)
    return 0


def saved_episode(title: str) -> int:
    best = 0
    needle = norm(title)
    if not POSTS.exists():
        return 0
    for path in POSTS.glob("*.json"):
        try:
            post = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if needle not in norm(post.get("anime_title") or ""):
            continue
        best = max(best, int(post.get("episode") or 0))
    return best


def chat_with_retry(prompt: str) -> str:
    """OpenAI when a key exists, otherwise Gemini. Three tries, then a longer wait."""
    last_error = "no model call"
    for attempt in range(3):
        try:
            if env("OPENAI_API_KEY"):
                response = requests.post(
                    "https://api.openai.com/v1/chat/completions",
                    headers={"Authorization": f"Bearer {env('OPENAI_API_KEY')}", "Content-Type": "application/json"},
                    json={
                        "model": env("OPENAI_MODEL", "gpt-4o"),
                        "temperature": 0.7,
                        "messages": [
                            {"role": "system", "content": "You write J-Anime Radar episode breakdowns."},
                            {"role": "user", "content": prompt},
                        ],
                    },
                    timeout=120,
                )
            elif env("GEMINI_API_KEY"):
                model = env("GEMINI_MODEL", "gemini-flash-latest")
                response = requests.post(
                    f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
                    headers={"x-goog-api-key": env("GEMINI_API_KEY"), "Content-Type": "application/json"},
                    json={
                        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
                        "generationConfig": {"temperature": 0.7, "maxOutputTokens": 4096},
                    },
                    timeout=120,
                )
            else:
                raise RuntimeError("no OPENAI_API_KEY or GEMINI_API_KEY")
            if response.status_code == 429 or response.status_code >= 500:
                wait = 12 * (2 ** attempt)
                print(f"  retry {attempt + 1} after HTTP {response.status_code}; sleep {wait}s")
                time.sleep(wait)
                last_error = f"http {response.status_code}"
                continue
            response.raise_for_status()
            if env("OPENAI_API_KEY"):
                return (((response.json().get("choices") or [{}])[0].get("message") or {}).get("content") or "").strip()
            parts = (((response.json().get("candidates") or [{}])[0].get("content") or {}).get("parts") or [])
            return "\n".join(part.get("text") or "" for part in parts).strip()
        except requests.RequestException as exc:
            wait = 12 * (2 ** attempt)
            print(f"  retry {attempt + 1} after {exc.__class__.__name__}; sleep {wait}s")
            time.sleep(wait)
            last_error = exc.__class__.__name__
    raise RuntimeError(last_error)


def ranking_row_for(title: str, mal_id: Any) -> dict:
    ranking = load_json(DATA / "ranking.json", {})
    for row in ranking.get("items") or []:
        if mal_id and str(row.get("mal_id")) == str(mal_id):
            return row
        if norm(row.get("title") or "") == norm(title):
            return row
    return {}


def generate(title: str = "", episode: int = 0, limit: int = 20) -> None:
    """Export briefings for enabled titles after the latest episode has finished.

    Priority titles go first, then the rest of the season desk. New HTML articles
    are published by the episode job, which also waits for the broadcast to end.
    """
    from fetch_and_summarize import episode_broadcast_ended, finished_episode  # noqa: E402

    targets = enabled_targets()
    if title:
        needle = title.lower()
        targets = [row for row in targets if needle in (row.get("en_title") or "").lower() or needle in (row.get("jp_title") or "")]
    targets.sort(key=lambda row: int(row.get("priority") or 100))
    ready = []
    for target in targets:
        name = target.get("en_title") or ""
        row = ranking_row_for(name, target.get("mal_id"))
        anime = {
            "latest_episode": row.get("latest"),
            "next_episode": row.get("next_episode"),
            "next_airing_at": row.get("next_airing_at"),
            "latest_episode_aired": row.get("latest_episode_aired"),
        }
        clocked = bool(anime.get("next_airing_at") or anime.get("latest_episode_aired"))
        if episode:
            ep = episode
            if clocked and not episode_broadcast_ended(anime, ep):
                print(f"skip {name} ep{ep}: broadcast has not ended")
                continue
        elif clocked:
            ep = finished_episode(anime)
        else:
            ep = saved_episode(name)
        if not ep:
            print(f"skip {name}: latest broadcast has not ended")
            continue
        if not find_post(name, ep):
            print(f"skip {name} ep{ep}: finished, waiting for the episode publisher")
            continue
        ready.append((name, ep))
    ready = ready[: max(1, limit)]
    for name, ep in ready:
        write_briefing(name, ep)
    print(f"briefings written: {len(ready)}")


def main() -> int:
    load_dotenv(ROOT / ".env")
    parser = argparse.ArgumentParser(description="Seasonal source-sales radar")
    parser.add_argument("--sync-targets", action="store_true")
    parser.add_argument("--fetch", action="store_true")
    parser.add_argument("--generate", action="store_true")
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--title", default="")
    parser.add_argument("--ep", type=int, default=0)
    parser.add_argument("--limit", type=int, default=20)
    args = parser.parse_args()
    if args.all:
        args.sync_targets = True
        args.fetch = True
        args.generate = True
    if not any((args.sync_targets, args.fetch, args.generate)):
        parser.error("choose --sync-targets, --fetch, --generate, or --all")
    if args.sync_targets or args.fetch:
        sync_targets()
    if args.fetch:
        fetch_sales(args.title)
    if args.generate:
        generate(args.title, args.ep, args.limit)
    return 0


if __name__ == "__main__":
    sys.exit(main())
