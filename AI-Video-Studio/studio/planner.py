"""Natural-language instruction -> edit plan (deterministic keyword planner).

Claude Code is the primary 'brain': it can read CLAUDE.md and write/adjust plan JSON directly.
This planner makes the CLI usable on its own and gives Claude a solid starting plan to refine.
"""
from __future__ import annotations

import re
from pathlib import Path

from . import config
from .media import AUDIO_EXT, IMAGE_EXT, VIDEO_EXT, list_media

FORMATS = [
    (r"\b(reels?|instagram|insta|shorts?|tiktok|vertical|9[:x/]16|story|stories)\b", (1080, 1920)),
    (r"\b(4[:x/]5|portrait post)\b", (1080, 1350)),
    (r"\b(square|1[:x/]1)\b", (1080, 1080)),
    (r"\b(youtube|horizontal|landscape|16[:x/]9|widescreen|1080p)\b", (1920, 1080)),
    (r"\b(4k|2160p|uhd)\b", (3840, 2160)),
]

PRESET_WORDS = [
    (r"\b(glitch|hype|energetic|aggressive|edm|gaming)\b", "glitch_energy"),
    (r"\b(moody|dark|noir|thriller)\b", "moody_dark"),
    (r"\b(retro|vintage|film look|8mm|16mm|nostalgic)\b", "retro_film"),
    (r"\b(vlog|bright|travel|happy|summer)\b", "bright_vlog"),
    (r"\b(black and white|b&w|monochrome|bw)\b", "bw_dramatic"),
    (r"\b(neon|cyberpunk|synthwave)\b", "neon_night"),
    (r"\b(clean|corporate|minimal|business)\b", "clean_corporate"),
    (r"\b(cinematic|film|movie|epic|trailer)\b", "cinematic"),
]

TRANSITION_WORDS = [
    (r"\bwhip\b", "whip"), (r"\bzoom transitions?\b", "zoomin"), (r"\bglitch transitions?\b", "glitch"),
    (r"\b(hard cuts?|jump cuts?|quick cuts?)\b", "cut"), (r"\bflash transitions?\b", "flash"),
    (r"\b(dissolves?|crossfades?|cross fades?)\b", "fade"), (r"\b(slide|wipe) transitions?\b", "slide"),
    (r"\bsmooth transitions?\b", "smoothleft"), (r"\bdip to black\b", "fadeblack"),
]


def _find(pattern: str, text: str) -> bool:
    return re.search(pattern, text, re.I) is not None


def parse_duration(text: str) -> float | None:
    m = re.search(r"(\d+(?:\.\d+)?)\s*-?\s*(s|sec|secs|second|seconds)\b", text, re.I)
    if m:
        return float(m.group(1))
    m = re.search(r"(\d+(?:\.\d+)?)\s*-?\s*(m|min|mins|minute|minutes)\b", text, re.I)
    if m:
        return float(m.group(1)) * 60
    return None


def classify_media(paths: list[str]) -> dict:
    out = {"video": [], "image": [], "audio": []}
    for p in paths:
        ext = Path(p).suffix.lower()
        if ext in VIDEO_EXT:
            out["video"].append(str(p))
        elif ext in IMAGE_EXT:
            out["image"].append(str(p))
        elif ext in AUDIO_EXT:
            out["audio"].append(str(p))
    return out


def plan_from_text(text: str, media: list[str] | None = None, music: str | None = None, name: str | None = None,
                   titles: list[str] | None = None, preset: str | None = None) -> dict:
    t = text.strip()
    media = list(media or [])
    if not media:  # default: everything in media/raw + media/images
        media = [str(p) for p in list_media(config.RAW, ("video",)) + list_media(config.IMAGES, ("image",))]
    cm = classify_media(media)
    if not music:
        music = cm["audio"][0] if cm["audio"] else None
        if not music and _find(r"\b(music|beat|song|track|soundtrack)\b", t):
            found = list_media(config.AUDIO, ("audio",))
            music = str(found[0]) if found else None

    job = "edit"
    if _find(r"\b(reference|recreate|same style|similar style|match (the )?style|like this video)\b", t):
        job = "reference"
    elif _find(r"\b(typography|kinetic|text animation|lyric|title sequence)\b", t) and not (cm["video"] or cm["image"]):
        job = "typography"

    W, H = 1080, 1920
    fmt_hit = False
    for pat, wh in FORMATS:
        if _find(pat, t):
            W, H = wh
            fmt_hit = True
            break
    if job == "typography" and not fmt_hit:
        W, H = 1920, 1080
    D = parse_duration(t) or (20.0 if job == "typography" else 15.0)

    if not preset:
        hits = [p for pat, p in PRESET_WORDS if _find(pat, t)]
        # an explicit "cinematic" wins over incidental words ("clean", "bright") unless a stronger style is named
        strong = [h for h in hits if h in ("glitch_energy", "moody_dark", "retro_film", "bw_dramatic", "neon_night")]
        preset = strong[0] if strong else ("cinematic" if "cinematic" in hits else (hits[0] if hits else "cinematic"))

    quoted = re.findall(r"[\"“]([^\"”]+)[\"”]", t)
    title_texts = titles or quoted

    plan: dict = {"job": job, "name": name or _slug(t), "preset": preset, "width": W, "height": H, "fps": 30,
                  "duration": D, "clips": [{"src": s} for s in cm["video"] + cm["image"]], "effects": {}, "audio": {"music": music}}

    tr = next((v for pat, v in TRANSITION_WORDS if _find(pat, t)), None)
    if tr:
        plan["transition"] = {"type": tr, "duration": 0.2 if tr in ("whip", "glitch", "flash") else 0.45}

    e = plan["effects"]
    if _find(r"\bgrain\b", t): e["grain"] = 10
    if _find(r"\blight ?leaks?\b", t): e["light_leaks"] = "cuts"
    if _find(r"\bglitch", t): e["glitch_on_cuts"] = True
    if _find(r"\b(rgb split|chromatic|aberration)\b", t): e["rgb_split"] = 4
    if _find(r"\b(shake|handheld)\b", t): e["shake"] = 10
    if _find(r"\bmotion blur\b", t): e["motion_blur"] = 3
    if _find(r"\b(letterbox|cinema bars|black bars)\b", t): e["letterbox"] = True
    if _find(r"\bvignette\b", t): e["vignette"] = True
    if _find(r"\bflash(es)? on (the )?beats?\b", t): e["flash_on_beats"] = True
    if _find(r"\b(punch|zoom) on (the )?beats?\b", t): e["punch_on_beats"] = True
    if _find(r"\b(slow ?mo|slow motion|speed ramp|ramps?)\b", t):
        for i, c in enumerate(plan["clips"]):
            if i % 2 == 1 and Path(c["src"]).suffix.lower() not in IMAGE_EXT:
                c["ramp"] = 0.6
    if _find(r"\b(zoom|ken burns|push in)\b", t) and not _find(r"zoom transition", t):
        for i, c in enumerate(plan["clips"]):
            c.setdefault("zoom", "in" if i % 2 == 0 else "out")

    if music and _find(r"\b(beat|sync|synchroni[sz]ed|rhythm|on the music|to the music)\b", t):
        plan["cut_mode"] = "beats"
        m = re.search(r"every (\d+) beats?", t, re.I)
        plan["beat_every"] = 0.5 * int(m.group(1)) if m else 1.5
    if _find(r"\b(keep|original) (the )?(audio|sound|voice)\b", t) or (not music and _find(r"\b(voice|dialogue|talking|interview)\b", t)):
        plan["audio"]["keep_original"] = True
    if _find(r"\b(clean ?up|denoise|noise reduction)\b.*\b(voice|audio)\b|\bvoice clean", t):
        plan["audio"]["voice_cleanup"] = True
        plan["audio"]["keep_original"] = True
    if _find(r"\b(subtitles?|captions?|transcri)", t):
        style = "boxed" if _find(r"\bboxed\b", t) else "clean" if _find(r"\bclean captions?\b", t) else "bold_pop"
        plan["captions"] = {"auto": True, "style": style, "model": "small"}

    want_type = _find(r"\b(typography|titles?|text|kinetic|lower thirds?)\b", t)
    if title_texts or want_type:
        if title_texts:
            texts = title_texts
        else:  # no quoted text: use a cleaned-up name of the first clip (pass --title or "quotes" for real copy)
            first = Path(plan["clips"][0]["src"]).stem if plan["clips"] else "my edit"
            first = re.sub(r"^(clip|vid|video|img|dsc|mvi)[_\-\s]*", "", first, flags=re.I)
            texts = [re.sub(r"[_\-]+", " ", first).strip().upper()[:28] or "MY EDIT"]
            plan["_note"] = "No title text given - placeholder used. Add text in \"quotes\" or pass --title."
        style = ("lowerthird" if _find(r"lower thirds?", t) else "glitch" if preset == "glitch_energy"
                 else "typewriter" if _find(r"typewriter", t) else "kinetic")
        n = len(texts)
        span = min(3.0, D / max(1, n) * 0.8)
        plan["titles"] = [{"text": s, "start": round(0.4 + i * (D / max(1, n)), 2), "duration": round(span, 2),
                           "position": "center" if i == 0 else "bottom"} for i, s in enumerate(texts)]
        plan["title_style"] = style
    if _find(r"\b3d (title|text|intro)\b", t):
        plan["intro_3d"] = {"text": (title_texts or [plan["name"].upper()])[0], "duration": 3.0}
    if _find(r"\blogo\b", t):
        plan["outro_logo"] = {"text": (title_texts or ["STUDIO"])[0], "tagline": "", "duration": 2.5}
    if job == "typography":
        plan["lines"] = title_texts or ["MAKE IT MOVE", "FEEL THE RHYTHM", "OWN THE FRAME"]
        if not title_texts:
            plan["_note"] = "No lines given - default lines used. Put each line in \"quotes\" or pass --title per line."
        plan["camera"] = "dramatic" if _find(r"\b(dramatic|dynamic|camera)\b", t) else "subtle"
    return plan


def _slug(t: str) -> str:
    words = re.findall(r"[a-z0-9]+", t.lower())[:5]
    return "_".join(words) or "edit"
