"""AlphaTex 생성.

파이프라인의 최종 산출물. 음표 + 튜닝 + 박자/템포 + sync 포인트를 텍스트
한 파일에 담아 프론트의 alphaTab에 그대로 넘긴다. MusicXML/GuitarPro 중간
변환을 건너뛴다.

음표 문법: fret.string.duration  (string 1 = 가장 얇은 현)
sync 문법: \\sync (barIndex occurence millisecondOffset ratioPosition)
"""

from __future__ import annotations

import pretty_midi

from .fretting import FrettedBar, FrettedScore

class UnsupportedSubdivision(ValueError):
    pass


# 슬롯 수 -> AlphaTex 음길이 표기. 큰 것부터 정렬한다.
#
# 스윙(subdivision=3)은 셋잇단으로 적는다. 셔플·블루스는 흔하고, 스윙 곡을
# 16분 격자에 억지로 맞추면 리듬이 틀린다.
#   1박 = 3슬롯이므로
#     8분 셋잇단 = 1슬롯,  4분 셋잇단 = 2슬롯 (1박의 2/3)
#     2분 셋잇단 = 4슬롯,  온음표 셋잇단 = 8슬롯
# {tu 3} 문법은 alphaTab 파서에서 확인했다 ({tuplet 3} 풀네임은 거부된다).
_DURATION_TABLES: dict[int, list[tuple[int, str]]] = {
    4: [(16, "1"), (8, "2"), (4, "4"), (2, "8"), (1, "16")],
    3: [
        (12, "1"),
        (8, "1{tu 3}"),
        (6, "2"),
        (4, "2{tu 3}"),
        (3, "4"),
        (2, "4{tu 3}"),
        (1, "8{tu 3}"),
    ],
}


def _duration_table(subdivision: int) -> list[tuple[int, str]]:
    table = _DURATION_TABLES.get(subdivision)
    if table is None:
        raise UnsupportedSubdivision(
            f"subdivision={subdivision}은 지원하지 않습니다. "
            f"지원: {sorted(_DURATION_TABLES)}"
        )
    return table


def _largest_fitting(slots: int, table: list[tuple[int, str]]) -> tuple[int, str]:
    """슬롯 수 이하로 표기 가능한 가장 긴 음길이를 고른다."""
    for size, token in table:
        if size <= slots:
            return size, token
    return table[-1]


def slots_of(duration_token: str, subdivision: int) -> int:
    """음길이 표기를 슬롯 수로 되돌린다.

    산출물을 다시 읽어야 하는 쪽(eval/run_eval.py)이 파싱 규칙을 따로 두면
    셋잇단 같은 표기가 추가될 때마다 어긋난다. 표를 여기 하나만 둔다.
    """
    for size, token in _duration_table(subdivision):
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
    lines.append(f"\\staff{{tabs}} \\tuning {_tuning_names(score.tuning)}")
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
    table = _duration_table(subdivision)
    tokens: list[str] = []
    pos = 0

    for note in sorted(bar.notes, key=lambda n: n.slot):
        if note.slot < pos:
            continue  # 단선율 전제 위반. 앞 음을 존중하고 건너뛴다.
        if note.slot > pos:
            tokens.extend(_rests(note.slot - pos, table))
            pos = note.slot

        remaining = min(note.duration_slots, bar.slots_per_bar - pos)

        # 타이(-)를 쓰지 않는다. alphaTab 파서가 -.8 / -.16 형태를 거부하는 것을
        # 실측 확인했다(tools/probe_syntax.mjs). 대신 표기 가능한 가장 긴
        # 음길이로 내림하고 남는 만큼을 쉼표로 채운다.
        # 대가: 실제 연주보다 음이 조금 짧게 표기될 수 있다. 리듬 위치는 정확하다.
        head, duration = _largest_fitting(remaining, table)
        # alphaTab 현 번호는 1부터, 가장 얇은 현이 1번
        tokens.append(f"{note.fret}.{note.string + 1}.{duration}")
        if remaining > head:
            tokens.extend(_rests(remaining - head, table))
        pos += remaining

    if pos < bar.slots_per_bar:
        tokens.extend(_rests(bar.slots_per_bar - pos, table))

    # 음이 하나도 없는 마디도 박자만큼 쉼표로 채워야 alphaTab이 마디 길이를 맞춘다
    if not tokens:
        tokens = _rests(bar.slots_per_bar, table)
    return " ".join(tokens)


def _rests(slots: int, table: list[tuple[int, str]]) -> list[str]:
    """남은 슬롯을 쉼표로 채운다. 큰 단위부터 욕심껏 쪼갠다."""
    out: list[str] = []
    remaining = slots
    while remaining > 0:
        size, duration = _largest_fitting(remaining, table)
        out.append(f"r.{duration}")
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
