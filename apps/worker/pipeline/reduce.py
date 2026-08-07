"""난이도 하향 — 원곡 채보를 초보자가 읽을 수 있는 형태로 깎는다.

원곡 채보가 상한이다. 상향은 편곡이므로 하지 않는다.

## 단계는 셋이다

원본 / 중급 / 초급. 더 쪼개면 사용자가 차이를 못 느끼고, 우리가 실제로 구분해
낼 수 있는 축(리듬 세분 · 화성 어휘 · 손 이동)도 셋을 넘지 않는다.

**원곡이 이미 쉬우면 단계를 만들지 않는다.** 참조 악보 수준(균일 8분 · 마디당
근음 하나 · 저프렛)으로 이미 연주되는 곡을 더 깎으면 원곡보다 심심해지기만
한다. `assess_original()`이 그 판정을 한다.

## 불변식 — 어떤 단계에서도 깨지 않는다

1. **시간축 불변.** 마디 수·박자·마디 시각을 바꾸지 않는다. 원곡 음원과 함께
   재생되고 커서가 그 위를 달리므로 시간축이 틀어지면 도구가 죽는다.
2. **근음 불변.** 마디의 근음은 마지막까지 남는다.
3. **다운비트에 음이 있다 — 균일 템플릿 단계(초급)에서만.** 원곡이 1박을
   쉬어도 초급판은 1박에 근음을 놓는다. 초보자가 마디 위치를 잃지 않게 하려는
   것이다. 단 원곡이 통째로 쉬는 마디는 비워둔다 — 안 치는 구간에 음을 만들어
   넣는 것은 다른 곡을 적는 것이다.

   **중급에는 적용하지 않는다.** 중급은 원곡 리듬을 유지하는 단계이므로 원곡이
   당김음으로 1박을 비웠으면 그것이 정답이다. 억지로 채우면 "원곡 리듬 유지"라는
   중급의 정의를 깨고 리듬이 달라진다.
4. **4현·저프렛 안에서 연주 가능하다.** 프렛 상한·이동 폭은 `fretting`이 맡는다.

## "몇 음을 남길까"가 아니라 "어느 음을 남길까"

균일 간격으로 근음만 놓으면 안전하지만 기계적이다. 원곡의 리듬감은 **어느 음을
남기는가**에서 나온다. 그래서 두 가지를 얹는다.

- **앵커(anchor)**: 마디에서 반드시 살리는 온셋. 다운비트와 **그 마디에서 가장
  센 엇박**이다. 곡을 상징하는 당김음이 여기 걸린다. 균일 격자를 깔고 그 위에
  앵커를 얹는 순서로 만든다.
- **근음 + 5도 + 옥타브**: 근음만 남기지 않는다. 원곡 음이 근음의 5도나 옥타브면
  그대로 살린다. 이 세 음은 운지가 근음 옆에 붙어 있어 초보자도 짚기 쉬운데
  소리는 훨씬 풍성하다.

## 도수는 근음만 알면 구할 수 있다

화성 분석 없이도 근음 대비 반음 거리로 도수를 안다(유니슨·옥타브 0, 3도 3~4,
5도 7, 7도 10~11). 그래서 화성 어휘를 깎는 것이 코드 인식 없이 구현된다.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field, replace

from .quantize import Bar, QuantizedNote, QuantizedScore

# 단계 번호. 클수록 어렵다(원본이 상한).
BEGINNER = 1
INTERMEDIATE = 2
ORIGINAL_LEVEL = 3

# 근음 대비 반음 거리 -> 도수 분류. 옥타브로 접어서 본다.
UNISON_OCTAVE = (0,)
THIRDS = (3, 4)
FIFTHS = (7,)
SEVENTHS = (10, 11)
# 위에 없는 거리(1,2,5,6,8,9)는 경과음·크로매틱으로 본다.

# 마디 근음을 고를 때 다운비트 음에 주는 가중치. 베이시스트는 마디 첫 박에
# 루트를 짚으므로 그 음이 근음일 확률이 높다.
DOWNBEAT_WEIGHT = 3.0


@dataclass(frozen=True)
class LevelProfile:
    """단계별로 어디까지 깎는지."""

    level: int
    name: str
    hint: str
    # 리듬을 균일 템플릿으로 덮어쓸지. False면 원곡 리듬을 유지한다.
    uniform_rhythm: bool
    # 템플릿을 쓸 때의 격자(비트당 슬롯). 균일화하지 않으면 무시된다.
    subdivision: int
    # 마디당 최대 음 수. 균일화할 때 밀도에 따라 이 안에서 고른다.
    max_notes_per_bar: int
    # 남길 도수. 여기 없는 도수는 근음으로 바꾼다.
    keep_intervals: tuple[int, ...]
    # 마디에서 가장 센 엇박을 살릴지 (시그니처 당김음 보존)
    keep_anchors: bool
    # 운지 제약 (fretting에 넘긴다). None이면 제약 없음.
    max_fret: int | None
    max_move: int | None


LEVELS: dict[int, LevelProfile] = {
    BEGINNER: LevelProfile(
        level=BEGINNER, name="초급",
        hint="균일한 리듬 + 근음·5도·옥타브, 저프렛",
        uniform_rhythm=True, subdivision=2, max_notes_per_bar=8,
        keep_intervals=UNISON_OCTAVE + FIFTHS,
        keep_anchors=True, max_fret=7, max_move=3,
    ),
    INTERMEDIATE: LevelProfile(
        level=INTERMEDIATE, name="중급",
        hint="원곡 리듬 유지, 경과음·크로매틱만 정리",
        uniform_rhythm=False, subdivision=0, max_notes_per_bar=0,
        keep_intervals=UNISON_OCTAVE + THIRDS + FIFTHS + SEVENTHS,
        keep_anchors=True, max_fret=12, max_move=5,
    ),
    ORIGINAL_LEVEL: LevelProfile(
        level=ORIGINAL_LEVEL, name="원본",
        hint="채보 결과 그대로",
        uniform_rhythm=False, subdivision=0, max_notes_per_bar=0,
        keep_intervals=tuple(range(12)),
        keep_anchors=True, max_fret=None, max_move=None,
    ),
}


# ─── 원곡이 이미 쉬운지 판정 ────────────────────────────────────────────────
#
# 기준선은 참조 악보(akbobada 초급 편곡판)의 실측값이다.
#   드라우닝: 마디당 8음 고정, 최소 8분, 마디당 근음 하나, 프렛 1~9
#   예뻤어:   마디당 4~8음, 최소 8분(일부 16분), 마디당 근음 하나, 프렛 1~10
# 원곡이 이 범위 안에서 연주되면 더 깎을 것이 없다.

# 마디당 서로 다른 피치가 이보다 많으면 화성 어휘가 초급을 넘는다.
EASY_MAX_PITCHES_PER_BAR = 2.0
# 16분 격자를 요구하는 온셋 비율이 이보다 크면 리듬이 초급을 넘는다.
# quantize.SIXTEENTH_REQUIRED_RATIO와 같은 값을 쓴다 — 같은 질문이다.
EASY_MAX_SIXTEENTH_RATIO = 0.05
# 마디당 음이 이보다 많으면 밀도가 초급을 넘는다.
EASY_MAX_NOTES_PER_BAR = 9.0


@dataclass
class OriginalAssessment:
    """원곡 자체의 난이도. 하향 단계를 제공할지 결정한다."""

    already_easy: bool
    notes_per_bar: float
    pitches_per_bar: float
    sixteenth_ratio: float
    reason: str

    def to_dict(self) -> dict:
        return {
            "alreadyEasy": self.already_easy,
            "notesPerBar": round(self.notes_per_bar, 2),
            "pitchesPerBar": round(self.pitches_per_bar, 2),
            "sixteenthRatio": round(self.sixteenth_ratio, 4),
            "reason": self.reason,
        }


def assess_original(score: QuantizedScore) -> OriginalAssessment:
    """원곡이 이미 초급 수준인지 본다.

    쉬운 곡을 더 깎으면 원곡보다 심심해지기만 한다. 그런 곡에는 단계를 만들지
    않고 원본 하나만 보여주는 것이 맞다.

    프렛은 보지 않는다 — 운지는 우리가 정하는 것이라 원곡의 난이도가 아니다.
    """
    active = [bar for bar in score.bars if bar.notes]
    if not active:
        return OriginalAssessment(
            already_easy=True, notes_per_bar=0.0, pitches_per_bar=0.0,
            sixteenth_ratio=score.sixteenth_ratio,
            reason="연주 구간이 없어 하향할 것이 없습니다",
        )

    notes_per_bar = sum(len(b.notes) for b in active) / len(active)
    pitches_per_bar = sum(len({n.pitch for n in b.notes}) for b in active) / len(active)

    reasons = []
    if notes_per_bar > EASY_MAX_NOTES_PER_BAR:
        reasons.append(f"마디당 {notes_per_bar:.1f}음")
    if pitches_per_bar > EASY_MAX_PITCHES_PER_BAR:
        reasons.append(f"마디당 서로 다른 음 {pitches_per_bar:.1f}개")
    if score.sixteenth_ratio > EASY_MAX_SIXTEENTH_RATIO:
        reasons.append(f"16분 리듬 {100 * score.sixteenth_ratio:.0f}%")

    if reasons:
        return OriginalAssessment(
            already_easy=False, notes_per_bar=notes_per_bar,
            pitches_per_bar=pitches_per_bar, sixteenth_ratio=score.sixteenth_ratio,
            reason="하향이 도움이 됩니다 — " + ", ".join(reasons),
        )
    return OriginalAssessment(
        already_easy=True, notes_per_bar=notes_per_bar,
        pitches_per_bar=pitches_per_bar, sixteenth_ratio=score.sixteenth_ratio,
        reason=(
            f"원곡이 이미 초급 수준입니다 (마디당 {notes_per_bar:.1f}음, "
            f"서로 다른 음 {pitches_per_bar:.1f}개, 16분 리듬 "
            f"{100 * score.sixteenth_ratio:.0f}%)"
        ),
    )


def available_levels(
    assessment: OriginalAssessment, *, practice_video: bool = False
) -> list[int]:
    """이 곡에 제공할 단계. 둘 중 하나라도 걸리면 원본 하나뿐이다.

    - **원곡이 이미 쉬우면** 더 깎아도 심심해지기만 한다.
    - **연습 영상(베이스 둘)이면** 하향이 오히려 해롭다. 하향은 검출된 음 수로
      밀도를 정하는데 두 연주가 섞이면 그 밀도가 실제 연주와 무관하고 근음도
      흔들린다. 게다가 이미 누군가 연습용으로 만들어 화면 악보까지 붙여둔
      자료다. 우리가 또 깎을 이유가 없다. (`diagnose.py` 참조)
    """
    if assessment.already_easy or practice_video:
        return [ORIGINAL_LEVEL]
    return sorted(LEVELS)


# ─── 하향 ──────────────────────────────────────────────────────────────────


@dataclass
class ReduceReport:
    level: int
    level_name: str
    bars: int = 0
    notes_before: int = 0
    notes_after: int = 0
    # 근음으로 바꾼 음(삭제가 아니라 대체다 — 리듬 감각을 끊지 않기 위해)
    replaced_with_root: int = 0
    # 도수 필터로 근음으로 바꾼 음
    replaced_nonharmonic: int = 0
    # 균일 템플릿을 씌운 마디 수
    templated_bars: int = 0
    # 원곡이 통째로 쉬어서 그대로 비운 마디 수
    silent_bars: int = 0
    # 시그니처 당김음으로 살린 온셋 수
    anchors_kept: int = 0
    # 5도·옥타브로 살린 음 수 (근음만 남기지 않은 덕에 풍성해진 만큼)
    colour_notes: int = 0

    def to_dict(self) -> dict:
        return {
            "level": self.level,
            "levelName": self.level_name,
            "bars": self.bars,
            "notesBefore": self.notes_before,
            "notesAfter": self.notes_after,
            "replacedWithRoot": self.replaced_with_root,
            "replacedNonharmonic": self.replaced_nonharmonic,
            "templatedBars": self.templated_bars,
            "silentBars": self.silent_bars,
            "anchorsKept": self.anchors_kept,
            "colourNotes": self.colour_notes,
        }


class UnsupportedLevel(ValueError):
    pass


def profile_of(level: int) -> LevelProfile:
    p = LEVELS.get(level)
    if p is None:
        raise UnsupportedLevel(
            f"level={level}은 없습니다. 지원: {sorted(LEVELS)} "
            f"({ORIGINAL_LEVEL}=원본, 낮을수록 쉬움)"
        )
    return p


def reduce_score(
    score: QuantizedScore, level: int, *, verbose: bool = False
) -> tuple[QuantizedScore, ReduceReport]:
    """난이도를 낮춘 악보를 만든다. 원본은 건드리지 않는다."""
    prof = profile_of(level)
    report = ReduceReport(level=level, level_name=prof.name, bars=len(score.bars))
    report.notes_before = sum(len(b.notes) for b in score.bars)

    if level == ORIGINAL_LEVEL:
        report.notes_after = report.notes_before
        return score, report

    target_sub = prof.subdivision if prof.uniform_rhythm else score.subdivision
    bars: list[Bar] = []

    for bar in score.bars:
        root = bar_root(bar)

        if prof.uniform_rhythm:
            new_bar, stats = _templated_bar(bar, prof, target_sub, root)
            if stats["templated"]:
                report.templated_bars += 1
            else:
                report.silent_bars += 1
            report.anchors_kept += stats["anchors"]
            report.colour_notes += stats["colour"]
        else:
            new_bar, replaced = _filtered_bar(bar, prof, root)
            report.replaced_nonharmonic += replaced
            if not bar.notes:
                report.silent_bars += 1
        bars.append(new_bar)

    report.notes_after = sum(len(b.notes) for b in bars)
    if prof.uniform_rhythm:
        report.replaced_with_root = report.notes_after - report.colour_notes

    reduced = replace(
        score, bars=bars, subdivision=target_sub, note_count=report.notes_after
    )

    if verbose:
        print(
            f"[reduce] Lv{level}({prof.name}): {report.notes_before} -> "
            f"{report.notes_after}음, subdiv {score.subdivision}->{target_sub}, "
            f"템플릿 {report.templated_bars}마디, 쉼표 {report.silent_bars}마디, "
            f"당김음 {report.anchors_kept}, 5도·옥타브 {report.colour_notes}, "
            f"비화성음 대체 {report.replaced_nonharmonic}"
        )
    return reduced, report


def bar_root(bar: Bar) -> int | None:
    """마디의 근음(MIDI 피치)을 고른다. 음이 없으면 None.

    지배 피치클래스를 지속시간·진폭으로 가중해 고르고, 다운비트 음에 가중치를
    더 준다. 그 다음 그 피치클래스를 가진 실제 음 중 **가장 낮은 것**을 근음
    피치로 쓴다 — 베이스 라인의 근음은 낮게 짚는 것이 관습이고, 낮은 쪽이
    저프렛에 들어올 확률도 높다.
    """
    if not bar.notes:
        return None

    weights: dict[int, float] = defaultdict(float)
    for note in bar.notes:
        w = max(1, note.duration_slots) * max(0.1, note.amplitude)
        if note.slot == 0:
            w *= DOWNBEAT_WEIGHT
        weights[note.pitch % 12] += w

    best_class = max(weights, key=lambda pc: weights[pc])
    candidates = [n.pitch for n in bar.notes if n.pitch % 12 == best_class]
    return min(candidates) if candidates else min(n.pitch for n in bar.notes)


def signature_offbeat(bar: Bar, subdivision: int) -> QuantizedNote | None:
    """그 마디에서 가장 센 엇박. 곡을 상징하는 당김음이 여기 걸린다.

    엇박 = 8분 자리가 아닌 슬롯. subdivision이 4(16분 격자)면 홀수 슬롯이,
    2(8분 격자)면 엇박이 없다(모든 슬롯이 8분 자리다).

    세기는 **실제 음량(loudness)**으로 본다. `amplitude`는 CREPE 확신도라서
    "센 음"과 무관하다(상관계수 -0.20).
    """
    if subdivision < 4 or not bar.notes:
        return None
    step = subdivision // 2      # 8분 자리 간격 (16분 격자에서 2)
    offbeats = [n for n in bar.notes if n.slot % step != 0]
    if not offbeats:
        return None
    strongest = max(offbeats, key=lambda n: n.loudness)
    # 음량을 재지 않았으면 판정하지 않는다. 0끼리 비교해 아무 음이나 고르면
    # 시그니처가 아니라 잡음을 살리는 것이 된다.
    return strongest if strongest.loudness > 0 else None


def _template_count(original_notes: int, max_notes: int) -> int:
    """원곡 마디의 음 밀도에 맞는 템플릿 음 수. 2의 거듭제곱으로 떨어뜨린다.

    안 친 구간에 음을 만들어 넣지 않으려면 밀도를 봐야 한다. 음이 두 개뿐인
    마디에 8분 여덟 개를 넣는 것은 다른 곡을 적는 것이다.
    """
    if original_notes <= 0:
        return 0
    count = 1
    while count * 2 <= max_notes and count * 2 <= original_notes:
        count *= 2
    return count


def _colour_pitch(
    bar: Bar, prof: LevelProfile, root: int, target_slot: int, span: int
) -> tuple[int, bool]:
    """템플릿 슬롯에 놓을 음높이. 반환 (피치, 근음이 아닌 색채음인가).

    근음만 남기지 않는다. 그 자리 근처에서 원곡이 실제로 연주한 음이 근음의
    5도나 옥타브면 그대로 살린다 — 운지가 근음 옆이라 짚기 쉬운데 소리는
    훨씬 풍성하다.

    다운비트는 항상 근음이다(불변식 3). 색채음은 그 외 자리에만 놓는다.
    """
    if target_slot == 0:
        return root, False

    # 원곡 슬롯 좌표계와 템플릿 좌표계가 다를 수 있으므로 비율로 맞춘다.
    ratio = bar.slots_per_bar / span if span else 1.0
    origin = target_slot * ratio
    nearby = [n for n in bar.notes if abs(n.slot - origin) <= ratio]
    if not nearby:
        return root, False

    closest = min(nearby, key=lambda n: abs(n.slot - origin))
    interval = (closest.pitch - root) % 12
    if interval in prof.keep_intervals and interval != 0:
        return closest.pitch, True
    # 옥타브 위 근음도 색채음으로 인정한다(도수는 0이지만 소리가 다르다).
    if interval == 0 and closest.pitch != root:
        return closest.pitch, True
    return root, False


def _templated_bar(
    bar: Bar, prof: LevelProfile, subdivision: int, root: int | None
) -> tuple[Bar, dict]:
    """마디를 균일 리듬으로 다시 적고 앵커를 얹는다.

    순서가 중요하다 — 균일 격자를 먼저 깔고, 그 위에 앵커(다운비트·시그니처
    당김음)를 얹는다. 앵커를 나중에 얹으므로 격자에 없는 자리라도 살아남는다.
    """
    slots_per_bar = bar.beats_per_bar * subdivision
    empty = replace(bar, slots_per_bar=slots_per_bar, notes=[])
    stats = {"templated": False, "anchors": 0, "colour": 0}

    if root is None or not bar.notes:
        return empty, stats

    count = _template_count(len(bar.notes), min(prof.max_notes_per_bar, slots_per_bar))
    if count <= 0:
        return empty, stats

    step = slots_per_bar // count
    amplitude = max(n.amplitude for n in bar.notes)
    residual = _mean_residual(bar)

    notes: list[QuantizedNote] = []
    for i in range(count):
        slot = i * step
        pitch, is_colour = _colour_pitch(bar, prof, root, slot, slots_per_bar)
        if is_colour:
            stats["colour"] += 1
        notes.append(
            QuantizedNote(
                slot=slot,
                duration_slots=step,
                pitch=pitch,
                amplitude=amplitude,
                # 템플릿으로 만든 음은 검출 위치에서 온 것이 아니다. 잔차를 0으로
                # 두면 "완벽하게 맞았다"는 거짓 신호가 되므로 원곡 잔차를 쓴다.
                residual=residual,
                low_confidence=False,
                loudness=max((n.loudness for n in bar.notes), default=0.0),
            )
        )

    # 시그니처 당김음을 얹는다. 균일 격자에 없는 자리이므로 앞 음의 길이를
    # 줄여 자리를 만든다 — 마디 길이는 불변이어야 한다.
    anchor = signature_offbeat(bar, bar.slots_per_bar // bar.beats_per_bar)
    if prof.keep_anchors and anchor is not None:
        placed = _place_anchor(notes, anchor, bar, prof, root, slots_per_bar)
        if placed:
            stats["anchors"] += 1

    stats["templated"] = True
    return replace(empty, notes=notes), stats


def _place_anchor(
    notes: list[QuantizedNote],
    anchor: QuantizedNote,
    bar: Bar,
    prof: LevelProfile,
    root: int,
    slots_per_bar: int,
) -> bool:
    """시그니처 당김음을 템플릿 위에 얹는다. 얹었으면 True.

    템플릿 슬롯과 겹치면 얹을 필요가 없다(이미 그 자리에 음이 있다). 겹치지
    않으면 그 자리에 음을 넣고 **앞 음의 길이를 줄여** 마디 길이를 지킨다.
    """
    # 원곡 좌표를 템플릿 좌표로 옮긴다.
    ratio = slots_per_bar / bar.slots_per_bar if bar.slots_per_bar else 1.0
    slot = int(round(anchor.slot * ratio))
    if slot <= 0 or slot >= slots_per_bar:
        return False
    if any(n.slot == slot for n in notes):
        return False

    prev = [n for n in notes if n.slot < slot]
    if not prev:
        return False
    before = max(prev, key=lambda n: n.slot)
    room = slot - before.slot
    if room < 1:
        return False

    interval = (anchor.pitch - root) % 12
    pitch = anchor.pitch if interval in prof.keep_intervals else root

    following = [n for n in notes if n.slot > slot]
    end = min((n.slot for n in following), default=slots_per_bar)
    before.duration_slots = room
    notes.append(
        QuantizedNote(
            slot=slot,
            duration_slots=max(1, end - slot),
            pitch=pitch,
            amplitude=anchor.amplitude,
            residual=anchor.residual,
            low_confidence=False,
            loudness=anchor.loudness,
        )
    )
    notes.sort(key=lambda n: n.slot)
    return True


def _mean_residual(bar: Bar) -> float:
    if not bar.notes:
        return 0.0
    return sum(n.residual for n in bar.notes) / len(bar.notes)


def _filtered_bar(
    bar: Bar, prof: LevelProfile, root: int | None
) -> tuple[Bar, int]:
    """도수 필터만 적용한다. 리듬과 슬롯은 원곡 그대로. 반환 (새 마디, 대체 수)."""
    if root is None or not bar.notes:
        return replace(bar, notes=list(bar.notes)), 0

    keep = set(prof.keep_intervals)
    notes: list[QuantizedNote] = []
    replaced = 0
    for note in bar.notes:
        interval = (note.pitch - root) % 12
        if interval in keep:
            notes.append(note)
            continue
        # 삭제하지 않고 근음으로 바꾼다. 음이 사라지면 리듬 감각이 끊긴다.
        octave = (note.pitch - root) // 12
        notes.append(replace(note, pitch=root + 12 * max(0, octave)))
        replaced += 1
    return replace(bar, notes=notes), replaced
