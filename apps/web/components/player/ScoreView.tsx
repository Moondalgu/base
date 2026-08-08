"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  ALPHATAB_BASE,
  bridgeExternalMedia,
  loadAlphaTab,
  type BridgeCallbacks,
  type ExternalMediaBridge,
} from "@/lib/player/alphatab";
// 단계 번호는 한 곳에서만 정의한다. 여기에 따로 두었다가 3단계로 재편할 때
// 갱신을 놓쳐, 원본을 보고 있는데 "쉬운 버전" 배너가 뜨는 버그가 있었다.
import { ORIGINAL_LEVEL } from "./ScoreControls";

/**
 * 부모(PlayerShell)가 재생/정지를 alphaTab 경유로 걸 수 있게 하는 핸들.
 *
 * 커서·비트 하이라이트는 alphaTab이 자신의 재생 상태가 "재생 중"일 때만
 * 그린다. 엔진만 몰래 켜면 alphaTab은 정지 상태로 남아 커서가 죽는다.
 * 그래서 UI 버튼은 alphaTab을 켜고, alphaTab이 handler를 통해 엔진을 켠다.
 */
export interface ScoreControl {
  setPlaying(playing: boolean): void;
  /** 브라우저 인쇄 창을 띄운다. 여기서 PDF로 저장한다 */
  print(): void;
}

interface Props {
  hash: string;
  /** 재생 위치(초). 이 값이 바뀔 때마다 커서를 옮긴다 */
  position: number;
  callbacks: BridgeCallbacks;
  /** 악보가 준비되면 여기에 재생 제어 핸들을 채워준다 (없으면 악보 미준비) */
  controlRef?: React.MutableRefObject<ScoreControl | null>;
  /** 품질 점수 — 낮으면 경고 배너를 띄운다 */
  qualityLevel?: "good" | "reference" | "failed";
  /** 난이도 (1=입문 ~ 5=원곡) */
  level?: number;
  /**
   * 이조(반음). **재생 피치와 같은 값이어야 한다** — 들리는 음과 악보가
   * 어긋나면 연습 도구로 쓸 수 없다.
   */
  transpose?: number;
  /** 튜닝 프리셋. 반음 내림 튜닝을 쓰면 이조 없이 키를 내릴 수 있다 */
  tuning?: string;
  /** 악보가 그려졌는지 부모에게 알린다. 인쇄 버튼을 띄울지 판단하는 데 쓴다 */
  onReady?: (ready: boolean) => void;
}

type Status = "loading" | "ready" | "empty" | "error";

/** 한 행에 놓을 마디 수. 참조 악보(akbobada)가 4마디씩이다. */
const BARS_PER_ROW = 4;

/**
 * 자동 넘김 뷰가 한 번에 보여줄 마디 수. 행당 마디 수와 같게 두어 한 행만 남긴다.
 * 창은 1·5·9…처럼 고정 경계로 끊는다 — 커서가 지날 때마다 한 마디씩 밀면
 * 악보가 계속 흔들려 읽을 수가 없다.
 */
const PAGE_BARS = BARS_PER_ROW;

type ViewMode = "continuous" | "paged";

/** 악보를 다시 그릴 때 워커가 헤더로 알려주는 것들 */
interface ScoreMeta {
  level: number;
  notes: number;
  octaveFolded: number;
  fromStatic: boolean;
}

export default function ScoreView({
  hash,
  position,
  callbacks,
  controlRef,
  qualityLevel,
  level = ORIGINAL_LEVEL,
  transpose = 0,
  tuning,
  onReady,
}: Props) {
  const hostRef = useRef<HTMLDivElement | null>(null);
  const bridgeRef = useRef<ExternalMediaBridge | null>(null);
  const callbacksRef = useRef(callbacks);
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const apiRef = useRef<any>(null);
  // api가 아직 없을 때 도착한 악보를 담아둔다. 악보 요청과 alphaTab 초기화가
  // 각각 비동기라 순서가 보장되지 않는다.
  const pendingTexRef = useRef<string | null>(null);
  const [status, setStatus] = useState<Status>("loading");
  const [error, setError] = useState("");
  const [meta, setMeta] = useState<ScoreMeta | null>(null);
  const [viewMode, setViewMode] = useState<ViewMode>("continuous");
  // 창 이동은 alphaTab 이벤트 안에서 일어난다. 그 시점의 값을 읽어야 하므로
  // 상태가 아니라 ref에 둔다(리렌더를 기다리면 창이 한 박 늦게 움직인다).
  const viewModeRef = useRef<ViewMode>("continuous");
  /** 현재 창의 첫 마디. alphaTab의 startBar와 같은 1-based */
  const windowStartRef = useRef(1);
  const onReadyRef = useRef(onReady);

  // 렌더 중에 ref를 쓰면 안 된다(react-hooks/refs). effect에서 동기화한다.
  // 부모가 매 렌더마다 새 콜백 객체를 만들어도 alphaTab 배선을 다시 하지 않게
  // 하려고 ref에 담아둔다.
  useEffect(() => {
    callbacksRef.current = callbacks;
  }, [callbacks]);

  useEffect(() => {
    onReadyRef.current = onReady;
  }, [onReady]);

  const applyTex = useCallback((tex: string) => {
    if (apiRef.current) apiRef.current.tex(tex);
    else pendingTexRef.current = tex;
  }, []);

  /**
   * 표시 범위를 설정에 반영하고 다시 그린다.
   *
   * `display.startBar`는 1-based 마디 번호, `barCount`는 −1이 전체다.
   * 설정만 바꾸면 아무 일도 일어나지 않는다 — updateSettings()로 내려보내고
   * render()로 다시 그려야 한다(alphaTab.d.ts의 updateSettings 예제).
   */
  const applyWindow = useCallback((mode: ViewMode, startBar: number) => {
    const api = apiRef.current;
    if (!api?.settings) return;
    const nextStart = mode === "paged" ? startBar : 1;
    const nextCount = mode === "paged" ? PAGE_BARS : -1;
    const display = api.settings.display;
    // 같은 범위로 다시 그리면 커서·스크롤만 흔들린다
    if (display.startBar === nextStart && display.barCount === nextCount) return;
    display.startBar = nextStart;
    display.barCount = nextCount;
    api.updateSettings();
    api.render();
  }, []);

  // alphaTab 인스턴스는 곡마다 한 번만 만든다. 난이도·이조가 바뀔 때
  // 인스턴스를 다시 만들면 커서 배선과 스크롤 위치가 초기화된다.
  useEffect(() => {
    let disposed = false;
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    let api: any = null;

    (async () => {
      try {
        const alphaTab = await loadAlphaTab();
        if (disposed || !hostRef.current) return;

        api = new alphaTab.AlphaTabApi(hostRef.current, {
          core: {
            tex: true,
            fontDirectory: `${ALPHATAB_BASE}/font/`,
          },
          display: {
            // 통상적인 베이스 악보 형태: 오선보 + TAB 병기 (참고 영상들과 동일)
            staveProfile: alphaTab.StaveProfile.ScoreTab,
            // Parchment 레이아웃을 쓰는 이유는 마디 폭이다. 기본 Page 레이아웃은
            // 마디 폭을 **내용량에 비례해** 배분한다. 그래서 음이 촘촘한 마디는
            // 넓고 온쉼표 하나뿐인 마디는 좁아져, 한 행에서 마디 하나가 화면
            // 대부분을 먹는다. 종이 악보는 마디 폭이 균등하다.
            //
            // Parchment는 마디 폭을 `displayScale` 비율로 배분하고, 이 값은
            // 설정하지 않으면 전부 1이라 **균등하게 나뉜다**(alphaTab 문서:
            // "if there are 3 bars and all define scale 1, they are sized evenly").
            layoutMode: alphaTab.LayoutMode.Parchment,
            scale: 0.9,
          },
          notation: {
            // TAB 줄 아래에 리듬 기둥을 그린다. 없으면 음표 길이를 알 수 없다.
            rhythmMode: alphaTab.TabRhythmMode.ShowWithBars,
          },
          player: {
            // 외부 오디오(우리 StemPlayer)를 시간축으로 쓴다
            playerMode: alphaTab.PlayerMode.EnabledExternalMedia,
            enableCursor: true,
            enableUserInteraction: true,
            scrollMode: alphaTab.ScrollMode.Continuous,
            scrollElement: hostRef.current.parentElement ?? undefined,
          },
        });

        // 행당 마디 수는 모델에 있다. Parchment 레이아웃이 이 값을 읽어
        // 시스템(행)을 나누고, 그 안에서 마디를 displayScale 비율대로 배분한다.
        //
        // 트랙 값이 악보 값보다 우선하므로 **양쪽에 다 넣어야 한다.** 악보에만
        // 넣으면 트랙의 기본값이 이겨서 행당 마디 수가 바뀌지 않는다.
        api.scoreLoaded.on(
          (loaded: {
            defaultSystemsLayout?: number;
            systemsLayout?: number[];
            tracks?: { defaultSystemsLayout?: number; systemsLayout?: number[] }[];
          }) => {
            loaded.defaultSystemsLayout = BARS_PER_ROW;
            // systemsLayout은 행별 마디 수를 하나씩 지정하는 배열이다. 남아
            // 있으면 defaultSystemsLayout보다 우선하므로 비운다.
            loaded.systemsLayout = [];
            for (const track of loaded.tracks ?? []) {
              track.defaultSystemsLayout = BARS_PER_ROW;
              track.systemsLayout = [];
            }
            // alphaTab은 트랙을 지정하지 않으면 **첫 트랙만** 그린다(d.ts:699).
            // 3단 악보는 Vocal이 첫 트랙이라 베이스가 통째로 사라진다.
            // scoreLoaded는 renderTracks로도 다시 발화하므로, 이미 전 트랙을
            // 그리고 있으면 다시 부르지 않는다(무한 재렌더 방지).
            const all = loaded.tracks ?? [];
            if (all.length > 1 && api.tracks?.length !== all.length) {
              api.renderTracks(all);
            }
          },
        );

        api.error.on((e: unknown) => {
          if (!disposed) {
            setError(String(e));
            setStatus("error");
          }
        });

        // 자동 넘김 — 연주 중인 마디가 창을 벗어나면 그 마디를 담는 창으로 옮긴다.
        // 재생 마디는 alphaTab이 커서를 옮길 때 같이 주는 Beat에서 얻는다
        // (beat.voice.bar.index는 0-based). 위치→마디 환산을 따로 하면 커서와
        // 창이 서로 다른 마디를 가리킬 수 있다.
        api.playedBeatChanged.on((beat: { voice?: { bar?: { index?: number } } }) => {
          if (disposed) return;
          const index = beat?.voice?.bar?.index;
          if (typeof index !== "number") return;
          // 전체 악보를 보는 동안에도 창 번호는 따라간다. 그래야 뷰를 바꾼
          // 순간 첫 마디가 아니라 연주 중인 마디가 보인다.
          const start = Math.floor(index / PAGE_BARS) * PAGE_BARS + 1;
          if (start === windowStartRef.current) return;
          windowStartRef.current = start;
          if (viewModeRef.current === "paged") applyWindow("paged", start);
        });

        api.renderFinished.on(() => {
          if (disposed) return;
          if (!bridgeRef.current) {
            try {
              bridgeRef.current = bridgeExternalMedia(api, {
                play: () => callbacksRef.current.play(),
                pause: () => callbacksRef.current.pause(),
                seekTo: (s) => callbacksRef.current.seekTo(s),
                setRate: (r) => callbacksRef.current.setRate(r),
                setVolume: (v) => callbacksRef.current.setVolume(v),
                durationSeconds: () => callbacksRef.current.durationSeconds(),
              });
            } catch (e) {
              setError(String(e));
              setStatus("error");
              return;
            }
            if (controlRef) {
              controlRef.current = {
                setPlaying: (playing: boolean) => {
                  // alphaTab을 켜면 alphaTab이 handler.play()로 엔진까지 켠다.
                  // 이 경로여야 커서·하이라이트가 함께 움직인다.
                  if (playing) api.play();
                  else api.pause();
                },
                print: () => {
                  // 인쇄는 화면 뷰와 무관하게 전곡을 낸다. 자동 넘김 상태에서는
                  // startBar/barCount가 4마디로 좁혀져 있으므로 여기서 되돌린다.
                  api.print("", {
                    display: { barsPerRow: BARS_PER_ROW, startBar: 1, barCount: -1 },
                  });
                },
              };
            }
          }
          setStatus("ready");
          onReadyRef.current?.(true);
        });

        apiRef.current = api;
        if (pendingTexRef.current !== null) {
          api.tex(pendingTexRef.current);
          pendingTexRef.current = null;
        }
      } catch (e) {
        if (!disposed) {
          setError(e instanceof Error ? (e.stack ?? e.message) : String(e));
          setStatus("error");
        }
      }
    })();

    return () => {
      disposed = true;
      onReadyRef.current?.(false);
      if (controlRef) controlRef.current = null;
      bridgeRef.current?.destroy();
      bridgeRef.current = null;
      apiRef.current = null;
      api?.destroy?.();
    };
    // controlRef는 ref 객체라 identity가 안 변한다 — hash에만 반응한다.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [hash]);

  // 난이도·이조·튜닝이 바뀌면 악보만 다시 받아 갈아끼운다.
  useEffect(() => {
    let cancelled = false;
    (async () => {
      const params = new URLSearchParams({
        level: String(level),
        transpose: String(transpose),
      });
      if (tuning) params.set("tuning", tuning);
      try {
        const res = await fetch(`/api/scores/${hash}?${params}`);
        if (cancelled) return;
        if (!res.ok) {
          setStatus("empty");
          setError(await res.text());
          return;
        }
        const tex = await res.text();
        if (cancelled) return;
        setMeta({
          level: Number(res.headers.get("x-score-level") ?? level),
          notes: 0,
          octaveFolded: Number(res.headers.get("x-score-octave-folded") ?? 0),
          fromStatic: res.headers.get("x-score-source") === "static",
        });
        applyTex(tex);
      } catch (e) {
        if (!cancelled) {
          setError(e instanceof Error ? e.message : String(e));
          setStatus("error");
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [hash, level, transpose, tuning, applyTex]);

  // 재생 위치를 alphaTab에 밀어넣는다. 부모가 50ms 주기로 갱신한다.
  useEffect(() => {
    bridgeRef.current?.updatePosition(position);
  }, [position]);

  // 뷰를 바꾸면 표시 범위를 다시 건다. status가 바뀔 때도 한 번 걸어
  // 인스턴스가 늦게 준비된 경우를 메운다(applyWindow가 같은 범위면 건너뛴다).
  useEffect(() => {
    viewModeRef.current = viewMode;
    applyWindow(viewMode, windowStartRef.current);
  }, [viewMode, status, applyWindow]);

  const isReduced = level < ORIGINAL_LEVEL;

  return (
    <section className="space-y-3">
      {qualityLevel === "reference" && (
        <p className="rounded border border-amber-300 bg-amber-50 px-3 py-2 text-xs text-amber-800 dark:border-amber-800 dark:bg-amber-950 dark:text-amber-200">
          자동 생성된 악보입니다. 부정확할 수 있어요.
        </p>
      )}

      {isReduced && (
        <p className="rounded border border-sky-300 bg-sky-50 px-3 py-2 text-xs text-sky-800 dark:border-sky-800 dark:bg-sky-950 dark:text-sky-200">
          쉬운 버전입니다. 원곡을 단순하게 고쳐 적었으므로 원곡과 다릅니다.
        </p>
      )}

      {meta && meta.octaveFolded > 0 && (
        <p className="text-xs text-neutral-500">
          {`키를 옮기면서 ${meta.octaveFolded}개 음이 4현 음역을 벗어나 옥타브를 올려 적었습니다.`}
        </p>
      )}

      <div className="flex items-center gap-2">
        <span className="text-sm text-neutral-600 dark:text-neutral-400">보기</span>
        {(
          [
            { key: "continuous", label: "전체 악보" },
            { key: "paged", label: `${PAGE_BARS}마디 자동 넘김` },
          ] as const
        ).map((v) => (
          <button
            key={v.key}
            onClick={() => setViewMode(v.key)}
            className={`rounded px-2 py-1 text-xs transition ${
              viewMode === v.key
                ? "bg-neutral-900 text-white dark:bg-white dark:text-neutral-900"
                : "bg-neutral-200 text-neutral-700 hover:bg-neutral-300 dark:bg-neutral-800 dark:text-neutral-300"
            }`}
            aria-pressed={viewMode === v.key}
          >
            {v.label}
          </button>
        ))}
      </div>

      {status === "loading" && <p className="text-sm text-neutral-500">악보를 그리는 중…</p>}

      {status === "empty" && (
        <div className="space-y-1">
          <p className="text-sm text-neutral-500">
            이 설정으로는 악보를 만들지 못했습니다. 연습 도구는 그대로 사용할 수 있습니다.
          </p>
          {error && <p className="text-xs text-neutral-400">{error}</p>}
        </div>
      )}

      {status === "error" && (
        <div className="space-y-2">
          <p className="text-sm text-red-600">악보를 표시하지 못했습니다.</p>
          <pre className="overflow-x-auto rounded bg-neutral-100 p-3 text-xs dark:bg-neutral-900">
            {error}
          </pre>
        </div>
      )}

      {/*
        컨테이너를 숨기면 안 된다. alphaTab은 폭이 0이면 렌더링을 건너뛰는데
        (AlphaTab skipped rendering because of width=0), status는 renderFinished에서만
        ready가 되므로 서로를 기다리는 교착이 생긴다.
        항상 자리를 잡아두고 준비 전에는 투명도만 낮춘다.
      */}
      <div
        className={`max-h-[420px] overflow-auto rounded border border-neutral-200 bg-white transition-opacity dark:border-neutral-800 ${
          status === "ready" ? "opacity-100" : "opacity-0"
        }`}
        style={{ minHeight: status === "ready" ? undefined : 1 }}
      >
        <div ref={hostRef} />
      </div>

      {status === "ready" && (
        <p className="text-xs text-neutral-500">
          슬랩·고스트노트 등 주법은 표기되지 않습니다. 음정과 리듬만 담겨 있어요.
        </p>
      )}
    </section>
  );
}
