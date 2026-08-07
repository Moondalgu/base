"""입력 진단 — 이 채보를 얼마나 믿을 수 있는가.

## 연습 영상 판정을 **버렸다** (2026-08-07)

원래 이 모듈은 "원곡 음원인가, 연습 영상(원곡 반주 + 커버 연주가 겹친 것)인가"를
가르려 했다. **골든셋 4곡에서 재보니 신호가 하나도 안 갈렸고, 하나는 방향이
반대였다.**

| 곡 | 실제 | 격자 정렬 | 어택 CV | 보컬 활동 |
|---|---|---|---|---|
| Queen — Another One Bites the Dust | 원곡 | 0.777 | 1.480 | 0.408 |
| The Beatles — Come Together | 원곡 | 0.751 | 1.389 | 0.348 |
| **Champagne Supernova 커버** | **연습 영상** | **0.730** | **1.096** | 0.635 |
| Jamiroquai — Virtual Insanity | 원곡 | 0.674 | 1.496 | 0.706 |

- **격자 정렬**: 진짜 연습 영상이 0.730으로 세 번째다. 원곡인 Virtual Insanity가
  더 낮다. 못 가른다.
- **어택 CV**: 진짜 연습 영상이 **1.096으로 가장 낮다.** 문서에는 "두 연주가
  겹치면 상승시간이 크게 흔들린다"고 적혀 있었는데 **실제는 정반대**다.
  게다가 임계 0.45를 네 곡 모두 넘는다.
- **보컬 활동**: 애초에 참고값으로만 두었고 실제로도 안 갈린다.

그 결과 **공식 스튜디오 음원 세 곡을 전부 "베이스가 둘 섞인 연습 영상"으로
판정**했다. 그러면 하향 단계를 막고 사용자에게 틀린 경고를 띄운다.

## 그래서 무엇을 하는가 — 원인 대신 관측을 보고한다

우리는 "베이스가 둘인가"를 **알 수 없다.** 알 수 있는 것은 "리듬 검출이
얼마나 격자에 얹혔는가"뿐이다. 그 둘은 다른 질문이고, 낮은 정렬의 원인은
최소 두 가지다.

1. 베이스가 둘 섞였다
2. **우리 검출이 나쁘다** (16비트 곡·배음이 강한 녹음)

원인을 특정할 수 없으므로 **관측만 말한다**: "리듬 검출 신뢰도가 낮습니다."
그것이 정직하고, 사용자가 취할 행동(원곡 음원을 넣어 본다)도 같다.

`practice_video`는 **항상 False**로 남겨두었다. 필드를 지우지 않은 이유는
구버전 manifest를 읽는 쪽이 있고, 나중에 진짜 신호를 찾으면 되살릴 자리이기
때문이다. 되살리려면 **위 표를 다시 만들어 갈리는지 확인해야 한다.**

## 하향 단계는 여전히 제한한다 — 근거만 바꿨다

리듬 검출을 믿을 수 없으면 하향이 해롭다. 하향은 검출된 음 수로 밀도를 정하는데
그 밀도가 실제 연주와 무관하기 때문이다. 그 판단은 유효하므로 남긴다.
다만 근거를 "연습 영상이라서"가 아니라 **"리듬 신뢰도가 낮아서"**로 바꾼다.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass, field
from pathlib import Path

SR = 22050

# 리듬 검출을 믿을 수 있다고 볼 격자 정렬률.
#
# `bassclean.GATE_TARGET_GRID_RATIO`와 같은 값이다 — 같은 질문("온셋이 격자에
# 얹혔는가")이기 때문이다. 두 값이 갈리면 "게이트는 목표에 닿았다는데 진단은
# 아니라고 한다"는 모순이 생긴다.
#
# **이것은 "베이스가 둘인가"를 묻지 않는다.** 그 판정은 버렸다(머리말 참조).
TRUSTED_GRID_RATIO = 0.95

# 어택 상승시간 변동계수. **판정에 쓰지 않는다.**
#
# 원래 "두 연주가 겹치면 상승시간이 흔들린다"는 근거로 보조 신호로 썼는데,
# 골든셋에서 진짜 연습 영상이 가장 **낮게**(1.096) 나왔다 — 방향이 반대다.
# 값은 계속 재서 manifest에 남긴다. 나중에 다른 용도로 쓸 수 있고, 무엇보다
# **이 신호가 안 갈린다는 사실 자체가 기록**이다.
ATTACK_CV_UNUSED_THRESHOLD = 0.45

# 상승시간을 잴 온셋 수 하한. 이보다 적으면 통계가 성립하지 않는다.
MIN_ONSETS_FOR_ATTACK = 12

# 어택 상승 구간을 볼 창(초). 이보다 길면 다음 음이 섞인다.
ATTACK_WINDOW_SEC = 0.15


@dataclass
class InputDiagnosis:
    """입력 종류 판정. 하향 단계를 제공할지 결정한다."""

    # **항상 False다.** 연습 영상 판정을 버렸다(머리말 참조). 필드를 남긴 것은
    # 구버전 manifest 호환과, 진짜 신호를 찾았을 때 되살릴 자리를 두기 위해서다.
    practice_video: bool
    # 리듬 검출을 믿을 수 있는가. 하향 단계 제공 여부가 여기 달린다.
    rhythm_confident: bool
    grid_ratio: float
    attack_cv: float
    vocal_activity: float
    reason: str
    signals: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "practiceVideo": self.practice_video,
            "rhythmConfident": self.rhythm_confident,
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
    """리듬 검출을 믿을 수 있는지 판정한다.

    grid_ratio는 **음량 게이트를 건 뒤**의 값이어야 한다. 게이트 전 값으로
    판정하면 게이트가 해결한 곡까지 낮게 나온다.

    **"베이스가 둘인가"는 판정하지 않는다.** 그 신호를 찾지 못했다(머리말 표).
    """
    attack_cv = attack_rise_variation(onsets, bass_stem)
    vocal = vocal_activity_ratio(vocals_stem) if vocals_stem else 0.0

    rhythm_confident = grid_ratio >= TRUSTED_GRID_RATIO

    signals: list[str] = []
    if not rhythm_confident:
        signals.append(f"온셋의 격자 정렬률 {100 * grid_ratio:.0f}%")
    if gate_applied:
        signals.append("음량 게이트 발동(약한 음을 버려 격자에 수렴시킴)")

    if rhythm_confident:
        reason = "리듬 검출을 믿을 수 있는 입력입니다."
    else:
        # **원인을 단정하지 않는다.** 정렬이 낮은 이유가 최소 두 가지이고
        # (베이스가 둘 / 우리 검출이 나쁨) 우리는 그것을 가르지 못한다.
        # 공식 스튜디오 음원을 "베이스가 둘 섞였다"고 단정했던 것이 그 실수다.
        reason = (
            f"리듬 검출 신뢰도가 낮습니다 (타점의 {100 * grid_ratio:.0f}%만 "
            "격자에 얹혔습니다). 원인은 두 가지일 수 있습니다 — "
            "베이스가 둘 섞인 음원(원곡 반주 위에 연주한 커버 영상)이거나, "
            "16비트·슬랩처럼 우리 검출이 약한 연주입니다. "
            "음정은 참고할 수 있지만 리듬은 원곡을 들어 확인하세요. "
            "난이도 조절은 검출된 음 수를 근거로 삼으므로 제공하지 않습니다."
        )

    result = InputDiagnosis(
        # 연습 영상 판정은 버렸다. 신호를 찾으면 여기를 되살린다.
        practice_video=False,
        rhythm_confident=rhythm_confident,
        grid_ratio=grid_ratio,
        attack_cv=attack_cv,
        vocal_activity=vocal,
        reason=reason,
        signals=signals,
    )
    if verbose:
        print(
            f"[diagnose] 리듬 {'신뢰' if rhythm_confident else '불신'} — "
            f"격자정렬 {100 * grid_ratio:.1f}%, 어택 편차 {attack_cv:.2f}(미사용), "
            f"보컬 활동 {100 * vocal:.1f}%(참고)"
        )
    return result
