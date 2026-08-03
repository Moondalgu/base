"""비트·다운비트 추적 — beat_this (ISMIR 2024).

중요: 베이스 스템이 아니라 **원본 믹스**에 돌린다. 드럼이 있어야 비트가 잡힌다.
여기서 나온 그리드가 이후 양자화의 기준이 되므로 파이프라인에서 가장
민감한 단계다. 비트가 틀리면 악보 전체가 틀린다.
"""

from __future__ import annotations

import json
import statistics
import time
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass
class BeatGrid:
    beats: list[float]          # 모든 비트의 타임스탬프(초)
    downbeats: list[float]      # 마디 시작 타임스탬프(초)
    beats_per_bar: int          # 4/4면 4
    median_bpm: float
    bpm_variance: float         # 비트 간격의 변동계수. 클수록 루바토/불안정

    def to_json(self, path: Path) -> None:
        path.write_text(json.dumps(asdict(self), ensure_ascii=False), encoding="utf-8")

    @classmethod
    def from_json(cls, path: Path) -> "BeatGrid":
        return cls(**json.loads(path.read_text(encoding="utf-8")))


def track_beats(wav_path: Path, outdir: Path, device: str = "cpu") -> BeatGrid:
    """원본 믹스에서 비트/다운비트를 뽑고 beats.json에 캐시한다."""
    cache = outdir / "beats.json"
    if cache.exists():
        return BeatGrid.from_json(cache)

    from beat_this.inference import File2Beats

    start = time.monotonic()
    file2beats = File2Beats(checkpoint_path="final0", device=device)
    beats, downbeats = file2beats(str(wav_path))
    elapsed = time.monotonic() - start

    beats = [float(b) for b in beats]
    downbeats = [float(b) for b in downbeats]

    grid = BeatGrid(
        beats=beats,
        downbeats=downbeats,
        beats_per_bar=_infer_beats_per_bar(beats, downbeats),
        median_bpm=_median_bpm(beats),
        bpm_variance=_interval_variation(beats),
    )
    grid.to_json(cache)
    print(
        f"[beats] {elapsed:.1f}s: {len(beats)} beats, {len(downbeats)} bars, "
        f"{grid.median_bpm:.1f} BPM, {grid.beats_per_bar}/4, var={grid.bpm_variance:.3f}"
    )
    return grid


def _infer_beats_per_bar(beats: list[float], downbeats: list[float]) -> int:
    """다운비트 사이에 낀 비트 수로 박자표를 추론한다.

    최빈값이 아니라 중앙값을 쓴다. 최빈값은 다운비트가 한두 군데 튀면
    엉뚱한 값으로 끌려가는데, 이 값이 마디 길이를 결정하므로 틀리면
    악보 전체가 틀린다.

    2박으로 나오는 경우가 흔한데(킥이 1·3박에만 있는 패턴), 실제로는
    4/4의 절반으로 잡은 것이다. 2는 4로 승격한다.
    """
    if len(downbeats) < 2:
        return 4
    counts = [
        sum(1 for b in beats if start <= b < end)
        for start, end in zip(downbeats, downbeats[1:])
    ]
    counts = [c for c in counts if c > 0]
    if not counts:
        return 4

    value = round(statistics.median(counts))
    if value == 2:
        # 2박 마디는 거의 항상 4/4를 반으로 쪼갠 결과다
        value = 4
    elif value == 1:
        value = 4
    return value if value in (3, 4, 5, 6, 7) else 4


def _median_bpm(beats: list[float]) -> float:
    intervals = _intervals(beats)
    if not intervals:
        return 0.0
    return 60.0 / statistics.median(intervals)


def _interval_variation(beats: list[float]) -> float:
    """비트 간격의 변동계수(표준편차/평균). 품질 게이트의 '비트 안정성' 입력."""
    intervals = _intervals(beats)
    if len(intervals) < 2:
        return 1.0
    mean = statistics.fmean(intervals)
    if mean == 0:
        return 1.0
    return statistics.pstdev(intervals) / mean


def _intervals(beats: list[float]) -> list[float]:
    return [b - a for a, b in zip(beats, beats[1:]) if b > a]
