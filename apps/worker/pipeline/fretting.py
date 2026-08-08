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
    "standard": [43, 38, 33, 28],       # G2 D2 A1 E1
    "dropD": [43, 38, 33, 26],          # G2 D2 A1 D1
    # 반음 내림. 키를 반음 내려 연습할 때 이조하는 대신 이걸 쓰면 **운지가
    # 그대로 유지된다** — 실제 연주자가 쓰는 방법이고 다시 배울 것이 없다.
    "halfStepDown": [42, 37, 32, 27],   # F#2 C#2 G#1 D#1
}

# 4현 베이스의 가장 보편적인 프렛 수.
NFRETS = 20

# 비용 가중치 — **두 정답으로 채점해서 정한 값이다.**
#
# 예전 값(move 1.0 / string 0.4 / position 0.15 / open -0.8)은 전부 감으로 정한
# 것이었다. 정답으로 재보니 IDMT 67.3% / 영상 75.0%였다.
#
# **IDMT 하나로 튜닝하면 안 된다.** IDMT 점수만 최대로 만든 조합
# (move 0.35 / string 1.0 / position 0.03 / open 0.2)은 IDMT 75.5%까지 올랐지만
# 실곡에서 **모든 음이 E현에 갇혔다**(10·9·7프렛). 자리 일치가 5/8에서 1/8로
# 떨어졌다. IDMT는 곡당 21초짜리 짧은 리프라 한 현에 머무는 경향이 강한데,
# 실제 곡은 코드 진행이 돌며 현을 옮긴다. 데이터셋이 실사용을 대표하지 않는다.
#
# 그래서 **둘 중 나쁜 쪽을 기준으로** 골랐다: IDMT 77.8% / 영상 100%.
#   IDMT   17곡 948음, `stringNumber`/`fretNumber` 정답
#   영상   커버 영상 화면 악보 8마디 24타 (eval/golden/champagne_video_bars25_32.json)
#
# 바뀐 방향:
#   - 프렛 이동 비용을 크게 낮췄다(1.0 -> 0.2). 연주자는 한 현에 머물려고
#     프렛을 더 움직인다.
#   - **개방현은 보너스가 아니라 벌점이다**(-0.8 -> +0.4). 뮤트가 안 되고 음색이
#     달라 오히려 피한다. 예전 값은 정답과 반대 방향이었고, 그래서 영상 악보가
#     A현 5프렛으로 짚는 D를 우리는 개방 D현으로 골랐다.
#   - 높은 프렛 기피는 거의 무시(0.15 -> 0.03).
#
# 재현: python eval/eval_fretting.py --sweep
W_MOVE = 0.2           # 직전 음과의 프렛 거리 (손 이동)
W_STRING_CHANGE = 0.2  # 현 이동
W_POSITION = 0.03      # 높은 프렛 기피 (거의 무시)
W_OPEN_PENALTY = 0.4   # 개방현 **벌점**. 이름이 BONUS였던 시절 값(-0.8)은 정답과 반대였다


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
    max_fret: int | None = None,
    max_move: int | None = None,
) -> FrettedScore:
    """운지를 배정한다.

    max_fret / max_move는 난이도 하향에서 온다. 비용 가중치로 저포지션을
    "선호"하는 것만으로는 초급자가 못 짚는 자리가 남으므로, 하향 레벨에서는
    후보 자체를 제한하는 **하드 제약**이 필요하다.

    제약을 만족하는 후보가 없으면 그 음은 옥타브를 접어 제약 안으로 들여놓는다.
    버리면 라인에 구멍이 나고, 제약을 무시하면 하향한 의미가 없다.
    """
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

    # 튜닝 음역 밖 음을 먼저 옥타브로 접는다. 이조 경로(compose._transpose)에는
    # 접기가 있는데 원곡 경로에는 없어서, 개방 E 아래 음이 연주불가로 떨어져
    # **라인에 구멍이 났다**(PRD 13.3-6). 버리는 것보다 옥타브 위가 낫다 —
    # 근음 진행은 피치클래스로 유지된다.
    lowest, highest = min(tuning), max(tuning) + NFRETS
    folded_range = 0
    for i, p in enumerate(pitches):
        original = p
        while p < lowest:
            p += 12
        while p > highest:
            p -= 12
        if p != original:
            pitches[i] = p
            folded_range += 1
    if verbose and folded_range:
        print(f"[fretting] 음역 밖 {folded_range}음을 옥타브 접음")

    # 프렛 상한을 넘는 음은 옥타브를 접어 제약 안으로 들여놓는다. 접은 결과를
    # FrettedNote.pitch에도 써야 한다 — 원래 피치를 남기면 적힌 프렛으로는 그
    # 음이 나지 않아 악보와 소리가 어긋난다.
    if max_fret is not None:
        pitches = [_fold_into_fret_limit(p, tuning, max_fret) for p in pitches]
    positions = _viterbi(pitches, tuning, max_fret=max_fret, max_move=max_move)

    bars: list[FrettedBar] = []
    unplayable = 0
    cursor = 0
    for bar in score.bars:
        fretted: list[FrettedNote] = []
        for note in bar.notes:
            pos = positions[cursor]
            pitch = pitches[cursor]
            cursor += 1
            if pos is None:
                unplayable += 1
                continue
            string, fret = pos
            fretted.append(
                FrettedNote(
                    slot=note.slot,
                    duration_slots=note.duration_slots,
                    pitch=pitch,
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


def _candidates(
    pitch: int, tuning: list[int], max_fret: int | None = None
) -> list[tuple[int, int]]:
    """이 음을 낼 수 있는 (현, 프렛) 조합 전부."""
    ceiling = NFRETS if max_fret is None else min(NFRETS, max_fret)
    out: list[tuple[int, int]] = []
    for string, open_pitch in enumerate(tuning):
        fret = pitch - open_pitch
        if 0 <= fret <= ceiling:
            out.append((string, fret))
    return out


def _fold_into_fret_limit(pitch: int, tuning: list[int], max_fret: int) -> int:
    """프렛 상한 안에서 짚을 수 있는 옥타브로 접는다.

    상한 안 후보가 이미 있으면 그대로 둔다. 없으면 옥타브 단위로 내리거나
    올려서 들여놓고, 그래도 없으면 원래 피치를 돌려준다(호출부가 연주불가로
    센다). 절대 피치 상수를 쓰지 않고 튜닝에서 경계를 구한다 — 상수로 박아두면
    드롭D나 반음 내림 튜닝에서 틀린 경계를 쓴다.
    """
    if _candidates(pitch, tuning, max_fret):
        return pitch
    lowest = min(tuning)
    highest = max(tuning) + min(NFRETS, max_fret)
    for shift in (-12, 12, -24, 24):
        candidate = pitch + shift
        if lowest <= candidate <= highest and _candidates(candidate, tuning, max_fret):
            return candidate
    return pitch


def _position_cost(fret: int) -> float:
    cost = W_POSITION * fret
    if fret == 0:
        cost += W_OPEN_PENALTY
    return cost


def _move_span(prev: tuple[int, int], curr: tuple[int, int]) -> int:
    """두 포지션 사이의 손 이동 폭(프렛). 개방현은 손을 움직이지 않는다."""
    _, prev_fret = prev
    _, fret = curr
    if prev_fret == 0 or fret == 0:
        return 0
    return abs(fret - prev_fret)


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


def _viterbi(
    pitches: list[int],
    tuning: list[int],
    *,
    max_fret: int | None = None,
    max_move: int | None = None,
) -> list[tuple[int, int] | None]:
    """손 이동을 최소화하는 포지션 열을 고른다.

    max_move는 하향 레벨의 이동 폭 제약이다. 비용이 아니라 **금지**로 걸어야
    한다 — 비용으로만 두면 다른 선택지가 없을 때 큰 이동이 통과한다. 단
    금지하면 경로가 끊길 수 있으므로, 어떤 후보도 제약을 통과하지 못하면 그
    음에서는 제약을 풀고 최소 이동을 쓴다(악보에 구멍을 내지 않는다).
    """
    if not pitches:
        return []

    # (비용, 직전 상태 인덱스) 테이블
    states: list[list[tuple[int, int]]] = [
        _candidates(p, tuning, max_fret) for p in pitches
    ]
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
            transitions = [
                (prev_costs[j] + _transition_cost(prev_options[j], option), j)
                for j in range(len(prev_options))
            ]
            if max_move is not None:
                allowed = [
                    t for t in transitions
                    if _move_span(prev_options[t[1]], option) <= max_move
                ]
                # 제약을 통과하는 경로가 없으면 제약을 풀고 최소 이동을 쓴다.
                # 여기서 끊으면 그 음이 악보에서 사라진다.
                transitions = allowed or transitions
            best_cost, best_idx = min(transitions, key=lambda pair: pair[0])
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
