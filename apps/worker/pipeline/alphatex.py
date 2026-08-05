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
    """
    for size, token, _ in _duration_table(subdivision):
        if token == duration_token:
            return size
    raise ValueError(f"알 수 없는 음길이 표기: {duration_token!r}")


def build(
    score: FrettedScore,
    *,
    title: str = "Untitled",
    artist: str = "",
    include_sync: bool = True,
) -> str:
    """FrettedScore를 AlphaTex 문자열로 만든다."""
    _duration_table(score.subdivision)  # 지원 여부를 먼저 확인한다

    lines: list[str] = []
    lines.append(f'\\title "{_escape(title)}"')
    if artist:
        lines.append(f'\\subtitle "{_escape(artist)}"')
    lines.append(f"\\tempo {score.median_bpm:.0f}")
    lines.append(".")
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

    bar_texts = [_render_bar(bar, score.subdivision) for bar in score.bars]
    lines.append(" |\n".join(bar_texts))

    if include_sync:
        lines.append("")
        lines.extend(_render_sync(score))

    return "\n".join(lines) + "\n"


def _escape(text: str) -> str:
    return text.replace('"', "'")


def _tuning_names(tuning: list[int]) -> str:
    """alphaTab \\tuning은 낮은 현부터 나열한다. 내부 표현은 thin->thick이라 뒤집는다."""
    return " ".join(pretty_midi.note_number_to_name(p) for p in reversed(tuning))


def _render_bar(bar: FrettedBar, subdivision: int) -> str:
    """마디 하나를 AlphaTex 토큰 열로 적는다.

    음 하나의 길이를 한 토큰으로 못 적으면 박 경계에서 잘라 타이(-)로 잇는다.
    표기 가능한 길이 후보를 큰 것부터 훑어 정렬 규칙(_DURATION_TABLES의 align)을
    통과하는 첫 길이를 쓰고, 남은 만큼을 같은 방식으로 이어 붙인다.
    쉼표도 같은 규칙으로 쪼갠다(타이가 없으므로 전부 r.* 토큰이다).

    음의 실제 길이가 그대로 악보에 남는다. 쉼표는 음이 실제로 쉬는 구간에만
    나오므로 음 중간에 쉼표가 끼어들지 않는다.
    """
    table = _duration_table(subdivision)
    tokens: list[str] = []
    pos = 0

    # 음은 슬롯 순서로 처리하고 pos는 뒤로 가지 않는다. 그래서 음과 음 사이의
    # 빈 구간은 이미 "연속된 쉼표 구간 전체"다. 따로 합산할 필요가 없다.
    for note in sorted(bar.notes, key=lambda n: n.slot):
        if note.slot < pos:
            continue  # 단선율 전제 위반. 앞 음을 존중하고 건너뛴다.
        if note.slot > pos:
            tokens.extend(_rests(pos, note.slot - pos, table))
            pos = note.slot

        # 마디를 넘는 음은 마디 끝에서 자른다. 문법상 마디 넘김 타이도 가능하지만
        # (0.4.4 0.4.4 0.4.2 | -.4.4 ... 형태를 파서로 확인) 여기서는 쓰지 않는다.
        remaining = min(note.duration_slots, bar.slots_per_bar - pos)
        if remaining <= 0:
            continue

        # alphaTab 현 번호는 1부터, 가장 얇은 현이 1번
        string = note.string + 1
        first = True
        while remaining > 0:
            size, duration = _largest_fitting(remaining, pos, table)
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
    return " ".join(tokens)


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
