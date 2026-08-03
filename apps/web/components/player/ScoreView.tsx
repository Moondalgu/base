"use client";

import { useEffect, useRef, useState } from "react";
import {
  ALPHATAB_BASE,
  bridgeExternalMedia,
  loadAlphaTab,
  type BridgeCallbacks,
  type ExternalMediaBridge,
} from "@/lib/player/alphatab";

interface Props {
  hash: string;
  /** 재생 위치(초). 이 값이 바뀔 때마다 커서를 옮긴다 */
  position: number;
  callbacks: BridgeCallbacks;
  /** 품질 점수 — 낮으면 경고 배너를 띄운다 */
  qualityLevel?: "good" | "reference" | "failed";
}

type Status = "loading" | "ready" | "empty" | "error";

export default function ScoreView({ hash, position, callbacks, qualityLevel }: Props) {
  const hostRef = useRef<HTMLDivElement | null>(null);
  const bridgeRef = useRef<ExternalMediaBridge | null>(null);
  const callbacksRef = useRef(callbacks);
  const [status, setStatus] = useState<Status>("loading");
  const [error, setError] = useState("");

  // 렌더 중에 ref를 쓰면 안 된다(react-hooks/refs). effect에서 동기화한다.
  // 부모가 매 렌더마다 새 콜백 객체를 만들어도 alphaTab 배선을 다시 하지 않게
  // 하려고 ref에 담아둔다.
  useEffect(() => {
    callbacksRef.current = callbacks;
  }, [callbacks]);

  useEffect(() => {
    let disposed = false;
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    let api: any = null;

    (async () => {
      try {
        const res = await fetch(`/api/artifacts/${hash}/score.alphatex`);
        if (!res.ok) {
          if (!disposed) setStatus("empty");
          return;
        }
        const tex = await res.text();
        const alphaTab = await loadAlphaTab();
        if (disposed || !hostRef.current) return;

        api = new alphaTab.AlphaTabApi(hostRef.current, {
          core: {
            tex: true,
            fontDirectory: `${ALPHATAB_BASE}/font/`,
          },
          display: {
            // 탭 악보만. 오선보는 베이스 연습에 굳이 필요하지 않다.
            staveProfile: alphaTab.StaveProfile.Tab,
            scale: 0.9,
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

        api.error.on((e: unknown) => {
          if (!disposed) {
            setError(String(e));
            setStatus("error");
          }
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
          }
          setStatus("ready");
        });

        api.tex(tex);
      } catch (e) {
        if (!disposed) {
          setError(e instanceof Error ? (e.stack ?? e.message) : String(e));
          setStatus("error");
        }
      }
    })();

    return () => {
      disposed = true;
      bridgeRef.current?.destroy();
      bridgeRef.current = null;
      api?.destroy?.();
    };
  }, [hash]);

  // 재생 위치를 alphaTab에 밀어넣는다. 부모가 50ms 주기로 갱신한다.
  useEffect(() => {
    bridgeRef.current?.updatePosition(position);
  }, [position]);

  return (
    <section className="space-y-3">
      {qualityLevel === "reference" && (
        <p className="rounded border border-amber-300 bg-amber-50 px-3 py-2 text-xs text-amber-800 dark:border-amber-800 dark:bg-amber-950 dark:text-amber-200">
          자동 생성된 악보입니다. 부정확할 수 있어요.
        </p>
      )}

      {status === "loading" && <p className="text-sm text-neutral-500">악보를 그리는 중…</p>}

      {status === "empty" && (
        <p className="text-sm text-neutral-500">
          이 곡은 악보를 만들지 못했습니다. 연습 도구는 그대로 사용할 수 있습니다.
        </p>
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
