"""Plan executor: JSON edit plan -> segments -> transitions -> grade/effects/titles/captions/audio -> export -> QC.

Plan schema (all keys optional except clips) -- see docs/WORKFLOW.md for the full reference.
"""
from __future__ import annotations

import copy
import json
import re
import shutil
import time
from pathlib import Path

from . import audio as A
from . import config, fx
from .log import log
from .media import IMAGE_EXT, describe, probe, run

DEFAULTS: dict = {
    "name": "edit",
    "width": 1080, "height": 1920, "fps": 30, "duration": 15.0,
    "clips": [],
    "cut_mode": "even",          # even | beats | explicit
    "cuts": [],                  # explicit cut times (cut_mode=explicit)
    "beat_every": 1.5,           # target seconds between beat-synced cuts
    "transition": {"type": "smoothleft", "duration": 0.45},
    "grade": "cinematic",
    "effects": {
        "grain": 0, "vignette": False, "rgb_split": 0, "motion_blur": 0, "light_leaks": False,
        "glitch_on_cuts": False, "flash_on_beats": False, "punch_on_beats": False,
        "letterbox": False, "sharpen": 0, "shake": 0,
    },
    "titles": [],                # [{"text","start","duration","style","position"}]
    "title_renderer": "auto",    # auto | remotion | ffmpeg
    "title_style": "kinetic",
    "captions": None,            # {"srt": path} or {"auto": true, "language": "en", "model": "small"}
    "audio": {"music": None, "keep_original": False, "original_volume": 0.35, "normalize": -14.0,
              "fade_in": 0.3, "fade_out": 1.2, "voice_cleanup": False},
    "export": {"crf": 18, "preset": "medium", "filename": None},
}


def _merge(base: dict, over: dict) -> dict:
    out = copy.deepcopy(base)
    for k, v in (over or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _merge(out[k], v)
        else:
            out[k] = copy.deepcopy(v)
    return out


def load_preset(name: str) -> dict:
    p = config.PRESETS / f"{name}.json"
    if not p.exists():
        raise FileNotFoundError(f"Preset '{name}' not found in {config.PRESETS}")
    d = json.loads(p.read_text())
    d.pop("description", None)
    return d


def normalize(plan: dict) -> dict:
    base = DEFAULTS
    if plan.get("preset"):
        base = _merge(DEFAULTS, load_preset(plan["preset"]))
    p = _merge(base, plan)
    if isinstance(p["transition"], str):
        p["transition"] = {"type": p["transition"], "duration": 0.45}
    p["name"] = re.sub(r"[^A-Za-z0-9_\-]+", "_", p["name"]).strip("_") or "edit"
    if not p["clips"]:
        raise ValueError("plan has no clips")
    p["clips"] = [{"src": c} if isinstance(c, str) else c for c in p["clips"]]
    return p


# --------------------------------------------------------------------------- timing
def compute_cuts(p: dict, beats: dict | None) -> list[float]:
    D = float(p["duration"])
    if p["cut_mode"] == "explicit" and p["cuts"]:
        return sorted(c for c in p["cuts"] if 0.3 < c < D - 0.3)
    if p["cut_mode"] == "beats" and beats:
        src = beats["prominent_beats"] if len(beats["prominent_beats"]) > D / max(p["beat_every"], 0.3) else beats["beats"]
        return A.cut_points_on_beats(src, D, target_len=p["beat_every"])
    n = max(1, len(p["clips"]))
    if p.get("segments"):
        n = int(p["segments"])
    return [round(D * k / n, 4) for k in range(1, n)]


def segment_windows(cuts: list[float], D: float, tds: list[float]) -> list[tuple[float, float]]:
    """Output-timeline (start, length) for each segment so each transition is centred on its cut."""
    edges = [0.0] + cuts + [D]
    out = []
    for k in range(len(edges) - 1):
        pre = tds[k - 1] / 2 if k > 0 else 0.0
        post = tds[k] / 2 if k < len(cuts) else 0.0
        out.append((edges[k] - pre, edges[k + 1] - edges[k] + pre + post))
    return out


# --------------------------------------------------------------------------- stages
def _pick_sources(p: dict, nseg: int) -> list[dict]:
    """Assign a clip spec to every segment, cycling through sources with advancing in-points."""
    infos = {}
    out, use_count = [], {}
    for k in range(nseg):
        c = dict(p["clips"][k % len(p["clips"])])
        src = c["src"]
        if src not in infos:
            infos[src] = probe(src) if Path(src).suffix.lower() not in IMAGE_EXT else {"duration": 0, "image": True}
        c["_info"] = infos[src]
        c["_use"] = use_count.get(src, 0)
        use_count[src] = c["_use"] + 1
        out.append(c)
    for c in out:
        c["_uses_total"] = use_count[c["src"]]
    return out


def render_segment(c: dict, length: float, p: dict, out: Path, idx: int) -> Path:
    W, H, F = p["width"], p["height"], p["fps"]
    spd = float(c.get("speed", 1.0))
    ramp = float(c.get("ramp", 0.0))
    src_len = length * spd
    info = c["_info"]
    is_img = info.get("image", False)
    cmd = [config.ffmpeg(), "-y", "-v", "error"]
    if is_img:
        cmd += ["-loop", "1", "-framerate", str(F), "-t", f"{src_len:.3f}", "-i", c["src"]]
    else:
        dur = info["duration"]
        if c.get("in") is not None:
            start = float(c["in"])
        else:  # spread repeated uses across the source
            free = max(0.0, dur - src_len)
            start = free * (c["_use"] + 0.5) / max(1, c["_uses_total"]) if c["_uses_total"] > 1 else free * 0.3
        if dur < start + src_len:
            cmd += ["-stream_loop", "-1"]
            start = min(start, max(0, dur - 0.1))
        cmd += ["-ss", f"{start:.3f}", "-t", f"{src_len + 0.2:.3f}", "-i", c["src"]]
    vf = ["setpts=PTS-STARTPTS"]
    if spd != 1.0 or ramp > 0:
        vf.append(fx.speed(src_len, spd, ramp))
        if c.get("smooth_slowmo") and (ramp > 0.3 or spd < 0.7):
            vf.append(f"minterpolate=fps={F}:mi_mode=mci:mc_mode=aobmc:me_mode=bidir")
    vf.append(f"fps={F}")
    vf += fx.fit(W, H, float(c.get("focus_x", 0.5)))
    z = c.get("zoom") or ("in" if is_img else None)
    if z in ("in", "out"):
        vf += fx.zoom(z, length, W, H, F, float(c.get("zoom_amount", 0.12)))
    sh = float(c.get("shake", p["effects"].get("shake", 0)))
    if sh > 0:
        vf += fx.shake(W, H, amp=sh)
    vf += ["setsar=1", "format=yuv420p"]
    cmd += ["-vf", ",".join(vf), "-an", "-t", f"{length:.4f}", "-r", str(F), "-c:v", "libx264", "-crf", "14",
            "-preset", "veryfast", "-g", str(F), str(out)]
    run(cmd)
    got = probe(out)["duration"]
    if got < length - 0.05:  # source ran out (e.g. odd timestamps) -> pad by holding last frame
        padded = out.with_name(out.stem + "_pad.mp4")
        run([config.ffmpeg(), "-y", "-v", "error", "-i", str(out), "-vf",
             f"tpad=stop_mode=clone:stop_duration={length-got+0.1:.3f}", "-t", f"{length:.4f}",
             "-c:v", "libx264", "-crf", "14", "-preset", "veryfast", str(padded)])
        padded.replace(out)
    return out


def assemble(segs: list[Path], cuts: list[float], tds: list[float], trans: list[str], p: dict, out: Path) -> Path:
    if len(segs) == 1:
        shutil.copy(segs[0], out)
        return out
    cmd = [config.ffmpeg(), "-y", "-v", "error"]
    for s in segs:
        cmd += ["-i", str(s)]
    parts, prev = [], "[0:v]"
    for k, cut in enumerate(cuts):
        td = tds[k]
        t = trans[k]
        lbl = f"[x{k}]"
        parts.append(f"{prev}[{k+1}:v]xfade=transition={t}:duration={td:.4f}:offset={cut - td/2:.4f}{lbl}")
        prev = lbl
    cmd += ["-filter_complex", ";".join(parts), "-map", prev, "-r", str(p["fps"]), "-c:v", "libx264", "-crf", "14",
            "-preset", "veryfast", "-pix_fmt", "yuv420p", str(out)]
    run(cmd)
    return out


def build_audio(p: dict, segs_meta: list[dict], work: Path, D: float) -> Path | None:
    au = p["audio"]
    F = []
    inputs = []
    if au.get("music"):
        inputs.append(("music", au["music"]))
    orig = []
    if au.get("keep_original"):
        for m in segs_meta:
            c = m["clip"]
            if c["_info"].get("image") or not c["_info"].get("audio"):
                continue
            if float(c.get("speed", 1)) != 1.0 or float(c.get("ramp", 0)) > 0:
                continue  # time-remapped segments are muted (pitch artefacts)
            orig.append(m)
    if not inputs and not orig:
        return None
    cmd = [config.ffmpeg(), "-y", "-v", "error"]
    labels = []
    idx = 0
    if au.get("music"):
        cmd += ["-i", au["music"]]
        F.append(f"[{idx}:a]aresample=48000,aformat=channel_layouts=stereo,atrim=0:{D:.3f},asetpts=PTS-STARTPTS,"
                 f"volume={au.get('music_volume', 1.0)}[m]")
        labels.append("[m]")
        idx += 1
    for j, m in enumerate(orig):
        c = m["clip"]
        cmd += ["-ss", f"{m['src_start']:.3f}", "-t", f"{m['length']:.3f}", "-i", c["src"]]
        fd = max(0.02, m["td_in"])
        chain = f"[{idx}:a]aresample=48000,aformat=channel_layouts=stereo,asetpts=PTS-STARTPTS,"
        if au.get("voice_cleanup"):
            chain += A.voice_cleanup_filter() + ","
        chain += (f"afade=t=in:d={fd:.3f},afade=t=out:st={max(0, m['length']-max(0.02, m['td_out'])):.3f}:d={max(0.02, m['td_out']):.3f},"
                  f"volume={au.get('original_volume', 0.35) if au.get('music') else 1.0},"
                  f"adelay={int(m['out_start']*1000)}|{int(m['out_start']*1000)}[o{j}]")
        F.append(chain)
        labels.append(f"[o{j}]")
        idx += 1
    if len(labels) > 1:
        F.append("".join(labels) + f"amix=inputs={len(labels)}:normalize=0:dropout_transition=0[mix]")
        last = "[mix]"
    else:
        last = labels[0]
    F.append(f"{last}apad=whole_dur={D:.3f},atrim=0:{D:.3f},"
             f"afade=t=in:d={au.get('fade_in', 0.3)},afade=t=out:st={max(0, D-au.get('fade_out', 1.2)):.3f}:d={au.get('fade_out', 1.2)}[aout]")
    mix = work / "audio_mix.wav"
    cmd += ["-filter_complex", ";".join(F), "-map", "[aout]", "-c:a", "pcm_s16le", str(mix)]
    run(cmd)
    return mix


def _drawtext_titles(titles: list[dict], p: dict) -> list[str]:
    font = config.font_file()
    out = []
    H = p["height"]
    for t in titles:
        s, d = float(t.get("start", 0)), float(t.get("duration", 2.5))
        e = s + d
        txt = str(t["text"]).replace("\\", "\\\\").replace(":", "\\:").replace("'", "’").replace("%", "\\%")
        size = int(t.get("size", H * 0.055))
        ypos = {"top": "h*0.14", "center": "(h-text_h)/2", "bottom": "h*0.78"}.get(t.get("position", "center"), "(h-text_h)/2")
        alpha = f"if(lt(t,{s}),0,if(lt(t,{s+0.35}),(t-{s})/0.35,if(lt(t,{e-0.35}),1,max(0,({e}-t)/0.35))))"
        ff = f"fontfile='{config.ff_filter_path(font)}':" if font else ""
        out.append(f"drawtext={ff}text='{txt}':fontsize={size}:fontcolor=white:borderw=3:bordercolor=black@0.6:"
                   f"x=(w-text_w)/2:y={ypos}+20*(1-min(1,max(0,(t-{s})/0.35))):alpha='{alpha}':enable='between(t,{s},{e})'")
    return out


def finalize(p: dict, assembled: Path, work: Path, cuts: list[float], beats: dict | None,
             audio_mix: Path | None, out: Path) -> Path:
    W, H, F, D = p["width"], p["height"], p["fps"], float(p["duration"])
    ef = p["effects"]
    cmd = [config.ffmpeg(), "-y", "-v", "error", "-i", str(assembled)]
    n_in = 1
    v = ["[0:v]setpts=PTS-STARTPTS"]
    if ef.get("motion_blur"):
        v.append(fx.motion_blur(int(ef["motion_blur"]) if ef["motion_blur"] is not True else 3))
    v += fx.grade(p.get("grade"))
    v.append("format=yuv420p")  # lut3d outputs RGB planes; later luma effects (grain c0) must see Y, not G
    if ef.get("sharpen"):
        v.append(fx.sharpen(float(ef["sharpen"])))
    if ef.get("rgb_split"):
        v.append(fx.rgb_split(int(ef["rgb_split"])))
    beat_times = [b for b in (beats or {}).get("prominent_beats", []) if b < D - 0.1]
    if ef.get("glitch_on_cuts") and cuts:
        v += fx.glitch([(max(0, c - 1.0 / F), c + 0.2) for c in cuts], 1.0)  # hit lands on the cut/beat
    if ef.get("flash_on_beats") and beat_times:
        v += fx.flashes(beat_times[::2] if len(beat_times) > 40 else beat_times)
    if ef.get("punch_on_beats") and beat_times:
        v.append(fx.zoom_punch(beat_times, W, H, F))
    if ef.get("grain"):
        v.append(fx.grain(float(ef["grain"])))
    if ef.get("vignette"):
        v.append(fx.vignette())
    if ef.get("letterbox") and W > H:
        v.append(fx.letterbox(W, H))
    graph = [",".join(v) + "[g0]"]
    cur = "[g0]"
    if ef.get("light_leaks"):
        wins = [(max(0, c - 0.6), min(D, c + 0.6)) for c in cuts] if ef["light_leaks"] == "cuts" else None
        leak = fx.make_light_leak(work / "leak.mp4", W, H, D, F, windows=wins)
        cmd += ["-i", str(leak)]
        op = float(ef.get("light_leak_opacity", 0.45))
        graph.append(f"{cur}format=gbrp[gb];[{n_in}:v]format=gbrp[lk];[gb][lk]blend=all_mode=screen:all_opacity={op},format=yuv420p[g1]")
        cur = "[g1]"
        n_in += 1
    titles = p.get("titles") or []
    if titles:
        renderer = p.get("title_renderer", "auto")
        ov = None
        if renderer in ("auto", "remotion"):
            from . import remotion_bridge
            try:
                ov = remotion_bridge.render_title_overlay(titles, W, H, F, D, p.get("title_style", "kinetic"), work)
            except Exception as e:  # noqa: BLE001
                if renderer == "remotion":
                    raise
                log(f"Remotion title overlay unavailable ({e}); falling back to FFmpeg drawtext")
        if ov:
            cmd += ["-i", str(ov)]
            graph.append(f"{cur}[{n_in}:v]overlay=0:0:format=auto:shortest=0,format=yuv420p[g2]")
            n_in += 1
        else:
            graph.append(f"{cur}" + ",".join(_drawtext_titles(titles, p)) + "[g2]")
        cur = "[g2]"
    cap = p.get("captions")
    if cap:
        from . import subtitles
        ass = subtitles.prepare_ass(cap, p, work)
        if ass:
            graph.append(f"{cur}subtitles=filename='{config.ff_filter_path(ass)}'[g3]")
            cur = "[g3]"
    graph.append(f"{cur}fps={F},format=yuv420p[vout]")
    amap = []
    if audio_mix:
        cmd += ["-i", str(audio_mix)]
        norm = p["audio"].get("normalize")
        af = A.loudnorm_filter(audio_mix, target=float(norm)) if norm is not None else "anull"
        graph.append(f"[{n_in}:a]{af},aresample=48000[aout]")
        amap = ["-map", "[aout]", "-c:a", "aac", "-b:a", "192k", "-ar", "48000"]
        n_in += 1
    ex = p["export"]
    cmd += ["-filter_complex", ";".join(graph), "-map", "[vout]"] + amap
    cmd += ["-t", f"{D:.3f}", "-r", str(F), "-c:v", "libx264", "-profile:v", "high", "-crf", str(ex.get("crf", 18)),
            "-preset", ex.get("preset", "medium"), "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(out)]
    config.assert_writable_output(out)
    run(cmd)
    return out


# --------------------------------------------------------------------------- main entry
def render_plan(plan: dict, out: Path | None = None, qc: bool = True) -> dict:
    from . import qc as QC

    t0 = time.time()
    p = normalize(plan)
    config.ensure_dirs()
    work = config.INTERMEDIATE / p["name"]
    work.mkdir(parents=True, exist_ok=True)
    (work / "plan.resolved.json").write_text(json.dumps(p, indent=2))
    D, F = float(p["duration"]), int(p["fps"])
    log(f"== Rendering '{p['name']}'  {p['width']}x{p['height']}@{F} {D}s, {len(p['clips'])} source(s)")
    for c in p["clips"]:
        if Path(c["src"]).suffix.lower() not in IMAGE_EXT:
            log("   source: " + describe(probe(c["src"])))

    beats = None
    music = p["audio"].get("music")
    if music and (p["cut_mode"] == "beats" or p["effects"].get("flash_on_beats") or p["effects"].get("punch_on_beats")):
        beats = A.analyze_beats(music)
        (work / "beats.json").write_text(json.dumps(beats, indent=1))
        log(f"   music: {beats['tempo_bpm']:.1f} BPM, {len(beats['beats'])} beats, {len(beats['prominent_beats'])} prominent")

    cuts = compute_cuts(p, beats)
    # snap every cut to the frame grid (xfade offsets must be frame-exact)
    cuts = sorted({round(round(c * F) / F, 6) for c in cuts if 1 <= round(c * F) <= round(D * F) - 1})
    nseg = len(cuts) + 1
    tr = p["transition"]
    tr_list = tr if isinstance(tr, list) else [tr] * len(cuts)
    trans, tds = [], []
    for k in range(len(cuts)):
        t = tr_list[k % len(tr_list)] if tr_list else {"type": "cut"}
        name = fx.transition_name(t.get("type", "fade"))
        if name in ("cut", "glitch"):
            trans.append("fade"); tds.append(1.0 / F)
            if name == "glitch":
                p["effects"]["glitch_on_cuts"] = True
        else:
            trans.append(name); tds.append(float(t.get("duration", 0.45)))
    # make sure transitions never overlap each other
    edges = [0.0] + cuts + [D]
    for k in range(len(cuts)):
        room = min(edges[k + 1] - edges[k], edges[k + 2] - edges[k + 1])
        tds[k] = min(tds[k], max(1.0 / F, room * 0.8))
        tds[k] = max(1, round(tds[k] * F)) / F  # whole frames
    wins = segment_windows(cuts, D, tds)
    log(f"   {nseg} segments, cuts at {[round(c, 2) for c in cuts]}")

    srcs = _pick_sources(p, nseg)
    segs, meta = [], []
    for k, ((start, length), c) in enumerate(zip(wins, srcs)):
        sp = work / f"seg_{k:02d}.mp4"
        render_segment(c, length + 2.0 / F, p, sp, k)
        segs.append(sp)
        info = c["_info"]
        src_start = float(c.get("in")) if c.get("in") is not None else (
            max(0.0, info.get("duration", 0) - length * float(c.get("speed", 1))) *
            ((c["_use"] + 0.5) / c["_uses_total"] if c["_uses_total"] > 1 else 0.3))
        meta.append({"clip": c, "out_start": max(0.0, start), "length": length, "src_start": src_start,
                     "td_in": tds[k - 1] if k > 0 else 0.0, "td_out": tds[k] if k < len(cuts) else 0.0})
    assembled = assemble(segs, cuts, tds, trans, p, work / "assembled.mp4")
    got = probe(assembled)["duration"]
    if got < D - 1.5 / F:
        raise RuntimeError(f"assembly produced {got:.3f}s, expected {D}s (transition timing bug) - see {work}")
    mix = build_audio(p, meta, work, D)

    fname = p["export"].get("filename") or f"{p['name']}.mp4"
    out = Path(out) if out else config.EXPORTS / fname
    out.parent.mkdir(parents=True, exist_ok=True)
    finalize(p, assembled, work, cuts, beats, mix, out)
    result = {"output": str(out), "cuts": cuts, "transitions": trans, "render_seconds": round(time.time() - t0, 1)}
    if qc:
        expect = {"width": p["width"], "height": p["height"], "fps": F, "duration": D, "vcodec": "h264",
                  "audio": bool(mix), "acodec": "aac" if mix else None}
        if mix and p["audio"].get("normalize") is not None:
            expect["lufs"] = float(p["audio"]["normalize"])
        expect = {k: v for k, v in expect.items() if v is not None}
        final, rep = QC.check_and_fix(out, expect)
        result["output"] = str(final)
        result["qc"] = rep
        log("   " + QC.summarize(rep))
    log(f"== Done in {result['render_seconds']}s -> {result['output']}")
    (work / "result.json").write_text(json.dumps(result, indent=2, default=str))
    return result
