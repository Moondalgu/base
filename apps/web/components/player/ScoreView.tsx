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
import { BADGE, BADGE_ACCENT, HINT } from "../ui";

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
  /** 마디 시작 시각(초, beats.json 다운비트). 시크 동기화가 마디를 계산한다 */
  barStarts?: number[];
  /** 사용자 보정이 저장될 때마다 부모가 올리는 판. 바뀌면 악보를 다시 받는다 */
  editsVersion?: number;
  /** 보정 저장 성공 콜백 — 부모가 editsVersion을 올려 전체(악보·연주)를 갱신한다 */
  onEditsChanged?: () => void;
}

/** 원장 행 — 편집 UI가 쓰는 열만 */
interface LedgerRow {
  bar: number;
  slot: number;
  pitch_detected: number;
  pitch_name: string;
  string: string;
  fret: number | string;
  src_start_sec: number | string;
  source: string;
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
  barStarts,
  editsVersion = 0,
  onEditsChanged,
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

  // --- 채보 보정(편집) ---
  // 클릭한 음을 원장(ledger)으로 특정해 검출 시각(srcStart) 기반 보정을 건다.
  // 보정은 원본 검출을 고치는 것이라(pipeline/edits.py) 모든 난이도에 전파된다.
  const [editMode, setEditMode] = useState(false);
  const editModeRef = useRef(false);
  const [selected, setSelected] = useState<LedgerRow | null>(null);
  const [editBusy, setEditBusy] = useState(false);
  const ledgerRef = useRef<{
    rows: LedgerRow[];
    slotsPerBar: number;
  } | null>(null);
  const onEditsChangedRef = useRef(onEditsChanged);
  useEffect(() => {
    onEditsChangedRef.current = onEditsChanged;
  }, [onEditsChanged]);
  useEffect(() => {
    editModeRef.current = editMode;
    if (!editMode) setSelected(null);
  }, [editMode]);

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
            // 음표 수평 간격(Gourlay 스프링) 강도. 기본 1은 16분·가사가 낀
            // 마디에서 음표가 맞닿는다(SVG 실측 p10=0px). 페이지 폭 확장과
            // 함께 참조 악보 수준의 여백을 만든다.
            stretchForce: 1.25,
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

        // 편집 모드 — 클릭한 비트를 (마디, 슬롯)으로 환산해 원장에서 음을 찾는다.
        // playbackStart의 기준(절대/마디 상대)이 버전에 따라 달라 둘 다 다룬다.
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        api.beatMouseDown.on((beat: any) => {
          if (disposed || !editModeRef.current) return;
          const bar = beat?.voice?.bar;
          const barIndex = bar?.index;
          if (typeof barIndex !== "number") return;
          if (bar?.staff?.track?.name && bar.staff.track.name !== "Bass") {
            setSelected(null); // 보컬 트랙은 편집 대상이 아니다
            return;
          }
          const info = ledgerRef.current;
          if (!info) return;
          const master = bar?.masterBar;
          const barStartTicks = typeof master?.start === "number" ? master.start : 0;
          let inBar = typeof beat?.playbackStart === "number" ? beat.playbackStart : 0;
          if (barStartTicks > 0 && inBar >= barStartTicks) inBar -= barStartTicks;
          const durTicks = master?.calculateDuration?.() ?? 3840;
          const slot = Math.round((inBar / Math.max(1, durTicks)) * info.slotsPerBar);
          const rows = info.rows.filter((r) => r.bar === barIndex + 1);
          if (rows.length === 0) {
            setSelected(null);
            return;
          }
          setSelected(
            rows.reduce((a, b) =>
              Math.abs(a.slot - slot) <= Math.abs(b.slot - slot) ? a : b,
            ),
          );
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
        if (process.env.NODE_ENV !== "production") {
          // 브라우저 콘솔·자동화에서 boundsLookup 등을 들여다보기 위한 개발용 훅
          (window as unknown as { __alphaTab?: unknown }).__alphaTab = api;
        }
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
  }, [hash, level, transpose, tuning, applyTex, editsVersion]);

  // 편집 모드가 켜져 있는 동안 원장을 들고 있는다 — 클릭한 비트를
  // (마디, 슬롯)으로 환산해 검출 시각을 찾는 유일한 지도다.
  useEffect(() => {
    if (!editMode) return;
    let cancelled = false;
    (async () => {
      try {
        const params = new URLSearchParams({
          level: String(level),
          transpose: String(transpose),
        });
        if (tuning) params.set("tuning", tuning);
        const res = await fetch(`/api/scores/${hash}/ledger/json?${params}`);
        if (!res.ok || cancelled) return;
        const data = await res.json();
        if (cancelled) return;
        ledgerRef.current = {
          rows: (data.rows ?? []) as LedgerRow[],
          slotsPerBar: (data.subdivision ?? 4) * (data.beatsPerBar ?? 4),
        };
      } catch {
        ledgerRef.current = null;
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [editMode, hash, level, transpose, tuning, editsVersion]);

  /**
   * 선택한 음에 보정을 저장한다. 목록 전체를 받아 그 음의 기존 보정을 걷어내고
   * 새 보정을 얹어 PUT — 멱등이라 재시도·중복 클릭에 안전하다.
   */
  const applyEdit = useCallback(
    async (action: "pitch" | "delete" | "revert", delta = 0) => {
      const row = selected;
      if (!row || editBusy) return;
      const src = Number(row.src_start_sec);
      if (!Number.isFinite(src)) return;
      setEditBusy(true);
      try {
        const cur = await fetch(`/api/scores/${hash}/edits`).then((r) => r.json());
        type EditItem = { srcStart: number; action: string; pitch?: number };
        let list: EditItem[] = Array.isArray(cur?.edits) ? cur.edits : [];
        list = list.filter((e) => Math.abs(e.srcStart - src) > 0.03);
        if (action === "pitch") {
          list.push({
            srcStart: src,
            action: "pitch",
            pitch: Number(row.pitch_detected) + delta,
          });
        } else if (action === "delete") {
          list.push({ srcStart: src, action: "delete" });
        }
        const res = await fetch(`/api/scores/${hash}/edits`, {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ edits: list }),
        });
        if (res.ok) {
          setSelected(null);
          onEditsChangedRef.current?.();
        }
      } finally {
        setEditBusy(false);
      }
    },
    [selected, editBusy, hash],
  );

  // 재생 위치를 alphaTab에 밀어넣는다. 부모가 50ms 주기로 갱신한다.
  //
  // **시크 동기화** — 위치가 연속 재생으로 설명되지 않게 점프하면(시크 바
  // 드래그·A/B 이동) 창과 스크롤을 그 마디로 직접 데려간다. 재생 중 창
  // 이동은 playedBeatChanged가 담당하지만 그 이벤트는 **재생 중에만**
  // 발화한다 — 일시정지 상태의 시크, 그리고 재생 중이라도 다음 비트 전까지의
  // 공백은 이 경로가 메운다. 마디 시각은 barStarts(beats.json 다운비트)로
  // 계산한다 — 악보 마디와 같은 격자에서 왔으므로 어긋나지 않는다.
  const lastPositionRef = useRef(0);
  useEffect(() => {
    bridgeRef.current?.updatePosition(position);
    const jumped = Math.abs(position - lastPositionRef.current) > 1.5;
    lastPositionRef.current = position;
    if (!jumped || !barStarts?.length) return;
    let idx = barStarts.findIndex((t) => t > position) - 1;
    if (idx < -1) idx = barStarts.length - 1;   // 마지막 마디 이후
    if (idx < 0) idx = 0;
    const start = Math.floor(idx / PAGE_BARS) * PAGE_BARS + 1;
    windowStartRef.current = start;
    if (viewModeRef.current === "paged") {
      applyWindow("paged", start);
    } else {
      // 전체 악보 — 커서가 그려진 뒤 그 마디로 스크롤한다. 커서 요소는
      // 렌더 직후에나 자리를 잡으므로 한 프레임 늦춘다.
      window.setTimeout(() => {
        const cursor = hostRef.current?.querySelector(".at-cursor-bar");
        (cursor as HTMLElement | null)?.scrollIntoView({
          block: "center", behavior: "smooth",
        });
      }, 250);
    }
  }, [position, barStarts, applyWindow]);

  // 뷰를 바꾸면 표시 범위를 다시 건다. status가 바뀔 때도 한 번 걸어
  // 인스턴스가 늦게 준비된 경우를 메운다(applyWindow가 같은 범위면 건너뛴다).
  useEffect(() => {
    viewModeRef.current = viewMode;
    applyWindow(viewMode, windowStartRef.current);
  }, [viewMode, status, applyWindow]);

  const isReduced = level < ORIGINAL_LEVEL;

  return (
    <section className="space-y-2">
      {/*
        악보에 붙는 단서는 전부 이 한 줄에 모은다. 예전처럼 배너를 세로로 쌓으면
        악보가 그만큼 아래로 밀리는데, 정작 읽어야 하는 것은 악보다. 긴 설명은
        꼬리표의 title로 접어 넣었다.
      */}
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex flex-wrap items-center gap-1.5">
          {qualityLevel === "reference" && (
            <span className={BADGE_ACCENT} title="자동 생성된 악보입니다. 부정확할 수 있어요.">
              참고용
            </span>
          )}
          {isReduced && (
            <span
              className={BADGE_ACCENT}
              title="쉬운 버전입니다. 원곡을 단순하게 고쳐 적었으므로 원곡과 다릅니다."
            >
              쉬운 버전
            </span>
          )}
          {meta && meta.octaveFolded > 0 && (
            <span
              className={BADGE}
              title={`키를 옮기면서 ${meta.octaveFolded}개 음이 4현 음역을 벗어나 옥타브를 올려 적었습니다.`}
            >
              {`옥타브 올림 ${meta.octaveFolded}`}
            </span>
          )}
          {status === "ready" && (
            <span
              className={`${BADGE} ${HINT}`}
              title="슬랩·고스트노트 등 주법은 표기되지 않습니다. 음정과 리듬만 담겨 있어요."
            >
              주법 미표기
            </span>
          )}
        </div>

        <div className="flex items-center gap-2">
          <button
            onClick={() => setEditMode((v) => !v)}
            className={`rounded-lg border px-2.5 py-1 text-xs transition ${
              editMode
                ? "border-amber-500 bg-amber-500 font-semibold text-white"
                : "border-neutral-200 text-neutral-600 hover:bg-neutral-100 dark:border-neutral-800 dark:text-neutral-300 dark:hover:bg-neutral-800"
            }`}
            aria-pressed={editMode}
            title="자동 채보가 틀린 음을 클릭해서 고칩니다. 고친 내용은 모든 난이도에 반영됩니다."
          >
            {editMode ? "보정 중" : "보정"}
          </button>
          <span className="hidden text-xs text-neutral-500 sm:inline dark:text-neutral-400">보기</span>
          <div className="inline-flex gap-1 rounded-lg border border-neutral-200 p-0.5 dark:border-neutral-800">
            {(
              [
                { key: "continuous", label: "전체 악보" },
                { key: "paged", label: `${PAGE_BARS}마디 자동 넘김` },
              ] as const
            ).map((v) => (
              <button
                key={v.key}
                onClick={() => setViewMode(v.key)}
                className={`rounded-md px-2.5 py-1 text-xs transition ${
                  viewMode === v.key
                    ? "bg-neutral-900 text-white dark:bg-white dark:text-neutral-900"
                    : "text-neutral-600 hover:bg-neutral-100 dark:text-neutral-300 dark:hover:bg-neutral-800"
                }`}
                aria-pressed={viewMode === v.key}
              >
                {v.label}
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* 보정 패널 — 악보 위 고정 바. 팝오버 좌표 계산 없이 항상 같은 자리라
          클릭→확인→저장의 시선 이동이 짧다. */}
      {editMode && (
        <div className="flex flex-wrap items-center gap-2 rounded-lg border border-amber-300 bg-amber-50 px-3 py-2 text-xs dark:border-amber-700 dark:bg-amber-950">
          {!selected && (
            <span className="text-neutral-600 dark:text-neutral-300">
              악보에서 고칠 음표를 클릭하세요. 고친 내용은 모든 난이도에 반영됩니다.
            </span>
          )}
          {selected && selected.source !== "검출" && (
            <span className="text-neutral-600 dark:text-neutral-300">
              {`${selected.bar}마디의 이 음은 쉬운 버전이 자동으로 만든 음입니다 — 원본 난이도에서 원래 검출 음을 고쳐주세요.`}
            </span>
          )}
          {selected && selected.source === "검출" && (
            <>
              <span className="font-medium">
                {`${selected.bar}마디 · ${selected.pitch_name || "음"} (${selected.string}현 ${selected.fret}프렛)`}
              </span>
              <button onClick={() => void applyEdit("pitch", -1)} disabled={editBusy}
                className="rounded-md border border-neutral-300 bg-white px-2 py-0.5 hover:bg-neutral-100 disabled:opacity-40 dark:border-neutral-600 dark:bg-neutral-900 dark:hover:bg-neutral-800">
                반음 ↓
              </button>
              <button onClick={() => void applyEdit("pitch", +1)} disabled={editBusy}
                className="rounded-md border border-neutral-300 bg-white px-2 py-0.5 hover:bg-neutral-100 disabled:opacity-40 dark:border-neutral-600 dark:bg-neutral-900 dark:hover:bg-neutral-800">
                반음 ↑
              </button>
              <button onClick={() => void applyEdit("pitch", -12)} disabled={editBusy}
                className="rounded-md border border-neutral-300 bg-white px-2 py-0.5 hover:bg-neutral-100 disabled:opacity-40 dark:border-neutral-600 dark:bg-neutral-900 dark:hover:bg-neutral-800">
                옥타브 ↓
              </button>
              <button onClick={() => void applyEdit("pitch", +12)} disabled={editBusy}
                className="rounded-md border border-neutral-300 bg-white px-2 py-0.5 hover:bg-neutral-100 disabled:opacity-40 dark:border-neutral-600 dark:bg-neutral-900 dark:hover:bg-neutral-800">
                옥타브 ↑
              </button>
              <button onClick={() => void applyEdit("delete")} disabled={editBusy}
                className="rounded-md border border-red-300 bg-white px-2 py-0.5 text-red-600 hover:bg-red-50 disabled:opacity-40 dark:border-red-700 dark:bg-neutral-900 dark:hover:bg-red-950">
                삭제
              </button>
              <button onClick={() => void applyEdit("revert")} disabled={editBusy}
                className="rounded-md border border-neutral-300 bg-white px-2 py-0.5 hover:bg-neutral-100 disabled:opacity-40 dark:border-neutral-600 dark:bg-neutral-900 dark:hover:bg-neutral-800"
                title="이 음에 저장된 보정을 지우고 자동 채보 값으로 되돌립니다">
                보정 취소
              </button>
              {editBusy && <span className="text-neutral-400">저장 중…</span>}
            </>
          )}
        </div>
      )}

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
          <pre className="overflow-x-auto rounded-lg bg-neutral-100 p-3 text-xs dark:bg-neutral-900">
            {error}
          </pre>
        </div>
      )}

      {/*
        컨테이너를 숨기면 안 된다. alphaTab은 폭이 0이면 렌더링을 건너뛰는데
        (AlphaTab skipped rendering because of width=0), status는 renderFinished에서만
        ready가 되므로 서로를 기다리는 교착이 생긴다.
        항상 자리를 잡아두고 준비 전에는 투명도만 낮춘다.

        높이를 뷰포트 기준으로 둔 이유는 악보가 화면의 주인공이기 때문이다.
        고정 560px은 큰 화면에서 아래를 비워두고 작은 화면에서는 넘친다.
        배경이 항상 흰색인 것은 alphaTab이 검은 잉크로 그리기 때문이다 —
        다크 모드에서도 종이는 종이다.
      */}
      <div
        className={`max-h-[70vh] overflow-auto rounded-xl border border-neutral-200 bg-white shadow-sm transition-opacity dark:border-neutral-800 ${
          status === "ready" ? "opacity-100" : "opacity-0"
        }`}
        style={{ minHeight: status === "ready" ? undefined : 1 }}
      >
        <div ref={hostRef} />
      </div>
    </section>
  );
}
