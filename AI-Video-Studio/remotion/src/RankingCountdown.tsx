import React, {useEffect, useState} from 'react';
import {AbsoluteFill, continueRender, delayRender, Easing, Img, interpolate, random, spring, staticFile, useCurrentFrame, useVideoConfig} from 'remotion';

// Bundled free font (Anton, SIL OFL 1.1 - see public/fonts/Anton-OFL.txt). Rendering waits until it is loaded.
const useAnton = () => {
  const [handle] = useState(() => delayRender('Loading Anton font'));
  useEffect(() => {
    const f = new FontFace('Anton', `url(${staticFile('fonts/Anton-Regular.ttf')})`);
    f.load()
      .then((ff) => {
        document.fonts.add(ff);
        continueRender(handle);
      })
      .catch(() => continueRender(handle));
  }, [handle]);
};

export type RankItem = {
  rank: number;
  name: string;
  caption?: string;
  before: string; // path inside remotion/public (copied there by the Python bridge)
  after: string;
  start: number; // seconds
  reveal: number; // seconds: BEFORE -> AFTER switch (placed on a strong beat)
  end: number; // seconds
};

export type RankingProps = {
  width: number;
  height: number;
  fps: number;
  durationSec: number;
  title: string;
  subtitle?: string;
  items: RankItem[];
  beats: number[]; // small pulses on these times (prominent beats only)
  accent: string;
  introEnd: number; // seconds
};

const FONT = "'Anton', 'Bebas Neue', 'Impact', 'Arial Black', sans-serif";
const BODY = "'Inter', 'Segoe UI', Arial, sans-serif";
const clamp = {extrapolateLeft: 'clamp' as const, extrapolateRight: 'clamp' as const};

const pulseAt = (t: number, beats: number[]) => {
  let p = 0;
  for (const b of beats) if (t >= b && t < b + 0.3) p = Math.max(p, Math.exp(-(t - b) * 12));
  return p;
};

const Photo: React.FC<{src: string; from: number; dur: number; t: number; dir: number}> = ({src, from, dur, t, dir}) => {
  const k = interpolate(t, [from, from + dur], [0, 1], clamp);
  const scale = 1.06 + 0.08 * k; // slow push-in (Ken Burns)
  const x = dir * 2 * (k - 0.5); // gentle drift in %
  return (
    <Img
      src={staticFile(src)}
      style={{width: '100%', height: '100%', objectFit: 'cover', transform: `scale(${scale}) translateX(${x}%)`}}
    />
  );
};

const Tag: React.FC<{text: string; color: string; t0: number; t: number; size: number}> = ({text, color, t0, t, size}) => {
  const {fps} = useVideoConfig();
  const s = spring({frame: Math.round((t - t0) * fps), fps, config: {damping: 14, stiffness: 200}});
  return (
    <div
      style={{
        position: 'absolute', top: size * 0.6, left: size * 0.6, padding: `${size * 0.15}px ${size * 0.45}px`,
        background: color, color: '#0b0b0f', fontFamily: FONT, fontSize: size, letterSpacing: size * 0.06,
        transform: `translateX(${(1 - s) * -140}%)`, boxShadow: '0 8px 30px rgba(0,0,0,0.5)',
      }}
    >
      {text}
    </div>
  );
};

const Item: React.FC<{it: RankItem; t: number; accent: string; pulse: number; last: boolean}> = ({it, t, accent, pulse, last}) => {
  const {fps, width, height} = useVideoConfig();
  const gold = it.rank === 1;
  const col = gold ? '#ffcc33' : accent;
  const local = t - it.start;
  const f = Math.round(local * fps);
  // 1) rank slam
  const slam = spring({frame: f, fps, config: {damping: 11, stiffness: 160, mass: 0.8}});
  const numIn = interpolate(local, [0, 0.55, 0.8], [1, 1, 0], clamp); // full-screen number, then shrinks to badge
  const shake = local < 0.35 ? Math.sin(local * 90) * 18 * (0.35 - local) / 0.35 : 0;
  // 2) photo frame geometry
  const frameTop = height * 0.17;
  const frameH = height * 0.6;
  const enter = interpolate(local, [0.45, 0.85], [0, 1], {...clamp, easing: Easing.out(Easing.cubic)});
  // 3) reveal wipe on the beat
  const rv = interpolate(t, [it.reveal - 0.02, it.reveal + 0.35], [0, 1], {...clamp, easing: Easing.inOut(Easing.cubic)});
  // flash only AT/after the reveal (clamping alone would hold 0.85 for the whole BEFORE phase)
  const flash = t < it.reveal ? 0 : interpolate(t, [it.reveal, it.reveal + 0.18], [0.85, 0], clamp);
  const punch = 1 + 0.06 * Math.exp(-Math.max(0, t - it.reveal) * 7) * (t >= it.reveal ? 1 : 0);
  // 4) exit: fast slide up with motion blur
  const ex = last ? 0 : interpolate(t, [it.end - 0.22, it.end], [0, 1], {...clamp, easing: Easing.in(Easing.cubic)});
  const capIn = spring({frame: Math.round((t - it.reveal - 0.25) * fps), fps, config: {damping: 15}});
  const tag = width * 0.055;
  const burst = gold && t >= it.reveal
    ? Array.from({length: 46}, (_, i) => {
        const a = random(`a${i}`) * Math.PI * 2;
        const sp = 0.35 + random(`s${i}`) * 0.75;
        const d = (t - it.reveal) * sp * width;
        const o = interpolate(t - it.reveal, [0, 1.4], [1, 0], clamp);
        return <div key={i} style={{position: 'absolute', left: width / 2 + Math.cos(a) * d, top: frameTop + frameH / 2 + Math.sin(a) * d,
          width: 10, height: 10, borderRadius: 5, background: i % 3 ? '#ffd966' : '#ffffff', opacity: o, boxShadow: '0 0 14px #ffcc33'}} />;
      })
    : null;
  return (
    <AbsoluteFill style={{transform: `translateY(${-ex * 110}%)`, filter: ex > 0 ? `blur(${ex * 18}px)` : undefined}}>
      {/* photo card */}
      <div style={{position: 'absolute', left: width * 0.06, width: width * 0.88, top: frameTop, height: frameH, overflow: 'hidden',
        borderRadius: width * 0.03, border: `${width * 0.008}px solid ${col}`, boxShadow: `0 0 ${40 + pulse * 60}px ${col}88`,
        opacity: enter, transform: `translateY(${(1 - enter) * 12}%) scale(${(0.92 + 0.08 * enter) * punch})`}}>
        <AbsoluteFill><Photo src={it.before} from={it.start} dur={it.reveal - it.start} t={t} dir={1} /></AbsoluteFill>
        <AbsoluteFill style={{clipPath: `inset(0 0 ${(1 - rv) * 100}% 0)`}}>
          <Photo src={it.after} from={it.reveal} dur={it.end - it.reveal} t={t} dir={-1} />
        </AbsoluteFill>
        {rv > 0 && rv < 1 && <div style={{position: 'absolute', left: 0, right: 0, top: `${rv * 100}%`, height: 8, background: col, boxShadow: `0 0 30px ${col}`}} />}
        <AbsoluteFill style={{background: 'white', opacity: flash}} />
        {t < it.reveal ? <Tag text="BEFORE" color="#e5e5e5" t0={it.start + 0.6} t={t} size={tag} /> : <Tag text="AFTER" color={col} t0={it.reveal + 0.1} t={t} size={tag} />}
        {burst}
      </div>
      {/* rank badge (after the slam) */}
      <div style={{position: 'absolute', top: height * 0.045, left: 0, right: 0, textAlign: 'center', fontFamily: FONT,
        fontSize: width * 0.16, color: col, opacity: 1 - numIn, textShadow: `0 0 ${30 + pulse * 50}px ${col}`}}>#{it.rank}</div>
      {/* caption */}
      <div style={{position: 'absolute', top: frameTop + frameH + height * 0.03, left: width * 0.06, right: width * 0.06, textAlign: 'center',
        opacity: capIn, transform: `translateY(${(1 - capIn) * 40}px)`}}>
        <div style={{fontFamily: FONT, fontSize: width * 0.085, color: 'white', letterSpacing: 2, lineHeight: 1.05, textTransform: 'uppercase'}}>{it.name}</div>
        {it.caption ? <div style={{fontFamily: BODY, fontWeight: 600, fontSize: width * 0.04, color: '#d8d8e0', marginTop: 12}}>{it.caption}</div> : null}
      </div>
      {/* full-screen rank slam */}
      {numIn > 0 && (
        <AbsoluteFill style={{alignItems: 'center', justifyContent: 'center', background: `rgba(5,5,10,${0.85 * numIn})`}}>
          <div style={{fontFamily: FONT, fontSize: width * 0.62, color: col, lineHeight: 1, opacity: numIn,
            transform: `translateX(${shake}px) scale(${(2.4 - 1.4 * slam) * (0.6 + 0.4 * numIn)})`, textShadow: `0 0 80px ${col}`}}>
            #{it.rank}
          </div>
        </AbsoluteFill>
      )}
    </AbsoluteFill>
  );
};

export const RankingCountdown: React.FC<RankingProps> = ({title, subtitle, items, beats, accent, introEnd}) => {
  useAnton();
  const frame = useCurrentFrame();
  const {fps, width, height} = useVideoConfig();
  const t = frame / fps;
  const pulse = pulseAt(t, beats);
  const bgShift = (t * 8) % 360;
  const intro = t < introEnd;
  const ti = spring({frame, fps, config: {damping: 13}});
  const introOut = interpolate(t, [introEnd - 0.25, introEnd], [1, 0], clamp);
  const cur = items.find((it) => t >= it.start && t < it.end);
  return (
    <AbsoluteFill style={{background: `radial-gradient(circle at 50% ${40 + Math.sin(t) * 8}%, #2a1640, #0a0910 70%)`, overflow: 'hidden'}}>
      <AbsoluteFill style={{background: `conic-gradient(from ${bgShift}deg at 50% 45%, transparent, ${accent}22, transparent 30%)`, opacity: 0.7 + pulse * 0.3}} />
      {intro && (
        <AbsoluteFill style={{alignItems: 'center', justifyContent: 'center', opacity: introOut}}>
          <div style={{fontFamily: FONT, fontSize: width * 0.15, color: 'white', textAlign: 'center', lineHeight: 1,
            transform: `scale(${0.7 + 0.3 * ti})`, textShadow: `0 0 60px ${accent}`}}>{title}</div>
          {subtitle ? <div style={{fontFamily: BODY, fontWeight: 700, fontSize: width * 0.045, color: accent, marginTop: 30, opacity: ti}}>{subtitle}</div> : null}
        </AbsoluteFill>
      )}
      {cur && <Item key={cur.rank} it={cur} t={t} accent={accent} pulse={pulse} last={cur === items[items.length - 1]} />}
      {!intro && (
        <div style={{position: 'absolute', bottom: height * 0.035, left: 0, right: 0, textAlign: 'center', fontFamily: BODY,
          fontWeight: 800, fontSize: width * 0.032, color: '#ffffffaa', letterSpacing: 4}}>{title}</div>
      )}
    </AbsoluteFill>
  );
};
