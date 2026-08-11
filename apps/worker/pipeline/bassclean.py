"""베이스 특화 후처리.

basic-pitch는 다성 모델이라 베이스 한 음의 배음을 별도 음으로 검출한다.
스모크 테스트 실측: E1 8음짜리 라인에서 29개 이벤트가 나왔고, 그중 상당수가
E3(+24), G3, A3 같은 배음이었다. 그대로 탭으로 만들면 9·12·14프렛에
존재하지 않는 음이 찍힌다.

베이스는 단선율이라는 전제를 쓸 수 있어서 이 정리가 가능하다.
기타였다면 화음과 배음을 구분할 방법이 없다.

프레임당 피치를 하나만 내는 엔진(CREPE)의 출력은 성질이 다르다. 배음
거짓 음도 조각도 동시 발음도 없으므로 걸러낼 대상이 없다. 그 경우는
clean(monophonic_source=True)로 해당 단계들을 건너뛴다.
"""

from __future__ import annotations

import json
import statistics
from dataclasses import asdict, dataclass
from pathlib import Path

# 4현 베이스 실용 음역: E1(28) ~ G2 20프렛(63)
BASS_MIDI_MIN = 28
# 20프렛 4현 베이스의 1현 20프렛이 E4(64). 63은 그 바로 아래 실용 상한이다.
# 21·24프렛 악기는 더 올라가지만 범용값으로 20프렛을 쓴다.
BASS_MIDI_MAX = 63

# 배음이 나타나는 반음 간격: 옥타브, 옥타브+5도, 2옥타브, 2옥타브+장3도
HARMONIC_INTERVALS = (12, 19, 24, 28, 31)

# 이보다 짧으면 노이즈로 간주.
# **추측(위험)이다** — 슬랩 고스트 노트와 16비트 뮤트 타격은 이보다 짧을 수 있고,
# 우리 슬랩 누락 51.7%와 무관하지 않을 가능성이 있다. IDMT 어노테이션의
# `excitationStyle`로 주법별 정답 음 길이 분포를 뽑으면 무엇을 자르고 있는지
# 바로 나온다. 아직 안 했다 (POLICY.md 4.1).
MIN_NOTE_SEC = 0.06
# basic-pitch amplitude 하한. **basic-pitch 경로 전용**이라 기본 엔진(CREPE)에서는
# 쓰이지 않는다 — clean(monophonic_source=True)가 해당 단계를 건너뛴다.
MIN_AMPLITUDE = 0.25
# 같은 피치가 이 간격 이내로 이어지면 한 음으로 병합.
# **basic-pitch 경로 전용.** 재타현 분리(reattack.py)와 방향이 반대인 규칙이지만
# 충돌하지 않는다 — CREPE 경로는 병합 단계를 아예 건너뛴다(POLICY.md 6장).
MERGE_GAP_SEC = 0.04
# 이만큼 겹치면 동시 발음으로 본다. **basic-pitch 경로 전용.**
OVERLAP_TOLERANCE = 0.05

# 같은 피치가 이어질 때 '한 음이 쪼개진 조각'인지 '다시 친 것'인지 가르는 기준.
# 다시 치면 진폭이 오르고(정답 데이터셋 중앙값 1.25배), 조각은 감쇠 중이라
# 앞 조각보다 낮다(중앙값 0.87배). 온셋 간격으로는 갈리지 않는다.
MERGE_MAX_AMPLITUDE_RATIO = 0.8
# 앞 음이 이 길이(박) 이하이면 "한 번 뜯은 음의 조각"으로 보고 진폭비를 묻지
# 않고 병합한다. 한 번 뜯은 음의 앞머리가 16분음표(0.25박)보다 짧게 끊길 수는
# 없다는 연주 사실에 기댄 값이고, 골든셋 스윙(none/0.2/0.3/0.4)에서 0.3이
# 최적이었다. 0.4로 올리면 Drowning 타현이 82%→33%로 무너진다(진짜 8분 페달을
# 삼킨다). **CREPE 출력에만 적용된다** — clean()의 주석 참조.
SHORT_PREV_BEATS = 0.3

# 스템 분리가 불완전해 베이스가 쉬는 구간에 다른 악기 배음이 누출되고,
# basic-pitch가 이를 음으로 오검출하는 경우가 있다. 절대 피치로는 판정할
# 수 없다(곡마다 베이스 음역이 다르다). 대신 그 곡 안에서 확실히 믿을 만한
# (진폭이 큰) 음들로 실제 음역을 추정하고, 그보다 한참 위에 있으면서
# 약한 음만 누출로 간주해 버린다.
LEAKAGE_CONFIDENT_AMPLITUDE = 0.6    # 이 이상이면 음역 추정에 쓸 만큼 믿는다
# 반음. 곡의 베이스 음역 위로 이만큼을 넘으면 의심.
# **추측(위험)** — 14는 장9도이고 베이스가 필인·코러스에서 옥타브 위(12반음)
# 이상으로 도약하는 것은 정상이다. 약하게 연주한 고음역 멜로디나 하모닉스가
# 누출로 오인될 수 있다(POLICY.md 4.2).
LEAKAGE_REGISTER_MARGIN = 14
# 이만큼 세면 고음역이어도 실연주로 인정한다. 위와 같은 등급(POLICY.md 4.2).
LEAKAGE_STRONG_AMPLITUDE = 0.85


@dataclass
class Note:
    start: float
    end: float
    pitch: int
    # CREPE periodicity(피치 확신도)다. **음량이 아니다.** 음량으로 오해해
    # 필터를 걸면 엉뚱한 것을 자른다 — 실측 상관계수 -0.20으로 거의 무관하다.
    # 음량이 필요하면 `loudness`를 쓴다.
    amplitude: float
    # basic-pitch가 검출한 원래 end. step5가 겹침 해소로 end를 잘라내도
    # 이 값은 그대로 둬서, step6 병합 판정이 잘린 end가 아니라 실제 검출
    # 구간 기준으로 이뤄지게 한다.
    detected_end: float = 0.0
    # 음 구간의 실제 음량(RMS). `measure_loudness()`가 오디오에서 채운다.
    # 0.0은 "재지 않았다"는 뜻이다.
    loudness: float = 0.0

    @property
    def duration(self) -> float:
        return self.end - self.start

    def overlaps(self, other: "Note") -> bool:
        return (
            min(self.end, other.end) - max(self.start, other.start)
            > OVERLAP_TOLERANCE
        )


@dataclass
class CleanReport:
    """품질 게이트에 넘길 통계."""

    input_count: int
    output_count: int
    dropped_harmonic: int
    dropped_out_of_range: int
    dropped_short: int
    dropped_overlap: int
    merged: int
    dropped_truncated: int = 0
    dropped_leakage: int = 0

    @property
    def out_of_range_ratio(self) -> float:
        return self.dropped_out_of_range / self.input_count if self.input_count else 0.0

    @property
    def harmonic_ratio(self) -> float:
        return self.dropped_harmonic / self.input_count if self.input_count else 0.0


def merge_same_pitch(
    notes: list[Note], *,
    ratio: float | None = None,
    gap: float | None = None,
    short_prev_sec: float | None = None,
) -> tuple[list[Note], int]:
    """같은 피치가 짧은 간격으로 이어지면 한 음으로 병합. 반환 (노트, 병합 수).

    병합 판정은 step5가 잘라낸 end가 아니라 채보 엔진이 원래 검출한
    detected_end 기준으로 한다. 안 그러면 step5가 맞닿게 잘라둔 별개의 음까지
    간격 0으로 보여서 계속 붙어버린다.

    온셋 간격 대신 진폭비로 "쪼개진 조각"인지 "다시 친 음"인지 가른다. 조각은
    앞소리보다 감쇠해서 진폭이 낮고(중앙값 0.87배), 재연주(루트 페달 포함)는
    다시 치니 진폭이 오른다(중앙값 1.25배). detected_end 간격 조건은 멀리
    떨어진 음이 붙는 것을 막는 안전장치로 그대로 둔다.

    **진폭비만으로는 갈리지 않는 곡이 있다.** AC/DC "Highway to Hell"의 병합
    후보쌍은 진폭비 중앙값이 1.00이라(서스테인이 길어 조각도 안 약해진다)
    조건을 통과하지 못하고, 한 번 뜯은 4분음표가 16분 두 조각으로 남아
    마디마다 타현이 하나씩 늘었다. 임계를 올려 해결하려 하면 진짜 재타현을
    뭉갠다 — 실측에서 Drowning 타현 일치율이 83%→12%로 붕괴했다.

    그래서 두 번째 판별자를 둔다: **앞 음이 아주 짧으면 조각으로 본다.**
    한 번 뜯은 음의 앞머리는 16분음표보다 짧게 끊길 수 없다. 실측 분포가
    이것을 뒷받침한다 — 병합 후보쌍 중 앞음이 16분 이하인 비율이 HTH는
    55%인데 Drowning은 10%다(같은 척도, 진폭비는 둘 다 1.00으로 무의미).

    short_prev_sec을 주면 그 길이 이하의 앞음은 진폭비를 묻지 않고 병합한다.

    ratio/gap을 주면 모듈 상수 대신 그 값을 쓴다 — 임계를 정답으로 채점하는
    스윕(eval/sweep_merge.py)이 재채보 없이 이 단계만 다시 돌리기 위한 것이다.
    """
    r = MERGE_MAX_AMPLITUDE_RATIO if ratio is None else ratio
    g = MERGE_GAP_SEC if gap is None else gap
    merged = 0
    out: list[Note] = []
    for note in notes:
        if out:
            prev = out[-1]
            short_prev = (
                short_prev_sec is not None
                and prev.detected_end - prev.start <= short_prev_sec
            )
            if (prev.pitch == note.pitch
                    and (short_prev or note.amplitude < prev.amplitude * r)
                    and note.start - prev.detected_end <= g):
                prev.end = max(prev.end, note.end)
                prev.detected_end = max(prev.detected_end, note.detected_end)
                # amplitude는 max로만 올라간다. 조각 체인이 이어질 때마다 기준
                # 진폭이 커지는 셈인데, 이건 의도된 동작이다 — 감쇠하는 뒷조각을
                # 계속 앞음(가장 센 진폭) 기준으로 흡수해야 한다.
                prev.amplitude = max(prev.amplitude, note.amplitude)
                merged += 1
                continue
        out.append(note)
    return out, merged


def clean(
    note_events: list[tuple],
    *,
    verbose: bool = False,
    monophonic_source: bool = False,
    beat_sec: float | None = None,
) -> tuple[list[Note], CleanReport]:
    """basic-pitch의 note_events를 단선율 베이스 라인으로 정리한다.

    note_events 튜플 구조 (실측 확인):
        (start_time, end_time, pitch_midi, amplitude, pitch_bends)

    monophonic_source는 프레임당 피치를 하나만 내는 엔진(CREPE 등)의 출력인지
    알려준다. 그런 출력에는 배음 거짓 음도, 한 음이 쪼개진 조각도, 동시 발음도
    애초에 없다. 그래서 배음 제거·단선율 강제·병합은 걸러낼 대상이 없는 채로
    실제 음을 깎아내기만 한다. 정답 데이터셋에서 이 세 단계를 건너뛴 쪽이
    거짓 음 10.5% / F 0.860으로 더 나았다. 남기는 것은 엔진과 무관하게
    유효한 판정뿐이다: 음역 접기/제거, 짧음·약함 제거, 누출 제거.
    """
    notes = [
        Note(
            start=float(e[0]),
            end=float(e[1]),
            pitch=int(e[2]),
            amplitude=float(e[3]),
            detected_end=float(e[1]),
        )
        for e in note_events
    ]
    total = len(notes)
    notes.sort(key=lambda n: (n.start, -n.amplitude))

    # 1) 배음 제거 — 아래 음과 겹치면서 배음 간격에 있고 더 약하면 버린다.
    #    가장 먼저 하는 이유: 배음은 음역 안에 있어서 범위 필터로는 안 걸린다.
    harmonic_dropped: list[Note] = []
    if not monophonic_source:
        survivors: list[Note] = []
        for note in notes:
            is_harmonic = any(
                (note.pitch - base.pitch) in HARMONIC_INTERVALS
                and note.overlaps(base)
                and note.amplitude <= base.amplitude
                for base in notes
                if base is not note
            )
            (harmonic_dropped if is_harmonic else survivors).append(note)
        notes = survivors

    # 2) 음역 밖 제거. 한 옥타브 위면 접어서 살린다.
    in_range: list[Note] = []
    out_of_range = 0
    for note in notes:
        pitch = note.pitch
        while pitch > BASS_MIDI_MAX:
            pitch -= 12
        while pitch < BASS_MIDI_MIN and pitch + 12 <= BASS_MIDI_MAX:
            pitch += 12
        if BASS_MIDI_MIN <= pitch <= BASS_MIDI_MAX:
            note.pitch = pitch
            in_range.append(note)
        else:
            out_of_range += 1
    notes = in_range

    # 3) 너무 짧거나 약한 음 제거
    before = len(notes)
    notes = [
        n for n in notes
        if n.duration >= MIN_NOTE_SEC and n.amplitude >= MIN_AMPLITUDE
    ]
    short_dropped = before - len(notes)

    # 4) 배음 누출 제거 — 확실히 믿을 만한(진폭이 큰) 음들로 이 곡의 실제
    #    베이스 음역을 추정하고, 그보다 한참 위에 있으면서 약한 음은 다른
    #    악기에서 새어든 것으로 보고 버린다. 음역 추정 근거(확신 음)가
    #    하나도 없으면 함부로 버리지 않고 이 단계를 건너뛴다.
    confident = [n.pitch for n in notes if n.amplitude >= LEAKAGE_CONFIDENT_AMPLITUDE]
    leakage_dropped = 0
    if confident:
        ceiling = statistics.median(confident) + LEAKAGE_REGISTER_MARGIN
        kept: list[Note] = []
        for n in notes:
            if n.pitch > ceiling and n.amplitude < LEAKAGE_STRONG_AMPLITUDE:
                leakage_dropped += 1
            else:
                kept.append(n)
        notes = kept

    # 5) 단선율 강제 — 겹치는 구간에서는 가장 센 음만 남긴다.
    overlap_dropped = 0
    truncated_dropped = 0
    merged = 0
    if not monophonic_source:
        notes.sort(key=lambda n: (n.start, -n.amplitude))
        mono: list[Note] = []
        for note in notes:
            if not mono:
                mono.append(note)
                continue
            prev = mono[-1]
            if note.start < prev.end - OVERLAP_TOLERANCE:
                if note.amplitude > prev.amplitude:
                    # 새 음이 더 세면 이전 음을 잘라내고 교체
                    prev.end = note.start
                    if prev.duration < MIN_NOTE_SEC:
                        mono.pop()
                        truncated_dropped += 1
                    mono.append(note)
                else:
                    overlap_dropped += 1
                continue
            # 살짝 겹치면 앞 음을 잘라 맞닿게 한다
            if note.start < prev.end:
                prev.end = note.start
            mono.append(note)
        notes = mono

        # 6) 같은 피치가 짧은 간격으로 이어지면 한 음으로 병합.
        #
        # 짧은 앞음 판별자는 **단선율 엔진(CREPE) 출력에만** 건다. 골든셋
        # 8곡 채점에서 CREPE 곡은 순 +29pp(Champagne +18, HTH +16), basic-pitch
        # 곡은 둘 다 −10pp로 정확히 갈렸다. basic-pitch는 폴리포닉
        # 아키텍처라 지속음을 0.17초 조각으로 쪼개는데, 그 조각은 이미 진폭비
        # 병합이 맡고 있어서 길이 규칙을 더 걸면 진짜 음까지 삼킨다.
        short_prev = (
            beat_sec * SHORT_PREV_BEATS
            if (beat_sec and monophonic_source) else None
        )
        notes, merged = merge_same_pitch(notes, short_prev_sec=short_prev)
    else:
        # 단선율 엔진 출력은 이미 시각 순이고 서로 겹치지 않는다. 정렬만 보장한다.
        notes.sort(key=lambda n: n.start)

    report = CleanReport(
        input_count=total,
        output_count=len(notes),
        dropped_harmonic=len(harmonic_dropped),
        dropped_out_of_range=out_of_range,
        dropped_short=short_dropped,
        dropped_overlap=overlap_dropped,
        merged=merged,
        dropped_truncated=truncated_dropped,
        dropped_leakage=leakage_dropped,
    )

    if verbose:
        if monophonic_source:
            print(
                f"[bassclean] {total} -> {len(notes)}  "
                f"(음역이탈 {out_of_range}, 짧음/약함 {short_dropped}, "
                f"누출 {report.dropped_leakage}) "
                f"(단선율 엔진: 배음·단선율·병합 생략)"
            )
        else:
            print(
                f"[bassclean] {total} -> {len(notes)}  "
                f"(배음 {report.dropped_harmonic}, 음역이탈 {out_of_range}, "
                f"짧음/약함 {short_dropped}, 누출 {report.dropped_leakage}, "
                f"겹침 {overlap_dropped}, 잘림 {report.dropped_truncated}, 병합 {merged})"
            )
    return notes, report


@dataclass
class LoudnessGateReport:
    """음량 게이트 결과. 왜 그만큼 버렸는지 되짚을 수 있게 남긴다."""

    applied: bool
    dropped: int
    kept: int
    threshold: float
    grid_before: float
    grid_after: float
    reason: str

    def to_dict(self) -> dict:
        return {
            "applied": self.applied,
            "dropped": self.dropped,
            "kept": self.kept,
            "threshold": round(self.threshold, 5),
            "gridBefore": round(self.grid_before, 4),
            "gridAfter": round(self.grid_after, 4),
            "reason": self.reason,
        }


# 온셋이 격자 자리에 얹혔다고 인정하는 여유(박 단위). 32분 간격의 절반이며
# **격자 종류와 무관하게 같은 자를 쓴다.** 여유를 격자 간격에 비례시키면
# (예: 16분 격자에 ±0.125박) 거친 격자가 박 전체를 덮어버려 어떤 온셋이든
# 통과한다 — 이 프로젝트에서 이미 한 번 그렇게 틀렸다.
GATE_GRID_TOLERANCE = 0.0625

# 판정에 쓰는 격자들. 한 사람이 치면 이 중 **하나에는** 거의 다 얹힌다.
#
# 4=16분(스트레이트), 3=8분 셋잇단(스윙·셔플), 6=16분 셋잇단(하프타임 셔플).
# 스윙 곡을 16분 격자로만 재면 정상 연주가 어긋난 것으로 보인다. 판정을
# 양자화의 스윙 검출 뒤로 미루면 순서가 얽히므로, 여기서 **격자를 여러 개
# 대보고 가장 잘 맞는 쪽**을 쓴다. 순서 의존이 없어진다.
GATE_GRID_DIVISORS = (4, 3, 6)

# 이 비율 이상이 격자에 걸리면 한 사람의 연주로 본다.
#
# **8분 격자로 판정하던 것을 16분으로 바꾼 이유(실측)**: IDMT 정답 17곡(한 사람
# 연주)의 8분 정렬률 중앙값이 0.870, 최소 0.600이었다. 0.85를 임계로 두면
# **정상 곡 17곡 중 8곡에 게이트가 발동**한다 — 정상 곡의 47%다. 그 8곡 중
# 6곡은 16분 정렬률이 0.98~1.00이었다. 8분 자리에 안 걸리는 게 당연한
# **정상 16비트 라인**을 두 연주 겹침으로 오판하고 실음을 지우고 있었다.
#
# 같은 자로 잰 16분 정렬률: 정답곡 중앙값 1.000 / 최소 0.786, 두 연주가 섞인
# 연습영상은 0.823. 0.95는 그 사이에 두되 정답곡 대부분(15/17)을 건드리지 않는다.
# 실측 오발동률: 옛 기준 6/17(35%) -> 이 기준 2/17(12%).
GATE_TARGET_GRID_RATIO = 0.95

# --- 얼마나 버릴지는 다른 질문이다 ---
#
# 위 기준은 **발동 여부**만 정한다. 일단 "두 연주가 섞였다"고 판정한 뒤에는
# 무엇을 향해 깎을지 목표가 따로 필요하고, 그 목표는 16분 격자일 수 없다.
#
# 이유: 두 연주자가 같은 라인을 시간차로 치면 남는 온셋이 **인접한 16분 자리에
# 짝으로** 앉는다. 즉 겹침 때문에 늘어난 음도 16분 격자에는 얹힌다 — 16분
# 정렬률을 목표로 삼으면 깎을 이유를 못 찾는다. 실측: 16분 목표로 두었을 때
# 344음이 남았고(옛 8분 목표는 263음), 영상 정답 대조에서 맞던 마디가 깨졌다.
#
# 두 연주가 겹친 라인은 실제보다 잘게 들린다. 그래서 수렴 목표는 **거친 격자**다.
GATE_CONVERGE_DIVISOR = 2      # 8분 격자
# 32분음표의 절반. 퀀타이즈 허용 오차의 통상값이고 사람의 리듬 인지 오차 안에 있다.
GATE_CONVERGE_TOLERANCE = 0.125
# **추측(위험)** — 발동 판정(GATE_TARGET_GRID_RATIO)은 실측으로 정했지만 이
# 수렴 목표는 옛 8분 기준 값을 그대로 물려받았다. 8분 격자에 85%를 맞추려는 것은
# 공격적이고 스윙·레이백 그루브를 훼손할 수 있다. 다시 재려면 골든셋 확대가
# 먼저다 — 정답이 한 곡뿐이라 과적합한다(POLICY.md 4.3).
GATE_CONVERGE_TARGET = 0.85

# 아무리 정렬이 나빠도 이 비율 넘게 버리지 않는다. 절반 넘게 버리면 남는 것이
# 라인이 아니라 파편이다.
GATE_MAX_DROP_RATIO = 0.45


def measure_loudness(notes: list[Note], stem_path: Path) -> None:
    """각 음 구간의 RMS를 재서 `Note.loudness`를 채운다 (제자리 수정).

    `Note.amplitude`는 CREPE 확신도이고 음량이 아니다. 두 연주가 섞인 입력에서
    "더 크게 녹음된 쪽"을 고르려면 실제 음량이 필요하다.
    """
    import librosa
    import numpy as np

    y, sr = librosa.load(str(stem_path), sr=22050, mono=True)
    for note in notes:
        a = max(0, int(note.start * sr))
        b = min(len(y), int(max(note.start + 0.02, note.end) * sr))
        seg = y[a:b]
        note.loudness = float(np.sqrt(np.mean(seg**2))) if len(seg) else 0.0


def _divisor_ratio(notes: list[Note], beats: list[float], divisor: int) -> float:
    """온셋이 1/divisor 격자 자리에 걸리는 비율."""
    import bisect

    if len(beats) < 2 or not notes:
        return 1.0
    slots = [k / divisor for k in range(divisor + 1)]
    used = hit = 0
    for note in notes:
        i = bisect.bisect_right(beats, note.start) - 1
        if i < 0 or i + 1 >= len(beats):
            continue
        span = beats[i + 1] - beats[i]
        if span <= 0:
            continue
        pos = (note.start - beats[i]) / span
        used += 1
        if min(abs(pos - s) for s in slots) <= GATE_GRID_TOLERANCE:
            hit += 1
    return hit / used if used else 1.0


def _grid_ratio(notes: list[Note], beats: list[float]) -> float:
    """온셋이 **가장 잘 맞는 격자**에 걸리는 비율. 한 사람의 연주면 높다.

    격자를 하나로 고정하면 그 격자를 쓰지 않는 연주가 어긋난 것으로 보인다.
    스트레이트 16분·8분 셋잇단·16분 셋잇단을 모두 대보고 최대를 쓴다.
    """
    return max(_divisor_ratio(notes, beats, d) for d in GATE_GRID_DIVISORS)


def _converge_ratio(notes: list[Note], beats: list[float]) -> float:
    """온셋이 **8분 자리**에 걸리는 비율. 게이트가 무엇을 향해 깎을지 정한다.

    `_grid_ratio`와 다른 지표인 것이 의도다. 그쪽은 "정상 곡인가"를 묻고
    이쪽은 "겹침이 풀렸는가"를 묻는다. 자세한 이유는 `GATE_CONVERGE_DIVISOR`
    주석에 있다.
    """
    import bisect

    if len(beats) < 2 or not notes:
        return 1.0
    slots = [k / GATE_CONVERGE_DIVISOR for k in range(GATE_CONVERGE_DIVISOR + 1)]
    used = hit = 0
    for note in notes:
        i = bisect.bisect_right(beats, note.start) - 1
        if i < 0 or i + 1 >= len(beats):
            continue
        span = beats[i + 1] - beats[i]
        if span <= 0:
            continue
        pos = (note.start - beats[i]) / span
        used += 1
        if min(abs(pos - s) for s in slots) <= GATE_CONVERGE_TOLERANCE:
            hit += 1
    return hit / used if used else 1.0


def _bar_of(start: float, beats: list[float], beats_per_bar: int) -> int:
    """온셋이 몇 번째 마디에 있는지. 위상은 정확하지 않아도 된다 —
    "한 마디를 통째로 비우지 않는다"는 목적에는 근사로 충분하다."""
    import bisect

    i = max(0, bisect.bisect_right(beats, start) - 1)
    return i // max(1, beats_per_bar)


def apply_gate(
    notes: list[Note],
    beats: list[float],
    *,
    enabled: bool,
    beats_per_bar: int = 4,
    verbose: bool = False,
) -> tuple[list[Note], LoudnessGateReport]:
    """게이트를 걸지 말지까지 포함한 입구. 노트를 만드는 경로는 전부 여기로 온다.

    게이트는 자동 판정이 아니라 **사용자가 커버 영상이라고 알려줬을 때만** 건다.
    자동 판정은 스튜디오 원곡에서 오발동해 멀쩡한 음을 버렸다 — 골든셋 채점에서
    발동한 곡마다 타현 정확도가 무너졌다(Come Together −32pp, Champagne −23pp,
    Highway to Hell −23pp, Queen −10pp).

    그 판단을 부르는 쪽마다 따로 적으면 한 곳을 고칠 때 나머지가 옛 동작으로
    남는다. 실제로 그랬다 — 워커·CLI는 옵트인으로 바뀌었는데 재조립 도구
    두 개(regen_beats·refresh_manifest)가 게이트를 계속 강제해서, 같은 곡을
    도구로 다시 만들면 웹과 다른 악보가 나왔다.
    """
    if enabled:
        return gate_by_loudness(
            notes, beats, beats_per_bar=beats_per_bar, verbose=verbose
        )
    # 게이트를 걸지 않아도 **정렬률은 잰다.** diagnose가 이 값으로 리듬 신뢰를
    # 판정하고, reduce가 그 판정으로 중급 단계를 열지 정한다. 0으로 채워두면
    # 게이트를 끈 곡이 전부 "리듬 불신"으로 떨어져 하향 단계가 초급만 남는다.
    ratio = _grid_ratio(notes, beats)
    return notes, LoudnessGateReport(
        applied=False, dropped=0, kept=len(notes), threshold=0.0,
        grid_before=ratio, grid_after=ratio,
        reason="커버 영상으로 표시되지 않아 게이트를 걸지 않았다",
    )


def gate_by_loudness(
    notes: list[Note],
    beats: list[float],
    *,
    beats_per_bar: int = 4,
    verbose: bool = False,
) -> tuple[list[Note], LoudnessGateReport]:
    """두 연주가 섞인 입력에서 **크게 녹음된 쪽만** 남긴다.

    연습 영상은 원곡 음원을 반주로 틀고 그 위에 커버 베이시스트가 연주한다.
    Demucs는 두 베이스를 한 스템으로 합치므로 채보하면 두 타점이 섞이고, 리듬이
    격자에서 흩어져 악보가 16분음표로 촘촘해진다. 사용자가 배우려는 것은 커버
    파트이고 그쪽이 더 크게 녹음돼 있다.

    **판정과 감량은 다른 질문이고 다른 지표를 쓴다.**

    - 발동 여부: `_grid_ratio` (16분·셋잇단 중 최선). 정상 곡을 건드리지 않기
      위한 문턱이다. 정상 16비트 라인도 스윙 곡도 이 문턱을 넘는다.
    - 얼마나 버릴지: `_converge_ratio` (8분 격자). 겹친 연주는 실제보다 잘게
      들리므로 거친 격자를 향해 수렴시킨다. 16분 격자를 목표로 삼으면 겹침으로
      늘어난 음도 인접 16분 자리에 앉아 있어 깎을 이유를 찾지 못한다.

    **임계값을 상수로 박지 않는다.** 약한 음을 조금씩 버리면서 수렴 지표가
    목표에 닿는 지점을 찾는다. 즉 임계를 곡마다 데이터가 정한다.
    """
    before = _grid_ratio(notes, beats)
    if not notes or before >= GATE_TARGET_GRID_RATIO:
        return notes, LoudnessGateReport(
            applied=False, dropped=0, kept=len(notes), threshold=0.0,
            grid_before=before, grid_after=before,
            reason="온셋이 이미 격자에 충분히 걸려 있어 한 사람의 연주로 본다",
        )
    if all(n.loudness <= 0 for n in notes):
        return notes, LoudnessGateReport(
            applied=False, dropped=0, kept=len(notes), threshold=0.0,
            grid_before=before, grid_after=before,
            reason="음량을 재지 않았다 (measure_loudness 미실행)",
        )

    # **마디마다 같은 비율로 버린다.** 곡 전체에서 약한 음부터 버리면 조용한
    # 마디가 통째로 몰살된다 — 실측: 정답이 3타인 마디가 0타가 됐다. 마디를
    # 비우면 악보에 구멍이 나고, 그것은 두 연주가 섞인 것보다 나쁘다.
    # 어느 마디든 최소 한 음은 남긴다.
    by_bar: dict[int, list[Note]] = {}
    for note in notes:
        by_bar.setdefault(_bar_of(note.start, beats, beats_per_bar), []).append(note)

    def keep_at(ratio_drop: float) -> list[Note]:
        kept: list[Note] = []
        for bar_notes in by_bar.values():
            # **이미 수렴 격자에 맞는 마디는 깎지 않는다.** 그 마디 온셋이 8분
            # 자리에 걸려 있으면 한 사람의 연주로 볼 근거가 있고, 깎을 이유가
            # 없다. 실측: 정답이 8타인 필인 마디(게이트 전 8타)를 5타로 깎았다.
            #
            # **여기에 16분 격자 보호를 더하면 안 된다(실측).** 곡 전체 판정에
            # 쓰는 `_grid_ratio` 문턱을 마디에도 적용해 "16분에 깨끗이 얹힌
            # 마디는 살리자"고 해봤다. 속주 구간은 실제로 살아났지만 남는 음이
            # 300 -> 364개로 늘어 반복 구간이 무너졌다:
            #
            #     타현 일치 43/59(73%) -> 31/59(53%), 평균오차 0.51 -> 0.80
            #
            # 곡 전체 판정과 마디 판정은 묻는 것이 다르다. 전체는 "이 입력이
            # 정상인가"이고 마디는 "이 마디를 깎아 수렴시킬 것인가"다. 같은
            # 문턱을 옮겨 쓸 근거가 없었다.
            if _converge_ratio(bar_notes, beats) >= GATE_CONVERGE_TARGET:
                kept.extend(bar_notes)
                continue
            ordered_bar = sorted(bar_notes, key=lambda n: n.loudness, reverse=True)
            keep_n = max(1, round(len(ordered_bar) * (1.0 - ratio_drop)))
            kept.extend(ordered_bar[:keep_n])
        return sorted(kept, key=lambda n: n.start)

    converge_before = _converge_ratio(notes, beats)
    best = (0.0, converge_before, list(notes))   # (버린 비율, 수렴 지표, 남은 음)
    for pct in range(5, int(GATE_MAX_DROP_RATIO * 100) + 1, 5):
        candidate = keep_at(pct / 100)
        ratio = _converge_ratio(candidate, beats)
        if ratio > best[1]:
            best = (pct / 100, ratio, candidate)
        if ratio >= GATE_CONVERGE_TARGET:
            break

    drop_ratio, converge_after, kept_notes = best
    # 보고하는 값은 발동 판정에 쓴 지표로 통일한다 — 진단(diagnose)이 같은
    # 지표·같은 문턱으로 읽기 때문이다. 두 지표를 섞어 보고하면 "게이트는
    # 됐다는데 진단은 아니라고 한다"는 모순이 생긴다.
    ratio = _grid_ratio(kept_notes, beats)
    drop = len(notes) - len(kept_notes)
    if drop == 0:
        return notes, LoudnessGateReport(
            applied=False, dropped=0, kept=len(notes), threshold=0.0,
            grid_before=before, grid_after=before,
            reason="약한 음을 버려도 정렬이 나아지지 않았다",
        )
    threshold = min((n.loudness for n in kept_notes), default=0.0)
    reason = (
        "목표 도달" if converge_after >= GATE_CONVERGE_TARGET
        else f"상한({GATE_MAX_DROP_RATIO:.0%})까지 버려도 목표 미달 — 최선 지점 채택"
    )
    report = LoudnessGateReport(
        applied=True, dropped=drop, kept=len(kept_notes), threshold=threshold,
        grid_before=before, grid_after=ratio, reason=reason,
    )
    if verbose:
        print(
            f"[gate] 음량 게이트: {len(notes)} -> {len(kept_notes)}음 "
            f"(임계 RMS {threshold:.4f}), 격자정렬 "
            f"{100 * before:.1f}% -> {100 * ratio:.1f}%, "
            f"8분수렴 {100 * converge_before:.1f}% -> {100 * converge_after:.1f}%"
            f" — {reason}"
        )
    return kept_notes, report


def save_notes(notes: list[Note], path: Path) -> None:
    """정리된 노트를 파일로 남긴다.

    이 파일이 악보의 원본이다. 난이도 레벨·이조·튜닝을 바꿀 때마다 채보를
    다시 돌리면 5분 곡에 8분이 걸린다(CREPE가 CPU 실시간의 1.3~1.4배). 노트가
    남아 있으면 양자화부터 다시 도는 것으로 끝나 즉시 응답할 수 있다.
    진단 도구도 재채보 없이 같은 입력을 다시 볼 수 있다.
    """
    payload = [asdict(n) for n in notes]
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def load_notes(path: Path) -> list[Note]:
    """save_notes로 남긴 노트를 되돌린다."""
    return [Note(**item) for item in json.loads(path.read_text(encoding="utf-8"))]


def to_pretty_midi(notes: list[Note], program: int = 33, tempo: float = 120.0):
    """정리된 노트를 PrettyMIDI로 되돌린다. tuttut 입력용.

    program 33 = Electric Bass (finger), General MIDI.
    """
    import pretty_midi

    midi = pretty_midi.PrettyMIDI(initial_tempo=tempo)
    instrument = pretty_midi.Instrument(program=program, name="bass")
    for note in notes:
        instrument.notes.append(
            pretty_midi.Note(
                velocity=max(1, min(127, int(note.amplitude * 127))),
                pitch=note.pitch,
                start=note.start,
                end=note.end,
            )
        )
    midi.instruments.append(instrument)
    return midi
