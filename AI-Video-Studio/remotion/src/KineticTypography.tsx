import React from 'react';
import {AbsoluteFill, Easing, interpolate, spring, useCurrentFrame, useVideoConfig} from 'remotion';
import {AnimatedBackground} from './components/AnimatedBackground';

export type KineticProps = {
  width: number;
  height: number;
  fps: number;
  durationSec: number;
  lines: string[];
  palette: string[];
  beats: number[]; // seconds; text & background pulse on these
  camera: 'dramatic' | 'subtle' | 'none';
};

const FONT = "'Inter', 'Segoe UI', 'Helvetica Neue', Arial, sans-serif";

/** Multi-keyframe camera path (rotateX/rotateY/translateZ/pan) with eased interpolation between keys. */
const useCamera = (mode: KineticProps['camera']) => {
  const frame = useCurrentFrame();
  const {durationInFrames} = useVideoConfig();
  if (mode === 'none') return 'none';
  const k = mode === 'dramatic' ? 1 : 0.35;
  const keys = [0, 0.22, 0.45, 0.7, 1].map((f) => f * (durationInFrames - 1));
  const ease = {easing: Easing.inOut(Easing.cubic), extrapolateLeft: 'clamp' as const, extrapolateRight: 'clamp' as const};
  const rx = interpolate(frame, keys, [18, -6, 10, -12, 4].map((v) => v * k), ease);
  const ry = interpolate(frame, keys, [-28, 14, -10, 22, 0].map((v) => v * k), ease);
  const rz = interpolate(frame, keys, [-4, 2, -2, 3, 0].map((v) => v * k), ease);
  const tz = interpolate(frame, keys, [-600, 0, -180, 120, 0].map((v) => v * k), ease);
  const tx = interpolate(frame, keys, [-60, 30, -20, 40, 0].map((v) => v * k), ease);
  return `translateX(${tx}px) translateZ(${tz}px) rotateX(${rx}deg) rotateY(${ry}deg) rotateZ(${rz}deg)`;
};

const beatPulse = (t: number, beats: number[]) => {
  let p = 0;
  for (const b of beats) {
    if (t >= b && t < b + 0.4) p = Math.max(p, Math.exp(-(t - b) * 9));
  }
  return p;
};

const Line: React.FC<{text: string; local: number; len: number; pulse: number; accent: string}> = ({text, local, len, pulse, accent}) => {
  const {fps, width} = useVideoConfig();
  const chars = text.split('');
  // fit the whole line into ~72% of the width (bold caps ≈ 0.68em per glyph) so camera moves never push it off-frame
  const size = Math.min(width * 0.11, (width * 0.72) / Math.max(6, text.length * 0.68));
  const exitStart = len - Math.round(0.5 * fps);
  return (
    <div style={{display: 'flex', justifyContent: 'center', whiteSpace: 'pre'}}>
      {chars.map((ch, i) => {
        const delay = i * 1.6;
        const s = spring({frame: local - delay, fps, config: {damping: 12, stiffness: 120, mass: 0.6}});
        // keyframes: rise -> overshoot -> settle -> exit, each with its own easing
        const y = interpolate(local - delay, [0, 8, 16, 24], [size * 1.4, -size * 0.12, size * 0.04, 0], {
          extrapolateLeft: 'clamp',
          extrapolateRight: 'clamp',
          easing: Easing.out(Easing.back(1.6)),
        });
        const exit = interpolate(local, [exitStart + i * 0.8, exitStart + i * 0.8 + 10], [0, 1], {
          extrapolateLeft: 'clamp',
          extrapolateRight: 'clamp',
          easing: Easing.in(Easing.exp),
        });
        const rot = interpolate(s, [0, 1], [i % 2 ? 50 : -50, 0]);
        const sc = (0.4 + 0.6 * s) * (1 + pulse * 0.12);
        return (
          <span
            key={i}
            style={{
              display: 'inline-block',
              fontFamily: FONT,
              fontWeight: 900,
              fontSize: size,
              lineHeight: 1.05,
              color: i % 5 === 2 ? accent : 'white',
              transform: `translateY(${y - exit * size * 1.2}px) rotateX(${rot}deg) scale(${sc})`,
              opacity: Math.min(1, s * 1.5) * (1 - exit),
              filter: `blur(${Math.max(0, (1 - s) * 8) + exit * 10}px)`,
              textShadow: `0 ${size * 0.06}px ${size * 0.3}px rgba(0,0,0,0.6), 0 0 ${pulse * 40}px ${accent}`,
            }}
          >
            {ch}
          </span>
        );
      })}
    </div>
  );
};

export const KineticTypography: React.FC<KineticProps> = ({lines, palette, beats, camera}) => {
  const frame = useCurrentFrame();
  const {fps, durationInFrames} = useVideoConfig();
  const t = frame / fps;
  const pulse = beatPulse(t, beats);
  const per = durationInFrames / Math.max(1, lines.length);
  const idx = Math.min(lines.length - 1, Math.floor(frame / per));
  const local = frame - idx * per;
  const cam = useCamera(camera);
  const accent = palette[2] ?? '#f97316';
  const underline = interpolate(local, [6, 26], [0, 1], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp', easing: Easing.out(Easing.cubic)});
  return (
    <AbsoluteFill>
      <AnimatedBackground palette={palette} pulse={pulse} />
      <AbsoluteFill style={{perspective: 1400, alignItems: 'center', justifyContent: 'center'}}>
        <div style={{transform: cam, transformStyle: 'preserve-3d', display: 'flex', flexDirection: 'column', alignItems: 'center'}}>
          <Line text={lines[idx]} local={local} len={per} pulse={pulse} accent={accent} />
          <div style={{height: 10, width: `${underline * 60}%`, minWidth: 0, background: accent, borderRadius: 5, marginTop: 24, boxShadow: `0 0 30px ${accent}`}} />
        </div>
      </AbsoluteFill>
    </AbsoluteFill>
  );
};
