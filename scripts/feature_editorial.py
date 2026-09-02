# -*- coding: utf-8 -*-
"""Feature (non-episode) editorial: separate Gemini prompt, JSON parser, seed fallback."""

from __future__ import annotations

import json
import os
import re
import time
from typing import Any, Dict, List, Optional

GEMINI_FEATURE_PROMPT = """You are a senior critic at J-Anime Radar, an English-language desk introducing Japanese anime to overseas readers.

Write an ORIGINAL series-level recommendation. This is NOT an episode recap and NOT a Wikipedia dump.
Do not paste official synopses verbatim. Do not invent interviews, fake viral tweets, or named fan accounts.
Keep plot description spoiler-light: premise and tone only, no late-game reveals.

Return ONLY compact JSON with these keys:
- headline (string; follow this shape in English: "【Recommended Anime】The Appeal of 『TITLE』 — Synopsis, Highlights, and Watch Guide")
- recommended_for (string; 40-80 words; who should start this title)
- intro (string; 90-140 words; basic facts + why it still matters)
- spoiler_free_synopsis (string; 110-160 words; premise without late spoilers)
- highlights (array of 2 or 3 objects: {"title": short label, "body": 70-110 words})
- platforms_and_close (string; 90-140 words; legal viewing advice + closing argument)
- vibe (short string; e.g. "Quiet Masterpiece", "Battle Classic", "Romance Staple")
- credit_hint (string; studio / original author if known from context; otherwise empty)

Total original prose must exceed 500 words. No markdown. No preamble.
"""

REQUIRED = (
    "headline",
    "recommended_for",
    "intro",
    "spoiler_free_synopsis",
    "highlights",
    "platforms_and_close",
)


def env(name: str, default: str = "") -> str:
    return (os.environ.get(name) or default).strip()


def _words(text: str) -> int:
    return len(re.findall(r"[A-Za-z0-9']+", text or ""))


def _clean(text: str) -> str:
    return re.sub(r"<[^>]+>", "", text or "").replace("\r", " ").replace("\n", " ").strip()


def parse_feature_json(text: str) -> dict:
    text = (text or "").strip()
    text = re.sub(r"^```json\s*|\s*```$", "", text, flags=re.I | re.M).strip()
    data = json.loads(text)
    missing = [k for k in REQUIRED if k not in data]
    if missing:
        raise ValueError(f"missing keys: {missing}")
    highs = data.get("highlights") or []
    if not isinstance(highs, list) or len(highs) < 2:
        raise ValueError("need 2+ highlights")
    norm = []
    for h in highs[:3]:
        if isinstance(h, dict):
            norm.append({"title": str(h.get("title") or "Highlight"), "body": str(h.get("body") or "")})
        else:
            norm.append({"title": "Highlight", "body": str(h)})
    data["highlights"] = [h for h in norm if h["body"].strip()]
    if len(data["highlights"]) < 2:
        raise ValueError("empty highlights")
    return data


def compose_feature_review(anime: dict, *, feature_kind: str) -> dict:
    english = anime.get("title_english") or anime.get("title") or "This title"
    native = anime.get("title_native") or ""
    studio = anime.get("studio") or "the credited studio"
    genres = ", ".join(anime.get("genres") or ["Drama"]) or "Drama"
    score = anime.get("score")
    score_s = f"community score around {score}" if score else "a reputation that outlived its cour"
    premise = _clean(anime.get("description") or "")[:420]
    if not premise:
        premise = f"{english} remains a reference point for {genres.lower()} anime rather than a nostalgia sticker."
    kind_line = (
        "It is airing this season outside the Top 20 desk, which is exactly why a guide still helps."
        if feature_kind == "offrank"
        else "It is a past work we are recommending as an archive briefing, not a new broadcast recap."
    )
    headline = f"【Recommended Anime】The Appeal of 『{english}』 — Synopsis, Highlights, and Watch Guide"
    recommended_for = (
        f"Start here if you want {genres.lower()} with a finished (or clearly shaped) thesis, not another unfinished seasonal experiment. "
        f"Readers who bounce off recap-blog padding should like this desk's angle: craft, tone, and legal platforms. "
        f"{kind_line} If you already live on chart-chasing sequels, this page is a palate cleanser."
    )
    intro = (
        f"{english}" + (f" ({native})" if native else "") + f" is credited to {studio}, filed under {genres}. "
        f"Public catalogs currently show {score_s}; that is heat, not a grade. "
        f"J-Anime Radar is introducing the series as a whole: who it is for, what the premise actually promises, and which viewing habits it rewards. "
        f"{kind_line} "
        f"We are not pretending a 22-minute recap can replace the show. We are arguing why the show is still a better use of a weekend than another algorithm suggestion. "
        f"The production committee, original author, and licensors remain the rights holders; this page is criticism and recommendation, not a substitute stream."
    )
    synopsis = (
        f"Spoiler-light premise only. The public pitch is a floor: {premise} "
        f"What matters for a first-time viewer is the contract: {english} asks you to care about {genres.lower()} texture—pace, faces, the cost of a choice—rather than a weekly power announcement. "
        f"Do not hunt late-game twists on this page. The useful question is whether the opening hours teach you the world's rules honestly. "
        f"If a scene would only make sense after a finale, we leave it off. If a scene explains why someone stays in the room, it belongs in a recommendation. "
        f"Treat the first cour (or the first film movement) as a thesis statement: tone, visual grammar, and whether the lead is a person or a merchandising silhouette."
    )
    h1 = {
        "title": "Tone before trivia",
        "body": (
            f"The first reason to queue {english} is not a trivia badge. {studio} stages {genres.lower()} as atmosphere you can sit in: blocking, silence, and whether a joke is allowed to hurt. "
            f"Japanese first-night culture around classics and mid-table seasonal shows still grades those things faster than plot wikis. "
            f"If you only remember a super move, you watched the trailer inside the series. If you remember a doorway, a meal, or a line that landed like a cost, you watched the show."
        ),
    }
    h2 = {
        "title": "Why it still clears the desk",
        "body": (
            f"Overseas lists flatten everything into 'must watch.' This title earns a page because the craft problem it solves is still rare in {genres.lower()} television: "
            f"a consistent moral temperature, a studio fingerprint, and characters who accumulate obligations instead of catchphrases. "
            f"{kind_line} A recommendation should change what you do tonight, not pad a keyword. If you start {english} after this briefing, start legally and start from episode one (or the intended film order)."
        ),
    }
    h3 = {
        "title": "How to watch without spoiling yourself",
        "body": (
            f"Skip comment sections that treat endings as sport. Use a licensed platform, turn off autoplay into a sequel you did not choose, and give the show two consecutive episodes before you judge the score. "
            f"Community numbers around {english} describe attention, not craft. If the opening hours feel slow, ask whether the slowness is the point—especially in archive titles that taught later seasons how to breathe."
        ),
    }
    close = (
        f"Watch {english} on a licensed service in your region. Availability rotates; the buttons below are starting points, not a rights map. "
        f"If your country is missing a seat, wait or use another official storefront—do not use this site as an excuse to pirate. "
        f"J-Anime Radar does not host video. We recommend {english} because a seasonal Top 20 desk still needs a memory: not every worthwhile series is airing in the current rank window. "
        f"When you finish, you will have a better eye for the next cour's imitators. That is the whole job of an archive (or off-rank) briefing."
    )
    payload = {
        "headline": headline,
        "recommended_for": recommended_for.strip(),
        "intro": intro.strip(),
        "spoiler_free_synopsis": synopsis.strip(),
        "highlights": [h1, h2, h3],
        "platforms_and_close": close.strip(),
        "vibe": "Archive Signal" if feature_kind == "archive" else "Off-Rank Spotlight",
        "credit_hint": studio,
        "_source": "editorial-seed",
    }
    blob = " ".join(
        [
            payload["headline"],
            payload["recommended_for"],
            payload["intro"],
            payload["spoiler_free_synopsis"],
            " ".join(h["body"] for h in payload["highlights"]),
            payload["platforms_and_close"],
        ]
    )
    payload["_word_count"] = _words(blob)
    return payload


def gemini_feature_review(anime: dict, *, feature_kind: str) -> Optional[dict]:
    api_key = env("GEMINI_API_KEY")
    if not api_key:
        return None
    try:
        import google.generativeai as genai
    except ImportError:
        return None

    genai.configure(api_key=api_key)
    models: List[str] = []
    preferred = env("GEMINI_MODEL", "gemini-1.5-flash")
    for m in [preferred, "gemini-1.5-flash", "gemini-2.0-flash", "gemini-2.5-flash", "gemini-flash-latest"]:
        if m and m not in models:
            models.append(m)

    user = {
        "title_english": anime.get("title_english"),
        "title_romaji": anime.get("title_romaji"),
        "title_native": anime.get("title_native"),
        "studio": anime.get("studio"),
        "genres": anime.get("genres"),
        "score": anime.get("score"),
        "source": anime.get("source"),
        "year": anime.get("season_year") or anime.get("year"),
        "feature_kind": feature_kind,
        "description": (anime.get("description") or "")[:900],
        "licensed_platforms": anime.get("watch"),
    }
    prompt = GEMINI_FEATURE_PROMPT + "\n\nSERIES CONTEXT:\n" + json.dumps(user, ensure_ascii=False)
    last_err = None
    for model_name in models:
        for attempt in range(4):
            try:
                model = genai.GenerativeModel(model_name)
                resp = model.generate_content(
                    prompt,
                    generation_config={"temperature": 0.7, "max_output_tokens": 4096},
                )
                data = parse_feature_json(resp.text or "")
                data.setdefault("vibe", "Recommended Anime")
                data["_source"] = "gemini"
                print(f"  Gemini feature OK ({model_name})", flush=True)
                time.sleep(8)
                return data
            except Exception as e:
                last_err = e
                msg = str(e).lower()
                if "429" in msg or "resource exhausted" in msg:
                    wait = 20 * (attempt + 1)
                    print(f"  Gemini 429 on {model_name}; sleep {wait}s", flush=True)
                    time.sleep(wait)
                    continue
                print(f"  Gemini feature error on {model_name}: {e}", flush=True)
                break
        time.sleep(2)
    print(f"  Gemini feature failed ({last_err}); seed fallback", flush=True)
    return None
