/**
 * 화면 표현 클래스 모음.
 *
 * 버튼 위계를 한 곳에서 정한다 — 주요 동작은 채움, 보조 선택은 아웃라인,
 * "지금 켜져 있음"은 포인트색(앰버)이다. 컴포넌트마다 클래스를 따로 적으면
 * 같은 뜻을 가진 버튼이 화면마다 다르게 생긴다.
 *
 * 포인트색을 앰버로 잡은 이유는 악보 커서다. alphaTab 마디 커서가 노란
 * 계열(globals.css `.at-cursor-bar`)이라, 재생 중인 컨트롤을 같은 색으로
 * 물들이면 화면에서 "지금 움직이는 것"이 한 무리로 보인다.
 */

/** 카드·패널 공통 테두리 */
export const CARD = "rounded-xl border border-neutral-200 dark:border-neutral-800";

/** 접이식 패널의 제목 줄 */
export const PANEL_SUMMARY =
  "flex cursor-pointer list-none select-none items-center gap-2 rounded-xl px-4 py-3 text-sm font-medium transition hover:bg-neutral-50 dark:hover:bg-neutral-900 [&::-webkit-details-marker]:hidden";

/** 접이식 패널의 본문 */
export const PANEL_BODY =
  "border-t border-neutral-200 px-4 py-4 dark:border-neutral-800";

/** 컨트롤 묶음의 이름표 */
export const FIELD_LABEL = "text-xs font-medium text-neutral-500 dark:text-neutral-400";

/** title 툴팁이 달려 있다는 표시. 설명 문단을 접어 넣은 자리에 쓴다 */
export const HINT = "cursor-help underline decoration-dotted decoration-neutral-400 underline-offset-4";

/** 사실을 보여주는 꼬리표 (BPM·마디 수처럼 누를 수 없는 것) */
export const BADGE =
  "inline-flex items-center gap-1 rounded-full border border-neutral-200 px-2 py-0.5 text-[11px] leading-5 text-neutral-600 dark:border-neutral-700 dark:text-neutral-400";

/** 눈에 걸려야 하는 꼬리표 */
export const BADGE_ACCENT =
  "inline-flex items-center gap-1 rounded-full border border-amber-400/70 bg-amber-50 px-2 py-0.5 text-[11px] leading-5 text-amber-800 dark:border-amber-500/40 dark:bg-amber-500/10 dark:text-amber-300";

/**
 * 여럿 중 하나를 고르는 버튼. 고른 것만 채운다.
 * 꺼진 쪽도 테두리를 두는 이유는 높이다 — 한쪽만 테두리가 있으면 고를 때마다
 * 줄 높이가 2px씩 흔들린다.
 */
export function chip(active: boolean): string {
  return `rounded-md border px-2.5 py-1 text-xs transition ${
    active
      ? "border-neutral-900 bg-neutral-900 text-white dark:border-white dark:bg-white dark:text-neutral-900"
      : "border-neutral-200 text-neutral-600 hover:bg-neutral-100 dark:border-neutral-700 dark:text-neutral-300 dark:hover:bg-neutral-800"
  }`;
}

/** 켜고 끄는 버튼. 켜져 있으면 포인트색이라 한눈에 보인다 */
export function toggleChip(active: boolean): string {
  return `rounded-md border px-2.5 py-1 text-xs font-medium transition ${
    active
      ? "border-amber-500 bg-amber-500 text-neutral-950 hover:bg-amber-400"
      : "border-neutral-200 text-neutral-600 hover:bg-neutral-100 dark:border-neutral-700 dark:text-neutral-300 dark:hover:bg-neutral-800"
  }`;
}

/** −/+ 같은 한 칸짜리 버튼 */
export const STEPPER =
  "flex h-7 w-7 items-center justify-center rounded-md border border-neutral-200 text-sm text-neutral-600 transition hover:bg-neutral-100 disabled:opacity-40 dark:border-neutral-700 dark:text-neutral-300 dark:hover:bg-neutral-800";

/** 링크처럼 쓰는 보조 버튼 (내보내기 등) */
export const OUTLINE_BTN =
  "rounded-md border border-neutral-200 px-2.5 py-1 text-xs text-neutral-600 transition hover:bg-neutral-100 dark:border-neutral-700 dark:text-neutral-300 dark:hover:bg-neutral-800";

export const SLIDER = "h-1.5 cursor-pointer accent-neutral-900 dark:accent-white";
/** 재생과 직접 엮인 슬라이더 */
export const SLIDER_ACCENT = "h-1.5 cursor-pointer accent-amber-500";

/** 숫자 표시 — 자리 흔들림을 막으려 고정폭 */
export const NUM = "font-mono text-xs tabular-nums text-neutral-500";

/** 컨트롤 묶음 사이 세로 구분선. 좁은 화면에서는 줄바꿈이 대신한다 */
export const DIVIDER = "hidden h-6 w-px shrink-0 bg-neutral-200 sm:block dark:bg-neutral-800";

/** 접이식 패널의 펼침 표시 */
export const CHEVRON = "shrink-0 text-xs text-neutral-400 transition-transform group-open:rotate-180";
