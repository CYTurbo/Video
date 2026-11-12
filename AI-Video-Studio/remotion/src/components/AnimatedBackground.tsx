import React from 'react';
import {AbsoluteFill, interpolate, random, useCurrentFrame, useVideoConfig} from 'remotion';

/** Drifting gradient + floating shapes + particle field. Deterministic (seeded), so renders are reproducible. */
export const AnimatedBackground: React.FC<{palette: string[]; pulse?: number; particles?: number}> = ({
  palette,
  pulse = 0,
  particles = 70,
}) => {
  const frame = useCurrentFrame();
  const {width, height, fps} = useVideoConfig();
  const t = frame / fps;
  const [c0, c1, c2, c3] = [palette[0] ?? '#0b0f2b', palette[1] ?? '#4c1d95', palette[2] ?? '#f97316', palette[3] ?? '#22d3ee'];
  const angle = 120 + t * 12;
  const shapes = Array.from({length: 7}, (_, i) => {
    const seed = `shape-${i}`;
    const size = (0.12 + random(seed) * 0.28) * Math.max(width, height);
    const x = (random(seed + 'x') * 1.2 - 0.1) * width + Math.sin(t * (0.3 + random(seed + 'sx') * 0.5) + i) * width * 0.06;
    const y = (random(seed + 'y') * 1.2 - 0.1) * height + Math.cos(t * (0.25 + random(seed + 'sy') * 0.4) + i) * height * 0.06;
    const rot = t * (random(seed + 'r') * 40 - 20);
    const kind = i % 3;
    return (
      <div
        key={i}
        style={{
          position: 'absolute',
          left: x - size / 2,
          top: y - size / 2,
          width: size,
          height: size,
          borderRadius: kind === 0 ? '50%' : kind === 1 ? '18%' : 0,
          border: kind === 2 ? `${size * 0.03}px solid ${i % 2 ? c2 : c3}` : undefined,
          background: kind === 2 ? 'transparent' : `radial-gradient(circle at 30% 30%, ${i % 2 ? c2 : c3}55, transparent 70%)`,
          transform: `rotate(${rot}deg) scale(${1 + pulse * 0.08})`,
          filter: 'blur(1px)',
          opacity: 0.55,
        }}
      />
    );
  });
  const dots = Array.from({length: particles}, (_, i) => {
    const seed = `p-${i}`;
    const speed = 0.02 + random(seed + 'v') * 0.08;
    const y = ((random(seed + 'y') - t * speed) % 1 + 1) % 1;
    const x = random(seed + 'x') + Math.sin(t * 0.8 + i) * 0.01;
    const s = 2 + random(seed + 's') * 6;
    const tw = 0.4 + 0.6 * Math.abs(Math.sin(t * (1 + random(seed + 't') * 3) + i));
    return (
      <div
        key={i}
        style={{
          position: 'absolute',
          left: x * width,
          top: y * height,
          width: s,
          height: s,
          borderRadius: '50%',
          background: i % 4 === 0 ? c2 : 'white',
          opacity: tw * 0.7,
          boxShadow: `0 0 ${s * 3}px ${i % 4 === 0 ? c2 : '#ffffff'}`,
        }}
      />
    );
  });
  const glow = interpolate(pulse, [0, 1], [0.25, 0.6]);
  return (
    <AbsoluteFill style={{background: `linear-gradient(${angle}deg, ${c0}, ${c1} 55%, ${c0})`, overflow: 'hidden'}}>
      <AbsoluteFill
        style={{
          background: `radial-gradient(ellipse at ${50 + Math.sin(t * 0.5) * 25}% ${50 + Math.cos(t * 0.4) * 20}%, ${c2}${Math.round(glow * 255)
            .toString(16)
            .padStart(2, '0')}, transparent 60%)`,
        }}
      />
      {shapes}
      {dots}
    </AbsoluteFill>
  );
};
