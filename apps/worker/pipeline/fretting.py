"""운지(현/프렛) 배정.

PRD는 tuttut(HMM+Viterbi)을 쓰기로 했고 스모크 테스트에서 동작을 확인했다.
그런데 **4현 단선율**이라는 우리 조건에서는 자체 DP가 더 낫다고 판단해 기본
백엔드를 바꿨다. 근거:

- 음 하나당 후보 포지션이 최대 4개뿐이라 상태공간이 사실상 없다
- 비용함수를 우리가 직접 통제해야 한다 (개방현 선호, 저포지션 편향은
  베이스 특유의 관습이고 기타용 가중치와 다르다)
- tuttut은 자체적으로 마디를 추정하는데, 우리는 이미 beat_this 그리드로
  마디를 확정했다. 두 마디 체계를 맞추는 비용이 DP를 직접 쓰는 비용보다 크다
- tuttut은 --no-deps 설치 + matplotlib + pretty-midi 버전 충돌을 안고 있다

tuttut 백엔드는 비교용으로 남겨둔다 (backend="tuttut").
"""

from __future__ import annotations

from dataclasses import dataclass

from .quantize import QuantizedScore

# 4현 베이스 표준 튜닝. thin -> thick 순서(1번현이 G2).
TUNING_PRESETS: dict[str, list[int]] = {
    "standard": [43, 38, 33, 28],   # G2 D2 A1 E1
    "dropD": [43, 38, 33, 26],      # G2 D2 A1 D1
}

NFRETS = 20

# 비용 가중치
W_MOVE = 1.0          # 직전 음과의 프렛 거리 (손 이동)
W_STRING_CHANGE = 0.4  # 현 이동
W_POSITION = 0.15      # 높은 프렛 기피 (저포지션 선호)
W_OPEN_BONUS = -0.8    # 개방현 보너스 (음수 = 비용 감소)


@dataclass
class FrettedNote:
    slot: int
    duration_slots: int
    pitch: int
    string: int    # 0 = 가장 얇은 현(G2)
    fret: int
    low_confidence: bool


@dataclass
class FrettedBar:
    index: int
    start_sec: float
    end_sec: float
    bpm: float
    slots_per_bar: int
    notes: list[FrettedNote]


@dataclass
class FrettedScore:
    bars: list[FrettedBar]
    tuning: list[int]
    tuning_name: str
    subdivision: int
    beats_per_bar: int
    median_bpm: float
    unplayable: int   # 튜닝 음역 안에서 짚을 수 없어 버린 음


def assign(
    score: QuantizedScore,
    tuning_name: str = "standard",
    *,
    backend: str = "dp",
    verbose: bool = False,
) -> FrettedScore:
    tuning = TUNING_PRESETS.get(tuning_name)
    if tuning is None:
        raise ValueError(f"알 수 없는 튜닝 프리셋: {tuning_name}")
    if backend != "dp":
        raise NotImplementedError(
            "현재 dp 백엔드만 구현되어 있습니다. tuttut 비교는 scripts/compare_fretting.py 참조."
        )

    # 마디 경계를 넘어서도 손 위치는 이어지므로 전체 시퀀스로 한 번에 DP를 돈다.
    flat: list[tuple[int, int]] = []  # (bar_idx, note_idx)
    pitches: list[int] = []
    for bi, bar in enumerate(score.bars):
        for ni, note in enumerate(bar.notes):
            flat.append((bi, ni))
            pitches.append(note.pitch)

    positions = _viterbi(pitches, tuning)

    bars: list[FrettedBar] = []
    unplayable = 0
    cursor = 0
    for bar in score.bars:
        fretted: list[FrettedNote] = []
        for note in bar.notes:
            pos = positions[cursor]
            cursor += 1
            if pos is None:
                unplayable += 1
                continue
            string, fret = pos
            fretted.append(
                FrettedNote(
                    slot=note.slot,
                    duration_slots=note.duration_slots,
                    pitch=note.pitch,
                    string=string,
                    fret=fret,
                    low_confidence=note.low_confidence,
                )
            )
        bars.append(
            FrettedBar(
                index=bar.index,
                start_sec=bar.start_sec,
                end_sec=bar.end_sec,
                bpm=bar.bpm,
                slots_per_bar=bar.slots_per_bar,
                notes=fretted,
            )
        )

    result = FrettedScore(
        bars=bars,
        tuning=tuning,
        tuning_name=tuning_name,
        subdivision=score.subdivision,
        beats_per_bar=score.beats_per_bar,
        median_bpm=score.median_bpm,
        unplayable=unplayable,
    )
    if verbose:
        total = sum(len(b.notes) for b in bars)
        print(
            f"[fretting] {tuning_name} {tuning}: {total} notes 배정, "
            f"연주불가 {unplayable}"
        )
    return result


def _candidates(pitch: int, tuning: list[int]) -> list[tuple[int, int]]:
    """이 음을 낼 수 있는 (현, 프렛) 조합 전부."""
    out: list[tuple[int, int]] = []
    for string, open_pitch in enumerate(tuning):
        fret = pitch - open_pitch
        if 0 <= fret <= NFRETS:
            out.append((string, fret))
    return out


def _position_cost(fret: int) -> float:
    cost = W_POSITION * fret
    if fret == 0:
        cost += W_OPEN_BONUS
    return cost


def _transition_cost(prev: tuple[int, int], curr: tuple[int, int]) -> float:
    prev_string, prev_fret = prev
    string, fret = curr
    cost = 0.0
    # 개방현은 손 위치를 바꾸지 않으므로 이동 비용을 매기지 않는다
    if prev_fret != 0 and fret != 0:
        cost += W_MOVE * abs(fret - prev_fret)
    if string != prev_string:
        cost += W_STRING_CHANGE * abs(string - prev_string)
    return cost


def _viterbi(pitches: list[int], tuning: list[int]) -> list[tuple[int, int] | None]:
    """손 이동을 최소화하는 포지션 열을 고른다."""
    if not pitches:
        return []

    # (비용, 직전 상태 인덱스) 테이블
    states: list[list[tuple[int, int]]] = [_candidates(p, tuning) for p in pitches]
    costs: list[list[float]] = []
    backptr: list[list[int]] = []

    for i, options in enumerate(states):
        if not options:
            # 짚을 수 없는 음. 비용 테이블에 자리만 두고 넘어간다.
            costs.append([])
            backptr.append([])
            continue

        row_costs: list[float] = []
        row_back: list[int] = []
        prev_options, prev_costs = _last_nonempty(states, costs, i)

        for option in options:
            base = _position_cost(option[1])
            if not prev_options:
                row_costs.append(base)
                row_back.append(-1)
                continue
            best_cost, best_idx = min(
                (
                    (prev_costs[j] + _transition_cost(prev_options[j], option), j)
                    for j in range(len(prev_options))
                ),
                key=lambda pair: pair[0],
            )
            row_costs.append(base + best_cost)
            row_back.append(best_idx)

        costs.append(row_costs)
        backptr.append(row_back)

    # 역추적
    result: list[tuple[int, int] | None] = [None] * len(pitches)
    last = _last_index_with_options(costs)
    if last is None:
        return result

    idx = min(range(len(costs[last])), key=lambda j: costs[last][j])
    for i in range(last, -1, -1):
        if not costs[i]:
            continue
        result[i] = states[i][idx]
        parent = backptr[i][idx]
        if parent < 0:
            break
        idx = parent
    return result


def _last_nonempty(
    states: list[list[tuple[int, int]]], costs: list[list[float]], upto: int
) -> tuple[list[tuple[int, int]], list[float]]:
    for j in range(upto - 1, -1, -1):
        if costs[j]:
            return states[j], costs[j]
    return [], []


def _last_index_with_options(costs: list[list[float]]) -> int | None:
    for i in range(len(costs) - 1, -1, -1):
        if costs[i]:
            return i
    return None


def to_ascii(score: FrettedScore) -> list[str]:
    """디버깅용 ASCII 탭. 현 이름은 thin -> thick 순."""
    import pretty_midi

    names = [pretty_midi.note_number_to_name(p)[:-1] for p in score.tuning]
    lines: list[list[str]] = [[] for _ in score.tuning]

    for bar in score.bars:
        cells = [["-"] * bar.slots_per_bar for _ in score.tuning]
        for note in bar.notes:
            label = str(note.fret)
            for offset, ch in enumerate(label):
                if note.slot + offset < bar.slots_per_bar:
                    cells[note.string][note.slot + offset] = ch
        for s in range(len(score.tuning)):
            lines[s].append("".join(cells[s]))

    return [f"{names[s]:>2} ||" + "|".join(lines[s]) + "|" for s in range(len(score.tuning))]
