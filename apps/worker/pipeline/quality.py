"""품질 게이트 (PRD 4.7).

자동 채보 결과가 쓰레기일 때 그대로 보여주면 신뢰가 무너진다.
5개 구성요소를 0~1로 정규화해 가중 합산한 뒤 3단계로 나눈다.

중요: 점수가 낮아도 스템 플레이어는 그대로 동작한다. 악보만 숨긴다.
채보가 실패해도 배속·부스트·솔로는 전부 살아있으므로 제품이 0이 되지 않는다.
"""

from __future__ import annotations

import statistics
from dataclasses import asdict, dataclass

from .bassclean import CleanReport, Note
from .beats import BeatGrid
from .fretting import FrettedScore
from .quantize import QuantizedScore

GOOD_THRESHOLD = 70
REFERENCE_THRESHOLD = 40

# 가중치 합 = 1.0
WEIGHTS = {
    "transcriptionConfidence": 0.30,
    "beatStability": 0.25,
    "quantizationResidual": 0.20,
    "densityConsistency": 0.15,
    "rangeIntegrity": 0.10,
}


@dataclass
class QualityReport:
    score: int
    level: str  # good | reference | failed
    components: dict[str, float]
    reason: str

    def to_dict(self) -> dict:
        return asdict(self)


def evaluate(
    notes: list[Note],
    clean_report: CleanReport,
    grid: BeatGrid,
    qscore: QuantizedScore,
    fscore: FrettedScore,
) -> QualityReport:
    """5개 구성요소를 각각 0~1로 만들고 가중 합산한다."""

    # 1) 채보 신뢰도 — basic-pitch amplitude 평균
    confidence = statistics.fmean(n.amplitude for n in notes) if notes else 0.0

    # 2) 비트 안정성 — 비트 간격 변동계수가 작을수록 좋다.
    #    0.10을 넘으면 루바토/템포 흔들림으로 보고 0점 쪽으로 보낸다.
    beat_stability = max(0.0, 1.0 - grid.bpm_variance / 0.10)

    # 3) 양자화 잔차 — 그리드에서 얼마나 벗어났나. 0.5면 완전히 어긋난 것.
    residual_score = max(0.0, 1.0 - qscore.mean_residual / 0.5)

    # 4) 밀도 일관성 — 마디당 음표 수가 들쭉날쭉하면 검출이 불안정하다는 뜻
    density_score = _density_consistency(fscore)

    # 5) 음역 무결성 — 음역 밖으로 버려진 비율이 높으면 베이스가 아닐 수 있다
    range_score = max(0.0, 1.0 - clean_report.out_of_range_ratio * 4)

    components = {
        "transcriptionConfidence": round(confidence, 4),
        "beatStability": round(beat_stability, 4),
        "quantizationResidual": round(residual_score, 4),
        "densityConsistency": round(density_score, 4),
        "rangeIntegrity": round(range_score, 4),
    }

    total = sum(components[k] * w for k, w in WEIGHTS.items())
    score = int(round(total * 100))

    note_count = sum(len(b.notes) for b in fscore.bars)
    if note_count == 0:
        return QualityReport(
            score=0,
            level="failed",
            components=components,
            reason="베이스 음을 하나도 찾지 못했어요.",
        )

    if score >= GOOD_THRESHOLD:
        level, reason = "good", ""
    elif score >= REFERENCE_THRESHOLD:
        level, reason = "reference", _weakest_reason(components)
    else:
        level, reason = "failed", _weakest_reason(components)

    return QualityReport(score=score, level=level, components=components, reason=reason)


def _density_consistency(fscore: FrettedScore) -> float:
    counts = [len(bar.notes) for bar in fscore.bars]
    counts = [c for c in counts if c > 0]
    if len(counts) < 3:
        return 0.5
    mean = statistics.fmean(counts)
    if mean == 0:
        return 0.0
    cv = statistics.pstdev(counts) / mean
    # 변동계수 0.8 이상이면 마디마다 밀도가 널뛴다는 뜻
    return max(0.0, 1.0 - cv / 0.8)


def _weakest_reason(components: dict[str, float]) -> str:
    """가장 약한 구성요소를 사람 말로 옮긴다 (QLT-03)."""
    messages = {
        "transcriptionConfidence": "베이스가 다른 악기에 묻혀서 음을 또렷하게 잡지 못했어요.",
        "beatStability": "박자가 일정하지 않아 마디를 정확히 나누지 못했어요.",
        "quantizationResidual": "연주가 박자에서 많이 벗어나 있어 리듬을 정리하기 어려웠어요.",
        "densityConsistency": "구간마다 음표 수가 크게 달라 검출이 불안정했어요.",
        "rangeIntegrity": "베이스 음역을 벗어난 소리가 많아요. 베이스가 아닐 수 있어요.",
    }
    weakest = min(components, key=lambda k: components[k])
    return messages.get(weakest, "")
