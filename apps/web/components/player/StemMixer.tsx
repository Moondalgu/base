"use client";

import { PRESETS, STEM_ORDER, type Gains, type StemName } from "@/lib/player/engine";

const LABELS: Record<StemName, string> = {
  drums: "드럼",
  bass: "베이스",
  vocals: "보컬",
  other: "그 외",
};

interface Props {
  gains: Gains;
  onGainChange: (stem: StemName, value: number) => void;
  onPreset: (key: string) => void;
  activePreset: string | null;
}

export default function StemMixer({ gains, onGainChange, onPreset, activePreset }: Props) {
  return (
    <section className="space-y-5">
      <div className="flex flex-wrap gap-2">
        {Object.entries(PRESETS).map(([key, preset]) => (
          <button
            key={key}
            onClick={() => onPreset(key)}
            className={`rounded-full px-4 py-1.5 text-sm transition ${
              activePreset === key
                ? "bg-neutral-900 text-white dark:bg-white dark:text-neutral-900"
                : "bg-neutral-200 text-neutral-700 hover:bg-neutral-300 dark:bg-neutral-800 dark:text-neutral-300 dark:hover:bg-neutral-700"
            }`}
          >
            {preset.label}
          </button>
        ))}
      </div>

      <div className="space-y-3">
        {STEM_ORDER.map((stem) => {
          const value = gains[stem];
          const isBass = stem === "bass";
          return (
            <div key={stem} className="flex items-center gap-3">
              <span
                className={`w-16 shrink-0 text-sm ${
                  isBass ? "font-semibold text-neutral-900 dark:text-white" : "text-neutral-600 dark:text-neutral-400"
                }`}
              >
                {LABELS[stem]}
              </span>
              <input
                type="range"
                min={0}
                max={2}
                step={0.01}
                value={value}
                onChange={(e) => onGainChange(stem, Number(e.target.value))}
                className="h-1.5 flex-1 cursor-pointer accent-neutral-900 dark:accent-white"
                aria-label={`${LABELS[stem]} 볼륨`}
              />
              <span className="w-12 shrink-0 text-right font-mono text-xs tabular-nums text-neutral-500">
                {Math.round(value * 100)}%
              </span>
              <button
                onClick={() => onGainChange(stem, value > 0 ? 0 : 1)}
                className="w-10 shrink-0 rounded border border-neutral-300 px-1 py-0.5 text-xs text-neutral-600 hover:bg-neutral-100 dark:border-neutral-700 dark:text-neutral-400 dark:hover:bg-neutral-800"
              >
                {value > 0 ? "뮤트" : "해제"}
              </button>
            </div>
          );
        })}
      </div>

      <p className="text-xs text-neutral-500">
        100%를 넘기면 부스트됩니다. 스템 간 어긋남 없이 실시간으로 섞입니다.
      </p>
    </section>
  );
}
