"""High-level jobs that pick the right tool automatically.

edit        -> FFmpeg pipeline (+ Remotion titles, + Blender 3D intro, + Remotion logo outro)
typography  -> Remotion KineticTypography (+ beat-synced pulses from music) -> FFmpeg mux/loudnorm -> QC
reference   -> analyse reference -> style plan (LUT, pacing, transitions, effects) -> edit -> compare
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from . import audio as A
from . import config
from .log import log
from .media import run


def execute(plan: dict) -> dict:
    job = plan.get("job", "edit")
    if job == "typography":
        return typography(plan)
    if job == "reference":
        return reference_edit(plan)
    return edit(plan)


def edit(plan: dict) -> dict:
    from .render import render_plan
    plan = dict(plan)
    W, H, F = plan.get("width", 1080), plan.get("height", 1920), plan.get("fps", 30)
    work = config.INTERMEDIATE / plan.get("name", "edit")
    work.mkdir(parents=True, exist_ok=True)
    clips = list(plan.get("clips", []))
    if plan.get("intro_3d"):
        from . import blender_bridge
        i3 = plan["intro_3d"]
        p = blender_bridge.render_title3d(i3["text"], work / "intro_3d.mp4", W, H, F, i3.get("duration", 3.0),
                                          samples=i3.get("samples", 12))
        clips.insert(0, {"src": str(p), "in": 0})
    if plan.get("outro_logo"):
        from . import remotion_bridge
        o = plan["outro_logo"]
        p = remotion_bridge.render_logo(o["text"], o.get("tagline", ""), W, H, F, o.get("duration", 2.5), work / "outro_logo.mp4")
        clips.append({"src": str(p), "in": 0})
    plan["clips"] = clips
    return render_plan(plan)


def typography(plan: dict) -> dict:
    from . import qc as QC
    from . import remotion_bridge
    W, H, F, D = plan.get("width", 1920), plan.get("height", 1080), plan.get("fps", 30), float(plan.get("duration", 20))
    name = plan.get("name", "typography")
    work = config.INTERMEDIATE / name
    work.mkdir(parents=True, exist_ok=True)
    music = (plan.get("audio") or {}).get("music")
    beats = []
    if music:
        bt = A.analyze_beats(music)
        (work / "beats.json").write_text(json.dumps(bt, indent=1))
        beats = [b for b in bt["prominent_beats"] if b < D]
        log(f"   music: {bt['tempo_bpm']:.1f} BPM, {len(beats)} prominent beats used for pulses")
    silent = remotion_bridge.render_kinetic(plan.get("lines") or ["MAKE IT MOVE"], W, H, F, D, work / "kinetic.mp4",
                                            beats=beats, palette=plan.get("palette"), camera=plan.get("camera", "dramatic"))
    out = config.EXPORTS / (plan.get("export", {}).get("filename") or f"{name}.mp4")
    cmd = [config.ffmpeg(), "-y", "-v", "error", "-i", str(silent)]
    if music:
        # trim + fade first, THEN measure loudness on exactly what will be heard (two-pass loudnorm)
        clip = work / "music_cut.wav"
        run([config.ffmpeg(), "-y", "-v", "error", "-i", music, "-af",
             f"atrim=0:{D},asetpts=PTS-STARTPTS,afade=t=in:d=0.2,afade=t=out:st={max(0, D-1.2)}:d=1.2",
             "-ar", "48000", "-ac", "2", str(clip)])
        cmd += ["-i", str(clip)]
        af = A.loudnorm_filter(clip) + ",aresample=48000"
        cmd += ["-filter_complex", f"[1:a]{af}[a]", "-map", "0:v", "-map", "[a]", "-c:a", "aac", "-b:a", "192k"]
    cmd += ["-t", str(D), "-c:v", "libx264", "-crf", "18", "-preset", "medium", "-pix_fmt", "yuv420p",
            "-movflags", "+faststart", str(out)]
    run(cmd)
    expect = {"width": W, "height": H, "fps": F, "duration": D, "vcodec": "h264", "audio": bool(music)}
    if music:
        expect.update({"acodec": "aac", "lufs": -14.0})
    final, rep = QC.check_and_fix(out, expect)
    log("   " + QC.summarize(rep))
    return {"output": str(final), "qc": rep, "beats_used": beats}


def reference_edit(plan: dict) -> dict:
    from . import reference as R
    from .media import list_media
    ref = plan.get("reference") or next((str(p) for p in list_media(config.REFERENCE, ("video",))), None)
    if not ref:
        raise FileNotFoundError("No reference video: put one in media/reference/ or pass --reference")
    footage = [c["src"] if isinstance(c, dict) else c for c in plan.get("clips", [])]
    if not footage:
        raise ValueError("No footage supplied for the recreation")
    name = plan.get("name", "reference_edit")
    prof = R.analyze(ref, config.PROJECTS / name / "reference_analysis")
    music = (plan.get("audio") or {}).get("music")
    style_plan = R.style_to_plan(prof, footage, name, music=music, duration=plan.get("duration_override"),
                                 width=plan.get("width_override"), height=plan.get("height_override"))
    for k in ("titles", "title_style", "captions"):
        if plan.get(k):
            style_plan[k] = plan[k]
    if style_plan.get("titles") and style_plan.get("_text_position_hint"):
        for t in style_plan["titles"]:
            t.setdefault("position", style_plan["_text_position_hint"])
    log(f"   style plan: {len(style_plan['cuts'])} cuts, effects {style_plan['effects']}, LUT {Path(style_plan['grade']).name}")
    res = edit(style_plan)
    # closed loop: measure the render's colour and correct the LUT once if it missed the reference
    ref_m = prof["lab_moments"]
    fr, _, _ = R._frames_lowres(res["output"], fps_cap=6)
    out_m = R.lab_moments(fr)
    delta = np.abs(np.array(ref_m["mean"]) - np.array(out_m["mean"]))
    log(f"   colour check: dL={delta[0]:.1f} da={delta[1]:.1f} db={delta[2]:.1f}")
    if delta[0] > 3 or delta[1] > 2 or delta[2] > 2:
        lut2 = R.correct_lut(Path(style_plan["grade"]), out_m, ref_m, config.PROJECTS / name / "match_reference_corrected.cube")
        style_plan["grade"] = str(lut2)
        (config.PROJECTS / name / "plan.json").write_text(json.dumps(style_plan, indent=2))
        log("   colour correction pass with corrected LUT")
        res = edit(style_plan)
        res["colour_correction_pass"] = True
    cmp = R.compare(ref, res["output"], config.PROJECTS / name)
    log("   comparison vs reference:\n" + cmp["table_md"])
    log(f"   {cmp['close']}/{cmp['total']} metrics close. {cmp['note']}")
    res["comparison"] = cmp
    res["reference_profile"] = str(config.PROJECTS / name / "reference_analysis" / "style_profile.json")
    res["limitations"] = prof["limitations"]
    return res
