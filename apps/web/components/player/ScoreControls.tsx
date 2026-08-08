"use client";

import {
  BADGE,
  BADGE_ACCENT,
  CARD,
  CHEVRON,
  FIELD_LABEL,
  HINT,
  OUTLINE_BTN,
  PANEL_BODY,
  PANEL_SUMMARY,
  SLIDER,
  STEPPER,
  chip,
} from "../ui";

/**
 * 난이도·키·튜닝·내보내기.
 *
 * 두 가지 원칙이 UI에 박혀 있다.
 *
 * 1) **난이도는 하향 단방향이다.** 원곡 채보가 상한이고 그보다 어렵게 만드는
 *    것은 편곡이다. 그래서 슬라이더 최대값이 "원곡"이다.
 * 2) **키를 바꾸면 재생 피치와 악보가 함께 움직인다.** 컨트롤이 하나뿐이라
 *    둘이 어긋난 상태를 만들 수 없다.
 *
 * 키를 내릴 때는 이조 대신 **튜닝 내리기**를 먼저 제안한다. 반음 내림 튜닝은
 * 운지가 그대로 유지되므로 다시 배울 것이 없다 — 실제 연주자가 쓰는 방법이다.
 *
 * 전체를 접이식 패널에 담고 접힌 상태에서도 현재 값(난이도·키·튜닝)이 제목
 * 줄에 남게 했다. 한 번 정하면 곡이 끝날 때까지 안 만지는 값들이라 펼쳐 두면
 * 악보 자리만 먹는데, 지금 무엇으로 보고 있는지는 항상 알아야 한다.
 */

export interface LevelInfo {
  level: number;
  name: string;
  hint: string;
}

/** 워커의 reduce.LEVELS와 같은 번호·이름·설명을 쓴다. */
export const LEVELS: LevelInfo[] = [
  { level: 1, name: "초급", hint: "균일한 리듬 + 근음·5도·옥타브, 저프렛" },
  { level: 2, name: "중급", hint: "원곡 리듬 유지, 경과음·크로매틱만 정리" },
  { level: 3, name: "원본", hint: "채보 결과 그대로" },
];

export const ORIGINAL_LEVEL = 3;

/** 이조 한계(반음). 오디오 피치 시프트 품질이 이 밖에서 무너진다. */
export const TRANSPOSE_LIMIT = 6;
/** 이 이상 옮기면 소리가 눈에 띄게 상한다. */
const TRANSPOSE_WARN = 3;

const TUNINGS = [
  { key: "standard", label: "표준 EADG" },
  { key: "halfStepDown", label: "반음 내림" },
  { key: "dropD", label: "드롭 D" },
];

const EXPORTS = [
  { fmt: "musicxml", label: "MusicXML", hint: "MuseScore·Guitar Pro (TAB 유지)" },
  { fmt: "mid", label: "MIDI", hint: "DAW (음정·리듬만)" },
];

/**
 * 음량 게이트 결과. 두 연주가 섞인 입력이면 게이트가 걸리고, 그래도 정렬이
 * 목표에 못 닿으면 높은 난이도는 신뢰할 수 없다.
 *
 * **필드 이름이 `grid*`다.** 게이트 판정을 8분 격자에서 16분·셋잇단 격자로
 * 바꿀 때 manifest 키가 `eighthBefore/After` -> `gridBefore/After`로 바뀌었다.
 * 옛 이름을 그대로 읽으면 값이 `undefined`가 되고, `?? 1`에 걸려 "정렬 100%"로
 * 읽혀 **경고가 조용히 사라진다.** 실제로 그렇게 됐던 자리다.
 */
export interface LoudnessGate {
  applied: boolean;
  dropped: number;
  gridBefore: number;
  gridAfter: number;
}

/** 이 값에 못 닿으면 리듬을 믿을 수 없다고 본다. 워커의 게이트 목표와 같다. */
const TRUSTED_GRID_RATIO = 0.95;

/** 리듬을 믿을 수 없을 때에도 신뢰할 수 있는 최고 단계. 근음 위주라 타점 오차가 사라진다. */
const MAX_TRUSTED_LEVEL_WHEN_MIXED = 1;

interface Props {
  /** 내보내기 링크를 만들 때 쓴다. 없으면 내보내기 영역을 숨긴다. */
  contentHash?: string;
  level: number;
  transpose: number;
  tuning: string;
  gate?: LoudnessGate;
  /**
   * 이 곡에 제공할 단계. 원곡이 이미 초급 수준이면 [3](원본)만 온다 —
   * 쉬운 곡을 더 깎으면 원곡보다 심심해지기만 한다.
   */
  levels?: number[];
  /** 단계를 하나만 주는 이유. 사용자에게 그대로 보여준다 */
  levelReason?: string;
  onLevel: (level: number) => void;
  onTranspose: (semitones: number) => void;
  onTuning: (tuning: string) => void;
  /** 인쇄 창 열기. 악보가 아직 안 그려졌으면 없다 */
  onPrint?: () => void;
}

export default function ScoreControls({
  contentHash,
  level,
  transpose,
  tuning,
  gate,
  levels,
  levelReason,
  onLevel,
  onTranspose,
  onTuning,
  onPrint,
}: Props) {
  const offered = LEVELS.filter((l) => !levels || levels.includes(l.level));
  // 단계가 하나뿐이면 슬라이더를 보여주지 않는다. 조절할 것이 없는 컨트롤은
  // 사용자에게 "왜 안 움직이지"라는 질문만 만든다.
  const singleLevel = offered.length <= 1;
  const current = LEVELS.find((l) => l.level === level) ?? LEVELS[LEVELS.length - 1];
  const clamp = (v: number) => Math.max(-TRANSPOSE_LIMIT, Math.min(TRANSPOSE_LIMIT, v));

  // 게이트가 걸렸는데도 정렬이 목표에 못 닿으면 두 연주가 완전히 갈리지 않은
  // 것이다. 그런 곡의 원곡 난이도는 타점을 믿을 수 없다.
  const rhythmUntrusted = Boolean(gate?.applied) && (gate?.gridAfter ?? 1) < TRUSTED_GRID_RATIO;
  const levelUntrusted = rhythmUntrusted && level > MAX_TRUSTED_LEVEL_WHEN_MIXED;

  const tuningLabel = TUNINGS.find((t) => t.key === tuning)?.label ?? tuning;
  const exportHint =
    "지금 화면의 난이도·키·튜닝 그대로 내려갑니다. 자동 채보는 완벽하지 않으니 MuseScore나 Guitar Pro에서 고쳐 쓰는 것을 전제로 두었습니다." +
    (onPrint ? " 인쇄는 화면 뷰와 무관하게 전곡을 냅니다." : "");

  return (
    <details open className={`group ${CARD}`}>
      <summary className={PANEL_SUMMARY}>
        <span className="mr-auto">악보 설정</span>
        {/*
          접었을 때 지금 무엇으로 보고 있는지가 남아야 한다. 난이도·키·튜닝은
          악보의 내용을 바꾸는 값이라, 모르고 보면 원곡으로 착각한다.
        */}
        <span className="flex flex-wrap items-center justify-end gap-1.5">
          {rhythmUntrusted && <span className={BADGE_ACCENT}>리듬 신뢰도 낮음</span>}
          <span className={BADGE}>{current.name}</span>
          {transpose !== 0 && (
            <span className={BADGE}>{`키 ${transpose > 0 ? `+${transpose}` : transpose}`}</span>
          )}
          <span className={BADGE}>{tuningLabel}</span>
        </span>
        <span className={CHEVRON} aria-hidden>
          ▾
        </span>
      </summary>

      <div className={`grid gap-6 md:grid-cols-3 ${PANEL_BODY}`}>
        <div className="space-y-2">
          <div className="flex items-baseline justify-between gap-2">
            <span
              className={`${FIELD_LABEL} ${HINT}`}
              title="쉬운 쪽으로만 조절됩니다. 원곡보다 어렵게 만드는 것은 편곡이라 하지 않습니다."
            >
              난이도
            </span>
            <span className="text-sm font-medium">{current.name}</span>
          </div>
          <p className="text-xs text-neutral-500">{current.hint}</p>

          {singleLevel ? (
            <p className="rounded-lg border border-neutral-200 bg-neutral-50 px-3 py-2 text-xs text-neutral-600 dark:border-neutral-800 dark:bg-neutral-900 dark:text-neutral-400">
              {levelReason ?? "이 곡은 원곡이 이미 초급 수준이라 단계를 나누지 않았습니다."}
            </p>
          ) : (
            <>
              <input
                type="range"
                min={offered[0].level}
                max={offered[offered.length - 1].level}
                step={1}
                value={level}
                onChange={(e) => onLevel(Number(e.target.value))}
                className={`${SLIDER} w-full`}
                aria-label="난이도"
              />
              <div className="flex justify-between text-[11px] text-neutral-400">
                {offered.map((l) => (
                  <span key={l.level}>{l.name}</span>
                ))}
              </div>
            </>
          )}
        </div>

        <div className="space-y-4">
          <div className="space-y-2">
            <span
              className={`${FIELD_LABEL} ${HINT} block`}
              title={`재생 음정과 악보가 함께 바뀝니다. 최대 ±${TRANSPOSE_LIMIT}반음.`}
            >
              키
            </span>
            <div className="flex items-center gap-1.5">
              <button
                onClick={() => onTranspose(clamp(transpose - 1))}
                disabled={transpose <= -TRANSPOSE_LIMIT}
                className={STEPPER}
                aria-label="키 내리기"
              >
                −
              </button>
              <span className="w-9 text-center font-mono text-xs tabular-nums text-neutral-500">
                {transpose > 0 ? `+${transpose}` : transpose}
              </span>
              <button
                onClick={() => onTranspose(clamp(transpose + 1))}
                disabled={transpose >= TRANSPOSE_LIMIT}
                className={STEPPER}
                aria-label="키 올리기"
              >
                +
              </button>
              {transpose !== 0 && (
                <button
                  onClick={() => onTranspose(0)}
                  className="rounded-md px-2 py-1 text-xs text-neutral-500 transition hover:bg-neutral-100 dark:hover:bg-neutral-800"
                >
                  원래 키로
                </button>
              )}
            </div>
            {Math.abs(transpose) >= TRANSPOSE_WARN && (
              <p className="text-xs text-amber-700 dark:text-amber-400">
                {`${Math.abs(transpose)}반음은 소리가 상할 수 있습니다. 반음만 내릴 것이라면 튜닝을 내리는 쪽이 낫습니다.`}
              </p>
            )}
          </div>

          <div className="space-y-2">
            <span
              className={`${FIELD_LABEL} ${HINT} block`}
              title="반음 내림 튜닝은 운지가 그대로라 다시 배울 것이 없습니다. 키를 반음 내리려면 이쪽이 낫습니다."
            >
              튜닝
            </span>
            <div className="flex flex-wrap gap-1.5">
              {TUNINGS.map((t) => (
                <button key={t.key} onClick={() => onTuning(t.key)} className={chip(tuning === t.key)}>
                  {t.label}
                </button>
              ))}
            </div>
          </div>
        </div>

        {(contentHash || onPrint) && (
          <div className="space-y-2">
            <span className={`${FIELD_LABEL} ${HINT} block`} title={exportHint}>
              내보내기
            </span>
            <div className="flex flex-wrap gap-1.5">
              {contentHash &&
                EXPORTS.map((f) => (
                  <a
                    key={f.fmt}
                    /*
                      지금 화면에 보이는 것과 **같은** 난이도·이조·튜닝으로 받는다.
                      다른 것이 내려가면 사용자가 알 방법이 없다.
                    */
                    href={`/api/exports/${contentHash}/${contentHash}.${f.fmt}?level=${level}&transpose=${transpose}&tuning=${tuning}`}
                    className={OUTLINE_BTN}
                    title={f.hint}
                  >
                    {f.label}
                  </a>
                ))}
              {contentHash && (
                <a
                  href={`/api/scores/${contentHash}/ledger?level=${level}&transpose=${transpose}&tuning=${tuning}`}
                  className={OUTLINE_BTN}
                  title="음표별 배치 데이터 — 마디·슬롯·박 위치, 검출 시각→스냅, 피치 출처, 현·프렛"
                >
                  음표 원장 CSV
                </a>
              )}
              {onPrint && (
                <button
                  onClick={onPrint}
                  className={OUTLINE_BTN}
                  title="브라우저 인쇄 창에서 'PDF로 저장'을 고르세요"
                >
                  인쇄/PDF
                </button>
              )}
            </div>
          </div>
        )}

        {/*
          단계가 하나뿐이면 그 사유(연습 영상 안내)가 위에 이미 떠 있다. 같은
          얘기를 두 번 하지 않는다 — 경고를 겹쳐 쌓으면 하나도 안 읽힌다.
        */}
        {rhythmUntrusted && !singleLevel && (
          <div className="space-y-1 rounded-lg border border-amber-300 bg-amber-50 px-3 py-2 text-xs text-amber-800 md:col-span-3 dark:border-amber-800 dark:bg-amber-950 dark:text-amber-200">
            {/*
              **원인을 단정하지 않는다.** 예전에는 "베이스가 둘 섞여 있습니다"라고
              적었는데, 공식 스튜디오 음원 세 곡에도 그 경고가 떴다. 격자 정렬이
              낮은 이유는 최소 둘이고(베이스가 둘 / 우리 검출이 약함) 우리는
              그것을 가르지 못한다(`pipeline/diagnose.py` 머리말).
            */}
            <p className="font-medium">이 곡은 리듬 검출 신뢰도가 낮습니다.</p>
            <p>
              {`타점의 ${Math.round(100 * (gate?.gridAfter ?? 0))}%만 격자에 얹혔습니다.`}
              {" 베이스가 둘 섞인 음원이거나, 16비트·슬랩처럼 우리가 약한 연주일 수 있습니다."}
              {` 리듬을 믿을 수 있는 것은 ${
                LEVELS.find((l) => l.level === MAX_TRUSTED_LEVEL_WHEN_MIXED)?.name
              } 이하입니다 — 음정은 참고하되 리듬은 원곡을 들어 확인하세요.`}
            </p>
          </div>
        )}

        {rhythmUntrusted && levelUntrusted && (
          <p className="text-xs text-red-700 md:col-span-3 dark:text-red-400">
            이 악보의 <strong>리듬은 신뢰할 수 없습니다.</strong> 음정만 참고하세요.
          </p>
        )}
      </div>
    </details>
  );
}
