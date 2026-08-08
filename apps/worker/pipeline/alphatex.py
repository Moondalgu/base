"""AlphaTex 생성.

파이프라인의 최종 산출물. 음표 + 튜닝 + 박자/템포 + sync 포인트를 텍스트
한 파일에 담아 프론트의 alphaTab에 그대로 넘긴다. MusicXML/GuitarPro 중간
변환을 건너뛴다.

음표 문법: fret.string.duration  (string 1 = 가장 얇은 현)
타이 문법: -.string.duration      (프렛 자리를 대시로 대신하되 현 번호는 필수)
붙임점    : duration에 {d} 접미    (예: 4{d} = 붙임점 4분음표, r.8{d} = 붙임점 8분쉼표)
sync 문법: \\sync (barIndex occurence millisecondOffset ratioPosition)
"""

from __future__ import annotations

import pretty_midi

from .fretting import FrettedBar, FrettedScore

class UnsupportedSubdivision(ValueError):
    pass


# 슬롯 수 -> (AlphaTex 음길이 표기, 정렬 단위). 큰 것부터 정렬한다.
#
# 세 번째 값 `align`은 "이 음길이를 쓸 수 있는 시작 위치"를 정한다.
# `pos % align == 0`일 때만 그 길이를 쓴다. 정통 악보 표기 규칙 때문이다:
# 음표는 자기 길이만큼의 박 블록 안에 온전히 들어가야 하고, 블록을 넘으면
# 두 조각으로 나눠 타이로 이어야 읽힌다.
#   - 일반 길이(2의 거듭제곱 슬롯)는 align = 자기 길이
#     예) 2박에서 시작하는 2분음표(슬롯 4, 8슬롯)는 4 % 8 != 0이라 쓸 수 없다.
#         4분음표 두 개를 타이로 잇는 것이 정석이다.
#   - 붙임점 길이는 align = 자기 길이보다 큰 최소의 2의 거듭제곱
#     (붙임점 4분 6슬롯 -> 8, 붙임점 8분 3슬롯 -> 4, 붙임점 2분 12슬롯 -> 16)
#     붙임점 음표는 그 블록의 3/4 지점까지만 차지하므로 블록 시작에서만 쓸 수 있다.
#     예) 슬롯 2에서 3슬롯은 2 % 4 != 0이라 붙임점 8분이 아니라 8분 + 타이 16분이다.
#
# 스윙(subdivision=3)은 셋잇단으로 적는다. 셔플·블루스는 흔하고, 스윙 곡을
# 16분 격자에 억지로 맞추면 리듬이 틀린다.
#   1박 = 3슬롯이므로
#     8분 셋잇단 = 1슬롯,  4분 셋잇단 = 2슬롯 (1박의 2/3)
#     2분 셋잇단 = 4슬롯,  온음표 셋잇단 = 8슬롯
# {tu 3} 문법은 alphaTab 파서에서 확인했다 ({tuplet 3} 풀네임은 거부된다).
# 셋잇단 격자에는 2의 거듭제곱 위계가 없으므로 align을 모두 1로 둔다(제약 없음).
# 붙임점도 섞지 않는다 — 셋잇단과 붙임점을 함께 쓰면 표기가 깨진다.
_DURATION_TABLES: dict[int, list[tuple[int, str, int]]] = {
    # 8분 격자(1박 = 2슬롯). 온셋이 8분으로 설명되는 곡은 이쪽을 쓴다.
    # align 규칙은 16분 표와 같은 원리다 — 일반 길이는 자기 길이, 붙임점은
    # 자기보다 큰 최소의 2의 거듭제곱(붙임점2분 6->8, 붙임점4분 3->4).
    2: [
        (8, "1", 8),
        (6, "2{d}", 8),
        (4, "2", 4),
        (3, "4{d}", 4),
        (2, "4", 2),
        (1, "8", 1),
    ],
    4: [
        (16, "1", 16),
        (12, "2{d}", 16),
        (8, "2", 8),
        (6, "4{d}", 8),
        (4, "4", 4),
        (3, "8{d}", 4),
        (2, "8", 2),
        (1, "16", 1),
    ],
    3: [
        (12, "1", 1),
        (8, "1{tu 3}", 1),
        (6, "2", 1),
        (4, "2{tu 3}", 1),
        (3, "4", 1),
        (2, "4{tu 3}", 1),
        (1, "8{tu 3}", 1),
    ],
}


# 검출된 물리적 길이를 그대로 적으면 스타카토가 16분음표+16분쉼표로 쪼개진다.
# 악보 관습은 리듬 값을 적고 길이는 아티큘레이션에 맡기는 것이다(PRD 4.8에서
# 주법은 표기하지 않기로 했으므로 더욱 그렇다). 음보다 짧거나 같은 쉼표는
# 그 음의 리듬 값 안으로 흡수한다. 음보다 긴 쉼표는 연주자가 실제로 쉬는
# 구간이므로 그대로 적는다.
ABSORB_REST_UP_TO_NOTE_LENGTH = True


def _duration_table(subdivision: int) -> list[tuple[int, str, int]]:
    table = _DURATION_TABLES.get(subdivision)
    if table is None:
        raise UnsupportedSubdivision(
            f"subdivision={subdivision}은 지원하지 않습니다. "
            f"지원: {sorted(_DURATION_TABLES)}"
        )
    return table


def _largest_fitting(
    slots: int, pos: int, table: list[tuple[int, str, int]]
) -> tuple[int, str]:
    """슬롯 pos에서 표기할 수 있는 가장 긴 음길이를 고른다.

    길이가 남은 슬롯 안에 들어가야 하고(size <= slots), 정렬 규칙도 통과해야
    한다(pos % align == 0). 표의 마지막 항목은 1슬롯/align 1이라 항상 통과하므로
    이 함수는 반드시 값을 돌려준다.
    """
    for size, token, align in table:
        if size <= slots and pos % align == 0:
            return size, token
    size, token, _ = table[-1]
    return size, token


def slots_of(duration_token: str, subdivision: int) -> int:
    """음길이 표기를 슬롯 수로 되돌린다.

    산출물을 다시 읽어야 하는 쪽(eval/run_eval.py, eval/compare_bars.py)이
    파싱 규칙을 따로 두면 붙임점·셋잇단 표기가 추가될 때마다 어긋난다.
    표를 여기 하나만 둔다.

    **음길이와 무관한 효과가 같은 중괄호에 섞여 들어온다.** alphaTex는 중괄호를
    연달아 쓰는 것을 거부하므로(`4{d}{ch "E"}` -> 파싱 실패) 붙임점과 코드
    심볼을 `4{d ch "E"}` 한 덩어리로 합쳐 적는다. 되읽을 때는 음길이에
    관계된 것만 남기고 나머지를 걷어내야 한다 — 그러지 않아 정답 대조 도구가
    통째로 죽은 적이 있다.
    """
    normalized = _strip_non_duration(duration_token)
    for size, token, _ in _duration_table(subdivision):
        if token == normalized:
            return size
    raise ValueError(
        f"알 수 없는 음길이 표기: {duration_token!r} (정규화 후 {normalized!r})"
    )


# 음길이에 영향을 주는 중괄호 지시자. 이것만 남기고 나머지는 걷어낸다.
_DURATION_EFFECTS = ("d", "tu")


def _strip_non_duration(token: str) -> str:
    """중괄호에서 음길이와 무관한 효과를 걷어낸다. `4{d ch "E"}` -> `4{d}`.

    중괄호 안은 `지시자 [인자...]`의 나열이다. 지시자 단위로 끊어 음길이에
    관계된 것만 인자까지 함께 남긴다. 조각 단위로 걸러내면 `{tu 3 ch "Am"}`에서
    셋잇단 숫자 3을 코드 인자로 착각해 잃는다.
    """
    if "{" not in token or not token.endswith("}"):
        return token
    head, _, body = token.partition("{")

    groups: list[list[str]] = []
    for part in body[:-1].split():
        # 인용부호로 시작하거나 소문자 지시자가 아니면 앞 지시자의 인자다.
        if groups and (part.startswith('"') or not part.isalpha()):
            groups[-1].append(part)
        else:
            groups.append([part])

    kept = [g for g in groups if g[0] in _DURATION_EFFECTS]
    if not kept:
        return head
    return f"{head}{{{' '.join(' '.join(g) for g in kept)}}}"


def build(
    score: FrettedScore,
    *,
    title: str = "Untitled",
    artist: str = "",
    include_sync: bool = True,
    chords: list[str] | None = None,
    key_signature: str | None = None,
    vocal: "QuantizedScoreLike | None" = None,
    vocal_syllables: list[dict] | None = None,
) -> str:
    """FrettedScore를 AlphaTex 문자열로 만든다.

    chords는 마디 순서와 같은 길이의 코드 이름 목록이다. 빈 문자열이면 그
    마디에는 코드를 적지 않는다 — 확신 없는 코드를 적는 것은 틀린 정보를
    주는 것이다.

    vocal은 베이스와 **같은 격자·위상으로 양자화된** QuantizedScore다
    (compose가 force_subdivision·force_phase로 맞춰서 넘긴다). 있으면 참조
    악보(드라우닝 3단)처럼 보컬 오선 트랙을 위에 얹는다. 코드 심볼은 베이스
    트랙에 남긴다 — 보컬은 쉼표 마디가 많은데 쉼표에는 코드를 못 붙인다
    (PRD 12.2 N6). 위치 폴리싱은 조판 단계(F7)에서 본다.
    """
    _duration_table(score.subdivision)  # 지원 여부를 먼저 확인한다

    lines: list[str] = []
    lines.append(f'\\title "{_escape(title)}"')
    if artist:
        lines.append(f'\\subtitle "{_escape(artist)}"')
    lines.append(f"\\tempo {score.median_bpm:.0f}")
    # 조표. 없으면 적지 않는다 — 조성을 모르는데 C장조로 찍으면 임시표가
    # 엉망이 되어 악보가 오히려 나빠진다.
    if key_signature:
        lines.append(f"\\ks {key_signature}")
    lines.append(".")
    lines.append("")
    if vocal is not None and any(b.notes for b in vocal.bars):
        lines.extend(_render_vocal_track(score, vocal, syllables=vocal_syllables))
        lines.append("")
    lines.append('\\track "Bass"')
    # \staff{tabs}만 쓰면 TAB만 렌더링되어 프론트엔드의 ScoreTab 설정(오선보+TAB)이
    # 무시된다. score를 같이 요청해야 위에 오선보, 아래에 TAB이 함께 나온다.
    #
    # \clef를 빼면 파싱은 통과하지만 음자리표가 G2(높은음자리표)로 남는다
    # (tools/probe_clef.mjs로 모델을 직접 읽어 확인). 베이스는 낮은음자리표로
    # 적는 악기이므로 명시해야 한다.
    lines.append(
        f"\\staff{{score tabs}} \\clef bass \\tuning {_tuning_names(score.tuning)}"
    )
    lines.append(f"\\ts {score.beats_per_bar} 4")
    lines.append("")

    # 마디를 넘는 음은 앞 마디 끝에서 자르지 않고 다음 마디 앞머리에 타이로 잇는다.
    # 그래서 마디를 순회하며 잔여 길이(carry)를 들고 다녀야 한다.
    bar_texts: list[str] = []
    carry: tuple[int, int] | None = None
    for i, bar in enumerate(score.bars):
        chord = chords[i] if chords and i < len(chords) else ""
        text, carry = _render_bar(
            bar, score.subdivision, carry_in=carry, chord=chord
        )
        bar_texts.append(text)
    lines.append(" |\n".join(bar_texts))

    if include_sync:
        lines.append("")
        lines.extend(_render_sync(score))

    return "\n".join(lines) + "\n"


def _escape(text: str) -> str:
    return text.replace('"', "'")


# alphaTex 음이름. 프로브 실측(tools/probe_vocal_pitch.mjs): `c4` = MIDI 60,
# 즉 옥타브 숫자 = midi // 12 − 1. 임시표는 샵으로 통일한다 — 조표가 플랫이어도
# 모델에는 피치로 들어가므로 렌더러가 이명동음을 알아서 처리한다.
_PITCH_LETTERS = ["c", "c#", "d", "d#", "e", "f", "f#", "g", "g#", "a", "a#", "b"]


def _vocal_pitch_name(midi: int) -> str:
    return f"{_PITCH_LETTERS[midi % 12]}{midi // 12 - 1}"


def _render_vocal_track(
    score: FrettedScore, vocal, syllables: list[dict] | None = None
) -> list[str]:
    """보컬 오선 트랙 전체를 적는다. 마디 수는 베이스 트랙과 정확히 맞춘다.

    베이스와 달리 타이·이월을 걸지 않는다. 마디를 넘거나 표기 단위로 못 적는
    잔여는 잘라서 쉼표로 채운다 — A.10과 같은 거래로, 위치는 정확하고 길이만
    짧게 적힌다. 보컬 멜로디는 음절 단위(8분·4분 중심)라 손실이 작다.

    syllables(ASR 음절, 시각 포함)를 주면 `\\lyrics`를 함께 적는다. alphaTab이
    음절을 음표 비트에만 순서대로 붙이므로(프로브 실측 — 쉼표는 소비하지 않음),
    **여기서 방출한 음표 순서 그대로** 음절 토큰을 만들어야 한다. 그래서
    정렬을 이 함수 밖에서 할 수 없다 — 겹침 스킵·마디 절단이 여기서 일어난다.
    """
    lines = ['\\track "Vocal"', "\\staff{score} \\clef treble",
             f"\\ts {score.beats_per_bar} 4"]
    vbars = {b.index: b for b in vocal.bars}
    table = _duration_table(vocal.subdivision)
    slots_per_bar = score.beats_per_bar * vocal.subdivision

    texts: list[str] = []
    note_times: list[float] = []
    for bar in score.bars:
        vb = vbars.get(bar.index)
        if vb is None or not vb.notes:
            texts.append(" ".join(_rests(0, slots_per_bar, table)))
            continue
        text, times = _render_vocal_bar(vb, table, slots_per_bar)
        texts.append(text)
        note_times.extend(times)

    if syllables and note_times:
        from .lyrics import align

        tokens = [_escape(t) for t in align(note_times, syllables)]
        lines.append(f'\\lyrics "{" ".join(tokens)}"')
    lines.append("")
    lines.append(" |\n".join(texts))
    return lines


def _render_vocal_bar(bar, table, slots_per_bar: int) -> tuple[str, list[float]]:
    """보컬 마디 하나 — (피치 토큰 열, 방출한 음표의 절대 시각 목록).

    단선율 강제(겹침은 확신도 순). 시각은 가사 정렬이 쓴다.
    """
    tokens: list[str] = []
    times: list[float] = []
    bar_len = bar.end_sec - bar.start_sec
    pos = 0
    for n in sorted(bar.notes, key=lambda n: (n.slot, -n.amplitude)):
        if n.slot < pos:
            continue  # 앞 음과 겹침 — 단선율이므로 건너뛴다
        if n.slot > pos:
            tokens.extend(_rests(pos, n.slot - pos, table))
            pos = n.slot
        span = min(n.duration_slots, slots_per_bar - pos)
        if span <= 0:
            continue
        size, duration = _largest_fitting(span, pos, table)
        tokens.append(f"{_vocal_pitch_name(n.pitch)}.{duration}")
        times.append(bar.start_sec + bar_len * (pos / slots_per_bar))
        pos += size
        if span > size:
            # 남은 길이는 쉼표로 — 타이 문법(A.10)이 절반만 통과하므로 걸지 않는다
            tokens.extend(_rests(pos, span - size, table))
            pos += span - size
    if pos < slots_per_bar:
        tokens.extend(_rests(pos, slots_per_bar - pos, table))
    return " ".join(tokens), times


def _tuning_names(tuning: list[int]) -> str:
    """alphaTab \\tuning은 낮은 현부터 나열한다. 내부 표현은 thin->thick이라 뒤집는다."""
    return " ".join(pretty_midi.note_number_to_name(p) for p in reversed(tuning))


def _render_bar(
    bar: FrettedBar,
    subdivision: int,
    carry_in: tuple[int, int] | None = None,
    chord: str = "",
) -> tuple[str, tuple[int, int] | None]:
    """마디 하나를 AlphaTex 토큰 열로 적는다. 반환 (토큰 문자열, carry_out).

    음 하나의 길이를 한 토큰으로 못 적으면 박 경계에서 잘라 타이(-)로 잇는다.
    표기 가능한 길이 후보를 큰 것부터 훑어 정렬 규칙(_DURATION_TABLES의 align)을
    통과하는 첫 길이를 쓰고, 남은 만큼을 같은 방식으로 이어 붙인다.
    쉼표도 같은 규칙으로 쪼갠다(타이가 없으므로 전부 r.* 토큰이다).

    carry_in/carry_out은 (현 번호, 남은 슬롯)이다. 마디를 넘는 음은 앞 마디에서
    자르지 않고 여기서 받아 마디 앞머리에 타이 토큰으로 먼저 적는다. carry가
    걸린 구간에는 다른 음이 올 수 없다(단선율) — 겹치면 carry를 우선하고 겹치는
    음은 건너뛴다.

    쉼표는 음이 실제로 쉬는 구간에만 나온다. 단, 음보다 짧거나 같은 쉼표는
    앞 음의 리듬 값에 흡수해서 악보가 잘게 쪼개지지 않게 한다
    (ABSORB_REST_UP_TO_NOTE_LENGTH 참조).
    """
    table = _duration_table(subdivision)
    tokens: list[str] = []
    pos = 0
    carry_out: tuple[int, int] | None = None

    # 앞 마디에서 넘어온 음을 마디 앞머리에 타이로 잇는다.
    if carry_in is not None:
        carry_string, carried = carry_in
        span = min(carried, bar.slots_per_bar)
        tokens.extend(_ties(0, span, carry_string, table))
        pos = span
        if carried > span:
            # 이 마디를 다 덮고도 남았다. 그대로 다음 마디로 넘긴다.
            return " ".join(tokens), (carry_string, carried - span)

    # 음은 슬롯 순서로 처리하고 pos는 뒤로 가지 않는다. 그래서 음과 음 사이의
    # 빈 구간은 이미 "연속된 쉼표 구간 전체"다. 따로 합산할 필요가 없다.
    notes = sorted(bar.notes, key=lambda n: n.slot)
    for i, note in enumerate(notes):
        if note.slot < pos:
            continue  # 단선율 전제 위반. 앞 음(또는 carry)을 존중하고 건너뛴다.
        if note.slot >= bar.slots_per_bar:
            continue  # 마디 밖 슬롯. 방어적 처리.
        if note.slot > pos:
            tokens.extend(_rests(pos, note.slot - pos, table))
            pos = note.slot

        remaining = note.duration_slots
        # 이 음 다음에 오는 빈 구간(다음 음의 슬롯까지, 없으면 마디 끝까지)
        next_slot = notes[i + 1].slot if i + 1 < len(notes) else bar.slots_per_bar
        remaining += _absorbable(remaining, pos, next_slot, table)

        # alphaTab 현 번호는 1부터, 가장 얇은 현이 1번
        string = note.string + 1
        first = True
        while remaining > 0:
            room = bar.slots_per_bar - pos
            if room <= 0:
                # 마디를 넘겼다. 남은 길이는 다음 마디가 타이로 받는다.
                carry_out = (string, remaining)
                break
            size, duration = _largest_fitting(min(remaining, room), pos, table)
            prefix = f"{note.fret}.{string}" if first else f"-.{string}"
            tokens.append(f"{prefix}.{duration}")
            first = False
            pos += size
            remaining -= size

    if pos < bar.slots_per_bar:
        tokens.extend(_rests(pos, bar.slots_per_bar - pos, table))

    # 음이 하나도 없는 마디도 박자만큼 쉼표로 채워야 alphaTab이 마디 길이를 맞춘다
    if not tokens:
        tokens = _rests(0, bar.slots_per_bar, table)

    # 코드 심볼은 마디의 **첫 음표**에 붙인다. `{ch "..."}`는 음길이 뒤에 오는
    # 비트 수식이므로 duration 위치에 이어 쓴다(현 번호 뒤의 음표 효과와 다르다).
    #
    # 쉼표(`r.4`)나 타이(`-.4.8`)에 붙이면 파서가 `Unexpected 'LBrace'`로 거부한다.
    # 마디가 쉼표뿐이면 코드를 적지 않는다 — 안 치는 마디의 코드는 의미도 없다.
    # (코드 이름은 오디오 분석 결과라 노트를 걸러낸 뒤에도 남아 있을 수 있다.
    #  음량 게이트가 그 마디 음을 전부 버린 경우가 실제로 나왔다.)
    if chord:
        first_note = next(
            (i for i, tok in enumerate(tokens) if tok[:1].isdigit()), None
        )
        if first_note is not None:
            tokens[first_note] = _with_chord(tokens[first_note], chord)
    return " ".join(tokens), carry_out


def _with_chord(token: str, chord: str) -> str:
    """음표 토큰에 코드 심볼을 붙인다.

    **중괄호를 연달아 쓸 수 없다.** `0.4.4{d}{ch "E"}`는 파서가 거부하고
    `0.4.4{d ch "E"}`는 통과한다(실측). 붙임점·셋잇단이 이미 붙은 토큰에
    코드를 더할 때는 기존 중괄호 안으로 넣어야 한다.
    """
    suffix = f'ch "{_escape(chord)}"'
    if token.endswith("}"):
        return f"{token[:-1]} {suffix}}}"
    return f"{token}{{{suffix}}}"


def _absorbable(
    note_slots: int, pos: int, next_slot: int, table: list[tuple[int, str, int]]
) -> int:
    """음 뒤 빈 구간에서 음길이에 흡수할 슬롯 수. 흡수하지 않으면 0.

    조건 두 개를 모두 만족해야 흡수한다.
      1) 빈 구간이 음길이보다 짧거나 같다 — 음보다 긴 쉼표는 진짜 쉼표다.
         (16분음표 뒤 8분쉼표는 흡수하지 않는다)
      2) 흡수하면 토큰 수가 줄어든다 — 예를 들어 홀수 슬롯의 16분음표는
         정렬 규칙 때문에 8분음표로 못 적어서 '16분 + 타이 16분'이 되는데,
         '16분 + 16분쉼표'와 토큰 수가 같으면서 읽기는 더 나쁘다.
    """
    if not ABSORB_REST_UP_TO_NOTE_LENGTH:
        return 0
    gap = next_slot - (pos + note_slots)
    if gap <= 0 or gap > note_slots:
        return 0
    merged = _token_count(note_slots + gap, pos, table)
    separate = _token_count(note_slots, pos, table) + _token_count(gap, pos + note_slots, table)
    return gap if merged < separate else 0


def _token_count(slots: int, pos: int, table: list[tuple[int, str, int]]) -> int:
    """슬롯 pos에서 slots만큼을 적는 데 필요한 토큰 수(정렬 규칙 분해 기준)."""
    count = 0
    remaining = slots
    cursor = pos
    while remaining > 0:
        size, _ = _largest_fitting(remaining, cursor, table)
        count += 1
        cursor += size
        remaining -= size
    return count


def _rests(pos: int, slots: int, table: list[tuple[int, str, int]]) -> list[str]:
    """슬롯 pos부터 slots만큼을 쉼표로 채운다.

    음표와 같은 정렬 규칙을 쓴다. 쉼표도 박 경계를 넘으면 나눠 적는 것이 정석이다.
    """
    out: list[str] = []
    remaining = slots
    cursor = pos
    while remaining > 0:
        size, duration = _largest_fitting(remaining, cursor, table)
        out.append(f"r.{duration}")
        cursor += size
        remaining -= size
    return out


def _ties(
    pos: int, slots: int, string: int, table: list[tuple[int, str, int]]
) -> list[str]:
    """슬롯 pos부터 slots만큼을 타이 토큰으로 채운다 (앞 마디에서 넘어온 음)."""
    out: list[str] = []
    remaining = slots
    cursor = pos
    while remaining > 0:
        size, duration = _largest_fitting(remaining, cursor, table)
        out.append(f"-.{string}.{duration}")
        cursor += size
        remaining -= size
    return out


def _render_sync(score: FrettedScore) -> list[str]:
    """마디마다 sync 포인트를 하나씩 발행한다.

    다운비트 시각이 곧 마디 시작이라 (barIndex, 0, ms, 0.0)으로 충분하다.
    비트마다 찍으면 파일만 커지고, 커서는 50ms 주기로 갱신되므로 마디 단위로
    충분히 따라온다.
    """
    lines = ["// 외부 오디오 동기화 지점 (마디 시작 = 다운비트)"]
    for bar in score.bars:
        ms = int(round(bar.start_sec * 1000))
        lines.append(f"\\sync ({bar.index} 0 {ms} 0.0)")
    return lines
