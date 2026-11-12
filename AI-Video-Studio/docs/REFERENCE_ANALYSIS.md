# Reference analysis — the two uploaded F1 videos

Files (repo root, commit 5863e72, left untouched — SHA-256 verified after analysis):
- **A** `From Klickpin.com- 1090645234830524341-…mp4` — 19.0 s, 702×396 (16:9), 30 fps, AAC stereo, 0.9 Mbit/s
- **B** `From Klickpin.com- 1047086982133100910-…mp4` — 25.75 s, 720×720 (1:1), 60 fps, AAC stereo, 1.4 Mbit/s

Both are low-resolution re-uploads (Pinterest/Klickpin). Footage is third-party (F1 / @béla.films) — studied for
technique only; it is not reused in any edit.

## A — fast F1 hype montage (style of @béla.films)
| Aspect | Measured / observed |
|---|---|
| Pacing | 39 shots in 19 s, average 0.49 s, median 0.43 s, shortest 0.27 s, longest 1.13 s; 120 cuts/min; slightly slower toward the end |
| Transitions | all hard cuts; one white flash frame (9.47 s); fade to black on the end card |
| Shot variety | alternates tight driver close-ups (helmet eyes), onboard/low tracking shots, crowd/celebration, drifts & donuts, sparks, fireworks, podium |
| Colour | dark cinematic look (L* 29, strong blacks ≈ 3, contrast 20), neutral overall; 3 short black-and-white inserts (5.4–5.9, 7.6–7.9, 9.1–9.4 s) |
| Motion | medium motion, handheld/fast camera material (jitter 0.29), motion-blurred onboard shots — in the source footage, not added |
| Text | none during the montage; creator watermark end card "@BÉLA.FILMS" (last ~1 s) |
| Music sync | **not detectable in this copy**: cuts land on audio onsets no more than random times do (0.077 vs 0.081). Likely the re-uploader changed/shifted the audio. Beat sync of the original edit cannot be verified from this file. |

## B — slow cinematic hero shot (official F1 social style)
| Aspect | Measured / observed |
|---|---|
| Pacing | 2 real shots: wide donut shot 0–9.67 s, then one 16 s close side-tracking shot; fade out at 25.6 s |
| Speed | slow motion throughout (very low optical-flow motion for a spinning car: 0.1–0.6 px/frame); smooth, no sudden ramps |
| Camera | slow lateral track to the right in the second shot (constant direction, gentle ease) |
| Transition | one hard cut, 36 ms before a beat (≈ 2 frames at 60 fps) — beat-timed; it is 1.5 s *before* the detected drop (11.2 s), not on it |
| Text | "MAX VERSTAPPEN", tall condensed bold font, yellow, two lines, upper third over the sky; pops on instantly at 13.4 s (on a downbeat, +118 ms); static; no masking (sits above the car, never behind it) |
| Colour | very dark night look (L* 20, crushed blacks ≈ 0), saturated reds (fireworks, tail lights), slight magenta-red bias |
| Branding | F1 logo bug top-left (official footage) |
| Music | ≈ 120 BPM, intro → drop at 11.2 s |

## Can AI-Video-Studio make these?
| Technique | A | B | Status |
|---|---|---|---|
| Hard cuts at 0.27–1.1 s | ✔ | ✔ | have it (frame-exact) |
| Cut timing on beats/downbeats | ✔ | ✔ | have it (verified ±½ frame) |
| Flash frame, B&W inserts, fade-to-black end card | ✔ | ✔ | have it (FFmpeg) |
| Dark cinematic grade, crushed blacks, saturated reds | ✔ | ✔ | have it (grades/LUT) |
| Static condensed title, pop-on at a downbeat | — | ✔ | have it; needs a free condensed font (Anton / Bebas Neue, SIL OFL) |
| Choosing the *best* moments from many clips | ✔ | — | **in progress** (footage analysis) |
| Clean slow motion | — | ✔ | best if your footage is shot at 60–120 fps; otherwise frame interpolation: FFmpeg minterpolate (have, mediocre) or RIFE (free, needs GPU — not installed) |
| Smooth lateral camera track | — | ✔ | in the footage itself; can be simulated (crop-pan) on 4K footage |

**Biggest real requirement is footage.** Both edits get their look mostly from the footage: A needs ~30–40 varied,
high-quality clips (close-ups, onboard, crowd, action); B needs one or two well-shot, high-frame-rate hero shots.
