# CAPABILITIES

Status legend:
- **Verified** — exercised by an automated test with a measured pass criterion (see TEST_RESULTS.md)
- **Rendered** — used inside a passing test render and visually checked on contact sheets, but not separately measured
- **Implemented** — code path exists and runs, not independently measured
- **Not tested here** — could not be run in the build environment (reason given)
- **Not supported** — honest gaps

All verification was done in a Linux container without a GPU (see SETUP_REPORT.md). The same code runs on Windows.

## Core processing (FFmpeg)
| Capability | Status | How |
|---|---|---|
| Inspect resolution / fps / duration / codecs / audio tracks / rotation | Verified (every test) | `studio inspect`, `media.probe` |
| Trim, crop to any aspect (cover crop with `focus_x`), scale, merge | Verified (A, C, D) | `render_segment`, `assemble` |
| 9:16 / 16:9 / 1:1 / 4:5 / 4K exports, H.264 High yuv420p + AAC, +faststart | Verified (A–E) | finalize encode |
| Horizontal → vertical with blurred fill | Implemented | `studio reformat --fit blur` |
| Frame extraction, contact sheets | Verified (every test) | `media.extract_frames`, `contact_sheet` |
| Speed change & speed ramps (continuous fast-slow-fast remap) | Rendered (A) | `fx.speed` setpts time-remap |
| Optical-flow slow motion | Implemented (slow) | `smooth_slowmo` → minterpolate |
| Batch/format conversion | Implemented | `reformat`, `render` per plan |
| QC: decode errors, black / frozen / blank frames, exposure, loudness, A/V length, spec match, auto-fix | Verified — QC caught 2 real bugs during development (frozen video, loudness off by 2 LU) | `studio/qc.py` |

## Cinematic editing
| Capability | Status | Notes |
|---|---|---|
| Smooth transitions (slides, fades, zoom, whip/blur, circle, wipes, pixelize, dip-to-black, flash) | Verified (A: gradual over ≥4 frames) | FFmpeg `xfade`, frame-exact offsets |
| Motion blur | Rendered (A) | Frame blending (`tmix`) — an approximation of shutter blur, not optical-flow blur |
| Camera shake | Rendered (A) | Layered-sine crop, per shot |
| Zoom (Ken Burns) / zoom transitions / beat punch-zoom | Rendered (A, C) | `zoompan` with 2× oversampling |
| Colour correction & cinematic grading (10 built-in looks + any .cube LUT) | Verified (A: measurable shift vs source) | `fx.GRADES`, `lut3d` |
| Film grain | Verified (D: grain re-measured in the output) | temporal luma noise |
| Light leaks | Rendered (A) | procedural, screen-blended, at cuts or throughout |
| Glitch, RGB split | Rendered (C) | `rgbashift` + noise + hue jitter, timed to cuts |
| Letterbox, vignette, sharpen | Implemented / rendered | |

## Motion graphics
| Capability | Status | Notes |
|---|---|---|
| Kinetic typography, multi-keyframe easing, animated backgrounds, particles, shapes | Verified (B) | Remotion `KineticTypography` |
| Dramatic 3D camera moves on 2D type (perspective, 5-key eased path) | Verified (B: motion every frame) | CSS 3D in Remotion |
| Animated titles over footage (kinetic, big pop, lower third, typewriter, glitch) | Rendered (A uses kinetic) | Remotion transparent ProRes 4444 overlay; FFmpeg drawtext fallback |
| Logo animation | Implemented | Remotion `LogoReveal` (rings, rotating mask, wipe) |
| 3D titles, materials, lighting, DOF, keyframed camera orbit, motion blur | Verified (F) | Blender `title3d.py`, headless |
| Python-driven Blender scene creation | Verified (F) | any script in `blender/scripts/` |
| Text tracking to moving objects | **Not supported** | no robust free tracker wired in; titles are screen-anchored |
| Particle systems in Blender | Not implemented | Remotion particle field available instead |

## Audio
| Capability | Status | Notes |
|---|---|---|
| Beat / tempo detection | Verified (C: 120.0 BPM, 98% recall & precision vs ground truth) | librosa, kick-band-stabilised |
| Beat-synchronised cuts | Verified (C: visual cuts within ±1 frame of beats in the final file) | |
| Flash / punch effects on beats; beat-pulsed typography | Rendered (B, C) | |
| Loudness normalisation (EBU R128 two-pass) | Verified (A–E: −14 LUFS ±2; G: −16 LUFS) | |
| Fade in/out, music + original audio mix | Verified (E keeps original audio) | |
| Voice cleanup (high-pass, FFT denoise, compression, limiter) | Verified (G: noise band −8 dB gain-compensated) | |
| Sound-effect sync to events | Implemented via plan timing; no SFX library is bundled (free SFX must be supplied) | |

## Social media
| Capability | Status |
|---|---|
| Instagram Reels / YouTube Shorts / TikTok 1080×1920 | Verified (A, C, E) |
| YouTube 16:9 | Verified (B, D) |
| Styled captions with word highlight (bold_pop, clean, boxed, neon) | Verified (E: visible in lower third only) |
| Automatic subtitle generation (Whisper) | **Not tested here** — the model host was blocked in the build container. Code path is standard faster-whisper; first run on Windows downloads the model for free. |
| Reusable presets | 9 presets in `presets/` (cinematic, glitch_energy, moody_dark, retro_film, bright_vlog, bw_dramatic, neon_night, clean_corporate, teal_orange_action) |

## Reference-based editing
| Capability | Status | Notes |
|---|---|---|
| Representative frames + contact sheet | Verified (D) | one keyframe per shot |
| Pacing (shots, ASL, cuts/min, trend) | Verified (D: all 7 cuts of a known reference found) | |
| Transition classification | Partly verified | cut / dissolve (blend-tested) / dip-to-black / flash. Slides and wipes are reported as cuts. |
| Colour (exposure, contrast, saturation, tint) → matching 3D LUT + closed-loop correction | Verified (D) | Reinhard transfer in Lab, re-measured after render |
| Grain, shake, zoom tendency, letterbox | Grain verified (D); others implemented | |
| Text placement | Heuristic only | edge-cluster detector (no OCR/fonts) |
| Comparison report (metric table + side-by-side frames) | Verified (D) | never claims a perfect match |

## Automation & usability
| Capability | Status |
|---|---|
| Natural language → plan → render → QC → export | Verified (A is driven entirely by a sentence) |
| Automatic tool selection (FFmpeg / Remotion / Blender) | Verified (A: FFmpeg+Remotion; B: Remotion; F: Blender) |
| Original media untouched | Verified (SHA-256 before/after every test run; pipeline refuses to write into `media/`) |
| No paid service needed | Verified — every tested workflow ran offline from free tools (Remotion: free licence tier, see SETUP_REPORT) |
