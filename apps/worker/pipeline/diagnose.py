"""입력이 어떤 종류인지 판정한다.

유튜브에서 베이스 곡을 찾으면 크게 두 종류가 나온다.

- **원곡 음원** — 베이스가 하나다. 우리가 잘 하는 입력이다.
- **연습 영상** — 원곡 음원을 반주로 틀고 그 위에 커버 베이시스트가 연주한다.
  화면에 그 사람의 악보와 재생 커서가 같이 나오는 경우가 많다.

연습 영상은 **베이스가 둘 섞여 있다.** Demucs는 둘을 구분하지 않고 하나의 bass
스템으로 합치므로, 채보하면 두 연주의 타점이 겹쳐 리듬이 격자에서 흩어진다.

## 연습 영상이면 하향 단계를 만들지 않는다

두 가지 이유다.

1. **이미 누군가 연습용으로 만든 것이다.** 커버 연주자가 화면 악보까지 붙여
   놓았다. 그것을 우리가 또 깎을 이유가 없다.
2. **품질이 낮아 하향이 오히려 해롭다.** 하향은 검출된 음 수로 밀도를 정하는데,
   두 연주가 섞이면 그 밀도 자체가 실제 연주와 무관하다. 근음도 흔들린다.
   깎을수록 원곡과 멀어진다.

원곡을 넣으라고 안내하는 편이 정직하다.

## 무엇으로 판정하는가

**주 신호 — 음량 게이트가 실패했다.** 게이트는 큰 소리 쪽만 남겨 한 사람의
연주로 수렴시키는 장치다. 그것을 걸었는데도 온셋이 격자 자리에 안 걸리면,
남은 음들이 여전히 한 사람의 연주가 아니라는 뜻이다.

격자는 16분·8분셋잇단·16분셋잇단 중 **가장 잘 맞는 것**을 쓴다. 8분 격자로만
재면 정상적인 16비트 라인과 스윙 곡이 연습 영상으로 몰린다(실측: IDMT 정답
17곡 중 8곡이 그렇게 오판됐다).

**보조 신호 — 어택 상승시간이 들쭉날쭉하다.** 단일 핑거스타일 어택은 20~60ms에
매끄럽게 오른다. 두 연주가 겹치면 마디마다 시간차가 벌어졌다 좁아지며 상승시간이
크게 흔들린다(실측: 26~128ms로 5배).

**보컬 잔존율은 주 신호로 쓰지 않는다.** 원곡 음원 자체를 넣어도 보컬은 있다.
"원곡"과 "원곡+커버"를 가르지 못한다. 참고값으로만 남긴다.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass, field
from pathlib import Path

SR = 22050

# 게이트 후에도 격자 정렬률이 이보다 낮으면 한 사람의 연주로 보지 않는다.
# bassclean.GATE_TARGET_GRID_RATIO와 **같은 값이어야 한다** — 같은 질문이기
# 때문이다. 두 값이 갈리면 "게이트는 목표에 닿았다고 하는데 진단은 아니라고
# 한다" 또는 그 반대의 모순이 생긴다.
PRACTICE_GRID_RATIO = 0.95

# 어택 상승시간(10%->90%) 변동계수가 이보다 크면 두 연주 겹침을 의심한다.
# 단일 핑거스타일은 20~60ms 범위에 매끄럽게 모인다.
PRACTICE_ATTACK_CV = 0.45

# 상승시간을 잴 온셋 수 하한. 이보다 적으면 통계가 성립하지 않는다.
MIN_ONSETS_FOR_ATTACK = 12

# 어택 상승 구간을 볼 창(초). 이보다 길면 다음 음이 섞인다.
ATTACK_WINDOW_SEC = 0.15


@dataclass
class InputDiagnosis:
    """입력 종류 판정. 하향 단계를 제공할지 결정한다."""

    practice_video: bool
    grid_ratio: float
    attack_cv: float
    vocal_activity: float
    reason: str
    signals: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "practiceVideo": self.practice_video,
            "gridRatio": round(self.grid_ratio, 4),
            "attackCv": round(self.attack_cv, 4),
            "vocalActivity": round(self.vocal_activity, 4),
            "reason": self.reason,
            "signals": self.signals,
        }


def attack_rise_variation(onsets: list[float], stem_path: Path) -> float:
    """어택 상승시간(10%→90%)의 변동계수. 못 재면 0.0.

    두 연주가 겹치면 마디마다 시간차가 벌어졌다 좁아지며 상승이 흔들린다.
    """
    import librosa
    import numpy as np

    if len(onsets) < MIN_ONSETS_FOR_ATTACK:
        return 0.0

    y, sr = librosa.load(str(stem_path), sr=SR, mono=True)
    rises: list[float] = []
    span = int(ATTACK_WINDOW_SEC * sr)

    for t in onsets:
        start = int(t * sr)
        seg = np.abs(y[start : start + span])
        if len(seg) < 32:
            continue
        peak = float(seg.max())
        if peak <= 1e-6:
            continue
        lo = np.argmax(seg >= peak * 0.1)
        hi = np.argmax(seg >= peak * 0.9)
        if hi <= lo:
            continue
        rises.append((hi - lo) / sr)

    if len(rises) < MIN_ONSETS_FOR_ATTACK:
        return 0.0
    mean = statistics.fmean(rises)
    return statistics.pstdev(rises) / mean if mean > 1e-9 else 0.0


def vocal_activity_ratio(stem_path: Path) -> float:
    """보컬 스템에서 뚜렷한 소리가 나는 시간 비율. 참고값이다."""
    import librosa
    import numpy as np

    if not stem_path.exists():
        return 0.0
    y, sr = librosa.load(str(stem_path), sr=SR, mono=True)
    env = librosa.feature.rms(y=y, frame_length=2048, hop_length=512)[0]
    if not len(env):
        return 0.0
    # 최대의 10%를 넘으면 "들린다"로 본다.
    return float(np.mean(env > env.max() * 0.1))


def diagnose(
    *,
    gate_applied: bool,
    grid_ratio: float,
    onsets: list[float],
    bass_stem: Path,
    vocals_stem: Path | None = None,
    verbose: bool = False,
) -> InputDiagnosis:
    """입력이 연습 영상(베이스 둘)인지 판정한다.

    grid_ratio는 **음량 게이트를 건 뒤**의 값이어야 한다. 게이트 전 값으로
    판정하면 게이트가 해결한 곡까지 연습 영상으로 몰린다.
    """
    attack_cv = attack_rise_variation(onsets, bass_stem)
    vocal = vocal_activity_ratio(vocals_stem) if vocals_stem else 0.0

    signals: list[str] = []
    # 주 신호: 게이트를 걸었는데도 한 사람의 연주로 수렴하지 않았다.
    gate_failed = gate_applied and grid_ratio < PRACTICE_GRID_RATIO
    if gate_failed:
        signals.append(
            f"큰 소리 쪽만 남겼는데도 격자에 걸리는 비율이 {100 * grid_ratio:.0f}%"
        )
    if attack_cv > PRACTICE_ATTACK_CV:
        signals.append(f"어택 상승시간 편차 {attack_cv:.2f}")

    practice = gate_failed
    if practice:
        reason = (
            "베이스가 둘 섞인 연습 영상으로 보입니다. 원곡 음원을 반주로 틀고 "
            "그 위에 연주한 영상이면 두 연주가 한 소리로 합쳐져 타점이 흐려집니다. "
            "이미 연습용으로 만들어진 자료이므로 난이도를 더 낮추지 않습니다 — "
            "원곡 음원을 넣으면 훨씬 정확하고 난이도 조절도 됩니다."
        )
    else:
        reason = "베이스가 하나인 입력으로 보입니다."

    result = InputDiagnosis(
        practice_video=practice,
        grid_ratio=grid_ratio,
        attack_cv=attack_cv,
        vocal_activity=vocal,
        reason=reason,
        signals=signals,
    )
    if verbose:
        print(
            f"[diagnose] {'연습 영상' if practice else '단일 베이스'} — "
            f"격자정렬 {100 * grid_ratio:.1f}%, 어택 편차 {attack_cv:.2f}, "
            f"보컬 활동 {100 * vocal:.1f}%"
            + (f" | {', '.join(signals)}" if signals else "")
        )
    return result
