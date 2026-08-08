"""비트 그리드 양자화.

basic-pitch는 초 단위 온셋을 낸다. beat_this의 비트/다운비트로 만든 그리드에
스냅하지 않으면 사람이 읽을 수 있는 리듬이 나오지 않는다.

핵심 결정: 마디는 다운비트로 정의하고, 그리드는 비트 사이를 선형 보간해 만든다.
비트가 불균등해도(실연주 템포 흔들림) 그리드가 따라간다.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass, field

from .bassclean import Note
from .beats import BeatGrid

# 격자 자동 선택(choose_subdivision)이 실패할 때만 쓰는 **폴백**이다.
# 16분은 대중음악의 통상 최소 단위다.
DEFAULT_SUBDIVISION = 4      # 비트당 슬롯 수. 4 = 16분음표 그리드. 판정 불가일 때의 값
# 스윙은 8분 셋잇단 구조다.
SWING_SUBDIVISION = 3        # 스윙이면 3등분(셋잇단)

# 스트레이트 곡의 격자는 고정하지 않고 온셋을 보고 고른다. 16분에 고정하면
# 8분음표 위의 미세한 흔들림이 옆 16분 슬롯에 얹혀 악보가 두 배로 촘촘해지고,
# 8분에 고정하면 진짜 16분을 쓰는 곡의 리듬이 뭉개진다.
#
# 임계값 근거 — IDMT 정답 17곡(정답 악보 + 정답 비트)에서 두 군이 겹치지 않는다.
#   정답 악보에 16분음표가 없는 8곡: 이 비율이 0.0~2.4%
#   16분음표를 쓰는 9곡:            9.1~40.0%
# 5%를 두면 17곡을 정확히 가른다. eval/eval_grid_resolution.py로 재현할 수 있다.
SIXTEENTH_REQUIRED_RATIO = 0.05

# 온셋이 8분 자리(0, 0.5박)에 얹혔다고 인정하는 여유. 16분 간격의 절반이다 —
# 이보다 가까우면 8분 위의 연주 흔들림과 구분되지 않는다.
EIGHTH_TOLERANCE = 0.125

# 격자를 판정하려면 최소 이만큼의 온셋이 필요하다. 이보다 적으면 통계가
# 성립하지 않으므로 DEFAULT_SUBDIVISION을 쓴다(잘게 적는 쪽이 안전하다).
MIN_NOTES_FOR_GRID_CHOICE = 12
# 격자 간격의 절반보다 멀면 그 격자 자리가 아니다 — 퀀타이즈의 논리적 기준.
SNAP_REJECT_RATIO = 0.5      # 그리드 간격의 이 비율을 넘게 벗어나면 저신뢰
# 양자화된 음은 최소 한 슬롯을 차지한다.
MIN_DURATION_SLOTS = 1
# 한 음이 차지할 수 있는 최대 마디 수. 마디 경계에서 자르지 않으므로 상한이 필요하다.
# 곡 끝의 여운이나 피치 검출 실패로 note.end가 크게 뒤로 밀리면 한 음의
# duration_slots가 수십 마디로 늘어나고, alphatex가 그 구간을 전부 타이로 덮어
# 뒤에 오는 음들이 악보에서 통째로 사라진다. 4마디는 온음표 네 개 분량으로,
# 실제 베이스 라인에서 이보다 긴 한 음은 사실상 없다.
MAX_DURATION_BARS = 4
# 스윙은 비트 그리드가 안정할 때만 추론할 수 있다. 비트 간격이 흔들리면
# "온셋이 박 안에서 어디에 있는지"라는 통계 자체가 신뢰할 수 없어져,
# 스트레이트 곡을 셋잇단으로 적어버린다.
SWING_MAX_BPM_VARIANCE = 0.05


@dataclass
class QuantizedNote:
    slot: int                # 마디 내 슬롯 인덱스 (0부터)
    duration_slots: int
    pitch: int
    amplitude: float         # CREPE 확신도. 음량이 아니다
    residual: float          # |원래온셋 - 스냅위치| / 그리드간격
    low_confidence: bool
    # 실제 음량(RMS). 하향에서 "이 마디에서 가장 센 엇박"을 찾을 때 쓴다 —
    # 확신도로는 셈이 되지 않는다(둘의 상관계수가 -0.20이다).
    loudness: float = 0.0


@dataclass
class Bar:
    index: int
    start_sec: float
    end_sec: float
    bpm: float
    beats_per_bar: int
    slots_per_bar: int
    notes: list[QuantizedNote] = field(default_factory=list)


@dataclass
class QuantizedScore:
    bars: list[Bar]
    subdivision: int
    beats_per_bar: int
    median_bpm: float
    mean_residual: float
    swing: bool
    dropped_pickup: int      # 첫 다운비트 앞에 있어서 버린 음
    note_count: int
    # 마디 시작 위상(비트 인덱스 mod beats_per_bar). manifest에 반드시 남긴다 —
    # 이 값 없이는 산출물에서 마디 시각을 재구성할 수 없어 평가가 틀어진다.
    phase: int = 0
    phase_corrected: bool = False
    # 16분 격자를 요구한 온셋의 비율. 격자를 왜 그렇게 골랐는지 남기는 값이다.
    # 이 값 없이 subdivision만 보면 판정 근거를 되짚을 수 없다.
    sixteenth_ratio: float = 0.0


def quantize(
    notes: list[Note],
    grid: BeatGrid,
    *,
    verbose: bool = False,
    force_subdivision: int | None = None,
    force_phase: int | None = None,
) -> QuantizedScore:
    """정리된 노트를 마디/슬롯 좌표로 옮긴다.

    force_subdivision을 주면 스윙 감지를 무시하고 그 값을 쓴다.
    셋잇단 표기가 안 되는 상황의 폴백용이다.

    force_phase는 **다른 트랙과 마디를 맞출 때** 쓴다. choose_phase는 "곡의
    첫 음은 마디 1박"이라는 베이스 전제로 위상을 고르는데, 보컬처럼 위빗에서
    시작하는 성부에 그대로 쓰면 트랙마다 마디 경계가 달라진다. 3단 악보는
    베이스 트랙의 위상을 여기로 넘겨 한 격자를 공유한다.
    """
    if len(grid.downbeats) < 2 or len(grid.beats) < 2:
        raise ValueError("비트 그리드가 부족합니다. 비트 추적 결과를 확인하세요.")

    swing = _detect_swing(notes, grid)
    sixteenth_ratio = 0.0
    if force_subdivision is not None:
        subdivision = force_subdivision
    elif swing:
        # 셋잇단 격자에는 8분/16분 구분이 없다. 스윙 판정이 먼저다.
        subdivision = SWING_SUBDIVISION
    else:
        subdivision, sixteenth_ratio = choose_subdivision(notes, grid)
    beats_per_bar = grid.beats_per_bar
    slots_per_bar = beats_per_bar * subdivision

    if force_phase is not None:
        phase, phase_corrected = force_phase, False
    else:
        phase, phase_corrected = choose_phase(notes, grid)
    bars = _build_bars(grid, phase, subdivision, slots_per_bar)
    grid_times, grid_coords = _build_grid(bars, grid, phase, subdivision, slots_per_bar)
    spacing = _median_spacing(grid_times)

    residuals: list[float] = []
    dropped_pickup = 0
    placed = 0

    for note in notes:
        if note.start < bars[0].start_sec - spacing:
            dropped_pickup += 1
            continue

        idx = _nearest_index(grid_times, note.start)
        residual = abs(note.start - grid_times[idx]) / spacing if spacing else 0.0
        bar_idx, slot = grid_coords[idx]

        end_idx = _nearest_index(grid_times, note.end)
        duration_slots = max(MIN_DURATION_SLOTS, end_idx - idx)

        bar = bars[bar_idx]
        # 그리드 마지막 항목은 마지막 마디의 끝 경계(slot == slots_per_bar)다.
        # 실제 슬롯이 아니므로 여기 스냅된 음은 버린다.
        if slot >= bar.slots_per_bar:
            continue
        # 마디를 넘기는 음도 실제 길이를 그대로 남긴다. 여기서 자르면 마디 넘김
        # 정보가 alphatex까지 도달하지 못해 이어진 음이 마디 끝에서 끊긴다.
        # 마디 경계 처리(타이 분할)는 마디 구조를 아는 alphatex가 담당한다.
        duration_slots = min(duration_slots, bar.slots_per_bar * MAX_DURATION_BARS)

        bar.notes.append(
            QuantizedNote(
                slot=slot,
                duration_slots=duration_slots,
                pitch=note.pitch,
                amplitude=note.amplitude,
                residual=residual,
                low_confidence=residual > SNAP_REJECT_RATIO,
                loudness=note.loudness,
            )
        )
        residuals.append(residual)
        placed += 1

    # 같은 슬롯에 두 음이 겹치면(단선율 전제) 센 음만 남긴다
    for bar in bars:
        bar.notes = _dedupe_slots(bar.notes)

    score = QuantizedScore(
        bars=bars,
        subdivision=subdivision,
        beats_per_bar=beats_per_bar,
        median_bpm=grid.median_bpm,
        mean_residual=statistics.fmean(residuals) if residuals else 0.0,
        swing=swing,
        dropped_pickup=dropped_pickup,
        note_count=sum(len(b.notes) for b in bars),
        phase=phase,
        phase_corrected=phase_corrected,
        sixteenth_ratio=sixteenth_ratio,
    )

    if verbose:
        note = " (다운비트 위상 교정됨)" if phase_corrected else ""
        grid_note = ""
        if force_subdivision is None and not swing:
            grid_note = f" (16분요구 {100 * sixteenth_ratio:.1f}%)"
        print(
            f"[quantize] {len(notes)} notes -> {score.note_count} in {len(bars)} bars, "
            f"{beats_per_bar}/4, subdiv={subdivision}{' (swing)' if swing else ''}"
            f"{grid_note}, phase={phase}{note}, 잔차평균={score.mean_residual:.3f}, "
            f"pickup버림={dropped_pickup}"
        )
    return score


def choose_subdivision(notes: list[Note], grid: BeatGrid) -> tuple[int, float]:
    """스트레이트 곡의 격자를 고른다. 반환 (subdivision, 16분 요구 비율).

    온셋 하나가 "16분 격자를 요구한다"고 보는 조건은 두 개를 모두 만족하는 것이다.
      - 박 안 상대위치가 홀수 16분(0.25 또는 0.75)에 가장 가깝다
      - **동시에** 가장 가까운 8분 자리에서 EIGHTH_TOLERANCE보다 멀다

    두 번째 조건이 없으면 8분음표 위의 연주 흔들림이 전부 16분으로 잡힌다.
    실제로 그 조건 없이 재봤을 때 스트레이트 곡도 절반 넘게 16분으로 판정됐다.

    비트 위상을 여기서 추정하지 않는다는 점이 중요하다. 그리드의 비트를 그대로
    쓴다 — 위상을 16분 격자 잔차로 구하면 답이 16분 간격만큼 임의로 밀린다.
    """
    beats = grid.beats
    if len(notes) < MIN_NOTES_FOR_GRID_CHOICE or len(beats) < 2:
        return DEFAULT_SUBDIVISION, 0.0

    import bisect

    eighth = (0.0, 0.5, 1.0)
    sixteenth = (0.0, 0.25, 0.5, 0.75, 1.0)
    used = 0
    needs16 = 0

    for note in notes:
        i = bisect.bisect_right(beats, note.start) - 1
        if i < 0 or i + 1 >= len(beats):
            continue
        span = beats[i + 1] - beats[i]
        if span <= 0:
            continue
        pos = (note.start - beats[i]) / span
        used += 1
        dist8 = min(abs(pos - s) for s in eighth)
        nearest16 = min(sixteenth, key=lambda s: abs(pos - s))
        if nearest16 in (0.25, 0.75) and dist8 > EIGHTH_TOLERANCE:
            needs16 += 1

    if used < MIN_NOTES_FOR_GRID_CHOICE:
        return DEFAULT_SUBDIVISION, 0.0

    ratio = needs16 / used
    return (4 if ratio >= SIXTEENTH_REQUIRED_RATIO else 2), ratio


def choose_phase(notes: list[Note], grid: BeatGrid) -> tuple[int, bool]:
    """마디 시작 위상을 고른다. 반환 (phase, 다운비트에서 교정됐는지).

    beat_this의 다운비트는 위상이 통째로 어긋나는 경우가 있다. 실측 사례:
    킥 1·3박 + 스네어 2·4박 패턴에서 백비트를 1박으로 듣고 다운비트를
    반 마디 밀어서 잡았다. 이러면 악보 전체가 밀린다.

    베이스는 이걸 교정할 단서를 준다. 베이시스트는 마디 첫 박에 루트를
    강하게 짚으므로, **강한 베이스 온셋이 마디 시작에 가장 많이 걸리는 위상**이
    맞을 확률이 높다. 후보 위상마다 점수를 매겨 고른다.
    """
    beats = grid.beats
    bpb = grid.beats_per_bar

    downbeat_phase = 0
    if grid.downbeats:
        first = grid.downbeats[0]
        downbeat_phase = min(range(len(beats)), key=lambda i: abs(beats[i] - first)) % bpb

    if not notes or len(beats) < bpb + 1:
        return downbeat_phase, False

    import bisect

    half_beat = statistics.median(_intervals(beats)) / 2 if len(beats) > 2 else 0.25

    def beat_index(t: float) -> int | None:
        pos = bisect.bisect_left(beats, t)
        candidates = [i for i in (pos - 1, pos) if 0 <= i < len(beats)]
        if not candidates:
            return None
        idx = min(candidates, key=lambda i: abs(beats[i] - t))
        return idx if abs(beats[idx] - t) <= half_beat else None

    # 가장 강한 단서: 곡의 첫 음은 거의 항상 마디 1박이다.
    # (픽업 마디로 시작하는 곡에서는 틀리지만 소수다)
    ordered = sorted(notes, key=lambda n: n.start)
    peak = max(n.amplitude for n in ordered)
    first_phase: int | None = None
    for note in ordered:
        if note.amplitude < peak * 0.4:
            continue  # 앞쪽 잡음성 약한 음은 건너뛴다
        idx = beat_index(note.start)
        if idx is not None:
            first_phase = idx % bpb
            break

    if first_phase is not None:
        return first_phase, first_phase != downbeat_phase

    # 첫 음을 못 잡으면 진폭 합이 가장 큰 위상으로 대체
    scores = [0.0] * bpb
    for note in notes:
        idx = beat_index(note.start)
        if idx is not None:
            scores[idx % bpb] += note.amplitude
    best = max(range(bpb), key=lambda p: scores[p])
    return best, best != downbeat_phase


def _bar_beat_spans(grid: BeatGrid, phase: int) -> list[list[float]]:
    """마디별 비트 경계 리스트를 만든다. 각 항목은 길이 beats_per_bar+1.

    다운비트를 그대로 마디 경계로 쓰지 않는다. beat_this의 다운비트는
    킥 패턴에 따라 4/4를 2박으로 쪼개거나 위상이 밀리는데, 비트 자체는 안정적이다.
    그래서 **비트 배열을 기준으로 beats_per_bar개씩 묶는다.**
    이렇게 하면 마디마다 정확히 beats_per_bar개 비트가 들어간다.
    """
    beats = grid.beats
    bpb = grid.beats_per_bar
    spans: list[list[float]] = []
    idx = phase
    while idx + bpb < len(beats):
        spans.append(beats[idx : idx + bpb + 1])
        idx += bpb

    # 남은 비트로 마지막 마디를 만든다 (끝은 평균 비트 간격으로 외삽)
    if idx < len(beats) - 1:
        tail = list(beats[idx:])
        step = statistics.median(_intervals(beats)) if len(beats) > 2 else 0.5
        while len(tail) < bpb + 1:
            tail.append(tail[-1] + step)
        spans.append(tail[: bpb + 1])

    return spans


def _intervals(beats: list[float]) -> list[float]:
    return [b - a for a, b in zip(beats, beats[1:]) if b > a]


def _build_bars(grid: BeatGrid, phase: int, subdivision: int, slots_per_bar: int) -> list[Bar]:
    bars: list[Bar] = []
    for i, span in enumerate(_bar_beat_spans(grid, phase)):
        start, end = span[0], span[-1]
        length = end - start
        bpm = (60.0 * grid.beats_per_bar / length) if length > 0 else grid.median_bpm
        bars.append(
            Bar(
                index=i,
                start_sec=start,
                end_sec=end,
                bpm=bpm,
                beats_per_bar=grid.beats_per_bar,
                slots_per_bar=slots_per_bar,
            )
        )
    return bars


def _build_grid(
    bars: list[Bar], grid: BeatGrid, phase: int, subdivision: int, slots_per_bar: int
) -> tuple[list[float], list[tuple[int, int]]]:
    """전체 그리드 시각과 (마디, 슬롯) 좌표를 만든다.

    마디를 균등 분할하지 않고 **비트 사이를 각각 subdivision등분**한다.
    실연주에서 비트 간격이 불균등해도 그리드가 따라가므로 스냅 잔차가 줄어든다.
    """
    spans = _bar_beat_spans(grid, phase)
    times: list[float] = []
    coords: list[tuple[int, int]] = []

    for bar, span in zip(bars, spans):
        slot = 0
        for b0, b1 in zip(span, span[1:]):
            step = (b1 - b0) / subdivision
            for k in range(subdivision):
                times.append(b0 + step * k)
                coords.append((bar.index, slot))
                slot += 1

    # 마지막 마디 끝 경계 — duration 계산이 끝을 넘어가지 않게 한 칸 더 둔다
    times.append(bars[-1].end_sec)
    coords.append((bars[-1].index, slots_per_bar))
    return times, coords


def _median_spacing(times: list[float]) -> float:
    gaps = [b - a for a, b in zip(times, times[1:]) if b > a]
    return statistics.median(gaps) if gaps else 0.0


def _nearest_index(times: list[float], value: float) -> int:
    import bisect

    pos = bisect.bisect_left(times, value)
    if pos == 0:
        return 0
    if pos >= len(times):
        return len(times) - 1
    before, after = times[pos - 1], times[pos]
    return pos - 1 if (value - before) <= (after - value) else pos


def _dedupe_slots(notes: list[QuantizedNote]) -> list[QuantizedNote]:
    best: dict[int, QuantizedNote] = {}
    for note in notes:
        current = best.get(note.slot)
        if current is None or note.amplitude > current.amplitude:
            best[note.slot] = note
    return [best[slot] for slot in sorted(best)]


def _detect_swing(notes: list[Note], grid: BeatGrid) -> bool:
    """비트 내 온셋 위치 분포로 스윙을 판정한다.

    스트레이트면 온셋이 0.0/0.5 근처, 스윙이면 0.0/0.66 근처에 모인다.
    단, 비트 간격이 불안정한 곡(bpm_variance가 높은 곡)은 온셋의 박 내
    상대위치 자체가 흔들리므로 이 통계를 신뢰할 수 없어 판정에서 제외한다.
    """
    if grid.bpm_variance > SWING_MAX_BPM_VARIANCE:
        return False

    beats = grid.beats
    if len(beats) < 4 or len(notes) < 8:
        return False

    import bisect

    offbeat_positions: list[float] = []
    for note in notes:
        pos = bisect.bisect_right(beats, note.start) - 1
        if pos < 0 or pos + 1 >= len(beats):
            continue
        span = beats[pos + 1] - beats[pos]
        if span <= 0:
            continue
        frac = (note.start - beats[pos]) / span
        # 박 정중앙 근처(0.35~0.85)에 있는 것만 스윙 판정에 쓴다
        if 0.35 <= frac <= 0.85:
            offbeat_positions.append(frac)

    if len(offbeat_positions) < 4:
        return False
    median = statistics.median(offbeat_positions)
    return median > 0.60
