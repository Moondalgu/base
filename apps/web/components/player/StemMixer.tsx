"use client";

import { PRESETS, STEM_ORDER, type Gains, type StemName } from "@/lib/player/engine";
import {
  BADGE,
  CARD,
  CHEVRON,
  FIELD_LABEL,
  HINT,
  PANEL_BODY,
  PANEL_SUMMARY,
  SLIDER,
  SLIDER_ACCENT,
  chip,
} from "../ui";

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
  /** 악보 연주 모드 — 원곡 베이스를 빼고 화면 악보를 샘플러로 연주한다 */
  synthOn: boolean;
  synthGain: number;
  onSynthToggle: () => void;
  onSynthGain: (value: number) => void;
}

/**
 * 스템 볼륨.
 *
 * 접이식이지만 접힌 상태에서도 베이스 볼륨은 제목 줄에 남긴다 — 이 도구에서
 * 사람이 가장 자주 확인하는 값이고, 0인 줄 모르고 "소리가 안 난다"고 볼 수
 * 있는 값이기도 하다. 베이스 줄만 포인트색을 쓴 것도 같은 이유다.
 */
export default function StemMixer({
  gains,
  onGainChange,
  onPreset,
  activePreset,
  synthOn,
  synthGain,
  onSynthToggle,
  onSynthGain,
}: Props) {
  return (
    <details open className={`group ${CARD}`}>
      <summary className={PANEL_SUMMARY}>
        <span className="mr-auto">스템 볼륨</span>
        <span className="flex flex-wrap items-center justify-end gap-1.5">
          {synthOn && <span className={BADGE}>악보 연주</span>}
          {activePreset && PRESETS[activePreset] && (
            <span className={BADGE}>{PRESETS[activePreset].label}</span>
          )}
          <span className={BADGE}>{`베이스 ${Math.round(gains.bass * 100)}%`}</span>
        </span>
        <span className={CHEVRON} aria-hidden>
          ▾
        </span>
      </summary>

      <div className={`space-y-4 ${PANEL_BODY}`}>
        <div className="flex flex-wrap items-center gap-1.5">
          <span
            className={`${FIELD_LABEL} ${HINT} mr-1`}
            title="100%를 넘기면 부스트됩니다. 스템 간 어긋남 없이 실시간으로 섞입니다."
          >
            프리셋
          </span>
          {Object.entries(PRESETS).map(([key, preset]) => (
            <button key={key} onClick={() => onPreset(key)} className={chip(activePreset === key)}>
              {preset.label}
            </button>
          ))}
        </div>

        {/* 악보 연주 — 원곡 베이스를 빼고 화면 악보(현재 난이도·키)를 샘플러로
            연주한다. 초보가 "정답 소리"를 들으며 따라 치는 용도라 기본 부스트. */}
        <div className="flex items-center gap-3 rounded-lg border border-neutral-200 px-3 py-2 dark:border-neutral-700">
          <button
            onClick={onSynthToggle}
            className={chip(synthOn)}
            title="원곡 베이스 대신 화면 악보를 연주합니다. 난이도·키를 바꾸면 소리도 따라갑니다."
          >
            {synthOn ? "악보 연주 중" : "악보 연주"}
          </button>
          <input
            type="range"
            min={0}
            max={2.5}
            step={0.01}
            value={synthGain}
            onChange={(e) => onSynthGain(Number(e.target.value))}
            disabled={!synthOn}
            className={`${SLIDER_ACCENT} flex-1 disabled:opacity-40`}
            aria-label="악보 연주 볼륨"
          />
          <span className="w-10 shrink-0 text-right font-mono text-xs tabular-nums text-neutral-500">
            {Math.round(synthGain * 100)}%
          </span>
        </div>

        <div className="space-y-2.5">
          {STEM_ORDER.map((stem) => {
            const value = gains[stem];
            const isBass = stem === "bass";
            return (
              <div key={stem} className="flex items-center gap-3">
                <span
                  className={`w-14 shrink-0 text-xs ${
                    isBass
                      ? "font-semibold text-neutral-900 dark:text-white"
                      : "text-neutral-600 dark:text-neutral-400"
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
                  className={`${isBass ? SLIDER_ACCENT : SLIDER} flex-1`}
                  aria-label={`${LABELS[stem]} 볼륨`}
                />
                <span className="w-10 shrink-0 text-right font-mono text-xs tabular-nums text-neutral-500">
                  {Math.round(value * 100)}%
                </span>
                <button
                  onClick={() => onGainChange(stem, value > 0 ? 0 : 1)}
                  className="w-11 shrink-0 rounded-md border border-neutral-200 py-0.5 text-xs text-neutral-600 transition hover:bg-neutral-100 dark:border-neutral-700 dark:text-neutral-400 dark:hover:bg-neutral-800"
                >
                  {value > 0 ? "뮤트" : "해제"}
                </button>
              </div>
            );
          })}
        </div>
      </div>
    </details>
  );
}
