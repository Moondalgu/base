"""베이스 특화 후처리.

basic-pitch는 다성 모델이라 베이스 한 음의 배음을 별도 음으로 검출한다.
스모크 테스트 실측: E1 8음짜리 라인에서 29개 이벤트가 나왔고, 그중 상당수가
E3(+24), G3, A3 같은 배음이었다. 그대로 탭으로 만들면 9·12·14프렛에
존재하지 않는 음이 찍힌다.

베이스는 단선율이라는 전제를 쓸 수 있어서 이 정리가 가능하다.
기타였다면 화음과 배음을 구분할 방법이 없다.
"""

from __future__ import annotations

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


@dataclass
class Note:
    start: float
    end: float
    pitch: int
    amplitude: float

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

    @property
    def out_of_range_ratio(self) -> float:
        return self.dropped_out_of_range / self.input_count if self.input_count else 0.0

    @property
    def harmonic_ratio(self) -> float:
        return self.dropped_harmonic / self.input_count if self.input_count else 0.0


def clean(note_events: list[tuple], *, verbose: bool = False) -> tuple[list[Note], CleanReport]:
    """basic-pitch의 note_events를 단선율 베이스 라인으로 정리한다.

    note_events 튜플 구조 (실측 확인):
        (start_time, end_time, pitch_midi, amplitude, pitch_bends)
    """
    notes = [
        Note(start=float(e[0]), end=float(e[1]), pitch=int(e[2]), amplitude=float(e[3]))
        for e in note_events
    ]
    total = len(notes)
    notes.sort(key=lambda n: (n.start, -n.amplitude))

    # 1) 배음 제거 — 아래 음과 겹치면서 배음 간격에 있고 더 약하면 버린다.
    #    가장 먼저 하는 이유: 배음은 음역 안에 있어서 범위 필터로는 안 걸린다.
    harmonic_dropped: list[Note] = []
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

    # 4) 단선율 강제 — 겹치는 구간에서는 가장 센 음만 남긴다.
    notes.sort(key=lambda n: (n.start, -n.amplitude))
    mono: list[Note] = []
    overlap_dropped = 0
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
                mono.append(note)
            else:
                overlap_dropped += 1
            continue
        # 살짝 겹치면 앞 음을 잘라 맞닿게 한다
        if note.start < prev.end:
            prev.end = note.start
        mono.append(note)
    notes = mono

    # 5) 같은 피치가 짧은 간격으로 이어지면 한 음으로 병합
    merged_notes: list[Note] = []
    merged = 0
    for note in notes:
        if merged_notes:
            prev = merged_notes[-1]
            if prev.pitch == note.pitch and note.start - prev.end <= MERGE_GAP_SEC:
                prev.end = max(prev.end, note.end)
                prev.amplitude = max(prev.amplitude, note.amplitude)
                merged += 1
                continue
        merged_notes.append(note)
    notes = merged_notes

    report = CleanReport(
        input_count=total,
        output_count=len(notes),
        dropped_harmonic=len(harmonic_dropped),
        dropped_out_of_range=out_of_range,
        dropped_short=short_dropped,
        dropped_overlap=overlap_dropped,
        merged=merged,
    )

    if verbose:
        print(
            f"[bassclean] {total} -> {len(notes)}  "
            f"(배음 {report.dropped_harmonic}, 음역이탈 {out_of_range}, "
            f"짧음/약함 {short_dropped}, 겹침 {overlap_dropped}, 병합 {merged})"
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
