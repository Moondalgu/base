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

# AlphaTex가 받는 음길이 값
VALID_DURATIONS = {1, 2, 4, 8, 16, 32, 64}


class UnsupportedSubdivision(ValueError):
    pass


def build(
    score: FrettedScore,
    *,
    title: str = "Untitled",
    artist: str = "",
    include_sync: bool = True,
) -> str:
    """FrettedScore를 AlphaTex 문자열로 만든다."""
    slot_value = 4 * score.subdivision
    if slot_value not in VALID_DURATIONS:
        raise UnsupportedSubdivision(
            f"subdivision={score.subdivision}은 아직 지원하지 않습니다 "
            f"(슬롯 음길이 {slot_value}이 AlphaTex 값이 아님). 셋잇단 표기 필요."
        )

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
    tokens: list[str] = []
    pos = 0
    for note in sorted(bar.notes, key=lambda n: n.slot):
        if note.slot < pos:
            continue  # 단선율 전제 위반. 앞 음을 존중하고 건너뛴다.
        if note.slot > pos:
            tokens.extend(_rests(note.slot - pos, subdivision))
            pos = note.slot

        remaining = min(note.duration_slots, bar.slots_per_bar - pos)

        # 타이(-)를 쓰지 않는다. alphaTab 파서가 -.8 / -.16 형태를 거부하는 것을
        # 실측 확인했다(tools/probe_syntax.mjs). 대신 음길이를 2의 거듭제곱으로
        # 내림하고 남는 만큼을 쉼표로 채운다.
        # 대가: 실제 연주보다 음이 조금 짧게 표기될 수 있다. 리듬 위치는 정확하다.
        head = _largest_power_of_two(remaining)
        duration = (4 * subdivision) // head
        # alphaTab 현 번호는 1부터, 가장 얇은 현이 1번
        tokens.append(f"{note.fret}.{note.string + 1}.{duration}")
        if remaining > head:
            tokens.extend(_rests(remaining - head, subdivision))
        pos += remaining

    if pos < bar.slots_per_bar:
        tokens.extend(_rests(bar.slots_per_bar - pos, subdivision))

    # 음이 하나도 없는 마디도 박자만큼 쉼표로 채워야 alphaTab이 마디 길이를 맞춘다
    if not tokens:
        tokens = _rests(bar.slots_per_bar, subdivision)
    return " ".join(tokens)


def _rests(slots: int, subdivision: int) -> list[str]:
    return [f"r.{(4 * subdivision) // chunk}" for chunk in _decompose(slots)]


def _largest_power_of_two(slots: int) -> int:
    chunk = 1
    while chunk * 2 <= slots:
        chunk *= 2
    return chunk


def _decompose(slots: int) -> list[int]:
    """슬롯 수를 2의 거듭제곱 조각으로 쪼갠다. 큰 조각 우선.

    AlphaTex 음길이가 2의 거듭제곱만 받으므로, 5슬롯 같은 값은
    4 + 1로 나눠 타이/쉼표로 이어붙인다.
    """
    out: list[int] = []
    remaining = slots
    while remaining > 0:
        chunk = 1
        while chunk * 2 <= remaining:
            chunk *= 2
        out.append(chunk)
        remaining -= chunk
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
