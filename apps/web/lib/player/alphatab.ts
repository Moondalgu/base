/**
 * alphaTab 로더 + 외부 미디어 동기화 배선.
 *
 * alphaTab은 렌더러 + 커서로만 쓴다. 소리는 100% StemPlayer가 낸다.
 * (PRD 4.2) 내장 신디사이저 alphaSynth는 쓰지 않는다.
 *
 * signalsmith와 같은 이유로 번들에 태우지 않는다 — alphaTab은 자체 Worker와
 * AudioWorklet을 만들고 폰트를 상대경로로 찾는데, Turbopack용 공식 플러그인이
 * 없다. public/vendor/alphatab/에서 원본을 그대로 로드하면 alphaTab이 자기
 * 스크립트 경로를 스스로 알아낸다.
 */

export const ALPHATAB_BASE = "/vendor/alphatab";

/* eslint-disable @typescript-eslint/no-explicit-any */
type AlphaTabModule = any;

let cached: AlphaTabModule | null = null;

export async function loadAlphaTab(): Promise<AlphaTabModule> {
  if (cached) return cached;
  cached = await import(
    /* webpackIgnore: true */ /* turbopackIgnore: true */ `${ALPHATAB_BASE}/alphaTab.mjs`
  );
  return cached;
}

export interface ExternalMediaBridge {
  /** 외부 재생 위치를 alphaTab에 밀어넣는다 (초 단위 입력) */
  updatePosition(seconds: number): void;
  destroy(): void;
}

export interface BridgeCallbacks {
  play(): void;
  pause(): void;
  seekTo(seconds: number): void;
  setRate(rate: number): void;
  setVolume(volume: number): void;
  durationSeconds(): number;
}

/**
 * alphaTab의 IExternalMediaHandler를 우리 플레이어에 연결한다.
 *
 * alphaTab이 커서를 그리려면 두 가지가 필요하다.
 *   1) 우리가 재생 위치를 주기적으로 알려준다 (updatePosition)
 *   2) alphaTab이 사용자 조작(악보 클릭 등)을 우리에게 되돌려준다 (handler)
 */
export function bridgeExternalMedia(
  api: any,
  callbacks: BridgeCallbacks,
): ExternalMediaBridge {
  const output = api.player?.output;
  if (!output) {
    throw new Error("alphaTab player output이 없습니다. playerMode를 확인하세요.");
  }

  output.handler = {
    get backingTrackDuration() {
      return callbacks.durationSeconds() * 1000;
    },
    get playbackRate() {
      return 1;
    },
    set playbackRate(value: number) {
      callbacks.setRate(value);
    },
    get masterVolume() {
      return 1;
    },
    set masterVolume(value: number) {
      callbacks.setVolume(value);
    },
    seekTo(timeMs: number) {
      callbacks.seekTo(timeMs / 1000);
    },
    play() {
      callbacks.play();
    },
    pause() {
      callbacks.pause();
    },
  };

  return {
    updatePosition(seconds: number) {
      output.updatePosition(seconds * 1000);
    },
    destroy() {
      output.handler = undefined;
    },
  };
}
