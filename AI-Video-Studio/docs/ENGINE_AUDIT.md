# ENGINE_AUDIT — what stands between the current engine and pro short-form edits

Honest assessment of the v1 engine (commit 47838d1) against the "viral edit" brief (phonk, funk, cinematic,
anime, football, car, velocity edits).

## What v1 does that is still useful
- Robust render backbone: frame-exact cuts, QC + auto-fix, loudness, H.264 social-ready output, 7 regression tests.
- Beat tracking verified (120 BPM ground truth, cuts within ½ frame of beats).
- Remotion / Blender bridges, captions, colour LUT matching.

## Why v1 edits look generic (root causes, highest impact first)

| # | Gap | Effect on the edit | Fix |
|---|---|---|---|
| 1 | **Music is only "a list of beats".** No downbeats, bars, phrases, sections, builds, drops, kick/snare/hat separation, energy curve. | Cuts don't follow musical structure; nothing anticipates or lands a drop; same density everywhere. | `studio/music.py`: structure map (downbeats, 4/8-bar phrases, sections, energy, builds, drops, per-band hits). |
| 2 | **Footage is never looked at.** Clips are cycled with arbitrary in-points. | Random moments, no action on the drop, no motion continuity between cuts. | Footage analysis: per-clip motion-energy curve (DIS optical flow), dominant motion direction, action peaks, sharpness, stability. |
| 3 | **One transition / one effect for the whole edit; effects on every beat** (`flash_on_beats`). | Exactly the "random effect on every beat" look. | Edit grammar: event-driven decisions — impact transitions only on phrase downbeats/drops, ramps *into* accents, quiet sections get long cinematic shots. |
| 4 | **Speed ramps are a fixed sine per clip**, not keyed to beats. | No real velocity feel. | Beat-keyed time-remap curves (slow between accents, snap on the hit), optional flow-based interpolation for the slow part. |
| 5 | **Transitions are stock `xfade` wipes** (and "whip" is a blur-crossfade). | Reads as template. | Custom compositor: real whip pan (both shots slide in the motion direction + `dblur` directional blur), zoom-through with radial blur, flash/exposure punch, glow/bloom, light streaks (`lagfun`), displacement (`displace`), masked transitions (`maskedmerge`). |
| 6 | **No styles** — presets only change grade/effect toggles. | All styles feel the same. | Style profiles (phonk, funk, cinematic, anime, football, car, velocity) each with its own pacing rules, transition vocabulary, ramp shapes, grade and effect budget. |
| 7 | **No preview/revision loop for creative issues.** QC checks only technical problems. | Bad creative decisions ship. | Low-res preview + sync report (cut vs musical event), repetition/readability checks, contact sheets for visual review before the final render. |
| 8 | **No masking/tracking/depth.** | No subject pop-outs, tracked text, parallax. | OpenCV trackers (MIL model-free; Nano/ViT with free ONNX models), segmentation (MediaPipe/rembg, Apache/MIT) and depth (Depth Anything V2 Small, Apache-2.0) as optional model-based steps — hardware-dependent, must be tested on the Windows PC. |
| 9 | Reference analysis measures pacing/colour only. | Can't identify ramps, whip pans, beat-locked effects. | Add motion-curve ramp detection, whip/zoom/flash classification, effect-vs-beat placement stats. |

## Tool decisions
| Tool | Decision | Reason |
|---|---|---|
| librosa (installed) | **Use** for all music analysis | ISC, Windows wheels, covers beats/onsets/bands/segmentation |
| aubio | **Rejected** | last release 0.4.9 (2019), no Windows/Python 3.13 wheel |
| Demucs 4.1.0 | **Optional, not installed** | MIT, but needs PyTorch (multi-GB) + model download; only worth it if band-split detection fails on dense mixes |
| FFmpeg `dblur`/`displace`/`maskedmerge`/`lagfun`/`perspective` | **Use** | already installed; real directional blur, displacement, masking, trails |
| OpenCV DIS optical flow | **Use** | motion analysis + flow-based interpolation without models |
| RIFE (ncnn-vulkan, MIT) | Candidate | best free frame interpolation, needs a Vulkan GPU — evaluate on the Windows PC |
| Rubber Band | Not needed yet | music is never time-stretched in these edits; FFmpeg `atempo` covers SFX |
| Kdenlive | Not needed | manual NLE; adds nothing to the automated pipeline |

## Blockers that need the user
- **Real footage** for the three demos (phonk/funk, cinematic, football/anime/car). Synthetic test clips cannot show
  whether creative decisions look professional.
- **Music with rights for the intended use** (own track, licensed track, or royalty-free with licence file).
- GPU-dependent features (RIFE, segmentation, depth) can only be verified on the Windows PC.

## Order of work
1. Music structure map (+ ground-truth tests) ← no footage needed
2. Footage analysis
3. Style profiles + edit grammar → shot-by-shot plan
4. Transition/effect compositor
5. Preview + revision loop
6. Optional model-based masking/tracking/depth, reference upgrades, trend-discovery workflow
