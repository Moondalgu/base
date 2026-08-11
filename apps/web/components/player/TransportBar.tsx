"use client";

import { chip, toggleChip, DIVIDER, NUM, SLIDER, SLIDER_ACCENT, STEPPER } from "../ui";
import { TRANSPOSE_LIMIT, TRANSPOSE_WARN } from "./ScoreControls";

interface Props {
  playing: boolean;
  position: number;
  duration: number;
  rate: number;
  semitones: number;
  /** 지금 악보에 찍힌 조표 이름(이조 반영). 조성을 못 찾았으면 빈 문자열 */
  keyName?: string;
  /** A-B 구간. 아직 안 찍었으면 null */
  loopStart: number | null;
  loopEnd: number | null;
  metronome: boolean;
  /** 비트 격자가 없으면 메트로놈을 켤 수 없다 */
  metronomeAvailable: boolean;
  /** 악보 연주 모드 — 원곡 베이스 대신 화면 악보를 샘플러로 연주 */
  synthOn: boolean;
  onToggle: () => void;
  onSeek: (seconds: number) => void;
  onRate: (rate: number) => void;
  onSemitones: (semitones: number) => void;
  onLoopA: () => void;
  onLoopB: () => void;
  onMetronome: () => void;
  onSynthToggle: () => void;
}

const RATE_PRESETS = [0.5, 0.75, 0.9, 1];

function fmt(seconds: number): string {
  if (!Number.isFinite(seconds)) return "0:00";
  const m = Math.floor(seconds / 60);
  const s = Math.floor(seconds % 60);
  return `${m}:${String(s).padStart(2, "0")}`;
}

/**
 * 연주 중에 손이 가는 것만 모은 고정 바.
 *
 * 화면 아래에 붙여둔 이유는 악보다. 악보를 보면서 배속·구간을 만지는 것이
 * 이 도구의 사용 방식인데, 컨트롤이 문서 흐름에 있으면 악보를 스크롤할 때마다
 * 화면 밖으로 나간다.
 *
 * 설명 문단은 각 묶음의 title로 접어 넣었다 — 바가 두 줄을 넘어가면 악보가
 * 그만큼 가려진다.
 */
export default function TransportBar({
  playing,
  position,
  duration,
  rate,
  semitones,
  keyName,
  loopStart,
  loopEnd,
  metronome,
  metronomeAvailable,
  synthOn,
  onToggle,
  onSeek,
  onRate,
  onSemitones,
  onLoopA,
  onLoopB,
  onMetronome,
  onSynthToggle,
}: Props) {
  const looping = loopStart !== null && loopEnd !== null;

  return (
    <section className="fixed inset-x-0 bottom-0 z-40 border-t border-neutral-200 bg-white/85 backdrop-blur-md dark:border-neutral-800 dark:bg-neutral-950/85">
      <div className="mx-auto w-full max-w-5xl px-4 pt-2 pb-[max(0.5rem,env(safe-area-inset-bottom))] sm:px-6">
        <div className="flex items-center gap-3">
          <span className={`${NUM} w-10 shrink-0`}>{fmt(position)}</span>
          <input
            type="range"
            min={0}
            max={duration || 1}
            step={0.01}
            value={Math.min(position, duration)}
            onChange={(e) => onSeek(Number(e.target.value))}
            className={`${SLIDER_ACCENT} flex-1`}
            aria-label="재생 위치"
          />
          <span className={`${NUM} w-10 shrink-0 text-right`}>{fmt(duration)}</span>
        </div>

        <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-2">
          <button
            onClick={onToggle}
            className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-amber-500 text-sm text-neutral-950 transition hover:bg-amber-400"
            aria-label={playing ? "일시정지" : "재생"}
          >
            <span className={playing ? "" : "translate-x-[1px]"}>{playing ? "❚❚" : "▶"}</span>
          </button>

          {/* 무엇이 들리는가 — 재생 버튼 바로 옆 1급 자리. 원곡/악보 전환이
              이 도구의 존재 이유(귀로 검증)라서 접이식 패널에 숨기지 않는다
              (Songscription 실물 대조에서 가져온 배치 문법). */}
          <div
            className="inline-flex shrink-0 gap-0.5 rounded-full border border-neutral-200 p-0.5 dark:border-neutral-700"
            title="악보 연주: 원곡 베이스를 빼고 화면 악보(현재 난이도·키)를 대신 연주합니다."
            role="group"
            aria-label="소리 모드"
          >
            {(
              [
                { on: false, label: "원곡" },
                { on: true, label: "악보 연주" },
              ] as const
            ).map((m) => (
              <button
                key={m.label}
                onClick={() => {
                  if (synthOn !== m.on) onSynthToggle();
                }}
                className={`rounded-full px-2.5 py-1 text-xs transition ${
                  synthOn === m.on
                    ? "bg-neutral-900 font-medium text-white dark:bg-white dark:text-neutral-900"
                    : "text-neutral-600 hover:bg-neutral-100 dark:text-neutral-300 dark:hover:bg-neutral-800"
                }`}
                aria-pressed={synthOn === m.on}
              >
                {m.label}
              </button>
            ))}
          </div>

          <div
            className="flex items-center gap-1.5"
            title="속도를 바꿔도 음정은 유지됩니다."
          >
            <span className="text-xs text-neutral-500 dark:text-neutral-400">속도</span>
            {RATE_PRESETS.map((r) => (
              <button key={r} onClick={() => onRate(r)} className={chip(Math.abs(rate - r) < 0.001)}>
                {Math.round(r * 100)}%
              </button>
            ))}
            <input
              type="range"
              min={0.25}
              max={2}
              step={0.01}
              value={rate}
              onChange={(e) => onRate(Number(e.target.value))}
              className={`${SLIDER} hidden w-24 lg:block`}
              aria-label="재생 속도"
            />
            <span className={`${NUM} w-9 text-right`}>{Math.round(rate * 100)}%</span>
          </div>

          <span className={DIVIDER} aria-hidden />

          {/* 키 — 재생 피치와 악보가 **함께** 움직인다. 컨트롤이 하나뿐이라
              둘이 어긋날 수 없다. 연주 중에 손이 가는 값이라 접이식 패널이
              아니라 여기(하단 고정 바)에 둔다. */}
          <div
            className="flex items-center gap-1.5"
            title={
              "반음 단위로 곡 전체를 옮깁니다. 소리와 악보가 같이 움직입니다." +
              (Math.abs(semitones) >= TRANSPOSE_WARN
                ? " 반음만 내릴 것이라면 악보 설정에서 튜닝을 내리는 쪽이 낫습니다 — 운지가 그대로 유지됩니다."
                : "")
            }
          >
            <span className="text-xs text-neutral-500 dark:text-neutral-400">키</span>
            <button
              onClick={() => onSemitones(semitones - 1)}
              disabled={semitones <= -TRANSPOSE_LIMIT}
              className={`${STEPPER} disabled:cursor-not-allowed disabled:opacity-40`}
              aria-label="키 내리기"
            >
              −
            </button>
            {/* 조표 이름이 있으면 그것을 보여준다. 반음 수(+2)는 지금 무슨
                키인지 알려주지 않는다. 조성을 못 찾은 곡에서는 반음 수로 되돌린다. */}
            <span
              className={`${NUM} min-w-[3.25rem] text-center`}
              aria-label={keyName ? `현재 키 ${keyName}` : undefined}
            >
              {keyName || (semitones > 0 ? `+${semitones}` : String(semitones))}
              {keyName && semitones !== 0 && (
                <span className="ml-1 text-[11px] text-neutral-500 dark:text-neutral-400">
                  {semitones > 0 ? `+${semitones}` : semitones}
                </span>
              )}
            </span>
            <button
              onClick={() => onSemitones(semitones + 1)}
              disabled={semitones >= TRANSPOSE_LIMIT}
              className={`${STEPPER} disabled:cursor-not-allowed disabled:opacity-40`}
              aria-label="키 올리기"
            >
              +
            </button>
            {semitones !== 0 && (
              <button
                onClick={() => onSemitones(0)}
                className="text-[11px] text-neutral-500 underline-offset-2 hover:underline dark:text-neutral-400"
              >
                원래 키
              </button>
            )}
          </div>

          <span className={DIVIDER} aria-hidden />

          <div
            className="flex items-center gap-1.5"
            title="구간 반복과 메트로놈은 배속을 바꿔도 그대로 따라옵니다."
          >
            <span className="text-xs text-neutral-500 dark:text-neutral-400">구간</span>
            <button
              onClick={onLoopA}
              className={toggleChip(loopStart !== null)}
              aria-pressed={loopStart !== null}
              title="현재 위치를 시작점으로. 다시 누르면 해제 — 마디 경계로 맞춰집니다"
            >
              {loopStart === null ? "A" : `A ${fmt(loopStart)}`}
            </button>
            <button
              onClick={onLoopB}
              className={toggleChip(loopEnd !== null)}
              aria-pressed={loopEnd !== null}
              title="현재 위치를 끝점으로. 다시 누르면 해제 — 마디 경계로 맞춰집니다"
            >
              {loopEnd === null ? "B" : `B ${fmt(loopEnd)}`}
            </button>
            {looping && (
              <span className="text-[11px] font-medium text-amber-600 dark:text-amber-400">
                반복 중
              </span>
            )}
          </div>

          <button
            onClick={onMetronome}
            disabled={!metronomeAvailable}
            className={`${toggleChip(metronome)} disabled:cursor-not-allowed disabled:opacity-40`}
            aria-pressed={metronome}
            title={
              metronomeAvailable
                ? "비트 격자에 맞춰 클릭을 냅니다"
                : "이 곡에는 비트 격자가 없습니다"
            }
          >
            메트로놈
          </button>
        </div>
      </div>
    </section>
  );
}
