"use client";

import { useCallback, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { CARD, FIELD_LABEL, chip } from "@/components/ui";

const WORKER = process.env.NEXT_PUBLIC_WORKER_URL ?? "http://localhost:8000";

// 워커의 jobs.STAGES와 같은 키를 쓴다. 모르는 키가 오면 키를 그대로 표시한다.
const STAGE_LABELS: Record<string, string> = {
  ingest: "오디오 준비",
  separate: "악기 분리",
  encode: "전송용 인코딩",
  beats: "박자 분석",
  transcribe: "음 검출",
  bassclean: "베이스 정리",
  chords: "코드 분석",
  score: "악보 생성",
};

interface StageState {
  key: string;
  label: string;
  status: "start" | "done";
  ms?: number;
}

/** 워커에 닿지도 못한 경우인지 판별한다 (파이프라인 실패와 구분) */
function isConnectionError(message: string): boolean {
  return /failed to fetch|networkerror|load failed|econnrefused|이벤트 스트림/i.test(
    message,
  );
}

export default function JobRunner() {
  const router = useRouter();
  const [url, setUrl] = useState("");
  const [tuning, setTuning] = useState("standard");
  const [running, setRunning] = useState(false);
  const [stages, setStages] = useState<StageState[]>([]);
  const [progress, setProgress] = useState(0);
  const [error, setError] = useState("");
  const [note, setNote] = useState("");
  const fileRef = useRef<HTMLInputElement | null>(null);

  const follow = useCallback(
    async (jobId: string) => {
      const res = await fetch(`${WORKER}/api/jobs/${jobId}/events`);
      if (!res.body) throw new Error("이벤트 스트림을 열 수 없습니다");

      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      for (;;) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });

        const lines = buffer.split("\n\n");
        buffer = lines.pop() ?? "";

        for (const chunk of lines) {
          const payload = chunk.replace(/^data: /, "").trim();
          if (!payload) continue;
          if (payload === "[DONE]") return;

          const event = JSON.parse(payload);
          if (typeof event.progress === "number") setProgress(event.progress);

          if (event.stage) {
            setStages((prev) => {
              const next = prev.filter((s) => s.key !== event.stage);
              next.push({
                key: event.stage,
                label: STAGE_LABELS[event.stage] ?? event.stage,
                status: event.status,
                ms: event.ms,
              });
              return next;
            });
          }

          if (event.status === "failed") {
            setError(event.error ?? "처리에 실패했습니다");
            return;
          }
          if (event.status === "done" && event.contentHash) {
            router.push(`/play/${event.contentHash}`);
            return;
          }
        }
      }
    },
    [router],
  );

  const start = useCallback(
    async (body: { kind: "url" } | { kind: "file"; file: File }) => {
      setRunning(true);
      setError("");
      setNote("");
      setStages([]);
      setProgress(0);

      try {
        let res: Response;
        if (body.kind === "url") {
          res = await fetch(`${WORKER}/api/jobs`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ source: url, tuning }),
          });
        } else {
          const form = new FormData();
          form.append("file", body.file);
          res = await fetch(`${WORKER}/api/upload?tuning=${tuning}`, {
            method: "POST",
            body: form,
          });
        }

        if (!res.ok) {
          throw new Error(`워커 응답 ${res.status} — ${await res.text()}`);
        }
        const data = await res.json();

        if (data.cached && data.contentHash) {
          setNote("이미 처리한 곡입니다. 바로 엽니다.");
          router.push(`/play/${data.contentHash}`);
          return;
        }
        await follow(data.jobId);
      } catch (e) {
        setError(
          e instanceof Error ? e.message : String(e),
        );
      } finally {
        setRunning(false);
      }
    },
    [url, tuning, follow, router],
  );

  return (
    <div className="space-y-5">
      <div className="space-y-2">
        <label className={`${FIELD_LABEL} block`}>유튜브 링크</label>
        <div className="flex gap-2">
          <input
            type="url"
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            placeholder="https://www.youtube.com/watch?v=..."
            disabled={running}
            className="flex-1 rounded-lg border border-neutral-200 px-3 py-2 text-sm outline-none transition focus:border-amber-400 dark:border-neutral-700 dark:bg-neutral-900"
          />
          <button
            onClick={() => start({ kind: "url" })}
            disabled={running || !url}
            className="rounded-lg bg-neutral-900 px-4 py-2 text-sm text-white transition hover:opacity-85 disabled:opacity-40 dark:bg-white dark:text-neutral-900"
          >
            분석
          </button>
        </div>
      </div>

      <div className="space-y-2">
        <label className={`${FIELD_LABEL} block`}>또는 오디오 파일</label>
        <input
          ref={fileRef}
          type="file"
          accept=".mp3,.wav,.m4a,.flac,.ogg,.opus,.aac"
          disabled={running}
          onChange={(e) => {
            const file = e.target.files?.[0];
            if (file) start({ kind: "file", file });
          }}
          className="w-full text-sm text-neutral-600 file:mr-3 file:rounded-md file:border-0 file:bg-neutral-200 file:px-3 file:py-1.5 file:text-sm dark:text-neutral-400 dark:file:bg-neutral-800"
        />
      </div>

      <div className="flex items-center gap-1.5">
        <span className={`${FIELD_LABEL} mr-1`}>튜닝</span>
        {[
          { key: "standard", label: "표준 (E A D G)" },
          { key: "dropD", label: "Drop D" },
        ].map((t) => (
          <button
            key={t.key}
            onClick={() => setTuning(t.key)}
            disabled={running}
            className={chip(tuning === t.key)}
          >
            {t.label}
          </button>
        ))}
      </div>

      {running && (
        <div className={`${CARD} space-y-3 p-4`}>
          <div className="h-1.5 overflow-hidden rounded-full bg-neutral-200 dark:bg-neutral-800">
            <div
              className="h-full bg-amber-500 transition-all"
              style={{ width: `${Math.round(progress * 100)}%` }}
            />
          </div>
          <ul className="space-y-1 text-xs">
            {stages.map((s) => (
              <li key={s.key} className="flex items-center gap-2">
                <span className={s.status === "done" ? "text-green-600" : "text-neutral-400"}>
                  {s.status === "done" ? "✓" : "…"}
                </span>
                <span className="text-neutral-700 dark:text-neutral-300">{s.label}</span>
                {s.ms !== undefined && (
                  <span className="font-mono text-neutral-400">
                    {(s.ms / 1000).toFixed(1)}s
                  </span>
                )}
              </li>
            ))}
          </ul>
          <p className="text-xs text-neutral-500">
            CPU로 처리하면 5분 곡에 10분쯤 걸립니다. 창을 닫아도 처리는 계속됩니다.
          </p>
        </div>
      )}

      {note && <p className="text-sm text-neutral-500">{note}</p>}
      {error && (
        <div className="space-y-1">
          <p className="text-sm text-red-600">처리하지 못했습니다.</p>
          <pre className="overflow-x-auto rounded bg-red-50 p-3 text-xs text-red-700 dark:bg-red-950 dark:text-red-300">
            {error}
          </pre>
          {/*
            연결 실패일 때만 워커 안내를 띄운다. 파이프라인이 실패한 경우에도
            "워커가 떠 있는지 확인하세요"를 보여주면 엉뚱한 곳을 보게 된다.
          */}
          {isConnectionError(error) && (
            <p className="text-xs text-neutral-500">
              워커가 떠 있는지 확인하세요: <code>uvicorn main:app --port 8000</code>
            </p>
          )}
        </div>
      )}
    </div>
  );
}
