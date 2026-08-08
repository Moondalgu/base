"use client";

interface Props {
  playing: boolean;
  position: number;
  duration: number;
  rate: number;
  semitones: number;
  /** A-B 구간. 아직 안 찍었으면 null */
  loopStart: number | null;
  loopEnd: number | null;
  metronome: boolean;
  /** 비트 격자가 없으면 메트로놈을 켤 수 없다 */
  metronomeAvailable: boolean;
  onToggle: () => void;
  onSeek: (seconds: number) => void;
  onRate: (rate: number) => void;
  onSemitones: (semitones: number) => void;
  onLoopA: () => void;
  onLoopB: () => void;
  onMetronome: () => void;
}

const RATE_PRESETS = [0.5, 0.75, 0.9, 1];

function fmt(seconds: number): string {
  if (!Number.isFinite(seconds)) return "0:00";
  const m = Math.floor(seconds / 60);
  const s = Math.floor(seconds % 60);
  return `${m}:${String(s).padStart(2, "0")}`;
}

export default function TransportBar({
  playing,
  position,
  duration,
  rate,
  semitones,
  loopStart,
  loopEnd,
  metronome,
  metronomeAvailable,
  onToggle,
  onSeek,
  onRate,
  onSemitones,
  onLoopA,
  onLoopB,
  onMetronome,
}: Props) {
  const looping = loopStart !== null && loopEnd !== null;
  const toggleClass = (on: boolean) =>
    `rounded px-2 py-1 text-xs transition ${
      on
        ? "bg-neutral-900 text-white dark:bg-white dark:text-neutral-900"
        : "bg-neutral-200 text-neutral-700 hover:bg-neutral-300 dark:bg-neutral-800 dark:text-neutral-300"
    }`;

  return (
    <section className="space-y-4">
      <div className="flex items-center gap-3">
        <button
          onClick={onToggle}
          className="h-11 w-11 shrink-0 rounded-full bg-neutral-900 text-white transition hover:opacity-80 dark:bg-white dark:text-neutral-900"
          aria-label={playing ? "일시정지" : "재생"}
        >
          {playing ? "❚❚" : "▶"}
        </button>
        <span className="w-12 shrink-0 font-mono text-xs tabular-nums text-neutral-500">
          {fmt(position)}
        </span>
        <input
          type="range"
          min={0}
          max={duration || 1}
          step={0.01}
          value={Math.min(position, duration)}
          onChange={(e) => onSeek(Number(e.target.value))}
          className="h-1.5 flex-1 cursor-pointer accent-neutral-900 dark:accent-white"
          aria-label="재생 위치"
        />
        <span className="w-12 shrink-0 font-mono text-xs tabular-nums text-neutral-500">
          {fmt(duration)}
        </span>
      </div>

      <div className="flex flex-wrap items-center gap-x-4 gap-y-3">
        <div className="flex items-center gap-2">
          <span className="text-sm text-neutral-600 dark:text-neutral-400">속도</span>
          {RATE_PRESETS.map((r) => (
            <button
              key={r}
              onClick={() => onRate(r)}
              className={`rounded px-2 py-1 text-xs transition ${
                Math.abs(rate - r) < 0.001
                  ? "bg-neutral-900 text-white dark:bg-white dark:text-neutral-900"
                  : "bg-neutral-200 text-neutral-700 hover:bg-neutral-300 dark:bg-neutral-800 dark:text-neutral-300"
              }`}
            >
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
            className="h-1.5 w-32 cursor-pointer accent-neutral-900 dark:accent-white"
            aria-label="재생 속도"
          />
          <span className="w-12 font-mono text-xs tabular-nums text-neutral-500">
            {Math.round(rate * 100)}%
          </span>
        </div>

        <div className="flex items-center gap-2">
          <span className="text-sm text-neutral-600 dark:text-neutral-400">피치</span>
          <button
            onClick={() => onSemitones(semitones - 1)}
            className="h-7 w-7 rounded bg-neutral-200 text-sm hover:bg-neutral-300 dark:bg-neutral-800"
          >
            −
          </button>
          <span className="w-10 text-center font-mono text-xs tabular-nums text-neutral-500">
            {semitones > 0 ? `+${semitones}` : semitones}
          </span>
          <button
            onClick={() => onSemitones(semitones + 1)}
            className="h-7 w-7 rounded bg-neutral-200 text-sm hover:bg-neutral-300 dark:bg-neutral-800"
          >
            +
          </button>
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-x-4 gap-y-3">
        <div className="flex items-center gap-2">
          <span className="text-sm text-neutral-600 dark:text-neutral-400">구간 반복</span>
          <button
            onClick={onLoopA}
            className={toggleClass(loopStart !== null)}
            aria-pressed={loopStart !== null}
            title="현재 위치를 시작점으로. 다시 누르면 해제"
          >
            {loopStart === null ? "A" : `A ${fmt(loopStart)}`}
          </button>
          <button
            onClick={onLoopB}
            className={toggleClass(loopEnd !== null)}
            aria-pressed={loopEnd !== null}
            title="현재 위치를 끝점으로. 다시 누르면 해제"
          >
            {loopEnd === null ? "B" : `B ${fmt(loopEnd)}`}
          </button>
          <span className="text-xs text-neutral-500">
            {looping ? "반복 중" : "마디 경계로 맞춰집니다"}
          </span>
        </div>

        <div className="flex items-center gap-2">
          <button
            onClick={onMetronome}
            disabled={!metronomeAvailable}
            className={`${toggleClass(metronome)} disabled:cursor-not-allowed disabled:opacity-40`}
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

      <p className="text-xs text-neutral-500">
        속도를 바꿔도 음정은 유지됩니다. 피치는 반음 단위로 따로 조절합니다.
        구간 반복과 메트로놈은 배속을 바꿔도 그대로 따라옵니다.
      </p>
    </section>
  );
}
