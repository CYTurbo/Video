# TEST_RESULTS

Run: 2026-11-14 13:59 on Linux 6.18.44-fc-v470 (x86_64, 4 CPU threads, no GPU in this environment)

Total time: 89s

| Test | Result | Time | Last run |
|---|---|---|---|
| A: Cinematic reel 1080x1920 15s | PASS | 143.3s | 2026-11-12 10:17 |
| B: Motion typography (Remotion) | PASS | 68.2s | 2026-11-12 10:19 |
| C: Music-synchronised edit | PASS | 78.8s | 2026-11-12 (full run) |
| D: Reference-style recreation | PASS | 324.6s | 2026-11-12 (full run) |
| E: Styled captions (burn-in) | PASS | 35.0s | 2026-11-12 (full run) |
| F: Blender scripted 3D animation | PASS | 172.1s | 2026-11-12 (full run) |
| G: Audio cleanup & loudness | PASS | 1.1s | 2026-11-12 (full run) |
| H: Music structure analysis | PASS | 6.0s | 2026-11-12 10:44 |
| I: Ranking countdown template | PASS | 88.6s | 2026-11-14 13:59 |

**Source media untouched:** YES (11 files hashed with SHA-256 before and after)

## Test A: Cinematic reel 1080x1920 15s — PASS

| Check | OK | Measured |
|---|---|---|
| file exists & decodes | ✓ | /home/user/Video/AI-Video-Studio/exports/testA_cinematic_reel.mp4 |
| resolution | ✓ | 1080x1920 |
| frame rate | ✓ | 30.0 |
| duration | ✓ | 15.000s (target 15.0) |
| video codec h264/yuv420p | ✓ | h264/yuv420p |
| no black/blank frames | ✓ | black=[], sampled luma std=[66.7, 57.7, 26.4, 22.6] |
| audio aac, length matches video | ✓ | aac 15.00s |
| loudness normalised ~-14 LUFS | ✓ | -14.74 LUFS |
| planner chose 9:16 + cinematic preset | ✓ | 1080x1920 preset=cinematic |
| smooth transitions rendered | ✓ | 4 x {'smoothleft'} at [3.0, 6.0, 9.0, 12.0] |
| motion blur (tmix) + speed ramp in graph | ✓ | tmix=3 frames; ramp=0.6 on alternate clips |
| colour grade measurably applied | ✓ | src b*=-9.24 contrast=19.58 -> out b*=2.14 contrast=27.3 |
| transitions are gradual (>=4 frames) | ✓ | frames-in-transition per cut=[11.0, 16.0, 16.0, 11.0] |

Synthetic procedural footage; motion blur is frame-blend (tmix) approximation of shutter blur.

Files: `exports/testA_cinematic_reel.mp4`, `exports/testA_cinematic_reel.contact.png`

## Test B: Motion typography (Remotion) — PASS

| Check | OK | Measured |
|---|---|---|
| file exists & decodes | ✓ | /home/user/Video/AI-Video-Studio/exports/testB_motion_typography.mp4 |
| resolution | ✓ | 1920x1080 |
| frame rate | ✓ | 30.0 |
| duration | ✓ | 10.000s (target 10.0) |
| video codec h264/yuv420p | ✓ | h264/yuv420p |
| no black/blank frames | ✓ | black=[], sampled luma std=[26.9, 40.6, 35.3, 33.5] |
| audio aac, length matches video | ✓ | aac 10.00s |
| loudness normalised ~-14 LUFS | ✓ | -14.9 LUFS |
| animated every frame (no static stretches) | ✓ | 100% of frames change |
| background animation (corner region changes) | ✓ | corner luma range 60.0 |
| multiple text keyframe states | ✓ | mean diff between line states [26.1 24.9] |
| text stays inside frame (no clipped glyphs at edges) | ✓ | max bright fraction in edge columns 0.000 |
| beat pulses wired to music | ✓ | 9 beats |

Easing (Easing.out(back), inOut(cubic), spring) and 5-key camera path are defined in remotion/src/KineticTypography.tsx; verified indirectly via per-frame motion.

Files: `exports/testB_motion_typography.mp4`, `exports/testB_motion_typography.contact.png`

## Test C: Music-synchronised edit — PASS

| Check | OK | Measured |
|---|---|---|
| tempo detected | ✓ | 120.0 BPM (truth 120) |
| beat detection vs ground truth (±70 ms) | ✓ | recall 0.98, precision 0.98 |
| file exists & decodes | ✓ | /home/user/Video/AI-Video-Studio/exports/testC_beat_sync.mp4 |
| resolution | ✓ | 1080x1920 |
| frame rate | ✓ | 30.0 |
| duration | ✓ | 12.000s (target 12.0) |
| video codec h264/yuv420p | ✓ | h264/yuv420p |
| no black/blank frames | ✓ | black=[], sampled luma std=[37.9, 27.2, 65.9, 21.6] |
| audio aac, length matches video | ✓ | aac 12.00s |
| loudness normalised ~-14 LUFS | ✓ | -14.92 LUFS |
| planned cuts land on true beats (±1 frame) | ✓ | 10 cuts, max offset 33 ms |
| visual cuts in OUTPUT align with OUTPUT audio beats (A/V sync) | ✓ | 10 cuts measured, median 8 ms, max 15 ms (1 frame = 33 ms) |

Synthetic 120 BPM track with known beat times used as ground truth.

Files: `exports/testC_beat_sync.mp4`, `exports/testC_beat_sync.contact.png`

## Test D: Reference-style recreation — PASS

| Check | OK | Measured |
|---|---|---|
| reference analysed: 8 shots found | ✓ | 8 shots, transitions {'cut': 7} |
| recreation passes QC | ✓ | PASS  testD_reference_recreation.mp4: 1920x1080 30.0fps h264/aac 10.00s -14.9 LUFS |
| pacing matched (avg shot length) | ✓ | [1.25, 1.25] |
| aspect matched | ✓ | [1.7778, 1.7778] |
| colour warmth matched (b*) | ✓ | [1.68, 1.03] |
| grain reproduced | ✓ | [4.613, 4.56] |
| style transfer moved colour toward reference | ✓ | ref b*=1.68, ungraded footage b*=-4.85, recreation b*=1.03 |

9/10 metrics within tolerance. Metric similarity only - visual judgement still required. Footage content differs by design.

| metric | reference | output | verdict |
|---|---|---|---|
| aspect | 1.7778 | 1.7778 | close |
| avg shot length (s) | 1.25 | 1.25 | close |
| cuts per minute | 42.0 | 42.0 | close |
| colour L_mean | 24.37 | 22.51 | close |
| colour L_contrast | 15.46 | 13.06 | close |
| colour a_mean | -1.39 | -1.59 | close |
| colour b_mean | 1.68 | 1.03 | close |
| colour saturation | 0.61 | 0.667 | close |
| grain | 4.613 | 4.56 | close |
| motion %/frame | 0.463 | 0.109 | differs |

Files: `exports/testD_reference_source.mp4`, `exports/testD_reference_recreation.mp4`, `exports/testD_reference_recreation.vs_reference.png`

## Test E: Styled captions (burn-in) — PASS

| Check | OK | Measured |
|---|---|---|
| file exists & decodes | ✓ | /home/user/Video/AI-Video-Studio/exports/testE_captions.mp4 |
| resolution | ✓ | 1080x1920 |
| frame rate | ✓ | 30.0 |
| duration | ✓ | 6.000s (target 6.0) |
| video codec h264/yuv420p | ✓ | h264/yuv420p |
| no black/blank frames | ✓ | black=[], sampled luma std=[46.0, 44.3, 43.1, 35.3] |
| audio aac, length matches video | ✓ | aac 6.00s |
| loudness normalised ~-14 LUFS | ✓ | -14.02 LUFS |
| captions visible in lower third only | ✓ | lower diff 12.4, upper diff 0.00 |
| word-by-word highlight events | ✓ | 11 ASS events |
| original clip audio kept | ✓ | aac track present |

Whisper transcription NOT tested here: model download failed (ProxyError). Works once huggingface.co is reachable.

Files: `exports/testE_captions.mp4`, `exports/testE_captions.contact.png`

## Test F: Blender scripted 3D animation — PASS

| Check | OK | Measured |
|---|---|---|
| render completed with expected specs | ✓ | PASS  testF_title3d.mp4: 960x540 24.0fps h264/no-audio 2.00s |
| camera animation (first vs last frame differ) | ✓ | mean diff 29.8 |
| frames not blank | ✓ | [51.3, 52.5, 43.9, 42.2] |

Engine: Cycles CPU via bpy (no GPU here).

Files: `tests/output/testF_title3d.mp4`, `tests/output/testF_title3d.contact.png`

## Test G: Audio cleanup & loudness — PASS

| Check | OK | Measured |
|---|---|---|
| normalised to -16 LUFS | ✓ | -22.59 -> -16.01 LUFS |
| high-band noise reduced (gain-compensated) | ✓ | noise band 0.0801 -> 0.0156 |
| true peak below 0 dBTP | ✓ | -8.72 dBTP |

Files: `exports/noisy_voice_clean.wav`

## Test H: Music structure analysis — PASS

| Check | OK | Measured |
|---|---|---|
| tempo | ✓ | 140.04 BPM (truth 140.0) |
| downbeats (bar 1 found, ±70 ms) | ✓ | recall 1.00, precision 1.00 |
| kick hits (±50 ms) | ✓ | recall 1.00, precision 1.00 |
| snare hits in drops (±50 ms), no false snares overall | ✓ | drop recall 1.00, overall precision 1.00 (1/16 rolls are a texture, not separable hits) |
| drops located (±1 beat) | ✓ | [20.5961, 41.169] vs [20.5714, 41.1429] |
| build-up located (±1 bar) | ✓ | [[13.7462, 20.5961]] vs [13.7143, 20.5714] |
| all 5 true sections found with correct label & bar | ✓ | detected [('intro', 0), ('build', 8), ('drop', 12), ('break', 20), ('drop', 24), ('outro', 31)] |

Synthetic structured 140 BPM track (test-only). Real dense mixes still need validation with user-supplied music.

Files: `tests/output/music_H/music_structure.png`

## Test I: Ranking countdown template — PASS

| Check | OK | Measured |
|---|---|---|
| file exists & decodes | ✓ | /home/user/Video/AI-Video-Studio/exports/testI_ranking.mp4 |
| resolution | ✓ | 1080x1920 |
| frame rate | ✓ | 30.0 |
| duration | ✓ | 29.500s (target 29.5) |
| video codec h264/yuv420p | ✓ | h264/yuv420p |
| no black/blank frames | ✓ | black=[], sampled luma std=[47.2, 84.2, 111.6, 44.3] |
| audio aac, length matches video | ✓ | aac 29.50s |
| loudness normalised ~-14 LUFS | ✓ | -14.8 LUFS |
| countdown order 5 -> 1 | ✓ | [5, 4, 3, 2, 1] |
| every reveal inside its entry | ✓ | [(1.7333, 3.4667, 6.8667), (6.8667, 8.6, 12.0333), (12.0333, 13.7333, 17.1667), (17.1667, 18.9, 22.3333), (22.3333, 24.0667, 29.2)] |
| #1 reveal lands on the music drop (loudness step in OUTPUT) | ✓ | +5.3 dB at 24.0667s |
| BEFORE photos shown at true brightness (no stuck flash) | ✓ | card luma [82.6, 89.3, 88.5, 90.2, 85.7] (placeholder grey ~70-100) |

Placeholder images (no people) + test track.

Files: `exports/testI_ranking.mp4`, `exports/testI_ranking.contact.png`
