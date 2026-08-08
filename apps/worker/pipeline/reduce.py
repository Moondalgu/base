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

## 참조 악보(사람 편곡) 문법 — 초급판 판단 기준 (2026-08-08 확정)

akbobada 초급 편곡판(드라우닝·예뻤어)을 마디 단위로 대조해 도출한 규칙.
"사람이 초보가 잘 칠 수 있게 바꾼 방식"이 하향 엔진의 정답 기준이다.

1. **곡 지배 밀도로 페달한다.** 마디별 검출 밀도를 따르지 않는다 — 검출이
   덜 잡힌 마디만 4분음표로 꺼지면 같은 그루브가 다른 리듬으로 적힌다.
2. **근음은 코드 체인지 단위(반마디)로 바뀐다.** 단 뒤 절반은 증거가
   충분할 때만(HALF_ROOT_MIN_*) — 마디 끝 픽업이 화성을 조기 전환시키면 안 된다.
3. **화성 가드: 근음은 코드 구성음이어야 한다.** 검출 반음 오차(B→C)는
   반음 이웃 교정 먼저, 재투표는 그 다음(픽업 승격 방지). 반마디 화성
   마디는 건드리지 않는다.
4. **같은 근음은 곡 안에서 같은 저옥타브.** 옥타브 튄 검출은 pc_floor로 내린다.
5. **성긴 마디(픽업·인트로 꼬리)는 검출 위치를 보존한다.** 슬롯 0부터
   깔면 마디 끝 픽업이 온음표로 둔갑한다. 참조는 쉼표+픽업으로 적는다.
6. **근음은 굵은 현(E·A)으로** — fretting.W_THIN_STRING이 담당.
7. 슬래시 코드(D♭m/E)는 베이스 음이 근음이다 — 검출이 이미 그렇게 낸다.

측정: 드라우닝 초급 근음 = 사람 채보(Songsterr) 95%. 어긋난 잔여는 아웃트로
필인 구간과 반마디 화성 해석 차이(참조 코드와는 일치 확인).
"""

from __future__ import annotations

from collections import Counter, defaultdict
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
    assessment: OriginalAssessment, *, rhythm_confident: bool = True
) -> list[int]:
    """이 곡에 제공할 단계.

    - **원곡이 이미 쉬우면** 원본 하나뿐이다. 더 깎아도 심심해지기만 한다.
    - **리듬을 믿을 수 없으면** 원본과 **초급**만 준다. 중급을 빼는 이유는
      아래에 있다.

    ## 리듬을 못 믿을 때 초급을 남기는 것이 요점이다

    처음에는 리듬 신뢰도가 낮으면 원본만 줬는데 **거꾸로였다.**

    레벨마다 리듬을 다루는 방식이 다르다(`LevelProfile.uniform_rhythm`).

    | 레벨 | 리듬 | 검출 리듬에 의존하는가 |
    |---|---|---|
    | 초급 | **균일 템플릿을 씌운다** | **아니오** |
    | 중급 | 원곡 리듬을 유지한다 | 예 |
    | 원본 | 검출 그대로 | 예 |

    **초급은 검출된 리듬을 버리고 균일 8분·4분으로 다시 적는다.** 그래서
    리듬 검출이 나쁠수록 초급이 상대적으로 안전해진다 — 틀린 리듬을 보여주는
    대신 읽을 수 있는 형태로 덮기 때문이다. 근음 정확도는 별개 축이고 반복
    구간에서 100%로 측정됐다.

    UI도 같은 판단을 이미 하고 있었다(`ScoreControls.MAX_TRUSTED_LEVEL_WHEN_MIXED
    = 1`: "리듬을 믿을 수 없을 때에도 신뢰할 수 있는 최고 단계"). 여기만 그것과
    어긋나 있었다.

    실측: 골든셋 4곡 전부 격자 정렬률이 0.95 미만이라 `rhythm_confident=False`다.
    원본만 주면 **하향 기능이 어느 곡에서도 안 열린다.**
    """
    if assessment.already_easy:
        return [ORIGINAL_LEVEL]
    if not rhythm_confident:
        # 균일 템플릿을 씌우는 단계만 남긴다. 중급은 원곡 리듬을 유지하므로
        # 틀린 리듬을 그대로 물려받는다.
        return sorted(
            level for level in LEVELS
            if level == ORIGINAL_LEVEL or LEVELS[level].uniform_rhythm
        )
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
    # 화성 가드가 코드 근음으로 스냅한 마디 수 (검출 근음이 반음 이웃이던 곳)
    harmony_snapped: int = 0

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
    score: QuantizedScore, level: int, *, verbose: bool = False,
    chord_tones: dict[int, frozenset[int]] | None = None,
) -> tuple[QuantizedScore, ReduceReport]:
    """난이도를 낮춘 악보를 만든다. 원본은 건드리지 않는다.

    chord_tones는 {마디 index: 코드 구성음 피치클래스 집합} — 오디오 화성 분석
    (chords.py, other 스템 크로마)에서 온 독립 증거다. 하향판의 **화성
    가드**로 쓴다: 마디가 단일 화성인데 베이스 근음이 코드 근음과 반음
    이웃이면 코드 쪽으로 스냅한다. 실측(드라우닝): Cm 마디 5곳에서 검출이
    B(반음 아래)를 근음으로 골라 화음이 깨졌다 — 코드 검출은 C를 냈다.
    반음 차이만 스냅한다(그 이상이면 코드 쪽이 틀렸을 수도 있다).
    """
    prof = profile_of(level)
    report = ReduceReport(level=level, level_name=prof.name, bars=len(score.bars))
    report.notes_before = sum(len(b.notes) for b in score.bars)

    if level == ORIGINAL_LEVEL:
        report.notes_after = report.notes_before
        return score, report

    target_sub = prof.subdivision if prof.uniform_rhythm else score.subdivision
    bars: list[Bar] = []

    # 참조 악보(akbobada 초급판)의 문법은 "곡 지배 밀도로 페달" — 마디마다
    # 밀도가 출렁이지 않는다. 마디별 검출 밀도를 그대로 따르면 **검출이 덜
    # 잡힌 마디만 4분음표로 꺼져서** 같은 그루브가 다른 리듬으로 적힌다
    # (드라우닝 9~12마디 실측). 그래서 곡 전체의 최빈 템플릿 밀도를 구해,
    # 활동이 그 절반 이상인 마디는 지배 밀도로 통일한다. 절반 미만(픽업·
    # 인트로 꼬리)은 마디별 밀도를 유지한다 — 안 친 구간에 음을 만들지 않는다.
    #
    # 근음 옥타브도 같은 원리로 통일한다. 검출이 옥타브 위(배음·주법)로 잡힌
    # 마디는 그 마디만 높게 적히는데, 참조 악보는 같은 코드면 같은 저음역이다.
    # 곡 안에서 그 피치클래스가 근음으로 쓰인 가장 낮은 옥타브로 내린다
    # (피치클래스는 그대로 — 근음 불변식 유지).
    modal_count = 0
    pc_floor: dict[int, int] = {}
    if prof.uniform_rhythm:
        counts: list[int] = []
        for bar in score.bars:
            r = bar_root(bar)
            if r is None:
                continue
            cap = min(prof.max_notes_per_bar, bar.beats_per_bar * target_sub)
            counts.append(_template_count(len(bar.notes), cap))
            pc_floor[r % 12] = min(pc_floor.get(r % 12, r), r)
        if counts:
            modal_count = Counter(counts).most_common(1)[0][0]

    for bar in score.bars:
        root = bar_root(bar)

        if prof.uniform_rhythm:
            # 근음은 반마디 단위로 본다 — 코드가 반마디로 바뀌는 곡(예뻤어
            # Am7♭5→A♭dim7)에서 마디당 근음 하나로 페달하면 뒤 코드가
            # 사라진다. 참조 악보 초급판이 실제로 반마디에 근음을 바꾼다.
            front, back = half_bar_roots(bar)
            # 화성 가드 — 단일 화성 마디(front==back pc)에서만. 반마디 화성
            # 마디는 마디 단위 코드로 재단할 수 없다(뒤 절반을 되돌려버린다).
            #
            # 규칙: **근음은 코드 구성음이어야 한다.** 실측(드라우닝 Fm 마디
            # 3곳): 검출이 {C, B, B, F}일 때 투표로 B(비구성음·반음 오차)가
            # 이겨 화음이 깨졌다. ①마디 안 코드 구성음 중 가중 최대로 교체,
            # ②구성음이 마디에 없으면 반음 이웃일 때만 스냅.
            if (chord_tones is not None and front is not None
                    and back is not None and front % 12 == back % 12):
                tones = chord_tones.get(bar.index)
                if tones and front % 12 not in tones:
                    # ① 반음 이웃 교정을 먼저 — 비구성음 근음의 가장 흔한
                    # 정체는 검출 반음 오차다(B는 C의 오검출). 재투표를 먼저
                    # 하면 마디 끝 픽업(다음 코드 선행음)이 근음으로 승격되는
                    # 오답이 나온다(실측: C 마디의 F 픽업이 이겼다).
                    want = min(
                        tones,
                        key=lambda pc: min((front - pc) % 12, (pc - front) % 12),
                    )
                    delta = (want - front) % 12
                    if delta > 6:
                        delta -= 12          # 최근접 방향 (반음 위/아래)
                    if abs(delta) == 1:
                        front += delta       # pc만 교정, 옥타브는 최근접 유지
                        back = front
                        report.harmony_snapped += 1
                    else:
                        # ② 반음 이웃이 없으면 마디 안 구성음 중 가중 최대
                        cand = _root_among(bar, tones)
                        if cand is not None:
                            front = back = cand
                            report.harmony_snapped += 1
            if front is not None:
                front = pc_floor.get(front % 12, front)
            if back is not None:
                back = pc_floor.get(back % 12, back)
            new_bar, stats = _templated_bar(
                bar, prof, target_sub, front,
                count_hint=modal_count, back_root=back,
            )
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


# 뒤 절반을 다른 근음으로 인정하기 위한 최소 증거. 마디 끝 픽업 한두 타
# (다음 코드를 미리 치는 관습)가 뒤 절반을 지배해버리면 화성이 반마디
# 일찍 바뀐다 — 실측: 이 기준 없이 예뻤어 근음 일치가 77%→54%로 무너졌다.
HALF_ROOT_MIN_NOTES = 2
HALF_ROOT_MIN_SLOTS_RATIO = 0.5   # 뒤 절반 길이의 절반 이상을 그 음이 채워야 한다


def half_bar_roots(bar: Bar) -> tuple[int | None, int | None]:
    """마디 앞/뒤 절반의 근음. 코드가 반마디로 바뀌는 곡(예뻤어 Am7♭5→A♭dim7)의
    참조 악보 문법이다 — 초급 페달이 마디당 근음 하나면 뒤 코드가 사라진다.

    단 뒤 절반은 **증거가 충분할 때만** 다른 근음으로 인정한다. 마디 끝
    픽업(다음 코드 선행)은 음 한두 개라 여기서 걸러진다. 증거가 부족하면
    앞 근음으로 페달을 잇는다.
    """
    half = bar.slots_per_bar // 2
    front_notes = [n for n in bar.notes if n.slot < half]
    back_notes = [n for n in bar.notes if n.slot >= half]
    fr = bar_root(replace(bar, notes=front_notes))
    br = bar_root(replace(bar, notes=back_notes))
    if fr is None:
        return br, br
    if br is None or br % 12 == fr % 12:
        return fr, fr

    # 뒤 절반 근음 피치클래스의 실제 점유를 본다
    root_notes = [n for n in back_notes if n.pitch % 12 == br % 12]
    covered = sum(min(n.duration_slots, bar.slots_per_bar - n.slot) for n in root_notes)
    if (len(root_notes) >= HALF_ROOT_MIN_NOTES
            and covered >= (bar.slots_per_bar - half) * HALF_ROOT_MIN_SLOTS_RATIO):
        return fr, br
    return fr, fr


def _root_among(bar: Bar, allowed_pcs: frozenset[int]) -> int | None:
    """허용 피치클래스(코드 구성음) 안에서 bar_root와 같은 가중 투표.

    화성 가드가 쓴다 — 비구성음이 투표에서 이겼을 때, 구성음들만 놓고
    다시 뽑는다. 마디에 구성음이 하나도 없으면 None.
    """
    filtered = [n for n in bar.notes if n.pitch % 12 in allowed_pcs]
    if not filtered:
        return None
    return bar_root(replace(bar, notes=filtered))


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
    bar: Bar, prof: LevelProfile, subdivision: int, root: int | None,
    count_hint: int = 0,
    back_root: int | None = None,
) -> tuple[Bar, dict]:
    """마디를 균일 리듬으로 다시 적고 앵커를 얹는다.

    순서가 중요하다 — 균일 격자를 먼저 깔고, 그 위에 앵커(다운비트·시그니처
    당김음)를 얹는다. 앵커를 나중에 얹으므로 격자에 없는 자리라도 살아남는다.

    count_hint는 곡 지배 밀도(reduce_score가 계산). 이 마디의 검출 활동이 그
    절반 이상이면 지배 밀도로 페달한다 — 검출 누락 마디가 혼자 다른 리듬으로
    꺼지는 것을 막는다(참조 악보 문법).
    """
    slots_per_bar = bar.beats_per_bar * subdivision
    empty = replace(bar, slots_per_bar=slots_per_bar, notes=[])
    stats = {"templated": False, "anchors": 0, "colour": 0}

    if root is None or not bar.notes:
        return empty, stats

    count = _template_count(len(bar.notes), min(prof.max_notes_per_bar, slots_per_bar))
    pedal = bool(count_hint) and len(bar.notes) * 2 >= count_hint
    if pedal:
        count = min(count_hint, slots_per_bar)
    if count <= 0:
        return empty, stats

    half = slots_per_bar // 2

    def root_at(slot: int) -> int:
        if back_root is not None and slot >= half:
            return back_root
        return root

    if count_hint and not pedal:
        # 성긴 마디(픽업·인트로 꼬리) — 참조 악보 문법: 검출된 **자리에서만**
        # 소리 낸다. 슬롯 0부터 균일하게 깔면 마디 끝 픽업 한 타가 온음표로
        # 둔갑한다(드라우닝 8마디 실측 — 참조는 쉼표 뒤 픽업이다).
        step = max(1, slots_per_bar // max(1, count_hint))
        seen: dict[int, QuantizedNote] = {}
        for n in sorted(bar.notes, key=lambda x: -x.amplitude):
            slot = min(slots_per_bar - step, round(n.slot / step) * step)
            if slot in seen:
                continue
            seen[slot] = replace(
                n, slot=slot, pitch=root_at(slot),
                duration_slots=min(n.duration_slots, step),
            )
        stats["templated"] = True
        return replace(empty, notes=sorted(seen.values(), key=lambda x: x.slot)), stats

    step = slots_per_bar // count
    amplitude = max(n.amplitude for n in bar.notes)
    residual = _mean_residual(bar)

    notes: list[QuantizedNote] = []
    for i in range(count):
        slot = i * step
        pitch, is_colour = _colour_pitch(bar, prof, root_at(slot), slot, slots_per_bar)
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
