"""패턴 관성 — 섹션 안의 리듬을 최빈 패턴으로 통일한다.

## 왜 필요한가

베이시스트는 2~4마디 리듬 패턴을 하나 잡으면 **섹션이 바뀔 때까지 타현 횟수와
리듬을 그대로 반복**한다. 코드 근음만 바뀐다. 사람이 치는 라인의 핵심은 변칙이
아니라 반복이다(`playing.json` patternInertia).

우리 검출은 그것을 모른다. 같은 그루브 16마디를 2·3·4·2·2·3·4·3타로 제멋대로
적었다. 정답은 전부 3타였다. **총량은 맞고 분포가 어긋나는** 전형적인 증상이고,
연주자가 "이 악보 못 쓴다"고 판단하는 가장 흔한 이유다.

## 어떻게 하는가

창(기본 4마디) 안에서 **슬롯 집합의 최빈 패턴**을 찾아 그 창의 마디에 씌운다.
음높이는 각 마디의 것을 그대로 쓴다 — 리듬만 통일하고 음은 건드리지 않는다.

## 무엇을 건드리지 않는가

- **필인**: 최빈보다 훨씬 많이 치는 마디는 그대로 둔다. 4·8마디 끝자락의 속주는
  실제 연주이고, 통일하면 곡의 맛이 죽는다(`playing.json` songSections.fill).
- **쉬는 마디**: 음이 없는 마디에 패턴을 만들어 넣지 않는다.
- **최빈이 뚜렷하지 않은 창**: 패턴이 갈리면 통일할 근거가 없다.

## 이것은 편집이 아니라 검출 보정이다

패턴을 씌워 늘어나는 음은 "없던 것을 만드는" 것이 아니라 **반복 구조로 놓친
타현을 되살리는** 것이다. 그래서 하향(reduce)이 아니라 양자화 뒤 후처리에 둔다.
"""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass, field, replace
from functools import lru_cache
from pathlib import Path

from . import sections as sections_mod
from .quantize import Bar, QuantizedNote, QuantizedScore

PLAYING_PATH = Path(__file__).with_name("playing.json")


@lru_cache(maxsize=1)
def playing() -> dict:
    """연주 관습 지식."""
    return json.loads(PLAYING_PATH.read_text(encoding="utf-8"))


# 패턴을 찾는 창 크기(마디).
#
# 연주자가 잡는 주기는 2~4마디지만 **창은 그보다 커야 한다.** 4마디로 잡고
# 슬롯 집합의 완전 일치를 요구했더니 21창 중 대부분을 건너뛰었다 — 우리 검출이
# 흔들리면 같은 슬롯 집합이 두 번 나오지 않는다.
#
# 12마디로 넓히고 **슬롯별 빈도**로 보면 답이 나온다. 8마디는 창 끝부분이 다른
# 패턴으로 통일되는 문제가 있었다. 실측: 16마디에서 슬롯 0이
# 16회, 7이 10회, 10이 12회, 나머지는 3회 이하 — 과반만 뽑으면 정답인 3타
# 패턴 {0,7,10}이 정확히 나온다.
WINDOW_BARS = 12

# 슬롯이 창 안 연주 마디의 이 비율 이상에서 나와야 패턴으로 인정한다.
# 과반이라는 뜻이고, 흔들리는 검출에서 반복되는 축만 남긴다.
SLOT_SUPPORT_RATIO = 0.5

# 패턴을 뽑으려면 창에 연주 마디가 최소 이만큼 있어야 한다.
MIN_ACTIVE_BARS = 4

# 패턴보다 이 배수 이상 많이 치는 마디는 필인으로 보고 건드리지 않는다.
#
# 2.0인 이유: 필인은 "약간 많은" 것이 아니라 **분명한 폭증**이다(4번째 박에
# 16분 3~4개가 다다닥). 1.6으로 두었더니 3타 패턴에서 5타인 마디가 필인으로
# 오분류돼 통일에서 빠졌다(정답 3타). 실제 필인은 8타여서 2.0으로도 보호된다.
FILL_ATTACK_RATIO = 2.0

# 통일 대상으로 삼을 타현 수 차이 상한. 최빈과 이보다 크게 벌어진 마디는
# 다른 리듬을 치고 있는 것일 수 있어 손대지 않는다.
MAX_ATTACK_GAP = 3

# 창을 곡 구조 경계로 자를 것인가(`sections.detect`), 고정 길이로 자를 것인가.
#
# **False다. 이론이 아니라 측정 때문이다.**
#
# 고정 창이 곡 구조를 무시하는 것은 사실이고, 벌스와 코러스를 한 창에 묶는
# 위험은 실재한다. 그래서 `sections.py`를 만들어 리듬 특징 기반 구조 분할을
# 붙였다. 그런데 유일한 정답(영상 화면 악보 16마디)에서 측정하면:
#
#     고정 12마디 창   자리 16/16, 타현수 16/16
#     구조 분할 창     자리 16/16, 타현수 14/16
#
# 구조 분할이 더 나쁘다. 경계가 정답 구간을 가로질러(25·41마디) 구간 끝
# 두 마디를 다음 섹션의 패턴으로 통일해 버린다.
#
# **다만 이 측정으로 구조 분할이 틀렸다고 결론 낼 수는 없다.** 이 곡은
# 100마디 넘게 같은 4마디 그루브를 반복하는 곡이라 나눌 구조가 애초에 없다.
# 구조 분할의 값어치는 벌스와 코러스의 밀도가 실제로 다른 곡에서 드러나고,
# 그런 곡의 정답이 우리에게 없다. 즉 **검증 불가**이고 켜는 것은 근거 없는
# 선택이 된다. 정답을 한 곡 더 확보한 뒤 다시 판정한다(NEXT.md).
USE_SECTIONS = False


@dataclass
class InertiaReport:
    windows: int = 0
    unified_bars: int = 0
    added_attacks: int = 0
    removed_attacks: int = 0
    fills_kept: int = 0
    silent_kept: int = 0
    skipped_windows: int = 0
    patterns: list[str] = field(default_factory=list)
    # 구조 분할 결과. 고정 창을 썼으면 빈 dict다.
    sections: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "windows": self.windows,
            "unifiedBars": self.unified_bars,
            "addedAttacks": self.added_attacks,
            "removedAttacks": self.removed_attacks,
            "fillsKept": self.fills_kept,
            "silentKept": self.silent_kept,
            "skippedWindows": self.skipped_windows,
            "sections": self.sections,
        }


def apply_inertia(
    score: QuantizedScore,
    *,
    window_bars: int = WINDOW_BARS,
    use_sections: bool = USE_SECTIONS,
    verbose: bool = False,
) -> tuple[QuantizedScore, InertiaReport]:
    """섹션 안의 리듬을 최빈 패턴으로 통일한다. 원본은 건드리지 않는다.

    창을 어떻게 자르는가는 `USE_SECTIONS` 주석을 보라. 기본은 고정 창이고
    구조 분할은 켤 수 있지만 아직 검증되지 않았다.
    """
    report = InertiaReport()
    bars = list(score.bars)

    if use_sections:
        sections, section_report = sections_mod.detect(score, verbose=verbose)
        report.sections = section_report.to_dict()
        windows = [(a, bars[a:b]) for a, b in sections]
    else:
        windows = [
            (s, bars[s : s + window_bars])
            for s in range(0, len(bars), window_bars)
        ]

    for start, window in windows:
        active = [b for b in window if b.notes]
        if len(active) < MIN_ACTIVE_BARS:
            report.skipped_windows += 1
            continue

        # 슬롯별 빈도를 센다. 슬롯 집합의 완전 일치를 요구하면 흔들리는 검출에서
        # 아무것도 안 걸린다 — 반복되는 **축**만 뽑는 것이 목적이다.
        freq: Counter = Counter()
        for bar in active:
            freq.update({n.slot for n in bar.notes})
        need = len(active) * SLOT_SUPPORT_RATIO
        pattern = tuple(sorted(s for s, c in freq.items() if c >= need))
        if not pattern:
            report.skipped_windows += 1
            continue

        report.windows += 1

        report.patterns.append(",".join(str(s) for s in pattern))
        for i, bar in enumerate(window):
            if not bar.notes:
                report.silent_kept += 1
                continue
            if len(bar.notes) >= len(pattern) * FILL_ATTACK_RATIO:
                report.fills_kept += 1
                continue
            if abs(len(bar.notes) - len(pattern)) > MAX_ATTACK_GAP:
                continue
            if tuple(sorted(n.slot for n in bar.notes)) == pattern:
                continue

            new_bar = _reslot(bar, pattern)
            delta = len(new_bar.notes) - len(bar.notes)
            if delta > 0:
                report.added_attacks += delta
            else:
                report.removed_attacks += -delta
            bars[start + i] = new_bar
            report.unified_bars += 1

    if verbose:
        top = Counter(report.patterns).most_common(3)
        print(
            f"[inertia] 창 {report.windows}개, 통일 {report.unified_bars}마디 "
            f"(+{report.added_attacks}타 / -{report.removed_attacks}타), "
            f"필인 유지 {report.fills_kept}, 쉼표 {report.silent_kept}, "
            f"건너뜀 {report.skipped_windows}창"
        )
        if top:
            print("[inertia] 최빈 패턴: " + ", ".join(f"{{{p}}}×{n}" for p, n in top))

    return replace(score, bars=bars, note_count=sum(len(b.notes) for b in bars)), report


def _reslot(bar: Bar, pattern: tuple[int, ...]) -> Bar:
    """마디를 주어진 슬롯 패턴으로 다시 적는다. 음높이는 그 마디의 것을 쓴다.

    각 목표 슬롯에 가장 가까운 원래 음의 피치를 가져온다. 리듬만 통일하고
    음정은 건드리지 않는 것이 원칙이다 — 음정은 검출이 잘 맞는 축이다.
    """
    ordered = sorted(bar.notes, key=lambda n: n.slot)
    slots = [s for s in pattern if s < bar.slots_per_bar]
    if not slots:
        return bar

    notes: list[QuantizedNote] = []
    for i, slot in enumerate(slots):
        source = min(ordered, key=lambda n: abs(n.slot - slot))
        end = slots[i + 1] if i + 1 < len(slots) else bar.slots_per_bar
        notes.append(
            replace(
                source,
                slot=slot,
                duration_slots=max(1, end - slot),
            )
        )
    return replace(bar, notes=notes)
