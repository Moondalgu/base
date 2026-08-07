"""악보 조립 — 노트와 비트 그리드에서 AlphaTex까지.

원본(`notes.json` + `beats.json`)에서 양자화 → 감산 → 이조 → 운지 → AlphaTex를
한 번에 만든다. 잡 실행 경로와 "레벨·이조·튜닝을 바꿔 다시 그려달라"는 요청
경로가 **같은 함수를 쓰게 하려고** 따로 뺐다. 두 경로가 갈라지면 웹에서 보는
악보와 파이프라인이 낸 악보가 조용히 달라진다.

여기서 채보는 다시 돌지 않는다. 노트는 이미 정해진 것이고, 바뀌는 것은
그것을 어떻게 적을지뿐이다.
"""

from __future__ import annotations

from dataclasses import dataclass

from . import alphatex, fretting, inertia, quantize, reduce
from .bassclean import Note
from .beats import BeatGrid
from .fretting import FrettedScore, TUNING_PRESETS
from .quantize import QuantizedScore
from .reduce import ReduceReport, UnsupportedLevel

# 원곡 그대로. 그보다 낮은 단계는 하향판이고 감산 규칙은 reduce.py가 담당한다.
ORIGINAL_LEVEL = reduce.ORIGINAL_LEVEL

# 이조 한계(반음). 오디오 피치 시프트 품질이 이 밖에서 무너지므로 악보만
# 더 옮길 수 있게 해도 함께 들을 수가 없다.
TRANSPOSE_LIMIT = 6


@dataclass
class BuiltScore:
    tex: str
    qscore: QuantizedScore
    fscore: FrettedScore
    level: int
    transpose: int
    # 하향으로 무엇이 얼마나 깎였는지. 원곡(Lv5)이면 깎은 것이 없다.
    reduction: ReduceReport
    # 이조로 4현 음역을 벗어나 옥타브를 접은 음 수. 0이 아니면 그 구간은
    # 원곡과 옥타브가 다르다는 뜻이라 사용자에게 알려줄 값이다.
    octave_folded: int
    # 표기 폴백이 걸렸는지. 셋잇단을 적을 수 없어 16분 격자로 되돌린 경우다.
    subdivision_forced: bool


def build(
    notes: list[Note],
    grid: BeatGrid,
    *,
    title: str = "Untitled",
    artist: str = "",
    tuning: str = "standard",
    level: int = ORIGINAL_LEVEL,
    transpose: int = 0,
    include_sync: bool = True,
    verbose: bool = False,
    chords: list[str] | None = None,
    key_signature: str | None = None,
) -> BuiltScore:
    """노트와 비트 그리드로 AlphaTex를 만든다.

    level은 난이도(1=초급 / 2=중급 / 3=원본). transpose는 반음 단위 이조이며 재생
    피치와 같은 값을 받아야 한다 — 악보와 소리가 어긋나면 연습 도구로 쓸 수 없다.
    """
    profile = reduce.profile_of(level)   # 없는 레벨이면 여기서 걸린다
    if abs(transpose) > TRANSPOSE_LIMIT:
        raise ValueError(
            f"이조 범위는 ±{TRANSPOSE_LIMIT}반음입니다 (요청: {transpose:+d})"
        )
    if tuning not in TUNING_PRESETS:
        raise ValueError(f"알 수 없는 튜닝 프리셋: {tuning}")

    working, octave_folded = _transpose(notes, transpose, TUNING_PRESETS[tuning])
    if verbose and octave_folded:
        print(f"[compose] 이조 {transpose:+d}반음, 음역 밖 {octave_folded}음을 옥타브 접음")

    def build_from(force_subdivision: int | None) -> tuple[
        QuantizedScore, FrettedScore, ReduceReport, str
    ]:
        qs = quantize.quantize(
            working, grid, verbose=verbose, force_subdivision=force_subdivision
        )
        # 패턴 관성 — 섹션 안의 리듬을 최빈 패턴으로 통일한다. 이것은 편집이
        # 아니라 **검출 보정**이다(반복 구조로 놓친 타현을 되살린다). 그래서
        # 하향보다 앞에 오고 원본 단계에도 적용된다.
        qs, _inertia_report = inertia.apply_inertia(qs, verbose=verbose)
        qs, report = reduce.reduce_score(qs, level, verbose=verbose)
        fs = fretting.assign(
            qs, tuning, verbose=verbose,
            max_fret=profile.max_fret, max_move=profile.max_move,
        )
        return qs, fs, report, alphatex.build(
            fs, title=title, artist=artist, include_sync=include_sync,
            chords=chords, key_signature=key_signature,
        )

    subdivision_forced = False
    try:
        qscore, fscore, reduction, tex = build_from(None)
    except alphatex.UnsupportedSubdivision as exc:
        # 예상 못 한 subdivision이면 스트레이트 16분으로 재양자화한다.
        # 리듬은 덜 정확해지지만 악보가 아예 안 나오는 것보다 낫다.
        if verbose:
            print(f"[compose] {exc}")
        qscore, fscore, reduction, tex = build_from(4)
        subdivision_forced = True

    return BuiltScore(
        tex=tex,
        qscore=qscore,
        fscore=fscore,
        level=level,
        transpose=transpose,
        octave_folded=octave_folded,
        subdivision_forced=subdivision_forced,
        reduction=reduction,
    )


def _transpose(
    notes: list[Note], semitones: int, tuning: list[int]
) -> tuple[list[Note], int]:
    """노트를 반음 단위로 옮긴다. 반환 (옮긴 노트, 옥타브를 접은 음 수).

    이조하면 원래 짚을 수 있던 음이 4현 밖으로 나간다. 내리면 개방 E 아래로,
    올리면 마지막 프렛 위로 벗어난다. 그 음만 옥타브 단위로 접어 음역 안에
    들여놓는다 — 버리면 라인에 구멍이 나고, 그대로 두면 운지에서 연주불가로
    떨어져 결국 사라진다.

    음역은 튜닝에서 직접 구한다. 상수로 박아두면 드롭D나 반음 내림 튜닝에서
    틀린 경계를 쓰게 된다.
    """
    if semitones == 0:
        return notes, 0

    lowest = min(tuning)
    highest = max(tuning) + fretting.NFRETS

    moved: list[Note] = []
    folded = 0
    for note in notes:
        pitch = note.pitch + semitones
        original = pitch
        while pitch < lowest:
            pitch += 12
        while pitch > highest:
            pitch -= 12
        if pitch != original:
            folded += 1
        moved.append(
            Note(
                start=note.start,
                end=note.end,
                pitch=pitch,
                amplitude=note.amplitude,
                detected_end=note.detected_end,
                # 음량을 함께 옮기지 않으면 이조한 순간 시그니처 당김음 판정이
                # 죽는다(그 판정은 loudness로만 한다).
                loudness=note.loudness,
            )
        )
    return moved, folded
