"""Ranking / countdown videos ("Top 5 ...") with before->after reveals timed to the music.

Spec (JSON) - YOU provide the images and the order; nothing is fetched from the internet:
{
  "name": "top5_glowups",
  "title": "TOP 5 GLOW-UPS",
  "subtitle": "you won't believe #1",
  "format": "9:16",                      # 9:16 | 16:9 | 1:1 | 4:5
  "music": "media/audio/track.mp3",      # optional; must be music you have rights to
  "accent": "#ff3d7f",
  "seconds_per_item": 4.5,               # target; snapped to whole bars when music is given
  "items": [
    {"rank": 5, "name": "Name or label", "caption": "2019 -> 2025", "before": "media/images/a_before.jpg", "after": "media/images/a_after.jpg"},
    ...
  ]
}
Items are shown in countdown order (highest rank number first, #1 last).
Only use photos you have permission to use (consenting people / your own images).
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path

import numpy as np

from . import config
from .log import log
from .media import IMAGE_EXT, run

FMT = {"9:16": (1080, 1920), "16:9": (1920, 1080), "1:1": (1080, 1080), "4:5": (1080, 1350)}


def _snap(t: float, grid: list[float]) -> float:
    if not grid:
        return t
    g = np.array(grid)
    return float(g[np.argmin(np.abs(g - t))])


def schedule(n: int, music: dict | None, per_item: float, fps: int) -> dict:
    """Timing plan: intro, item windows and reveal times. With music, everything lands on bars/beats and the
    #1 reveal is moved onto the drop when the track has one in reach."""
    q = lambda x: round(round(x * fps) / fps, 4)  # noqa: E731 - frame-exact times
    if not music:
        intro = 2.0
        starts = [intro + i * per_item for i in range(n)]
        items = [{"start": q(s), "reveal": q(s + per_item * 0.45), "end": q(s + per_item)} for s in starts]
        items[-1]["end"] = q(items[-1]["end"] + 1.5)
        return {"intro_end": intro, "items": items, "duration": items[-1]["end"] + 0.3, "beats": [], "music_offset": 0.0,
                "notes": ["no music: fixed timing"]}
    db = music["downbeats"]
    bar = float(np.median(np.diff(db))) if len(db) > 2 else 2.0
    bars_per_item = max(1, int(round(per_item / bar)))
    L = bars_per_item * bar
    reveal_bars = max(1, int(round(0.45 * L / bar)))
    # Build to #1: pick a music start offset (on a downbeat) so the #1 reveal lands exactly on a drop,
    # with a ~2-bar intro under the title card. Earlier entries then ride the build-up.
    offset, first = 0.0, next((d for d in db if d >= 1.5), db[0] if db else 2.0)
    intro_bars = max(1, int(round(2.0 / bar)))
    for d in music.get("drops", []):
        first_needed = d - reveal_bars * bar - (n - 1) * L
        cand_off = first_needed - intro_bars * bar
        if cand_off >= -0.05 and cand_off + intro_bars * bar + n * L + bar <= music["duration"] + 0.05:
            offset, first = max(0.0, cand_off), first_needed
            break
    starts = [first + i * bars_per_item * bar for i in range(n)]
    strong = sorted({round(k["t"], 4) for k in music["kicks"] if k["s"] >= 0.5} | {round(s["t"], 4) for s in music["snares"] if s["s"] >= 0.5})
    grid = strong or music["beats"]
    items = []
    for s in starts:
        target = s + reveal_bars * bar  # reveal on a downbeat a bit before the middle -> AFTER gets more time
        lo, hi = s + 1.2, s + L - 1.2  # reveal must stay inside this entry (BEFORE and AFTER both readable)
        cands = [g for g in grid if lo <= g <= hi] or [b for b in music["beats"] if lo <= b <= hi]
        rv = _snap(target, cands) if cands else target  # quiet passage with no beats: keep the planned time
        items.append({"start": s, "reveal": rv, "end": s + L})
    notes = [f"{music['tempo_bpm']:.0f} BPM, {bars_per_item} bar(s) = {bars_per_item * bar:.2f}s per entry"]
    # put the #1 reveal on the drop if a drop falls inside / just after the last window
    last = items[-1]
    drop = next((d for d in music.get("drops", []) if last["start"] + 1.0 <= d <= last["end"]), None)
    if drop:
        last["reveal"] = drop
        last["end"] = max(last["end"], drop + 2 * bar)
        notes.append(f"#1 reveal moved onto the drop at {drop:.2f}s")
    else:
        notes.append("no drop near #1 - reveal on a strong beat")
    last["end"] += bar  # let #1 breathe
    for it in items:
        if not (it["start"] + 0.8 <= it["reveal"] <= it["end"] - 0.8):
            raise RuntimeError(f"bad reveal timing {it} - please report")
    if offset > 0:
        notes.append(f"music starts at {offset:.2f}s into the track so the drop hits the #1 reveal")
    for it in items:  # shift to the video timeline (music trimmed by `offset`)
        for k in it:
            it[k] = q(it[k] - offset)
    dur = min(items[-1]["end"] + 0.3, music["duration"] - offset)
    pulses = [round(b - offset, 4) for b in music.get("accents", []) if offset <= b < offset + dur]
    return {"intro_end": q(first - offset), "items": items, "duration": round(dur, 3), "beats": pulses,
            "music_offset": round(offset, 4), "notes": notes}


def make(spec: dict) -> dict:
    from . import qc as QC
    from . import remotion_bridge
    from . import music as M
    from .audio import loudnorm_filter

    name = spec.get("name", "ranking")
    W, H = FMT.get(spec.get("format", "9:16"), (1080, 1920))
    fps = int(spec.get("fps", 30))
    items = sorted(spec["items"], key=lambda it: -int(it["rank"]))
    if not items:
        raise ValueError("spec has no items")
    work = config.INTERMEDIATE / name
    work.mkdir(parents=True, exist_ok=True)
    pub = config.REMOTION_DIR / "public" / "ranking" / name
    if pub.exists():
        shutil.rmtree(pub)
    pub.mkdir(parents=True)
    staged = []
    for it in items:
        rec = dict(it)
        for side in ("before", "after"):
            src = Path(it[side])
            if not src.exists() or src.suffix.lower() not in IMAGE_EXT:
                raise FileNotFoundError(f"#{it['rank']} {side}: '{src}' is missing or not an image ({', '.join(sorted(IMAGE_EXT))})")
            dst = pub / f"r{it['rank']}_{side}{src.suffix.lower()}"
            shutil.copy2(src, dst)  # copy - originals are never modified
            rec[side] = f"ranking/{name}/{dst.name}"
        staged.append(rec)
    music = None
    if spec.get("music"):
        music = M.analyze(spec["music"], work)
    plan = schedule(len(staged), music, float(spec.get("seconds_per_item", 4.5)), fps)
    for rec, tm in zip(staged, plan["items"]):
        rec.update(tm)
    props = {"width": W, "height": H, "fps": fps, "durationSec": plan["duration"], "title": spec.get("title", "TOP RANKING"),
             "subtitle": spec.get("subtitle", ""), "items": staged, "beats": plan["beats"],
             "accent": spec.get("accent", "#ff3d7f"), "introEnd": plan["intro_end"]}
    (work / "ranking_plan.json").write_text(json.dumps({"props": props, "notes": plan["notes"]}, indent=2))
    for n in plan["notes"]:
        log("   " + n)
    for rec in staged:
        log(f"   #{rec['rank']:<2} {rec['name'][:30]:30s} {rec['start']:6.2f}s  reveal {rec['reveal']:6.2f}s  -> {rec['end']:6.2f}s")
    silent = remotion_bridge.render("RankingCountdown", props, work / "ranking_silent.mp4")
    out = config.EXPORTS / f"{name}.mp4"
    D = plan["duration"]
    cmd = [config.ffmpeg(), "-y", "-v", "error", "-i", str(silent)]
    if music:
        clip = work / "music_cut.wav"
        run([config.ffmpeg(), "-y", "-v", "error", "-i", spec["music"], "-af",
             f"atrim={plan.get('music_offset', 0)}:{plan.get('music_offset', 0) + D},asetpts=PTS-STARTPTS,"
             f"afade=t=in:d=0.4,afade=t=out:st={max(0, D - 1.5)}:d=1.5", "-ar", "48000", "-ac", "2", str(clip)])
        cmd += ["-i", str(clip), "-filter_complex", f"[1:a]{loudnorm_filter(clip)},aresample=48000[a]",
                "-map", "0:v", "-map", "[a]", "-c:a", "aac", "-b:a", "192k"]
    cmd += ["-t", f"{D}", "-c:v", "libx264", "-crf", "18", "-preset", "medium", "-pix_fmt", "yuv420p",
            "-movflags", "+faststart", str(out)]
    run(cmd)
    expect = {"width": W, "height": H, "fps": fps, "duration": D, "vcodec": "h264", "audio": bool(music)}
    if music:
        expect.update({"acodec": "aac", "lufs": -14.0})
    final, rep = QC.check_and_fix(out, expect)
    log("   " + QC.summarize(rep))
    return {"output": str(final), "qc": rep, "schedule": plan, "items": staged}


def placeholder_images(folder: Path, n: int = 5) -> list[dict]:
    """Clearly-fake placeholder cards (no people) for testing the template layout and timing."""
    from PIL import Image, ImageDraw, ImageFont, ImageFilter
    folder.mkdir(parents=True, exist_ok=True)
    font = ImageFont.truetype(str(config.REMOTION_DIR / "public" / "fonts" / "Anton-Regular.ttf"), 120)
    small = ImageFont.truetype(str(config.REMOTION_DIR / "public" / "fonts" / "Anton-Regular.ttf"), 54)
    rng = np.random.default_rng(3)
    out = []
    for r in range(n, 0, -1):
        paths = {}
        for side in ("before", "after"):
            w, h = 1200, 1500
            yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
            if side == "before":
                base = np.array([70, 70, 78], np.float32) + rng.uniform(-8, 8, 3)
                img = np.ones((h, w, 3), np.float32) * base + (yy / h * 25)[..., None]
            else:
                c1, c2 = rng.uniform(80, 255, 3), rng.uniform(80, 255, 3)
                k = ((xx + yy) / (w + h))[..., None]
                img = c1 * (1 - k) + c2 * k
                for _ in range(5):
                    cx, cy, rad = rng.uniform(0, w), rng.uniform(0, h), rng.uniform(150, 420)
                    img += np.exp(-((xx - cx) ** 2 + (yy - cy) ** 2) / (2 * rad * rad))[..., None] * rng.uniform(30, 90, 3)
            im = Image.fromarray(np.clip(img, 0, 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(2))
            d = ImageDraw.Draw(im)
            d.text((w / 2, h / 2 - 80), side.upper(), font=font, fill=(255, 255, 255), anchor="mm")
            d.text((w / 2, h / 2 + 60), f"PLACEHOLDER  -  ENTRY #{r}", font=small, fill=(255, 255, 255), anchor="mm")
            p = folder / f"entry{r}_{side}.jpg"
            im.save(p, quality=90)
            paths[side] = str(p)
        out.append({"rank": r, "name": f"Entry {r}", "caption": "your caption here", **paths})
    return out
