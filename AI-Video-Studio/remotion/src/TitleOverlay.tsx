import React from 'react';
import {AbsoluteFill, Easing, interpolate, spring, useCurrentFrame, useVideoConfig} from 'remotion';

export type Title = {
  text: string;
  start: number; // seconds
  duration: number; // seconds
  position?: 'top' | 'center' | 'bottom';
  style?: string;
  color?: string;
  accent?: string;
};

export type TitleOverlayProps = {
  width: number;
  height: number;
  fps: number;
  durationSec: number;
  style: string; // kinetic | bigpop | lowerthird | typewriter | glitch
  titles: Title[];
};

const FONT = "'Inter', 'Segoe UI', 'Helvetica Neue', Arial, sans-serif";

const posStyle = (pos: Title['position'], h: number): React.CSSProperties => {
  if (pos === 'top') return {justifyContent: 'flex-start', paddingTop: h * 0.12};
  if (pos === 'bottom') return {justifyContent: 'flex-end', paddingBottom: h * 0.16};
  return {justifyContent: 'center'};
};

const Kinetic: React.FC<{t: Title; local: number; dur: number}> = ({t, local, dur}) => {
  const {fps, width} = useVideoConfig();
  const words = t.text.split(/\s+/);
  const longest = Math.max(...words.map((w) => w.length), 4);
  const size = Math.min(width * 0.13, (width * 0.8) / (longest * 0.68)); // longest word always fits
  const outStart = dur - 0.45 * fps;
  return (
    <div style={{display: 'flex', flexWrap: 'wrap', justifyContent: 'center', gap: size * 0.25, maxWidth: width * 0.86}}>
      {words.map((w, i) => {
        const s = spring({frame: local - i * 4, fps, config: {damping: 13, stiffness: 140, mass: 0.7}});
        const out = interpolate(local, [outStart + i * 2, outStart + i * 2 + 10], [0, 1], {
          extrapolateLeft: 'clamp',
          extrapolateRight: 'clamp',
          easing: Easing.in(Easing.cubic),
        });
        return (
          <span
            key={i}
            style={{
              display: 'inline-block',
              fontFamily: FONT,
              fontWeight: 900,
              fontSize: size,
              lineHeight: 1,
              color: i % 3 === 1 ? t.accent ?? '#ffb347' : t.color ?? 'white',
              textTransform: 'uppercase',
              letterSpacing: interpolate(s, [0, 1], [size * 0.25, size * 0.02]),
              transform: `translateY(${(1 - s) * size * 0.9 - out * size * 0.6}px) scale(${0.6 + 0.4 * s}) rotate(${(1 - s) * (i % 2 ? 8 : -8)}deg)`,
              opacity: Math.min(1, s * 1.4) * (1 - out),
              filter: `blur(${(1 - s) * 10 + out * 8}px)`,
              textShadow: '0 6px 30px rgba(0,0,0,0.55)',
            }}
          >
            {w}
          </span>
        );
      })}
    </div>
  );
};

const BigPop: React.FC<{t: Title; local: number; dur: number}> = ({t, local, dur}) => {
  const {fps, width} = useVideoConfig();
  const s = spring({frame: local, fps, config: {damping: 9, stiffness: 180}});
  const o = interpolate(local, [dur - 8, dur], [1, 0], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});
  const size = Math.min(width * 0.16, (width * 1.6) / Math.max(5, t.text.length * 0.6));
  return (
    <div
      style={{
        fontFamily: FONT,
        fontWeight: 900,
        fontSize: size,
        color: t.color ?? 'white',
        textAlign: 'center',
        maxWidth: width * 0.9,
        transform: `scale(${s})`,
        opacity: o,
        textShadow: `0 0 40px ${t.accent ?? 'rgba(255,140,60,0.8)'}`,
        WebkitTextStroke: `${size * 0.02}px rgba(0,0,0,0.4)`,
      }}
    >
      {t.text}
    </div>
  );
};

const LowerThird: React.FC<{t: Title; local: number; dur: number}> = ({t, local, dur}) => {
  const {fps, width} = useVideoConfig();
  const inn = interpolate(local, [0, 0.5 * fps], [0, 1], {extrapolateRight: 'clamp', easing: Easing.out(Easing.exp)});
  const out = interpolate(local, [dur - 0.4 * fps, dur], [0, 1], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp', easing: Easing.in(Easing.cubic)});
  const size = width * 0.055;
  return (
    <div style={{alignSelf: 'flex-start', marginLeft: width * 0.07, overflow: 'hidden'}}>
      <div style={{height: size * 0.18, width: `${inn * 100}%`, background: t.accent ?? '#f97316', marginBottom: size * 0.2}} />
      <div
        style={{
          fontFamily: FONT,
          fontWeight: 800,
          fontSize: size,
          color: t.color ?? 'white',
          background: 'rgba(0,0,0,0.55)',
          padding: `${size * 0.25}px ${size * 0.5}px`,
          transform: `translateX(${(-1 + inn) * 110 - out * 110}%)`,
        }}
      >
        {t.text}
      </div>
    </div>
  );
};

const Typewriter: React.FC<{t: Title; local: number; dur: number}> = ({t, local, dur}) => {
  const {fps, width} = useVideoConfig();
  const n = Math.floor(interpolate(local, [0, Math.min(dur * 0.6, t.text.length * 2)], [0, t.text.length], {extrapolateRight: 'clamp'}));
  const o = interpolate(local, [dur - 8, dur], [1, 0], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});
  const caret = Math.floor(local / (fps / 3)) % 2 === 0;
  return (
    <div style={{fontFamily: "'Courier New', monospace", fontWeight: 700, fontSize: width * 0.07, color: t.color ?? 'white', opacity: o, maxWidth: width * 0.86, textAlign: 'center', textShadow: '0 4px 20px rgba(0,0,0,0.7)'}}>
      {t.text.slice(0, n)}
      <span style={{opacity: caret ? 1 : 0}}>▌</span>
    </div>
  );
};

const Glitch: React.FC<{t: Title; local: number; dur: number}> = ({t, local, dur}) => {
  const {width} = useVideoConfig();
  const jitter = (k: number) => (Math.sin(local * 12.9898 + k * 78.233) * 43758.5453) % 1;
  const on = local < 10 || (local % 23 < 3);
  const dx = on ? jitter(1) * width * 0.02 : 0;
  const o = interpolate(local, [dur - 6, dur], [1, 0], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});
  const size = Math.min(width * 0.14, (width * 1.6) / Math.max(5, t.text.length * 0.6));
  const base: React.CSSProperties = {position: 'absolute', fontFamily: FONT, fontWeight: 900, fontSize: size, whiteSpace: 'nowrap'};
  return (
    <div style={{position: 'relative', opacity: o, height: size, width: '100%', display: 'flex', justifyContent: 'center'}}>
      <span style={{...base, color: '#ff004c', transform: `translateX(${dx - size * 0.03}px)`, mixBlendMode: 'screen'}}>{t.text}</span>
      <span style={{...base, color: '#00e5ff', transform: `translateX(${-dx + size * 0.03}px)`, mixBlendMode: 'screen'}}>{t.text}</span>
      <span style={{...base, color: 'white'}}>{t.text}</span>
    </div>
  );
};

const STYLES: Record<string, React.FC<{t: Title; local: number; dur: number}>> = {
  kinetic: Kinetic,
  bigpop: BigPop,
  lowerthird: LowerThird,
  typewriter: Typewriter,
  glitch: Glitch,
};

export const TitleOverlay: React.FC<TitleOverlayProps> = ({titles, style}) => {
  const frame = useCurrentFrame();
  const {fps, height} = useVideoConfig();
  return (
    <AbsoluteFill style={{backgroundColor: 'transparent'}}>
      {titles.map((t, i) => {
        const s = Math.round(t.start * fps);
        const d = Math.round(t.duration * fps);
        const local = frame - s;
        if (local < 0 || local >= d) return null;
        const C = STYLES[t.style ?? style] ?? Kinetic;
        return (
          <AbsoluteFill key={i} style={{alignItems: 'center', ...posStyle(t.position, height)}}>
            <C t={t} local={local} dur={d} />
          </AbsoluteFill>
        );
      })}
    </AbsoluteFill>
  );
};
