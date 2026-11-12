import React from 'react';
import {CalculateMetadataFunction, Composition} from 'remotion';
import {TitleOverlay, TitleOverlayProps} from './TitleOverlay';
import {KineticTypography, KineticProps} from './KineticTypography';
import {LogoReveal, LogoRevealProps} from './LogoReveal';

// Every composition takes width/height/fps/durationSec from input props so the Python
// pipeline can drive any format (9:16, 16:9, 1:1) without editing code.
type Sized = {width: number; height: number; fps: number; durationSec: number};

const sized: CalculateMetadataFunction<any> = ({props}) => {
  const p = props as Sized;
  return {
    width: p.width,
    height: p.height,
    fps: p.fps,
    durationInFrames: Math.max(1, Math.round(p.durationSec * p.fps)),
  };
};

export const RemotionRoot: React.FC = () => {
  return (
    <>
      <Composition
        id="TitleOverlay"
        component={TitleOverlay}
        width={1080}
        height={1920}
        fps={30}
        durationInFrames={150}
        calculateMetadata={sized}
        defaultProps={
          {
            width: 1080,
            height: 1920,
            fps: 30,
            durationSec: 5,
            style: 'kinetic',
            titles: [{text: 'Your Title Here', start: 0.3, duration: 3.5, position: 'center'}],
          } satisfies TitleOverlayProps
        }
      />
      <Composition
        id="KineticTypography"
        component={KineticTypography}
        width={1920}
        height={1080}
        fps={30}
        durationInFrames={300}
        calculateMetadata={sized}
        defaultProps={
          {
            width: 1920,
            height: 1080,
            fps: 30,
            durationSec: 10,
            lines: ['MAKE IT MOVE', 'TYPE IN MOTION', 'EVERY FRAME COUNTS'],
            palette: ['#0b0f2b', '#4c1d95', '#f97316', '#22d3ee'],
            beats: [],
            camera: 'dramatic',
          } satisfies KineticProps
        }
      />
      <Composition
        id="LogoReveal"
        component={LogoReveal}
        width={1920}
        height={1080}
        fps={30}
        durationInFrames={120}
        calculateMetadata={sized}
        defaultProps={
          {width: 1920, height: 1080, fps: 30, durationSec: 4, text: 'STUDIO', tagline: 'made with code', color: '#f97316'} satisfies LogoRevealProps
        }
      />
    </>
  );
};
