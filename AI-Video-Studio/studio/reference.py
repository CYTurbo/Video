"""Reference-video style analysis, style transfer to an edit plan, and output-vs-reference comparison.

What is measured (and how):
  pacing       PySceneDetect ContentDetector + own frame-difference analysis -> shot list, ASL, cuts/min
  transitions  per boundary: hard cut / dissolve (gradual diff ramp) / dip-to-black / flash-to-white
  colour       Lab mean/contrast, saturation, shadow & highlight tint, black/white levels
  grain        high-frequency residual in flat areas (relative, not absolute ISO)
  motion       Farneback optical flow: magnitude, pan direction, zoom (divergence), shake (jitter)
  text         HEURISTIC text-region detector (morphological), aggregated to top / middle / bottom
  letterbox    FFmpeg cropdetect
  music sync   fraction of cuts within 100 ms of a detected beat (if the reference has audio)
"""
from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

import numpy as np

from . import config
from .log import log
from .media import contact_sheet, extract_frames, probe, run

LW, LH = 192, 108  # low-res analysis size (keeps analysis fast on any machine)


def _frames_lowres(path: str, fps_cap: float = 30.0):
    info = probe(path)
    v = info["video"]
    fps = min(v["fps"] or 30, fps_cap)
    w = LW if v["width"] >= v["height"] else LH
    h = LH if v["width"] >= v["height"] else LW
    cmd = [config.ffmpeg(), "-v", "error", "-i", path, "-vf", f"fps={fps},scale={w}:{h}", "-f", "rawvideo",
           "-pix_fmt", "rgb24", "-"]
    raw = subprocess.run(cmd, capture_output=True).stdout
    arr = np.frombuffer(raw, np.uint8)
    n = len(arr) // (w * h * 3)
    return arr[: n * w * h * 3].reshape(n, h, w, 3), fps, info


def _scenes(path: str) -> list[float]:
    try:
        from scenedetect import ContentDetector, detect
        sc = detect(path, ContentDetector(threshold=27.0, min_scene_len=6))
        return [s[0].get_seconds() for s in sc[1:]]
    except Exception as e:  # noqa: BLE001
        log(f"   PySceneDetect failed ({e}); using frame-difference only", echo=False)
        return []


def _boundaries(frames: np.ndarray, fps: float) -> tuple[list[dict], np.ndarray, np.ndarray]:
    g = frames.astype(np.float32).mean(axis=3)
    luma = g.mean(axis=(1, 2))
    diff = np.zeros(len(g))
    diff[1:] = np.abs(g[1:] - g[:-1]).mean(axis=(1, 2))
    out = []
    # hard cuts: a single-frame spike well above the LOCAL difference level (robust to fast-moving content)
    for i in range(1, len(diff)):
        lo, hi = max(1, i - 15), min(len(diff), i + 16)
        # a cut separates two shots: compare against the quieter side (the other side may be fast motion)
        before, after = diff[lo:max(lo, i - 1)], diff[i + 2:hi]
        sides = [float(np.median(x)) for x in (before, after) if len(x) >= 3]
        local = min(sides) if sides else 0.0
        near = np.r_[diff[max(1, i - 2):i], diff[i + 1:i + 3]]
        if diff[i] > 10 and diff[i] > 2.5 * local + 6 and (len(near) == 0 or diff[i] >= near.max()):
            out.append({"t": i / fps, "type": "cut"})
    # dips to black / flashes to white
    for i in range(2, len(luma) - 2):
        if luma[i] < 12 and luma[i] <= luma[i - 1] and luma[i] <= luma[i + 1] and luma[max(0, i - 8)] > 30:
            out.append({"t": i / fps, "type": "fadeblack"})
        if luma[i] > 235 and luma[i] >= luma[i - 1] and luma[i] >= luma[i + 1] and luma[max(0, i - 6)] < 200:
            out.append({"t": i / fps, "type": "fadewhite"})
    # dissolves: sustained elevated difference AND the middle frame is a linear blend of the window's end frames
    win = max(6, int(fps * 0.25))
    sm = np.convolve(diff, np.ones(win) / win, mode="same")
    base = np.median(sm)
    gf = g
    i = 1
    while i < len(sm):
        if sm[i] > max(3.0, base * 3):
            j = i
            while j < len(sm) and sm[j] > max(3.0, base * 3):
                j += 1
            a0, a1 = max(0, i - 1), min(len(gf) - 1, j)
            if j - i >= win and a1 - a0 >= 4:
                m = (a0 + a1) // 2
                span = float(np.abs(gf[a1] - gf[a0]).mean())
                blend_err = float(np.abs(gf[m] - (gf[a0] + gf[a1]) / 2).mean()) / (span + 1e-6)
                if span > 8 and blend_err < 0.3 and not any(abs(b["t"] - (i + j) / 2 / fps) < 0.3 for b in out):
                    out.append({"t": (i + j) / 2 / fps, "type": "dissolve", "dur": round((j - i) / fps, 2)})
            i = j
        i += 1
    out.sort(key=lambda b: b["t"])
    merged = []
    for b in out:
        if merged and abs(b["t"] - merged[-1]["t"]) < 0.25:
            if b["type"] != "cut":
                merged[-1] = b
            continue
        merged.append(b)
    return merged, diff, luma


def colour_stats(frames: np.ndarray) -> dict:
    import cv2
    idx = np.linspace(0, len(frames) - 1, min(40, len(frames))).astype(int)
    Ls, As, Bs, Ss, shA, shB, hiA, hiB, p2, p98 = ([] for _ in range(10))
    for i in idx:
        f = frames[i].astype(np.float32) / 255.0
        lab = cv2.cvtColor(f, cv2.COLOR_RGB2LAB)
        hsv = cv2.cvtColor(f, cv2.COLOR_RGB2HSV)
        L, a, b = lab[..., 0], lab[..., 1], lab[..., 2]
        Ls.append((L.mean(), L.std()))
        As.append(a.mean()); Bs.append(b.mean()); Ss.append(hsv[..., 1].mean())
        sh, hi = L < 30, L > 70
        if sh.any():
            shA.append(a[sh].mean()); shB.append(b[sh].mean())
        if hi.any():
            hiA.append(a[hi].mean()); hiB.append(b[hi].mean())
        p2.append(np.percentile(L, 2)); p98.append(np.percentile(L, 98))
    Ls = np.array(Ls)
    m = lambda x: round(float(np.mean(x)), 2) if len(x) else None  # noqa: E731
    return {"L_mean": m(Ls[:, 0]), "L_contrast": m(Ls[:, 1]), "a_mean": m(As), "b_mean": m(Bs),
            "saturation": round(float(np.mean(Ss)), 3), "shadow_tint_ab": [m(shA), m(shB)],
            "highlight_tint_ab": [m(hiA), m(hiB)], "black_level": m(p2), "white_level": m(p98),
            "warmth": "warm" if m(Bs) and m(Bs) > 6 else "cool" if m(Bs) is not None and m(Bs) < -3 else "neutral"}


def lab_moments(frames: np.ndarray) -> dict:
    import cv2
    idx = np.linspace(0, len(frames) - 1, min(30, len(frames))).astype(int)
    labs = np.concatenate([cv2.cvtColor(frames[i].astype(np.float32) / 255.0, cv2.COLOR_RGB2LAB).reshape(-1, 3) for i in idx])
    return {"mean": labs.mean(0).tolist(), "std": labs.std(0).tolist()}


def motion_stats(frames: np.ndarray, fps: float) -> dict:
    import cv2
    step = max(1, int(round(fps / 15)))
    mags, dx, dy, div = [], [], [], []
    h, w = frames.shape[1:3]
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    rx, ry = xx - w / 2, yy - h / 2
    rn = np.sqrt(rx ** 2 + ry ** 2) + 1e-3
    prev = cv2.cvtColor(frames[0], cv2.COLOR_RGB2GRAY)
    for i in range(step, len(frames), step):
        cur = cv2.cvtColor(frames[i], cv2.COLOR_RGB2GRAY)
        fl = cv2.calcOpticalFlowFarneback(prev, cur, None, 0.5, 3, 15, 3, 5, 1.2, 0)
        prev = cur
        mags.append(float(np.linalg.norm(fl, axis=2).mean()) / w * 100 / step)
        dx.append(float(fl[..., 0].mean()) / w * 100 / step)
        dy.append(float(fl[..., 1].mean()) / h * 100 / step)
        div.append(float(((fl[..., 0] * rx + fl[..., 1] * ry) / rn).mean()) / w * 100 / step)
    if not mags:
        return {}
    dxa = np.array(dx)
    jitter = float(np.abs(np.diff(dxa)).mean()) if len(dxa) > 2 else 0.0
    return {"motion_pct_per_frame": round(float(np.mean(mags)), 3), "pan_x": round(float(np.mean(dx)), 3),
            "pan_y": round(float(np.mean(dy)), 3), "zoom_divergence": round(float(np.mean(div)), 3),
            "shake_jitter": round(jitter, 3),
            "level": "high" if np.mean(mags) > 1.2 else "medium" if np.mean(mags) > 0.4 else "low"}


def grain_estimate(path: str, duration: float) -> float:
    import cv2
    vals = []
    for t in np.linspace(duration * 0.1, duration * 0.9, 5):
        raw = subprocess.run([config.ffmpeg(), "-v", "error", "-ss", f"{t:.2f}", "-i", path, "-frames:v", "1", "-vf",
                              "crop='min(640,iw)':'min(360,ih)'", "-f", "image2pipe", "-vcodec", "png", "-"], capture_output=True).stdout
        g = cv2.imdecode(np.frombuffer(raw, np.uint8), cv2.IMREAD_GRAYSCALE) if raw else None
        if g is None:
            continue
        g = g.astype(np.float32)  # full-resolution crop: downscaling would average the grain away
        hp = g - cv2.GaussianBlur(g, (0, 0), 1.2)
        edges = cv2.Canny(g.astype(np.uint8), 40, 120)
        flat = cv2.dilate(edges, np.ones((5, 5), np.uint8)) == 0
        if flat.sum() > 1000:
            vals.append(float(hp[flat].std()))
    return round(float(np.median(vals)), 3) if vals else 0.0


def text_regions(path: str, times: list[float]) -> dict:
    """HEURISTIC: finds text-like horizontal clusters of strong edges. Not OCR."""
    import cv2
    counts = {"top": 0, "middle": 0, "bottom": 0}
    boxes_total = 0
    for t in times:
        raw = subprocess.run([config.ffmpeg(), "-v", "error", "-ss", f"{t:.2f}", "-i", path, "-frames:v", "1", "-vf",
                              "scale=640:-2", "-f", "image2pipe", "-vcodec", "png", "-"], capture_output=True).stdout
        g = cv2.imdecode(np.frombuffer(raw, np.uint8), cv2.IMREAD_GRAYSCALE) if raw else None
        if g is None:
            continue
        H, W = g.shape
        grad = cv2.morphologyEx(g, cv2.MORPH_GRADIENT, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3)))
        _, bw = cv2.threshold(grad, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)
        if (bw > 0).mean() > 0.25:  # too busy -> texture, not text
            continue
        con = cv2.morphologyEx(bw, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_RECT, (max(9, W // 40), 3)))
        cnts, _ = cv2.findContours(con, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        for c in cnts:
            x, y, w, h = cv2.boundingRect(c)
            fill = (bw[y:y + h, x:x + w] > 0).mean() if w * h else 0
            if w > 3 * h and 0.02 * H < h < 0.15 * H and w > 0.12 * W and 0.25 < fill < 0.85:
                cy = (y + h / 2) / H
                counts["top" if cy < 0.33 else "middle" if cy < 0.66 else "bottom"] += 1
                boxes_total += 1
    dom = max(counts, key=counts.get) if boxes_total else None
    return {"heuristic": True, "regions": counts, "dominant": dom, "frames_checked": len(times)}


def letterbox(path: str) -> dict:
    err = run([config.ffmpeg(), "-hide_banner", "-i", path, "-t", "20", "-vf", "cropdetect=24:2:0", "-f", "null", "-"],
              check=False).stderr
    m = re.findall(r"crop=(\d+):(\d+):(\d+):(\d+)", err)
    if not m:
        return {"detected": False}
    w, h, x, y = map(int, m[-1])
    v = probe(path)["video"]
    det = (v["height"] - h) > v["height"] * 0.06
    return {"detected": bool(det), "active_area": [w, h], "ratio": round(w / max(h, 1), 3)}


def analyze(path: str | Path, out_dir: Path | None = None, light: bool = False) -> dict:
    path = str(path)
    name = Path(path).stem
    out_dir = out_dir or (config.PROJECTS / f"reference_{name}")
    out_dir.mkdir(parents=True, exist_ok=True)
    log(f"== Analysing reference {Path(path).name}")
    frames, afps, info = _frames_lowres(path)
    v = info["video"]
    D = info["duration"]
    bounds, diff, luma = _boundaries(frames, afps)
    sd = _scenes(path)
    # merge PySceneDetect cuts that our detector missed
    for t in sd:
        if not any(abs(t - b["t"]) < 0.3 for b in bounds):
            bounds.append({"t": t, "type": "cut"})
    bounds.sort(key=lambda b: b["t"])
    edges = [0.0] + [b["t"] for b in bounds] + [D]
    shots = [round(edges[i + 1] - edges[i], 3) for i in range(len(edges) - 1) if edges[i + 1] - edges[i] > 0.05]
    tcount: dict[str, int] = {}
    for b in bounds:
        tcount[b["type"]] = tcount.get(b["type"], 0) + 1
    half = D / 2
    first = sum(1 for b in bounds if b["t"] < half)
    second = len(bounds) - first
    prof = {
        "source": path, "duration": round(D, 3), "width": v["width"], "height": v["height"], "fps": v["fps"],
        "aspect": round(v["width"] / v["height"], 4), "has_audio": bool(info["audio"]),
        "pacing": {"shots": len(shots), "avg_shot_len": round(float(np.mean(shots)), 3) if shots else D,
                   "median_shot_len": round(float(np.median(shots)), 3) if shots else D,
                   "min_shot": round(min(shots), 3) if shots else D, "max_shot": round(max(shots), 3) if shots else D,
                   "cuts_per_min": round(len(bounds) / D * 60, 2) if D else 0,
                   "trend": "accelerating" if second > first * 1.3 else "slowing" if first > second * 1.3 else "steady",
                   "shot_lengths": shots},
        "boundaries": [{**b, "t": round(b["t"], 3)} for b in bounds],
        "transitions": tcount,
        "colour": colour_stats(frames),
        "lab_moments": lab_moments(frames),
        "motion": motion_stats(frames, afps),
        "grain": grain_estimate(path, D),
        "letterbox": letterbox(path),
    }
    mids = [edges[i] + (edges[i + 1] - edges[i]) / 2 for i in range(len(edges) - 1)][:24]
    if not light:
        prof["text"] = text_regions(path, mids[:12] or [D / 2])
        kf = extract_frames(path, mids, out_dir / "keyframes", width=480)
        prof["keyframes"] = [str(k) for k in kf]
        prof["contact_sheet"] = str(contact_sheet(path, out_dir / "reference_contact.png", n=12))
    if info["audio"]:
        try:
            from .audio import analyze_beats
            bt = analyze_beats(path)
            beats = np.array(bt["beats"])
            on = sum(1 for b in bounds if len(beats) and np.min(np.abs(beats - b["t"])) < 0.1)
            prof["music"] = {"tempo_bpm": round(bt["tempo_bpm"], 1),
                             "cuts_on_beat_ratio": round(on / max(1, len(bounds)), 3)}
        except Exception as e:  # noqa: BLE001
            prof["music"] = {"error": str(e)}
    prof["reproducible"], prof["limitations"] = _reproducibility(prof)
    (out_dir / "style_profile.json").write_text(json.dumps(prof, indent=2))
    (out_dir / "style_report.md").write_text(report_md(prof))
    log(f"   {prof['pacing']['shots']} shots, ASL {prof['pacing']['avg_shot_len']}s, transitions {tcount}, "
        f"colour {prof['colour']['warmth']}, motion {prof['motion'].get('level')}")
    return prof


def _reproducibility(p: dict) -> tuple[list[str], list[str]]:
    rep, lim = [], []
    rep.append(f"Pacing: {p['pacing']['shots']} shots, avg {p['pacing']['avg_shot_len']}s (cut times are copied/scaled)")
    if p["transitions"]:
        rep.append(f"Transitions: {p['transitions']} -> mapped to FFmpeg xfade equivalents")
    rep.append(f"Colour: {p['colour']['warmth']} look, contrast {p['colour']['L_contrast']} -> matched with a generated 3D LUT")
    if p["grain"] > 2.5:
        rep.append(f"Film grain (estimate {p['grain']}) -> FFmpeg temporal noise")
    m = p.get("motion") or {}
    if m.get("shake_jitter", 0) > 0.15:
        rep.append("Handheld camera shake -> procedural shake")
    if abs(m.get("zoom_divergence", 0)) > 0.08:
        rep.append("Zoom-in/out camera moves -> Ken-Burns zoom per shot")
    if p["letterbox"].get("detected"):
        rep.append(f"Letterbox bars (active ratio {p['letterbox']['ratio']})")
    lim.append("Exact footage content, lens/optics and in-camera motion cannot be copied - your footage drives the image.")
    lim.append("Text detection is heuristic (no OCR): positions are approximate and fonts/wording are not reproduced.")
    lim.append("Bespoke VFX (rotoscoping, tracking, 3D integration, AI effects) are not auto-identified; ask for them explicitly.")
    lim.append("Transition classification covers cut / dissolve / dip-to-black / flash; wipes and custom transitions are reported as cuts or dissolves.")
    return rep, lim


def report_md(p: dict) -> str:
    c, m, pc = p["colour"], p.get("motion", {}), p["pacing"]
    lines = [f"# Style report: {Path(p['source']).name}", "",
             f"- Format: {p['width']}x{p['height']} @ {p['fps']} fps, {p['duration']} s, audio: {p['has_audio']}",
             f"- Pacing: {pc['shots']} shots, average {pc['avg_shot_len']} s (median {pc['median_shot_len']} s), "
             f"{pc['cuts_per_min']} cuts/min, {pc['trend']}",
             f"- Transitions: {p['transitions'] or 'none detected (single shot)'}",
             f"- Colour: {c['warmth']}, L mean {c['L_mean']}, contrast {c['L_contrast']}, saturation {c['saturation']}, "
             f"shadows a/b {c['shadow_tint_ab']}, highlights a/b {c['highlight_tint_ab']}",
             f"- Grain estimate: {p['grain']}",
             f"- Motion: {m}",
             f"- Letterbox: {p['letterbox']}",
             f"- Text placement (heuristic): {p.get('text')}",
             f"- Music: {p.get('music')}", "", "## Reproducible", *[f"- {x}" for x in p["reproducible"]], "",
             "## Limitations", *[f"- {x}" for x in p["limitations"]]]
    return "\n".join(lines) + "\n"


# ----------------------------------------------------------------- colour matching LUT
def make_match_lut(src_moments: dict, ref_moments: dict, out: Path, size: int = 33, strength: float = 0.85) -> Path:
    """Reinhard colour transfer in Lab baked into a .cube 3D LUT (usable in FFmpeg, Resolve, Kdenlive, Blender)."""
    import cv2
    ms, ss = np.array(src_moments["mean"]), np.array(src_moments["std"]) + 1e-3
    mt, st = np.array(ref_moments["mean"]), np.array(ref_moments["std"]) + 1e-3
    ratio = np.clip(st / ss, 0.6, 1.6)
    g = np.linspace(0, 1, size, dtype=np.float32)
    b, gg, r = np.meshgrid(g, g, g, indexing="ij")  # .cube: R changes fastest
    rgb = np.stack([r, gg, b], -1).reshape(-1, 1, 3)
    lab = cv2.cvtColor(rgb, cv2.COLOR_RGB2LAB).reshape(-1, 3)
    ratio = 1 + (ratio - 1) * strength           # contrast/saturation: partial (avoids harsh looks)
    new = (lab - ms) * ratio + mt                 # means (exposure, tint): fully matched
    new[:, 0] = np.clip(new[:, 0], 0, 100)
    out_rgb = np.clip(cv2.cvtColor(new.reshape(-1, 1, 3).astype(np.float32), cv2.COLOR_LAB2RGB).reshape(-1, 3), 0, 1)
    with open(out, "w") as f:
        f.write(f"TITLE \"AI-Video-Studio match\"\nLUT_3D_SIZE {size}\nDOMAIN_MIN 0 0 0\nDOMAIN_MAX 1 1 1\n")
        for row in out_rgb:
            f.write(f"{row[0]:.6f} {row[1]:.6f} {row[2]:.6f}\n")
    return out


def footage_moments(paths: list[str]) -> dict:
    from .media import IMAGE_EXT
    allf = []
    for p in paths:
        if Path(p).suffix.lower() in IMAGE_EXT:
            continue
        fr, _, _ = _frames_lowres(p, fps_cap=4)
        allf.append(fr[:: max(1, len(fr) // 10)])
    return lab_moments(np.concatenate(allf)) if allf else {"mean": [50, 0, 0], "std": [20, 10, 10]}


def style_to_plan(prof: dict, footage: list[str], name: str, music: str | None = None,
                  duration: float | None = None, width: int | None = None, height: int | None = None) -> dict:
    proj = config.PROJECTS / name
    proj.mkdir(parents=True, exist_ok=True)
    D = float(duration or min(prof["duration"], 60))
    if width and height:
        W, H = width, height
    elif prof["aspect"] < 0.8:
        W, H = 1080, 1920
    elif prof["aspect"] > 1.2:
        W, H = 1920, 1080
    else:
        W, H = 1080, 1080
    scale = D / prof["duration"]
    cuts = [round(b["t"] * scale, 3) for b in prof["boundaries"] if 0.3 < b["t"] * scale < D - 0.3]
    trans = []
    for b in prof["boundaries"]:
        if not 0.3 < b["t"] * scale < D - 0.3:
            continue
        t = b["type"]
        trans.append({"type": "cut"} if t == "cut" else {"type": "fade", "duration": min(1.0, b.get("dur", 0.5))}
                     if t == "dissolve" else {"type": t, "duration": 0.4})
    lut = make_match_lut(footage_moments(footage), prof["lab_moments"], proj / "match_reference.cube")
    m = prof.get("motion") or {}
    eff = {"grain": round(min(30, max(0, (prof["grain"] - 1.5) * 5)), 1) if prof["grain"] > 2.0 else 0,
           "vignette": prof["colour"]["L_mean"] is not None and prof["colour"]["L_contrast"] > 22,
           "shake": 8 if m.get("shake_jitter", 0) > 0.15 else 0,
           "motion_blur": 3 if m.get("level") == "high" else 0,
           "letterbox": bool(prof["letterbox"].get("detected")) and W > H}
    clips = []
    zoom_cycle = (["in", "out"] if abs(m.get("zoom_divergence", 0)) > 0.08 else [None])
    for i, f in enumerate(footage):
        clips.append({"src": f, "zoom": zoom_cycle[i % len(zoom_cycle)]})
    plan = {"name": name, "width": W, "height": H, "fps": int(round(prof["fps"] or 30)) if prof["fps"] <= 60 else 30,
            "duration": D, "clips": clips, "cut_mode": "explicit", "cuts": cuts,
            "transition": trans or [{"type": "cut"}], "grade": str(lut), "effects": eff,
            "audio": {"music": music}}
    if music and (prof.get("music") or {}).get("cuts_on_beat_ratio", 0) > 0.5:
        plan["cut_mode"] = "beats"
        plan["beat_every"] = prof["pacing"]["median_shot_len"]
    txt = prof.get("text") or {}
    if txt.get("dominant"):
        plan["_text_position_hint"] = {"top": "top", "middle": "center", "bottom": "bottom"}[txt["dominant"]]
    (proj / "plan.json").write_text(json.dumps(plan, indent=2))
    return plan


def compare(ref: str | Path, out: str | Path, out_dir: Path | None = None) -> dict:
    """Side-by-side metric table + visual keyframe comparison. Never claims a 'perfect' match."""
    a = analyze(ref, (out_dir or config.PROJECTS) / "_cmp_ref", light=True)
    b = analyze(out, (out_dir or config.PROJECTS) / "_cmp_out", light=True)
    rows = []

    def row(label, x, y, tol, rel=False):
        if x is None or y is None:
            rows.append((label, x, y, "n/a"))
            return
        d = abs(x - y) / (abs(x) + 1e-6) if rel else abs(x - y)
        rows.append((label, x, y, "close" if d <= tol else "differs"))
    row("aspect", a["aspect"], b["aspect"], 0.02)
    row("avg shot length (s)", a["pacing"]["avg_shot_len"], b["pacing"]["avg_shot_len"], 0.25, rel=True)
    row("cuts per minute", a["pacing"]["cuts_per_min"], b["pacing"]["cuts_per_min"], 0.25, rel=True)
    for k, tol in [("L_mean", 6), ("L_contrast", 5), ("a_mean", 3), ("b_mean", 4), ("saturation", 0.06)]:
        row(f"colour {k}", a["colour"][k], b["colour"][k], tol)
    row("grain", a["grain"], b["grain"], 1.5)
    row("motion %/frame", a["motion"].get("motion_pct_per_frame"), b["motion"].get("motion_pct_per_frame"), 0.5, rel=True)
    close = sum(1 for r in rows if r[3] == "close")
    res = {"reference": str(ref), "output": str(out), "rows": rows, "close": close, "total": len(rows),
           "transitions_ref": a["transitions"], "transitions_out": b["transitions"],
           "note": "Metric similarity only - visual judgement still required. Footage content differs by design."}
    # visual side-by-side
    od = (out_dir or config.PROJECTS) / "_cmp_visual"
    od.mkdir(parents=True, exist_ok=True)
    try:
        from PIL import Image
        n = 4
        fa = extract_frames(ref, [a["duration"] * (i + .5) / n for i in range(n)], od / "a", 320)
        fb = extract_frames(out, [b["duration"] * (i + .5) / n for i in range(n)], od / "b", 320)
        ia = [Image.open(x).convert("RGB") for x in fa]
        ib = [Image.open(x).convert("RGB").resize(ia[0].size) for x in fb]
        w, h = ia[0].size
        sheet = Image.new("RGB", (w * n, h * 2), (0, 0, 0))
        for i in range(min(n, len(ia), len(ib))):
            sheet.paste(ia[i], (i * w, 0)); sheet.paste(ib[i], (i * w, h))
        p = Path(out).with_suffix(".vs_reference.png")
        sheet.save(p)
        res["visual"] = str(p)
    except Exception as e:  # noqa: BLE001
        res["visual_error"] = str(e)
    md = ["| metric | reference | output | verdict |", "|---|---|---|---|"] + [f"| {r[0]} | {r[1]} | {r[2]} | {r[3]} |" for r in rows]
    res["table_md"] = "\n".join(md)
    Path(out).with_suffix(".comparison.json").write_text(json.dumps(res, indent=2, default=str))
    return res


def correct_lut(lut_in: Path, out_moments: dict, ref_moments: dict, out: Path) -> Path:
    """Closed-loop fix: shift an existing LUT's output so the RENDERED result's Lab means land on the reference."""
    import cv2
    rows = [l.split() for l in Path(lut_in).read_text().splitlines()]
    size = int(next(r[1] for r in rows if r and r[0] == "LUT_3D_SIZE"))
    vals = np.array([[float(x) for x in r] for r in rows if len(r) == 3 and r[0][0] in "0123456789.-"], np.float32)
    lab = cv2.cvtColor(vals.reshape(-1, 1, 3), cv2.COLOR_RGB2LAB).reshape(-1, 3)
    lab += np.array(ref_moments["mean"]) - np.array(out_moments["mean"])
    lab[:, 0] = np.clip(lab[:, 0], 0, 100)
    rgb = np.clip(cv2.cvtColor(lab.reshape(-1, 1, 3).astype(np.float32), cv2.COLOR_LAB2RGB).reshape(-1, 3), 0, 1)
    with open(out, "w") as f:
        f.write(f"TITLE \"AI-Video-Studio match (corrected)\"\nLUT_3D_SIZE {size}\nDOMAIN_MIN 0 0 0\nDOMAIN_MAX 1 1 1\n")
        for r in rgb:
            f.write(f"{r[0]:.6f} {r[1]:.6f} {r[2]:.6f}\n")
    return out
