import React from 'react';
import {AbsoluteFill, Easing, interpolate, spring, useCurrentFrame, useVideoConfig} from 'remotion';

export type LogoRevealProps = {width: number; height: number; fps: number; durationSec: number; text: string; tagline: string; color: string};

/** Shape-animation logo sting: expanding rings + rotating square mask + letter reveal. */
export const LogoReveal: React.FC<LogoRevealProps> = ({text, tagline, color}) => {
  const frame = useCurrentFrame();
  const {fps, width, height, durationInFrames} = useVideoConfig();
  const m = Math.min(width, height);
  const rings = [0, 6, 12].map((d, i) => {
    const p = interpolate(frame - d, [0, 30], [0, 1], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp', easing: Easing.out(Easing.cubic)});
    return (
      <div key={i} style={{position: 'absolute', width: m * 0.9 * p, height: m * 0.9 * p, borderRadius: '50%', border: `${4 + i * 2}px solid ${color}`, opacity: 1 - p}} />
    );
  });
  const sq = spring({frame: frame - 8, fps, config: {damping: 14}});
  const reveal = interpolate(frame, [18, 40], [0, 100], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp', easing: Easing.inOut(Easing.quad)});
  const tag = interpolate(frame, [40, 55], [0, 1], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});
  const out = interpolate(frame, [durationInFrames - 12, durationInFrames], [1, 0], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});
  return (
    <AbsoluteFill style={{background: '#08080c', alignItems: 'center', justifyContent: 'center', opacity: out}}>
      {rings}
      <div style={{position: 'absolute', width: m * 0.32, height: m * 0.32, border: `6px solid ${color}`, transform: `rotate(${(1 - sq) * 180 + 45}deg) scale(${sq})`}} />
      <div style={{fontFamily: 'Inter, Arial, sans-serif', fontWeight: 900, fontSize: m * 0.16, color: 'white', letterSpacing: m * 0.01, clipPath: `inset(0 ${100 - reveal}% 0 0)`}}>{text}</div>
      <div style={{position: 'absolute', top: height / 2 + m * 0.14, fontFamily: 'Inter, Arial, sans-serif', fontSize: m * 0.04, color, opacity: tag, letterSpacing: m * 0.012, textTransform: 'uppercase'}}>{tagline}</div>
    </AbsoluteFill>
  );
};
