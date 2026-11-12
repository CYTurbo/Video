"""Automated rendering tests (Phase 7 + Phase 10). Writes docs/TEST_RESULTS.md.

A test only passes when the *measured* output meets its criteria -- a render command exiting 0 is not enough.

  python tests/run_tests.py            # all tests
  python tests/run_tests.py A C        # selected tests
"""
from __future__ import annotations

import datetime as dt
import json
import platform
import sys
import time
import traceback
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from studio import audio as A  # noqa: E402
from studio import config, jobs, planner, qc, synth  # noqa: E402
from studio import reference as R  # noqa: E402
from studio.media import probe, run, snapshot_hashes  # noqa: E402

ASSETS = ROOT / "tests" / "assets"
OUT = ROOT / "tests" / "output"
RESULTS: list[dict] = []


def record(tid, name, passed, checks, notes="", files=None, seconds=0.0):
    RESULTS.append({"id": tid, "name": name, "passed": passed, "checks": checks, "notes": notes,
                    "files": files or [], "seconds": round(seconds, 1), "ran_at": f"{dt.datetime.now():%Y-%m-%d %H:%M}"})
    print(f"\n[{'PASS' if passed else 'FAIL'}] Test {tid}: {name} ({seconds:.0f}s)")
    for c in checks:
        print(f"    {'✓' if c[1] else '✗'} {c[0]}: {c[2]}")


def assets() -> dict:
    need = ["clip_bokeh_city.mp4", "clip_ocean_sunset.mp4", "clip_neon_tunnel.mp4", "clip_mountains.mp4",
            "clip_fractal.mp4", "clip_with_audio.mp4", "image_abstract.jpg", "music_120bpm.wav"]
    if not all((ASSETS / n).exists() for n in need):
        print("Generating synthetic test assets ...")
        synth.make_all(ASSETS)
    return {n.split(".")[0]: str(ASSETS / n) for n in need}


def _spec_checks(rep, W, H, fps, D, audio=True):
    pr = rep.get("probe", {})
    v = pr.get("video") or {}
    a = (pr.get("audio") or [{}])[0] if pr.get("audio") else {}
    c = [("file exists & decodes", Path(rep["file"]).exists() and not any("decode" in p for p in rep["problems"]), rep["file"]),
         ("resolution", (v.get("width"), v.get("height")) == (W, H), f"{v.get('width')}x{v.get('height')}"),
         ("frame rate", abs((v.get("fps") or 0) - fps) < 0.05, v.get("fps")),
         ("duration", abs(pr.get("duration", 0) - D) <= 0.15, f"{pr.get('duration', 0):.3f}s (target {D})"),
         ("video codec h264/yuv420p", v.get("codec") == "h264" and v.get("pix_fmt") == "yuv420p", f"{v.get('codec')}/{v.get('pix_fmt')}"),
         ("no black/blank frames", not any("black" in p or "blank" in p for p in rep["problems"]),
          f"black={rep.get('black_segments')}, sampled luma std={[f.get('std') for f in rep.get('frame_stats', [])][:4]}")]
    if audio:
        c.append(("audio aac, length matches video", a.get("codec") == "aac" and abs(a.get("duration", 0) - (v.get("duration") or 0)) < 0.2,
                  f"{a.get('codec')} {a.get('duration', 0):.2f}s"))
        lufs = (rep.get("loudness") or {}).get("lufs")
        c.append(("loudness normalised ~-14 LUFS", lufs is not None and abs(lufs + 14) <= 2, f"{lufs} LUFS"))
    return c


def _segment_colour(path, t0, t1):
    fr, _, _ = R._frames_lowres(str(path), fps_cap=6)
    info = probe(path)
    n = len(fr)
    i0, i1 = int(n * t0 / info["duration"]), max(int(n * t0 / info["duration"]) + 1, int(n * t1 / info["duration"]))
    return R.colour_stats(fr[i0:i1])


# ---------------------------------------------------------------------------- tests
def test_A(a):
    """Cinematic reel: 1080x1920, 15 s, smooth transitions, motion blur, colour grade, MP4 -- driven by natural language."""
    t0 = time.time()
    instr = ("Take these clips and create a 15-second cinematic Instagram reel with smooth transitions, motion blur, "
             "a speed ramp, light leaks, grain and the title \"Golden Hour\". Professional color grading.")
    plan = planner.plan_from_text(instr, [a["clip_ocean_sunset"], a["clip_neon_tunnel"], a["clip_bokeh_city"],
                                          a["clip_mountains"], a["image_abstract"]], a["music_120bpm"], name="testA_cinematic_reel")
    res = jobs.execute(plan)
    rep = res["qc"]
    out = Path(res["output"])
    checks = _spec_checks(rep, 1080, 1920, 30, 15.0)
    resolved = json.loads((config.INTERMEDIATE / "testA_cinematic_reel" / "plan.resolved.json").read_text())
    checks.append(("planner chose 9:16 + cinematic preset", resolved["width"] == 1080 and plan["preset"] == "cinematic",
                   f"{resolved['width']}x{resolved['height']} preset={plan['preset']}"))
    checks.append(("smooth transitions rendered", res["transitions"] and all(t == "smoothleft" for t in res["transitions"]),
                   f"{len(res['transitions'])} x {set(res['transitions'])} at {res['cuts']}"))
    checks.append(("motion blur (tmix) + speed ramp in graph", resolved["effects"]["motion_blur"] == 3 and
                   any(c.get("ramp") for c in resolved["clips"]), "tmix=3 frames; ramp=0.6 on alternate clips"))
    # colour grade measurably changed the image vs the ungraded source (ocean segment, first 2.5 s)
    src = R.colour_stats(R._frames_lowres(a["clip_ocean_sunset"], fps_cap=6)[0][:15])
    graded = _segment_colour(out, 0.2, 2.4)
    d_con = graded["L_contrast"] - src["L_contrast"]
    checks.append(("colour grade measurably applied", abs(graded["b_mean"] - src["b_mean"]) > 1 or abs(d_con) > 1,
                   f"src b*={src['b_mean']} contrast={src['L_contrast']} -> out b*={graded['b_mean']} contrast={graded['L_contrast']}"))
    # transitions are not hard cuts: frame difference around each cut is spread over several frames
    fr, fps, _ = R._frames_lowres(str(out))
    g = fr.astype(np.float32).mean(axis=3)
    d = np.r_[0, np.abs(g[1:] - g[:-1]).mean(axis=(1, 2))]
    spread = []
    for c in res["cuts"]:
        i = int(c * fps)
        win = d[max(0, i - 8): i + 8]
        spread.append(round(float((win > win.max() * 0.3).sum()), 1))
    checks.append(("transitions are gradual (>=4 frames)", all(s >= 4 for s in spread), f"frames-in-transition per cut={spread}"))
    record("A", "Cinematic reel 1080x1920 15s", all(c[1] for c in checks), checks,
           notes="Synthetic procedural footage; motion blur is frame-blend (tmix) approximation of shutter blur.",
           files=[str(out), rep.get("contact_sheet")], seconds=time.time() - t0)


def test_B(a):
    """Motion typography: Remotion KineticTypography (multi-keyframe easing, animated bg, 3D camera)."""
    t0 = time.time()
    plan = {"job": "typography", "name": "testB_motion_typography", "width": 1920, "height": 1080, "fps": 30,
            "duration": 10.0, "lines": ["MAKE IT MOVE", "TYPE IN MOTION", "EVERY FRAME COUNTS"], "camera": "dramatic",
            "audio": {"music": a["music_120bpm"]}}
    res = jobs.execute(plan)
    rep = res["qc"]
    out = Path(res["output"])
    checks = _spec_checks(rep, 1920, 1080, 30, 10.0)
    fr, fps, _ = R._frames_lowres(str(out))
    g = fr.astype(np.float32).mean(axis=3)
    d = np.abs(g[1:] - g[:-1]).mean(axis=(1, 2))
    moving = float((d > 0.3).mean())
    checks.append(("animated every frame (no static stretches)", moving > 0.9, f"{moving*100:.0f}% of frames change"))
    # background animates even while text holds: compare corners (no text there)
    corner = fr[:, :20, :30].astype(np.float32).mean(axis=(1, 2, 3))
    checks.append(("background animation (corner region changes)", float(np.ptp(corner)) > 2, f"corner luma range {np.ptp(corner):.1f}"))
    # three different lines -> three distinct text states
    mid = [int(len(fr) * k / 6) for k in (1, 3, 5)]
    dist = [float(np.abs(g[mid[i]] - g[mid[j]]).mean()) for i, j in ((0, 1), (1, 2))]
    checks.append(("multiple text keyframe states", all(x > 3 for x in dist), f"mean diff between line states {np.round(dist, 1)}"))
    # text must stay inside the frame: no bright glyph pixels touching the outer 1.5% columns
    edge = max(2, int(fr.shape[2] * 0.015))
    bright = (fr.astype(np.int16).max(axis=3) > 235)
    touch = float(np.r_[bright[:, :, :edge].mean(axis=(1, 2)), bright[:, :, -edge:].mean(axis=(1, 2))].max())
    checks.append(("text stays inside frame (no clipped glyphs at edges)", touch < 0.02, f"max bright fraction in edge columns {touch:.3f}"))
    checks.append(("beat pulses wired to music", len(res["beats_used"]) > 5, f"{len(res['beats_used'])} beats"))
    record("B", "Motion typography (Remotion)", all(c[1] for c in checks), checks,
           notes="Easing (Easing.out(back), inOut(cubic), spring) and 5-key camera path are defined in remotion/src/KineticTypography.tsx; "
                 "verified indirectly via per-frame motion.", files=[str(out), rep.get("contact_sheet")], seconds=time.time() - t0)


def test_C(a):
    """Music-synchronised edit: detect beats, cut on prominent beats, verify cuts land on beats in the final file."""
    t0 = time.time()
    truth = json.loads(Path(a["music_120bpm"]).with_suffix(".beats.json").read_text())
    bt = A.analyze_beats(a["music_120bpm"])
    det = np.array(bt["beats"])
    gt = np.array([b for b in truth["beats"] if b < bt["duration"] - 0.5])
    hits = sum(1 for b in gt if len(det) and np.min(np.abs(det - b)) <= 0.07)
    recall = hits / len(gt)
    prec = sum(1 for b in det if np.min(np.abs(gt - b)) <= 0.07) / max(1, len(det))
    checks = [("tempo detected", abs(bt["tempo_bpm"] - 120) < 2 or abs(bt["tempo_bpm"] - 60) < 1 or abs(bt["tempo_bpm"] - 240) < 2,
               f"{bt['tempo_bpm']:.1f} BPM (truth 120)"),
              ("beat detection vs ground truth (±70 ms)", recall > 0.9 and prec > 0.9, f"recall {recall:.2f}, precision {prec:.2f}")]
    plan = {"name": "testC_beat_sync", "preset": "glitch_energy", "width": 1080, "height": 1920, "fps": 30, "duration": 12.0,
            "clips": [a["clip_neon_tunnel"], a["clip_bokeh_city"], a["clip_fractal"], a["clip_ocean_sunset"]],
            "cut_mode": "beats", "beat_every": 1.0, "transition": {"type": "cut"},
            "effects": {"glitch_on_cuts": True, "flash_on_beats": True, "punch_on_beats": True},
            "audio": {"music": a["music_120bpm"]}}
    res = jobs.execute(plan)
    rep = res["qc"]
    out = Path(res["output"])
    checks += _spec_checks(rep, 1080, 1920, 30, 12.0)
    cuts = np.array(res["cuts"])
    on = [float(np.min(np.abs(gt - c))) for c in cuts]
    checks.append(("planned cuts land on true beats (±1 frame)", all(x <= 1 / 30 + 0.07 for x in on),
                   f"{len(cuts)} cuts, max offset {max(on)*1000:.0f} ms"))
    # measure actual cuts in the rendered file (scene detection) and beats in the rendered audio
    # measure: where does the visual change actually START near each planned cut (in the OUTPUT file),
    # and how far is that from the nearest beat detected in the OUTPUT audio?
    fr_o, fps_o, _ = R._frames_lowres(str(out))
    g_o = fr_o.astype(np.float32).mean(axis=3)
    d_o = np.r_[0, np.abs(g_o[1:] - g_o[:-1]).mean(axis=(1, 2))]
    bt_out = A.analyze_beats(out)
    ob = np.array(bt_out["beats"])
    offs = []
    for c in cuts:
        i0, i1 = max(1, int((c - 0.3) * fps_o)), min(len(d_o), int((c + 0.3) * fps_o))
        w = d_o[i0:i1]
        peak_t = (i0 + int(np.argmax(w > 0.5 * w.max()))) / fps_o  # onset of the visual change
        offs.append(abs(peak_t - float(ob[np.argmin(np.abs(ob - peak_t))])))
    checks.append(("visual cuts in OUTPUT align with OUTPUT audio beats (A/V sync)",
                   len(offs) == len(cuts) and max(offs) <= 0.07,
                   f"{len(offs)} cuts measured, median {np.median(offs)*1000:.0f} ms, max {max(offs)*1000:.0f} ms (1 frame = 33 ms)"))
    record("C", "Music-synchronised edit", all(c[1] for c in checks), checks,
           notes="Synthetic 120 BPM track with known beat times used as ground truth.",
           files=[str(out), rep.get("contact_sheet")], seconds=time.time() - t0)


def test_D(a):
    """Reference-based editing: build a reference with a KNOWN style, recreate it with different footage, compare."""
    t0 = time.time()
    ref_plan = {"name": "testD_reference_source", "width": 1920, "height": 1080, "fps": 30, "duration": 10.0,
                "clips": [a["clip_fractal"], a["clip_neon_tunnel"], a["clip_ocean_sunset"]], "segments": 8,
                "transition": {"type": "cut"}, "grade": "warm_film", "effects": {"grain": 16, "vignette": True},
                "audio": {"music": a["music_120bpm"]}}
    ref = jobs.execute(ref_plan)["output"]
    plan = {"job": "reference", "reference": ref, "name": "testD_reference_recreation",
            "clips": [{"src": a["clip_bokeh_city"]}, {"src": a["clip_mountains"]}, {"src": a["clip_with_audio"]}],
            "audio": {"music": a["music_120bpm"]}}
    res = jobs.execute(plan)
    cmp = res["comparison"]
    rows = {r[0]: r for r in cmp["rows"]}
    prof = json.loads(Path(res["reference_profile"]).read_text())
    checks = [("reference analysed: 8 shots found", prof["pacing"]["shots"] == 8, f"{prof['pacing']['shots']} shots, transitions {prof['transitions']}"),
              ("recreation passes QC", res["qc"]["passed"], qc.summarize(res["qc"]).splitlines()[0]),
              ("pacing matched (avg shot length)", rows["avg shot length (s)"][3] == "close", rows["avg shot length (s)"][1:3]),
              ("aspect matched", rows["aspect"][3] == "close", rows["aspect"][1:3]),
              ("colour warmth matched (b*)", rows["colour b_mean"][3] == "close", rows["colour b_mean"][1:3]),
              ("grain reproduced", rows["grain"][3] == "close", rows["grain"][1:3])]
    # baseline: same footage, no style transfer -> colour should be further from the reference
    base = R.colour_stats(R._frames_lowres(a["clip_bokeh_city"], fps_cap=4)[0])
    rb = rows["colour b_mean"]
    checks.append(("style transfer moved colour toward reference", abs(rb[2] - rb[1]) < abs(base["b_mean"] - rb[1]),
                   f"ref b*={rb[1]}, ungraded footage b*={base['b_mean']}, recreation b*={rb[2]}"))
    record("D", "Reference-style recreation", all(c[1] for c in checks), checks,
           notes=f"{cmp['close']}/{cmp['total']} metrics within tolerance. " + cmp["note"] + "\n\n" + cmp["table_md"],
           files=[ref, res["output"], cmp.get("visual")], seconds=time.time() - t0)


def test_E(a):
    """Captions: styled word-highlight captions burned in (from SRT; Whisper transcription tested separately)."""
    t0 = time.time()
    from studio import subtitles
    srt = OUT / "sample.srt"
    OUT.mkdir(parents=True, exist_ok=True)
    srt.write_text("1\n00:00:00,300 --> 00:00:02,400\nThis caption was generated automatically\n\n"
                   "2\n00:00:02,600 --> 00:00:05,600\nand styled for vertical social video\n", encoding="utf-8")
    plan = {"name": "testE_captions", "preset": "bright_vlog", "width": 1080, "height": 1920, "duration": 6.0,
            "clips": [a["clip_with_audio"]], "transition": {"type": "cut"},
            "captions": {"srt": str(srt), "style": "bold_pop"}, "audio": {"keep_original": True}}
    res = jobs.execute(plan)
    out = Path(res["output"])
    checks = _spec_checks(res["qc"], 1080, 1920, 30, 6.0)
    # caption region (lower third) should differ from an uncaptioned render of the same plan
    plan2 = dict(plan, name="testE_nocaptions", captions=None)
    out2 = Path(jobs.execute(plan2)["output"])
    import cv2
    def grab(p, t):
        raw = __import__("subprocess").run([config.ffmpeg(), "-v", "error", "-ss", str(t), "-i", str(p), "-frames:v", "1",
                                            "-f", "image2pipe", "-vcodec", "png", "-"], capture_output=True).stdout
        return cv2.imdecode(np.frombuffer(raw, np.uint8), cv2.IMREAD_GRAYSCALE).astype(np.float32)
    f1, f2 = grab(out, 1.2), grab(out2, 1.2)
    H = f1.shape[0]
    lower = float(np.abs(f1[int(H * .62):int(H * .85)] - f2[int(H * .62):int(H * .85)]).mean())
    upper = float(np.abs(f1[:int(H * .4)] - f2[:int(H * .4)]).mean())
    checks.append(("captions visible in lower third only", lower > 3 and upper < 1.0, f"lower diff {lower:.1f}, upper diff {upper:.2f}"))
    ass = (config.INTERMEDIATE / "testE_captions" / "captions.ass").read_text()
    checks.append(("word-by-word highlight events", ass.count("Dialogue:") >= 10, f"{ass.count('Dialogue:')} ASS events"))
    checks.append(("original clip audio kept", bool(res["qc"]["probe"]["audio"]), "aac track present"))
    try:
        subtitles.transcribe(a["clip_with_audio"], model="tiny")
        wh = "Whisper transcription ran."
    except Exception as e:  # noqa: BLE001
        wh = f"Whisper transcription NOT tested here: model download failed ({type(e).__name__}). Works once huggingface.co is reachable."
    record("E", "Styled captions (burn-in)", all(c[1] for c in checks), checks, notes=wh,
           files=[str(out), res["qc"].get("contact_sheet")], seconds=time.time() - t0)


def test_F(a):
    """Blender: scripted 3D title with keyframed camera, rendered headless."""
    t0 = time.time()
    from studio import blender_bridge
    out = OUT / "testF_title3d.mp4"
    OUT.mkdir(parents=True, exist_ok=True)
    blender_bridge.render_title3d("AI STUDIO", out, 960, 540, 24, 2.0, samples=6)
    rep = qc.check(out, {"width": 960, "height": 540, "fps": 24, "duration": 2.0})
    fr, fps, _ = R._frames_lowres(str(out))
    g = fr.astype(np.float32).mean(axis=3)
    d = float(np.abs(g[-1] - g[0]).mean())
    checks = [("render completed with expected specs", rep["passed"], qc.summarize(rep).splitlines()[0]),
              ("camera animation (first vs last frame differ)", d > 3, f"mean diff {d:.1f}"),
              ("frames not blank", all(f.get("std", 0) > 5 for f in rep["frame_stats"]), [f.get("std") for f in rep["frame_stats"]][:4])]
    record("F", "Blender scripted 3D animation", all(c[1] for c in checks), checks,
           notes=f"Engine: Cycles CPU via {blender_bridge.available()} (no GPU here).", files=[str(out), rep.get("contact_sheet")],
           seconds=time.time() - t0)


def test_G(a):
    """Audio: voice cleanup + normalisation + fades on a noisy clip."""
    t0 = time.time()
    noisy = OUT / "noisy_voice.wav"
    OUT.mkdir(parents=True, exist_ok=True)
    run([config.ffmpeg(), "-y", "-v", "error", "-i", a["clip_with_audio"], "-f", "lavfi", "-i", "anoisesrc=c=pink:a=0.05:d=6",
         "-filter_complex", "[0:a]volume=0.4[v];[v][1:a]amix=inputs=2:normalize=0", "-t", "6", str(noisy)])
    from studio.cli import main
    main(["audio-clean", str(noisy), "--lufs", "-16"])
    clean = config.EXPORTS / "noisy_voice_clean.wav"
    l0, l1 = A.loudness(noisy), A.loudness(clean)

    def noise_floor(p):
        y, sr = A.load_mono(p)
        import librosa
        S = np.abs(librosa.stft(y))
        return float(np.mean(S[int(S.shape[0] * 0.6):]))  # >~6.6 kHz band where only noise lives
    n0, n1 = noise_floor(noisy), noise_floor(clean)
    gain = 10 ** ((l1["lufs"] - l0["lufs"]) / 20)
    checks = [("normalised to -16 LUFS", abs(l1["lufs"] + 16) < 1.5, f"{l0['lufs']} -> {l1['lufs']} LUFS"),
              ("high-band noise reduced (gain-compensated)", n1 / gain < n0 * 0.5, f"noise band {n0:.4f} -> {n1/gain:.4f}"),
              ("true peak below 0 dBTP", l1["true_peak"] < 0, f"{l1['true_peak']} dBTP")]
    record("G", "Audio cleanup & loudness", all(c[1] for c in checks), checks, files=[str(clean)], seconds=time.time() - t0)


def test_H(a):
    """Music structure: tempo, downbeats, kick/snare hits, sections, build and drops vs a ground-truth track."""
    t0 = time.time()
    from studio import music
    f = ASSETS / "music_structured_140.wav"
    if not f.exists():
        synth.synth_structured_track(f)
    gt = json.loads(Path(str(f) + ".structure.json").read_text())
    m = music.analyze(f, OUT / "music_H")

    def rp(det, truth, tol):
        det, truth = np.array(det), np.array(truth)
        if not len(det) or not len(truth):
            return 0.0, 0.0
        return (float(np.mean([np.min(np.abs(det - x)) <= tol for x in truth])),
                float(np.mean([np.min(np.abs(truth - x)) <= tol for x in det])))
    db = rp(m["downbeats"], gt["downbeats"], 0.07)
    kk = rp([k["t"] for k in m["kicks"]], gt["kicks"], 0.05)
    drop_snares = [x for x in gt["snares"] if any(d <= x < d + 8 * gt["bar"] for d in gt["drops"])]
    sn = rp([x["t"] for x in m["snares"]], drop_snares, 0.05)
    _, sn_prec = rp([x["t"] for x in m["snares"]], gt["snares"], 0.05)
    secs = {(s["label"], round(s["start"] / gt["bar"])) for s in m["sections"]}
    want = {(s["label"], round(s["start"] / gt["bar"])) for s in gt["sections"]}
    checks = [("tempo", abs(m["tempo_bpm"] - gt["bpm"]) < 1, f"{m['tempo_bpm']} BPM (truth {gt['bpm']})"),
              ("downbeats (bar 1 found, ±70 ms)", min(db) >= 0.95, f"recall {db[0]:.2f}, precision {db[1]:.2f}"),
              ("kick hits (±50 ms)", min(kk) >= 0.9, f"recall {kk[0]:.2f}, precision {kk[1]:.2f}"),
              ("snare hits in drops (±50 ms), no false snares overall", sn[0] >= 0.9 and sn_prec >= 0.9,
               f"drop recall {sn[0]:.2f}, overall precision {sn_prec:.2f} (1/16 rolls are a texture, not separable hits)"),
              ("drops located (±1 beat)", len(m["drops"]) == 2 and all(min(abs(np.array(m["drops"]) - d)) < 60 / gt["bpm"] for d in gt["drops"]),
               f"{m['drops']} vs {gt['drops']}"),
              ("build-up located (±1 bar)", len(m["builds"]) == 1 and abs(m["builds"][0][0] - gt["build"][0]) < gt["bar"],
               f"{m['builds']} vs {gt['build']}"),
              ("all 5 true sections found with correct label & bar", want <= secs, f"detected {sorted(secs, key=lambda x: x[1])}")]
    record("H", "Music structure analysis", all(c[1] for c in checks), checks,
           notes="Synthetic structured 140 BPM track (test-only). Real dense mixes still need validation with user-supplied music.",
           files=[str(OUT / "music_H" / "music_structure.png")], seconds=time.time() - t0)


TESTS = {"A": test_A, "B": test_B, "C": test_C, "D": test_D, "E": test_E, "F": test_F, "G": test_G, "H": test_H}


def _merge_previous():
    """Keep results of tests not re-run this time (so a subset re-run doesn't drop the others)."""
    prev_f = OUT / "results.json"
    if not prev_f.exists():
        return
    ran = {r["id"] for r in RESULTS}
    for r in json.loads(prev_f.read_text()):
        if r["id"] not in ran:
            RESULTS.append(r)
    RESULTS.sort(key=lambda r: r["id"])


def write_report(before, after, total):
    lines = ["# TEST_RESULTS", "", f"Run: {dt.datetime.now():%Y-%m-%d %H:%M} on {platform.system()} {platform.release()} "
             f"({platform.machine()}, {__import__('os').cpu_count()} CPU threads, no GPU in this environment)", "",
             f"Total time: {total:.0f}s", "", "| Test | Result | Time | Last run |", "|---|---|---|---|"]
    for r in RESULTS:
        lines.append(f"| {r['id']}: {r['name']} | {'PASS' if r['passed'] else 'FAIL'} | {r['seconds']}s | {r.get('ran_at', '')} |")
    unchanged = before == after
    lines += ["", f"**Source media untouched:** {'YES' if unchanged else 'NO'} ({len(before)} files hashed with SHA-256 before and after)", ""]
    for r in RESULTS:
        lines += [f"## Test {r['id']}: {r['name']} — {'PASS' if r['passed'] else 'FAIL'}", "", "| Check | OK | Measured |", "|---|---|---|"]
        for c in r["checks"]:
            lines.append(f"| {c[0]} | {'✓' if c[1] else '✗'} | {str(c[2]).replace('|', '/')} |")
        if r["notes"]:
            lines += ["", r["notes"]]
        if r["files"]:
            lines += ["", "Files: " + ", ".join(f"`{Path(f).relative_to(ROOT) if f and Path(f).is_absolute() and str(f).startswith(str(ROOT)) else f}`" for f in r["files"] if f)]
        lines.append("")
    (ROOT / "docs" / "TEST_RESULTS.md").write_text("\n".join(lines))
    (OUT / "results.json").write_text(json.dumps(RESULTS, indent=2, default=str))


def main():
    sel = [s.upper() for s in sys.argv[1:]] or list(TESTS)
    config.ensure_dirs()
    a = assets()
    before = snapshot_hashes(ASSETS) | {("media/" + k): v for k, v in snapshot_hashes(config.MEDIA).items()}
    t0 = time.time()
    for k in sel:
        try:
            TESTS[k](a)
        except Exception as e:  # noqa: BLE001
            traceback.print_exc()
            record(k, TESTS[k].__doc__.strip().split(":")[0], False, [("test raised", False, f"{type(e).__name__}: {e}")])
    after = snapshot_hashes(ASSETS) | {("media/" + k): v for k, v in snapshot_hashes(config.MEDIA).items()}
    _merge_previous()
    write_report(before, after, time.time() - t0)
    print(f"\nSource media untouched: {before == after}")
    print(f"{sum(r['passed'] for r in RESULTS)}/{len(RESULTS)} tests passed. Report: docs/TEST_RESULTS.md")
    return 0 if all(r["passed"] for r in RESULTS) and before == after else 1


if __name__ == "__main__":
    sys.exit(main())
