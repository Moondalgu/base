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

import statistics
from dataclasses import dataclass

# 4현 베이스 실용 음역: E1(28) ~ G2 20프렛(63)
BASS_MIDI_MIN = 28
BASS_MIDI_MAX = 63

# 배음이 나타나는 반음 간격: 옥타브, 옥타브+5도, 2옥타브, 2옥타브+장3도
HARMONIC_INTERVALS = (12, 19, 24, 28, 31)

MIN_NOTE_SEC = 0.06          # 이보다 짧으면 노이즈로 간주
MIN_AMPLITUDE = 0.25         # basic-pitch amplitude 하한
MERGE_GAP_SEC = 0.04         # 같은 피치가 이 간격 이내로 이어지면 한 음으로 병합
OVERLAP_TOLERANCE = 0.05     # 이만큼 겹치면 동시 발음으로 본다

# 같은 피치가 이어질 때 '한 음이 쪼개진 조각'인지 '다시 친 것'인지 가르는 기준.
# 다시 치면 진폭이 오르고(정답 데이터셋 중앙값 1.25배), 조각은 감쇠 중이라
# 앞 조각보다 낮다(중앙값 0.87배). 온셋 간격으로는 갈리지 않는다.
MERGE_MAX_AMPLITUDE_RATIO = 0.8

# 스템 분리가 불완전해 베이스가 쉬는 구간에 다른 악기 배음이 누출되고,
# basic-pitch가 이를 음으로 오검출하는 경우가 있다. 절대 피치로는 판정할
# 수 없다(곡마다 베이스 음역이 다르다). 대신 그 곡 안에서 확실히 믿을 만한
# (진폭이 큰) 음들로 실제 음역을 추정하고, 그보다 한참 위에 있으면서
# 약한 음만 누출로 간주해 버린다.
LEAKAGE_CONFIDENT_AMPLITUDE = 0.6    # 이 이상이면 음역 추정에 쓸 만큼 믿는다
LEAKAGE_REGISTER_MARGIN = 14         # 반음. 곡의 베이스 음역 위로 이만큼을 넘으면 의심
LEAKAGE_STRONG_AMPLITUDE = 0.85      # 이만큼 세면 고음역이어도 실연주로 인정한다


@dataclass
class Note:
    start: float
    end: float
    pitch: int
    amplitude: float
    # basic-pitch가 검출한 원래 end. step5가 겹침 해소로 end를 잘라내도
    # 이 값은 그대로 둬서, step6 병합 판정이 잘린 end가 아니라 실제 검출
    # 구간 기준으로 이뤄지게 한다.
    detected_end: float = 0.0

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


def clean(
    note_events: list[tuple],
    *,
    verbose: bool = False,
    monophonic_source: bool = False,
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

        # 6) 같은 피치가 짧은 간격으로 이어지면 한 음으로 병합
        merged_notes: list[Note] = []
        for note in notes:
            if merged_notes:
                prev = merged_notes[-1]
                # 병합 판정은 step5가 잘라낸 end가 아니라 basic-pitch가 원래
                # 검출한 detected_end 기준으로 한다. 안 그러면 step5가 맞닿게
                # 잘라둔 별개의 음까지 간격 0으로 보여서 계속 붙어버린다.
                #
                # 온셋 간격 대신 진폭비로 "쪼개진 조각"인지 "다시 친 음"인지
                # 가른다. 조각은 앞소리보다 감쇠해서 진폭이 낮고(중앙값 0.87배),
                # 재연주(루트 페달 포함)는 다시 치니 진폭이 오른다(중앙값 1.25배).
                # detected_end 간격 조건은 멀리 떨어진 음이 붙는 것을 막는
                # 안전장치로 그대로 둔다.
                if (prev.pitch == note.pitch
                        and note.amplitude < prev.amplitude * MERGE_MAX_AMPLITUDE_RATIO
                        and note.start - prev.detected_end <= MERGE_GAP_SEC):
                    prev.end = max(prev.end, note.end)
                    prev.detected_end = max(prev.detected_end, note.detected_end)
                    # amplitude는 max로만 올라간다. 조각 체인이 이어질 때마다
                    # 기준 진폭이 커지는 셈인데, 이건 의도된 동작이다 — 감쇠하는
                    # 뒷조각들을 계속 앞음(가장 센 진폭) 기준으로 흡수해야 한다.
                    prev.amplitude = max(prev.amplitude, note.amplitude)
                    merged += 1
                    continue
            merged_notes.append(note)
        notes = merged_notes
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
