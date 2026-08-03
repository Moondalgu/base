"use client";

import { useEffect, useState } from "react";
import { StemPlayer, STEM_ORDER, type StemName } from "@/lib/player/engine";

interface Row {
  name: string;
  detail: string;
  pass: boolean;
}

const SR = 44100;

function rms(samples: Float32Array): number {
  let sum = 0;
  for (let i = 0; i < samples.length; i++) sum += samples[i] * samples[i];
  return Math.sqrt(sum / samples.length);
}

/** 스템별 게인과 속도를 주고 오프라인 렌더링해 좌채널을 돌려준다 */
async function render(
  hash: string,
  gains: Partial<Record<StemName, number>>,
  rate: number,
  seconds: number,
): Promise<Float32Array> {
  const ctx = new OfflineAudioContext({
    numberOfChannels: 2,
    length: Math.floor(SR * seconds),
    sampleRate: SR,
  });

  const urls = Object.fromEntries(
    STEM_ORDER.map((n) => [n, `/api/artifacts/${hash}/stems/${n}.wav`]),
  ) as Record<StemName, string>;

  const player = await StemPlayer.create({ urls, context: ctx });
  for (const [stem, value] of Object.entries(gains)) {
    player.setGain(stem as StemName, value as number);
  }
  await player.prepareOffline(rate);
  const buf = await ctx.startRendering();
  return buf.getChannelData(0);
}

export default function SelfTest({ hash }: { hash: string }) {
  const [rows, setRows] = useState<Row[]>([]);
  const [done, setDone] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    let cancelled = false;
    const out: Row[] = [];
    const push = (r: Row) => {
      if (cancelled) return;
      out.push(r);
      setRows([...out]);
    };

    (async () => {
      try {
        const full = await render(hash, {}, 1, 6);
        const rFull = rms(full);
        push({
          name: "4스템 전체 재생",
          detail: `RMS ${rFull.toFixed(4)}`,
          pass: rFull > 0.001,
        });

        const bassOnly = await render(hash, { drums: 0, bass: 1, vocals: 0, other: 0 }, 1, 6);
        const rBass = rms(bassOnly);
        push({
          name: "베이스만 (솔로)",
          detail: `RMS ${rBass.toFixed(4)} — 전체의 ${(rBass / rFull * 100).toFixed(0)}%`,
          pass: rBass > 0.001 && rBass < rFull,
        });

        const noBass = await render(hash, { drums: 1, bass: 0, vocals: 1, other: 1 }, 1, 6);
        const rNoBass = rms(noBass);
        push({
          name: "베이스 빼고 (minus-one)",
          detail: `RMS ${rNoBass.toFixed(4)} — 베이스만 대비 확실히 다름`,
          pass: rNoBass > 0.001 && Math.abs(rNoBass - rBass) > rBass * 0.1,
        });

        const boosted = await render(hash, { drums: 0, bass: 2, vocals: 0, other: 0 }, 1, 6);
        const ratio = rms(boosted) / rBass;
        push({
          name: "베이스 2배 부스트",
          detail: `RMS 비율 ${ratio.toFixed(2)} (기대 2.00)`,
          pass: ratio > 1.85 && ratio < 2.15,
        });

        const muteAll = await render(hash, { drums: 0, bass: 0, vocals: 0, other: 0 }, 1, 6);
        push({
          name: "전체 뮤트 시 무음",
          detail: `RMS ${rms(muteAll).toExponential(2)}`,
          pass: rms(muteAll) < rFull * 0.01,
        });

        // 반배속: 원본 6초 구간이 12초로 늘어나므로 후반부에도 소리가 있어야 한다
        const slow = await render(hash, {}, 0.5, 12);
        const tail = slow.slice(Math.floor(slow.length * 0.6));
        push({
          name: "반배속 — 길이 확장",
          detail: `후반부 RMS ${rms(tail).toFixed(4)}`,
          pass: rms(tail) > 0.001,
        });

        if (!cancelled) setDone(true);
      } catch (e) {
        if (!cancelled) setError(e instanceof Error ? (e.stack ?? e.message) : String(e));
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [hash]);

  const allPass = done && rows.every((r) => r.pass);

  return (
    <div className="space-y-4">
      <table className="w-full text-sm">
        <tbody>
          {rows.map((r) => (
            <tr key={r.name} className="border-b border-neutral-200 dark:border-neutral-800">
              <td className="py-2 pr-4">{r.name}</td>
              <td className="py-2 pr-4 font-mono text-xs text-neutral-500">{r.detail}</td>
              <td className={`py-2 font-medium ${r.pass ? "text-green-600" : "text-red-600"}`}>
                {r.pass ? "통과" : "실패"}
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      {!done && !error && <p className="text-sm text-neutral-500">검증 중…</p>}
      {error && (
        <pre className="overflow-x-auto rounded bg-red-50 p-3 text-xs text-red-700 dark:bg-red-950 dark:text-red-300">
          {error}
        </pre>
      )}
      {done && (
        <p
          id="selftest-result"
          className={`text-sm font-semibold ${allPass ? "text-green-600" : "text-red-600"}`}
        >
          {allPass ? "RESULT: PASS" : "RESULT: FAIL"}
        </p>
      )}
    </div>
  );
}
