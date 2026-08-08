"""비트·다운비트 추적 — beat_this (ISMIR 2024).

중요: 베이스 스템이 아니라 **원본 믹스**에 돌린다. 드럼이 있어야 비트가 잡힌다.
여기서 나온 그리드가 이후 양자화의 기준이 되므로 파이프라인에서 가장
민감한 단계다. 비트가 틀리면 악보 전체가 틀린다.

검출된 비트는 개별 위치가 흔들린다. 양자화는 비트 사이를 등분해 슬롯을
만들기 때문에, 비트 하나가 밀리면 그 구간의 음이 전부 함께 밀린다.
실측하면 같은 곡 안에서 마디 길이가 1.86~4.02초까지 벌어진다(중앙값 3.20).
반면 **템포 자체는 정확하다** — 최적 템포를 다시 탐색해도 검출 중앙값과 같은
값이 나오고 위상 보정량도 0.06초 수준이다.

그래서 검출 비트를 그대로 쓰지 않고, 같은 템포의 **균일 격자**를 다시
피팅해 마디 시작이 실제 연주 온셋에 걸리는지 비교한다. 더 잘 맞으면 격자를
교체한다. 위상 판단은 드럼이 아니라 **베이스 스템**으로 한다 — 베이시스트가
마디 첫 박에 루트를 짚는 습성이 마디 시작의 가장 강한 단서다.
"""

from __future__ import annotations

import json
import math
import statistics
import time
from dataclasses import asdict, dataclass, replace
from pathlib import Path

# 위상 피팅용 분석 파라미터. 온셋 강도만 보면 되므로 낮은 SR로 충분하다.
SR = 22050
# librosa 계열 온셋 분석의 통상 홉. sr=22050에서 11.6ms.
HOP = 256

# 엔벨로프가 이 값을 넘는 구간만 "연주 중"으로 본다. 무연주 인트로/아웃트로를
# 점수와 정렬 오차 계산에서 빼기 위한 기준이다.
ACTIVITY_LEVEL = 0.08

# 강한 온셋 추출 기준(peak_pick의 delta). 마디 시작에 걸릴 만한 또렷한
# 어택만 남긴다.
ONSET_DELTA = 0.15

# 템포 탐색 범위 — 검출 중앙 BPM 기준 ±7%. 문제는 템포가 아니라 격자
# 불균일성이므로 넓게 훑을 이유가 없다.
BPM_SEARCH_RANGE = 0.07
# 탐색 해상도. 더 줄여도 결과가 바뀌지 않는다(추측·무해).
BPM_SEARCH_STEP = 0.05
# 10ms 해상도. 사람의 리듬 인지 임계 안에 있다(추측·무해).
PHASE_SEARCH_STEP = 0.01

# 이보다 적은 마디로는 격자 품질을 판단할 수 없다.
MIN_FIT_BARS = 8


@dataclass
class BeatGrid:
    beats: list[float]          # 모든 비트의 타임스탬프(초)
    downbeats: list[float]      # 마디 시작 타임스탬프(초)
    beats_per_bar: int          # 4/4면 4
    median_bpm: float
    bpm_variance: float         # 비트 간격의 변동계수. 클수록 루바토/불안정
    # --- 균일 격자 피팅 결과 ---
    # 기존 beats.json에도 그대로 로드돼야 하므로 전부 기본값을 준다
    # (from_json이 cls(**json)이다).
    uniform: bool = False              # beats/downbeats가 균일 격자로 교체됐는지
    fitted_bpm: float | None = None    # 탐색으로 찾은 템포. 채택 여부와 무관하게 기록
    fitted_phase: float | None = None  # 앵커(연주 시작 시각) 기준 위상(초)
    align_before: float | None = None  # 검출 격자의 정렬 오차(마디 시작→최근접 온셋 평균, 초)
    align_after: float | None = None   # 균일 격자의 정렬 오차(초)

    def to_json(self, path: Path) -> None:
        path.write_text(json.dumps(asdict(self), ensure_ascii=False), encoding="utf-8")

    @classmethod
    def from_json(cls, path: Path) -> "BeatGrid":
        return cls(**json.loads(path.read_text(encoding="utf-8")))


def track_beats(
    wav_path: Path,
    outdir: Path,
    device: str = "cpu",
    *,
    phase_source: Path | None = None,
) -> BeatGrid:
    """원본 믹스에서 비트/다운비트를 뽑고 beats.json에 캐시한다.

    phase_source를 주면 그 오디오(보통 베이스 스템)로 균일 격자를 피팅해,
    검출 격자보다 마디 시작이 잘 맞을 때 격자를 교체한다. 없거나 파일이
    없으면 검출 결과를 그대로 쓴다.
    """
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
    print(
        f"[beats] {elapsed:.1f}s: {len(beats)} beats, {len(downbeats)} bars, "
        f"{grid.median_bpm:.1f} BPM, {grid.beats_per_bar}/4, var={grid.bpm_variance:.3f}"
    )

    if phase_source is not None:
        source = Path(phase_source)
        if source.exists():
            grid = fit_uniform_grid(grid, source, verbose=True)

    grid.to_json(cache)
    return grid


def fit_uniform_grid(grid: BeatGrid, phase_source: Path, *, verbose: bool = False) -> BeatGrid:
    """단일 템포 + 위상으로 균일 격자를 피팅해 더 잘 맞으면 교체한다.

    반환값은 항상 유효한 BeatGrid다. 피팅이 불가능하거나(연주 구간이 너무
    짧다, 온셋이 없다) 검출 격자보다 못하면 원본을 그대로 돌려준다.
    """
    def skip(reason: str) -> BeatGrid:
        if verbose:
            print(f"[beats] 균일 격자 피팅 건너뜀: {reason}")
        return grid

    if len(grid.beats) < 2 or not grid.downbeats or grid.median_bpm <= 0:
        return skip("검출 격자가 부족함")

    try:
        import librosa
        import numpy as np
    except ImportError:
        return skip("librosa/numpy 없음")

    y, sr = librosa.load(str(phase_source), sr=SR, mono=True)
    if y.size == 0:
        return skip(f"{phase_source.name}이 비어 있음")

    env = librosa.onset.onset_strength(y=y, sr=sr, hop_length=HOP)
    peak = float(env.max()) if env.size else 0.0
    if peak <= 0:
        return skip(f"{phase_source.name}에 온셋이 없음")
    env = env / peak
    frame_sec = HOP / sr

    # 연주 구간. 이 밖에서는 마디 시작에 걸릴 온셋이 애초에 없으므로
    # 점수를 계산하면 좋은 격자가 오히려 손해를 본다.
    active = np.flatnonzero(env > ACTIVITY_LEVEL)
    if active.size == 0:
        return skip("연주 구간을 찾지 못함")
    act_start = float(active[0]) * frame_sec
    act_end = float(active[-1]) * frame_sec

    bpb = grid.beats_per_bar
    median_bar = bpb * 60.0 / grid.median_bpm
    if act_end - act_start < MIN_FIT_BARS * median_bar:
        return skip(
            f"연주 구간 {act_end - act_start:.1f}s가 {MIN_FIT_BARS}마디"
            f"({MIN_FIT_BARS * median_bar:.1f}s)보다 짧음"
        )

    onsets = _strong_onsets(librosa, np, env, frame_sec, act_start, act_end)
    if onsets.size == 0:
        return skip("강한 온셋이 없음")

    # 위상의 기준점은 연주가 시작되는 시각이다. 검출 다운비트를 기준으로 삼으면
    # 그 다운비트가 이미 밀려 있을 때 위상 값이 그만큼 왜곡돼 읽힌다.
    anchor = act_start
    fit = _search_tempo_phase(np, env, frame_sec, anchor, act_start, act_end, bpb, grid.median_bpm)
    if fit is None:
        return skip("템포/위상 후보를 찾지 못함")
    bpm, phase = fit

    bar_len = bpb * 60.0 / bpm
    fitted_starts = _bar_starts(np, anchor + phase, bar_len, act_start, act_end)
    detected_starts = _detected_bar_starts(np, grid, act_start, act_end)
    if detected_starts.size == 0 or fitted_starts.size < MIN_FIT_BARS:
        return skip("비교할 마디가 부족함")

    align_before = _mean_onset_distance(np, detected_starts, onsets)
    align_after = _mean_onset_distance(np, fitted_starts, onsets)

    measured = replace(
        grid,
        fitted_bpm=round(bpm, 2),
        fitted_phase=round(phase, 3),
        align_before=round(align_before, 4),
        align_after=round(align_after, 4),
    )

    if align_after >= align_before:
        # 검출 격자가 이미 더 잘 맞는다. 균일 격자를 강요하면 오히려 밀린다.
        if verbose:
            print(
                f"[beats] 균일 격자 미채택: 검출 격자가 더 잘 맞음 "
                f"(정렬오차 {align_before:.3f}s vs {align_after:.3f}s)"
            )
        return measured

    beats, downbeats = _uniform_beats(anchor + phase, bpm, bpb, grid.beats[-1])
    if len(beats) < bpb + 1 or len(downbeats) < 2:
        return measured

    uniform = replace(
        measured,
        beats=beats,
        downbeats=downbeats,
        # 저장되는 비트열이 이 템포로 만들어졌으므로 median_bpm도 같이 맞춘다.
        # (alphatex의 \tempo, quantize의 마디 길이 폴백이 이 값을 쓴다)
        median_bpm=round(bpm, 2),
        # bpm_variance는 **검출 비트로 계산한 값을 그대로 유지한다.** 균일
        # 격자의 간격 변동은 정의상 0이지만, 그 0을 여기에 쓰면 두 곳이 깨진다.
        #  - quality.beatStability가 이 값을 읽는다 → "비트가 완벽했다"는
        #    거짓 보고가 된다. 실제로 흔들린 건 사실이고, 우리가 덮은 것이다.
        #  - quantize.SWING_MAX_BPM_VARIANCE 게이트가 이 값을 읽는다 → 0이면
        #    게이트가 열려 스트레이트 곡을 셋잇단으로 적기 시작한다.
        bpm_variance=grid.bpm_variance,
        uniform=True,
    )
    if verbose:
        print(
            f"[beats] 균일 격자 채택: {bpm:.2f} BPM, 위상 {phase:+.3f}s "
            f"(정렬오차 {align_before:.3f}s → {align_after:.3f}s)"
        )
    return uniform


def _strong_onsets(librosa, np, env, frame_sec: float, act_start: float, act_end: float):
    """또렷한 어택의 시각 목록. 격자 정렬을 평가할 기준점이다."""
    frames = librosa.util.peak_pick(
        env, pre_max=4, post_max=4, pre_avg=8, post_avg=8, delta=ONSET_DELTA, wait=6
    )
    times = np.asarray(frames, dtype=float) * frame_sec
    return times[(times >= act_start) & (times <= act_end)]


def _search_tempo_phase(
    np,
    env,
    frame_sec: float,
    anchor: float,
    act_start: float,
    act_end: float,
    bpb: int,
    median_bpm: float,
) -> tuple[float, float] | None:
    """(BPM, 위상) 격자 탐색. 점수는 마디 시작 시각의 온셋 강도 평균이다.

    "마디 시작이 진짜 마디 시작이면 그 순간 소리가 크다"를 그대로 점수화한
    것이다. 온셋 목록과의 거리로 점수를 매기면 온셋이 촘촘한 구간에 끌려가서
    엉뚱한 템포가 이긴다.
    """
    lo = median_bpm * (1.0 - BPM_SEARCH_RANGE)
    hi = median_bpm * (1.0 + BPM_SEARCH_RANGE)
    candidates = np.arange(lo, hi + BPM_SEARCH_STEP / 2, BPM_SEARCH_STEP)

    best_score = -1.0
    best: tuple[float, float] | None = None

    for bpm in candidates:
        bar_len = bpb * 60.0 / float(bpm)
        phases = np.arange(0.0, bar_len, PHASE_SEARCH_STEP)
        if phases.size == 0:
            continue
        k_lo = math.floor((act_start - anchor - bar_len) / bar_len)
        k_hi = math.ceil((act_end - anchor) / bar_len)
        ks = np.arange(k_lo, k_hi + 1)
        starts = anchor + phases[:, None] + bar_len * ks[None, :]

        inside = (starts >= act_start) & (starts <= act_end)
        counts = inside.sum(axis=1)
        frames = np.clip((starts / frame_sec).astype(np.int64), 0, env.size - 1)
        totals = (env[frames] * inside).sum(axis=1)
        scores = np.where(counts >= MIN_FIT_BARS, totals / np.maximum(counts, 1), -1.0)

        idx = int(scores.argmax())
        if scores[idx] > best_score:
            best_score = float(scores[idx])
            best = (float(bpm), float(phases[idx]))

    return best


def _detected_bar_starts(np, grid: BeatGrid, act_start: float, act_end: float):
    """검출 격자가 실제로 만들어내는 마디 시작 시각들.

    downbeats를 그대로 쓰지 않는다. 양자화는 다운비트를 마디 경계로 쓰지 않고
    **비트 배열을 beats_per_bar개씩 묶는다**(quantize._bar_beat_spans). 실측하면
    검출 다운비트는 간격이 0.82~3.52초로 튀어서 마디 경계로 성립하지 않는다.
    다운비트 하나하나는 온셋에 잘 걸리기 때문에, 그것으로 정렬 오차를 재면
    "잘 맞는다"는 착시가 생기고 격자 교체 판단이 뒤집힌다. 그래서 비교 기준도
    양자화가 쓰는 방식과 같게 맞춘다.

    위상은 첫 다운비트에 가장 가까운 비트의 인덱스에서 가져온다
    (quantize.choose_phase의 기본값과 같은 규칙).
    """
    beats = grid.beats
    bpb = grid.beats_per_bar
    phase = min(range(len(beats)), key=lambda i: abs(beats[i] - grid.downbeats[0])) % bpb
    starts = [b for b in beats[phase::bpb] if act_start <= b <= act_end]
    return np.asarray(starts, dtype=float)


def _bar_starts(np, first_start: float, bar_len: float, act_start: float, act_end: float):
    """연주 구간을 덮는 균일 마디 시작 시각들."""
    k_lo = math.ceil((act_start - first_start) / bar_len)
    k_hi = math.floor((act_end - first_start) / bar_len)
    if k_hi < k_lo:
        return np.asarray([], dtype=float)
    return first_start + bar_len * np.arange(k_lo, k_hi + 1)


def _mean_onset_distance(np, bar_starts, onsets) -> float:
    """마디 시작마다 가장 가까운 강한 온셋까지의 거리, 그 평균."""
    pos = np.searchsorted(onsets, bar_starts)
    left = np.clip(pos - 1, 0, onsets.size - 1)
    right = np.clip(pos, 0, onsets.size - 1)
    dist = np.minimum(
        np.abs(bar_starts - onsets[left]),
        np.abs(bar_starts - onsets[right]),
    )
    return float(dist.mean())


def _uniform_beats(
    first_start: float, bpm: float, bpb: int, last_beat: float
) -> tuple[list[float], list[float]]:
    """곡 전체를 덮는 균일 비트열과 그 다운비트.

    앞쪽으로 물릴 때는 **마디 길이 단위로** 물린다. 비트 하나 단위로 물리면
    첫 비트가 마디 중간이 되어 피팅한 위상이 그만큼 어긋난다.
    """
    beat_len = 60.0 / bpm
    bar_len = beat_len * bpb
    start = first_start - bar_len * math.floor(first_start / bar_len)
    count = math.floor((last_beat - start) / beat_len) if last_beat > start else 0
    beats = [round(start + i * beat_len, 6) for i in range(count + 1)]
    beats = [b for b in beats if b >= 0]
    return beats, beats[::bpb]


def _infer_beats_per_bar(beats: list[float], downbeats: list[float]) -> int:
    """다운비트 사이에 낀 비트 수로 박자표를 추론한다.

    **정규화를 집계보다 먼저 한다.** beat_this는 같은 곡 안에서 다운비트를
    마디마다 찍다가 반 마디마다 찍다가 하며 섞는다 — 실측(Virtual Insanity,
    4/4 펑크): 다운비트 간 비트 수가 {4: 52, 2: 51, 3: 9}로 쌍봉이었다.
    이 상태에서 중앙값을 내면 두 봉우리 사이의 소수값 3에 떨어져
    **박자표가 3/4로 오검출되고 전 마디 귀속이 깨진다.**

    2박 구간은 거의 항상 4/4의 반 마디(킥 1·3박 패턴)이고, 1박 구간은
    인접 비트 사이에 다운비트가 중복 검출된 노이즈다. 그래서 2는 4로
    승격하고 1은 버린 **뒤에** 중앙값을 낸다. 진짜 3/4 곡은 3이 지배해
    중앙값이 그대로 3이 된다.

    중앙값을 유지하는 이유(최빈값 아님): 다운비트가 한두 군데 튀어도
    끌려가지 않는다. 이 값이 마디 길이를 결정하므로 틀리면 악보 전체가
    틀린다.
    """
    if len(downbeats) < 2:
        return 4
    counts = [
        sum(1 for b in beats if start <= b < end)
        for start, end in zip(downbeats, downbeats[1:])
    ]
    normalized = []
    for c in counts:
        if c <= 1:
            continue  # 0 = 빈 구간, 1 = 중복 다운비트 노이즈
        if c == 2:
            c = 4     # 반 마디 다운비트 → 4/4로 승격
        normalized.append(c)
    if not normalized:
        return 4

    value = round(statistics.median(normalized))
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
