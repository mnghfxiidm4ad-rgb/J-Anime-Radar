# -*- coding: utf-8 -*-
"""Rewrite stored posts with Gemini, one at a time. Resumes by skipping gemini-insider."""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))

from editorial import GEMINI_SYSTEM_INSTRUCTION, parse_gemini_review  # noqa: E402
from feature_editorial import parse_feature_json  # noqa: E402
from fetch_and_summarize import paragraphs  # noqa: E402

POSTS = ROOT / "data" / "posts"
LOG = ROOT / "data" / "gemini_rewrite.log"
DONE = "gemini-insider"
SLEEP_OK = 50
MODELS = [
    "gemini-3.5-flash",
    "gemini-3-flash-preview",
    "gemini-3.1-flash-lite",
    "gemini-flash-lite-latest",
    "gemini-3.5-flash-lite",
]
BANNED = (
    "plot dump",
    "opening contract",
    "public catalog pitch",
    "sensory disorientation",
    "tactile labor",
    "let me talk about",
    "here is the part people outside japan",
)


def log(msg: str) -> None:
    print(msg, flush=True)
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a", encoding="utf-8") as handle:
        handle.write(msg + "\n")


def _env_value(text: str, name: str) -> str:
    match = re.search(rf"^{re.escape(name)}=(.*)$", text, re.M)
    if not match:
        return ""
    return match.group(1).strip().strip('"').strip("'")


def load_key() -> str:
    local = ROOT / ".env"
    if local.exists():
        value = _env_value(local.read_text(encoding="utf-8", errors="replace"), "GEMINI_API_KEY")
        if value:
            return value
    value = (os.environ.get("GEMINI_API_KEY") or "").strip()
    if value:
        return value
    for path in (
        Path(r"D:\For_work01\IndieGem\.env"),
        Path(r"D:\For_work01\note記事\.env"),
    ):
        if path.exists():
            value = _env_value(path.read_text(encoding="utf-8", errors="replace"), "GEMINI_API_KEY")
            if value:
                return value
    return ""


def draft_text(post: dict) -> str:
    chunks = []
    if post.get("kind") == "feature":
        chunks.append(post.get("recommended_for") or "")
        chunks.extend(post.get("intro_paragraphs") or [])
        chunks.extend(post.get("synopsis_paragraphs") or [])
        for item in post.get("highlights") or []:
            chunks.append(item.get("title") or "")
            chunks.append(item.get("body") or "")
        chunks.extend(post.get("close_paragraphs") or [])
    else:
        chunks.append(post.get("episode_title") or "")
        chunks.append(post.get("quick_take") or "")
        chunks.extend(post.get("synopsis_paragraphs") or [])
        chunks.extend(post.get("sakuga_paragraphs") or [])
        chunks.extend(post.get("story_paragraphs") or [])
        chunks.extend(post.get("voice_paragraphs") or [])
        chunks.extend(post.get("takeaway_paragraphs") or [])
    text = "\n\n".join(str(chunk) for chunk in chunks if chunk)
    return text[:7500]


def platforms(post: dict) -> str:
    names = []
    for item in post.get("watch") or []:
        name = item.get("name") if isinstance(item, dict) else str(item)
        name = (name or "").strip()
        if name and name not in names:
            names.append(name)
    return ", ".join(names) if names else "a licensed platform already linked on the page"


def episode_prompt(post: dict) -> str:
    title = post.get("anime_title") or "Untitled"
    episode = post.get("episode")
    return f"""Rewrite the SOURCE DRAFT into a finished episode article for J-Anime Radar.

This is a rewrite of the draft, not a research assignment.
- Keep concrete events, character beats, staff names, seiyuu names, and Japanese quotes that are already in the draft.
- If a sentence is grammatically broken, repair that meaning. Do not invent a new scene to fill a hole.
- If the draft never names a specific scene, do not invent a fight, a confession, a score, or a death. Write honestly about the pressure of this series at this point in the season.
- Sound like one person who just finished the broadcast and is talking to a friend. Contractions are good. Vary the first sentence. Do not start with "Let me talk about" or "Here is the part people outside Japan".
- No lecture vocabulary. No "plot dump", "opening contract", or "public catalog pitch".
- If the draft has a Japanese 「」 line, keep its sharpest clause and explain the slang in plain English. Do not attribute it to a named account.
- Licensed platforms, use only these: {platforms(post)}

SERIES
- title: {title}
- native: {post.get("title_native") or ""}
- episode: {episode}
- studio: {post.get("studio") or ""}
- genres: {", ".join(post.get("genres") or [])}

SOURCE DRAFT
{draft_text(post)}

Return ONLY compact JSON (no markdown fence) with:
- episode_title (catchy subtitle only, not the series name)
- quick_take (1-2 screenshot sentences)
- episode_synopsis_analysis (the hook, 2 short paragraphs, no heading)
- japan_fan_reactions object with sakuga_and_direction, voice_acting_highlights, story_and_lore
  sakuga and voice are markdown bullets starting with - **Label:**
  story_and_lore is 2 markdown bullets: - **「Japanese」 (English):** why it landed
- one_sentence_verdict
- desk_score (integer 1-100)
- licensed_streaming (platform names from the list above)
- deep_dive_takeaway (verdict plus one sentence naming the platforms)
- episode_vibe (short plain label)
At least 450 words of original prose. Every sentence has to sound said, not generated.
"""


def feature_prompt(post: dict) -> str:
    title = post.get("anime_title") or "Untitled"
    return f"""Rewrite this series recommendation so it sounds like a friend pressing a show into someone's hands. Not a brochure. Not a Wikipedia page.

Keep the premise facts already in the draft. No late-game spoilers. No invented interviews.
Licensed platforms, use only these: {platforms(post)}

SERIES
- title: {title}
- native: {post.get("title_native") or ""}
- studio: {post.get("studio") or ""}
- genres: {", ".join(post.get("genres") or [])}

SOURCE DRAFT
{draft_text(post)}

Return ONLY compact JSON with:
- headline
- recommended_for (40-80 words)
- intro (90-140 words)
- spoiler_free_synopsis (110-160 words)
- highlights (2 or 3 objects with title and body; body 70-110 words)
- platforms_and_close (90-140 words)
- vibe (short)
Total prose over 450 words. Sound like a person.
"""


def words(text: str) -> int:
    return len(re.findall(r"[A-Za-z0-9']+", text or ""))


def generate(api_key: str, prompt: str) -> str:
    last_error = "no attempt"
    for model in MODELS:
        for attempt in range(5):
            try:
                response = requests.post(
                    f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
                    headers={"x-goog-api-key": api_key, "Content-Type": "application/json"},
                    json={
                        "systemInstruction": {"parts": [{"text": GEMINI_SYSTEM_INSTRUCTION}]},
                        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
                        "generationConfig": {
                            "temperature": 0.8,
                            "maxOutputTokens": 4096,
                            "responseMimeType": "application/json",
                        },
                    },
                    timeout=120,
                )
            except requests.RequestException as exc:
                last_error = f"network {exc.__class__.__name__}"
                time.sleep(15)
                continue
            if response.status_code == 429:
                message = ""
                try:
                    message = (response.json().get("error") or {}).get("message") or ""
                except Exception:
                    message = response.text or ""
                delay = re.search(r"retry in (\d+)h", message, re.I)
                if delay:
                    log(f"  daily quota on {model}; next model")
                    last_error = f"daily {model}"
                    break
                wait = 30 * (attempt + 1)
                log(f"  429 on {model}; sleep {wait}s")
                time.sleep(wait)
                last_error = "429"
                continue
            if response.status_code == 404:
                log(f"  model {model} not found")
                last_error = "404"
                break
            if response.status_code >= 500:
                last_error = f"http {response.status_code}"
                time.sleep(20)
                continue
            if response.status_code >= 400:
                # responseMimeType can 400 on some models. Retry once without it.
                if attempt == 0 and "responseMimeType" in (response.text or ""):
                    last_error = "mime"
                    continue
                detail = (response.text or "")[:180].replace("\n", " ")
                raise SystemExit(f"STOP http {response.status_code} {detail}")
            data = response.json()
            parts = (((data.get("candidates") or [{}])[0].get("content") or {}).get("parts") or [])
            text = "\n".join(part.get("text") or "" for part in parts).strip()
            if not text:
                last_error = "empty"
                time.sleep(10)
                continue
            log(f"  model {model}")
            return text
    if str(last_error).startswith("daily"):
        raise SystemExit("STOP daily quota on every configured model. Resume after the free-tier window resets.")
    raise RuntimeError(last_error)


def acceptable(text: str) -> bool:
    lowered = (text or "").lower()
    if any(phrase in lowered for phrase in BANNED):
        return False
    return words(text) >= 380



def as_text(value):
    if value is None:
        return ""
    if isinstance(value, list):
        return "\n".join(as_text(item) for item in value if item is not None)
    if isinstance(value, dict):
        return "\n".join(as_text(item) for item in value.values())
    return str(value)


def apply_episode(post: dict, review: dict) -> None:
    reactions = review.get("japan_fan_reactions") or {}
    if not isinstance(reactions, dict):
        reactions = {}
    quick = as_text(review.get("quick_take")).strip()
    verdict = as_text(review.get("one_sentence_verdict")).strip()
    hook = as_text(review.get("episode_synopsis_analysis"))
    hood = as_text(reactions.get("sakuga_and_direction"))
    voice = as_text(reactions.get("voice_acting_highlights"))
    radar = as_text(reactions.get("story_and_lore"))
    take = as_text(review.get("deep_dive_takeaway")) or verdict
    review["quick_take"] = quick
    review["one_sentence_verdict"] = verdict
    review["episode_synopsis_analysis"] = hook
    review["deep_dive_takeaway"] = take
    review["episode_title"] = as_text(review.get("episode_title")).strip()
    review["episode_vibe"] = as_text(review.get("episode_vibe")).strip()
    review["licensed_streaming"] = as_text(review.get("licensed_streaming")).strip()
    reactions["sakuga_and_direction"] = hood
    reactions["voice_acting_highlights"] = voice
    reactions["story_and_lore"] = radar
    review["japan_fan_reactions"] = reactions
    score = review.get("desk_score")
    try:
        score = int(score)
    except (TypeError, ValueError):
        score = None
    if score is not None and not 1 <= score <= 100:
        score = None
    streaming = as_text(review.get("licensed_streaming")).strip() or platforms(post)
    review["_source"] = DONE
    review["where_to_watch"] = post.get("watch") or []
    post["episode_title"] = review.get("episode_title") or post.get("episode_title")
    post["episode_vibe"] = review.get("episode_vibe") or post.get("episode_vibe")
    post["quick_take"] = quick
    post["pullquote"] = quick or verdict
    post["one_sentence_verdict"] = verdict
    post["desk_score"] = score
    post["licensed_streaming"] = streaming
    post["synopsis_paragraphs"] = paragraphs(hook)
    post["sakuga_paragraphs"] = paragraphs(hood)
    post["story_paragraphs"] = paragraphs(radar)
    post["voice_paragraphs"] = paragraphs(voice)
    post["takeaway_paragraphs"] = paragraphs(take)
    post["raw"] = review
    post["source"] = DONE


def apply_feature(post: dict, review: dict) -> None:
    review["_source"] = DONE
    post["headline"] = review.get("headline") or post.get("headline")
    post["episode_title"] = post["headline"]
    post["episode_vibe"] = review.get("vibe") or post.get("episode_vibe")
    post["recommended_for"] = review.get("recommended_for") or ""
    post["pullquote"] = (review.get("recommended_for") or "")[:280]
    post["intro_paragraphs"] = paragraphs(review.get("intro") or "")
    post["synopsis_paragraphs"] = paragraphs(review.get("spoiler_free_synopsis") or "")
    post["highlights"] = review.get("highlights") or []
    post["close_paragraphs"] = paragraphs(review.get("platforms_and_close") or "")
    post["takeaway_paragraphs"] = paragraphs(review.get("platforms_and_close") or "")
    post["quick_take"] = post["pullquote"]
    post["one_sentence_verdict"] = (review.get("platforms_and_close") or "").split(".")[0][:220]
    post["raw"] = review
    post["source"] = DONE


def blob_of(post: dict) -> str:
    if post.get("kind") == "feature":
        parts = [post.get("recommended_for") or "", post.get("pullquote") or ""]
        parts.extend(post.get("intro_paragraphs") or [])
        parts.extend(post.get("synopsis_paragraphs") or [])
        return "\n".join(str(part) for part in parts)
    parts = [post.get("quick_take") or ""]
    parts.extend(post.get("synopsis_paragraphs") or [])
    parts.extend(post.get("sakuga_paragraphs") or [])
    parts.extend(post.get("story_paragraphs") or [])
    return "\n".join(str(part) for part in parts)


def rewrite_post(api_key: str, post: dict) -> None:
    feature = post.get("kind") == "feature"
    prompt = feature_prompt(post) if feature else episode_prompt(post)
    last = "none"
    for attempt in range(2):
        text = generate(api_key, prompt if attempt == 0 else prompt + "\n\nThe previous draft still sounded like a template or was too short. Rewrite it again, specific and spoken.")
        try:
            if feature:
                review = parse_feature_json(text)
                apply_feature(post, review)
            else:
                review = parse_gemini_review(text, {"watch": post.get("watch") or []}, int(post.get("episode") or 1))
                apply_episode(post, review)
        except Exception as exc:
            last = f"parse {exc}"
            continue
        if acceptable(blob_of(post)):
            return
        last = "thin or banned phrasing"
    raise RuntimeError(last)


def pending_paths(only_slug: str) -> list:
    rows = []
    for path in POSTS.glob("*.json"):
        post = json.loads(path.read_text(encoding="utf-8"))
        if post.get("source") == DONE:
            continue
        if only_slug and path.stem != only_slug and post.get("slug") != only_slug:
            continue
        kind_rank = 0 if post.get("kind") != "feature" else 1
        aired = str(post.get("aired") or "")
        rows.append((kind_rank, aired, path.name, path))
    rows.sort(key=lambda item: (item[0], item[1], item[2]), reverse=False)
    # newest episodes first, features after
    episodes = [item for item in rows if item[0] == 0]
    features = [item for item in rows if item[0] == 1]
    episodes.sort(key=lambda item: (item[1], item[2]), reverse=True)
    return [item[3] for item in episodes + features]


def rebuild() -> None:
    subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "fetch_and_summarize.py"), "--rebuild-only"],
        cwd=ROOT,
        check=False,
    )


def main() -> int:
    limit = None
    only_slug = ""
    args = sys.argv[1:]
    if "--limit" in args:
        limit = int(args[args.index("--limit") + 1])
    if "--slug" in args:
        only_slug = args[args.index("--slug") + 1]
    api_key = load_key()
    if not api_key:
        log("STOP no API key")
        return 1
    paths = pending_paths(only_slug)
    if limit is not None:
        paths = paths[:limit]
    log(f"queue {len(paths)}")
    done = 0
    for index, path in enumerate(paths, 1):
        post = json.loads(path.read_text(encoding="utf-8"))
        label = post.get("slug") or path.stem
        log(f"[{index}/{len(paths)}] {label}")
        try:
            rewrite_post(api_key, post)
        except SystemExit as exc:
            log(str(exc))
            return 1
        except Exception as exc:
            log(f"  FAIL {label}: {exc}")
            time.sleep(SLEEP_OK)
            continue
        path.write_text(json.dumps(post, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        done += 1
        log(f"  OK {label} {words(blob_of(post))}w | {(post.get('quick_take') or '')[:140]}")
        if done % 8 == 0:
            log("  rebuilding HTML")
            rebuild()
        if index != len(paths):
            time.sleep(SLEEP_OK)
    log(f"queue done ok={done} attempted={len(paths)}")
    if done:
        rebuild()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
