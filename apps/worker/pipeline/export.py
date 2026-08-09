"""내보내기 — MusicXML · MIDI.

## 왜 필요한가

자동 채보는 100%가 되지 않는다. 경쟁 서비스 리뷰의 합의가 "출발점으로는 훌륭하지만
거의 항상 수동 보정이 필요하다"이고, 우리 실측 정확도도 그 수준이다(타현 73%).

**보정하려면 내보낼 수 있어야 한다.** Guitar Pro·MuseScore·DAW로 옮겨 고치는 것이
실제 연주자의 작업 흐름이다. 경쟁사(Klangio·Songscription)는 PDF·MIDI·MusicXML·
GuitarPro를 전부 준다. 내보내기가 없으면 우리 출력은 막다른 길이다 — 사용자가
틀린 곳을 알아도 할 수 있는 일이 없다(`MARKET.md`).

## 왜 MusicXML과 MIDI인가

- **MusicXML**: MuseScore·Guitar Pro·Sibelius·Dorico가 모두 읽는다. **현·프렛을
  담을 수 있다**(`<notations><technical><string>/<fret>`). TAB이 보존되는 유일한
  범용 포맷이다.
- **MIDI**: DAW로 가는 길. 현·프렛은 없어지지만 음정·리듬은 남는다. 백킹 트랙을
  만들거나 다른 악기로 옮길 때 쓴다.

GuitarPro(.gp)는 독자 바이너리 포맷이라 직접 쓰지 않는다. **MusicXML을 Guitar Pro가
읽으므로 경로가 이미 열려 있다.**

PDF는 여기서 만들지 않는다 — alphaTab이 브라우저에서 렌더하고 있으므로 그쪽
인쇄 경로가 훨씬 싸다(`NEXT.md` 6번).

## 현 번호 규약이 세 군데에서 다르다 — 여기가 함정이다

| 곳 | 1번이 무엇 |
|---|---|
| 우리 `FrettedNote.string` | 0 = 가장 얇은 현(G2) |
| alphaTex | 1 = 가장 얇은 현(G2) |
| **MusicXML** | **1 = 가장 얇은 현** (MusicXML 표준: string 1 = highest) |

MusicXML은 alphaTex와 같은 방향이라 `string + 1`이면 된다. IDMT 정답만 반대다
(1 = E, 가장 두꺼운 현). 이 표를 안 보고 짐작하면 TAB이 위아래로 뒤집힌다.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET

from .fretting import FrettedScore

# MusicXML의 divisions — 4분음표 하나를 몇 단위로 쪼갤지.
#
# 960은 16분음표·셋잇단·점음표를 모두 정수로 담는다(960 = 2^6 × 15). 잘못 잡으면
# 셋잇단에서 반올림 오차가 누적돼 마디 길이가 안 맞고, MuseScore가 마디를
# 조용히 늘려 악보가 어긋난다.
DIVISIONS = 960

# 음이름 표기. MusicXML은 step(A~G) + alter(±1)로 적는다.
_STEPS = ["C", "C", "D", "D", "E", "F", "F", "G", "G", "A", "A", "B"]
_ALTERS = [0, 1, 0, 1, 0, 0, 1, 0, 1, 0, 1, 0]

# 음길이 이름. MusicXML `<type>`에 들어가는 값이고 없으면 MuseScore가 경고한다.
_TYPE_BY_QUARTERS = [
    (4.0, "whole", 0),
    (3.0, "half", 1),
    (2.0, "half", 0),
    (1.5, "quarter", 1),
    (1.0, "quarter", 0),
    (0.75, "eighth", 1),
    (0.5, "eighth", 0),
    (0.375, "16th", 1),
    (0.25, "16th", 0),
    (0.125, "32nd", 0),
]


def _type_of(quarters: float) -> tuple[str, int]:
    """길이(4분음표 단위)를 (type 이름, 붙임점 수)로 바꾼다.

    표에 없는 길이(셋잇단 등)는 **가장 가까운 것으로 내림**한다. 실제 지속
    시간은 `<duration>`이 정확하게 담고 있으므로 재생은 맞다. `<type>`은
    표기용이고, 틀리면 모양만 어색해진다 — 마디 길이는 깨지지 않는다.
    """
    for q, name, dots in _TYPE_BY_QUARTERS:
        if quarters >= q - 1e-6:
            return name, dots
    return "32nd", 0


def to_musicxml(
    score: FrettedScore,
    *,
    title: str = "Untitled",
    artist: str = "",
    key_signature: str | None = None,
) -> str:
    """FrettedScore를 MusicXML(part-wise)로 만든다. 현·프렛을 함께 담는다."""
    root = ET.Element("score-partwise", version="4.0")

    work = ET.SubElement(root, "work")
    ET.SubElement(work, "work-title").text = title
    if artist:
        ident = ET.SubElement(root, "identification")
        creator = ET.SubElement(ident, "creator", type="composer")
        creator.text = artist
    ident = root.find("identification") or ET.SubElement(root, "identification")
    encoding = ET.SubElement(ident, "encoding")
    ET.SubElement(encoding, "software").text = "Lowend"

    part_list = ET.SubElement(root, "part-list")
    sp = ET.SubElement(part_list, "score-part", id="P1")
    ET.SubElement(sp, "part-name").text = "Bass"
    midi = ET.SubElement(sp, "midi-instrument", id="P1-I1")
    # 34 = Electric Bass (finger). MIDI 프로그램은 0-기반이므로 33을 쓴다.
    ET.SubElement(midi, "midi-program").text = "34"

    part = ET.SubElement(root, "part", id="P1")

    carry = None  # 앞 마디에서 넘어온 (note, 남은 슬롯 수)
    for bi, bar in enumerate(score.bars):
        measure = ET.SubElement(part, "measure", number=str(bi + 1))

        if bi == 0:
            attrs = ET.SubElement(measure, "attributes")
            ET.SubElement(attrs, "divisions").text = str(DIVISIONS)
            key = ET.SubElement(attrs, "key")
            ET.SubElement(key, "fifths").text = str(_fifths(key_signature))
            time = ET.SubElement(attrs, "time")
            ET.SubElement(time, "beats").text = str(score.beats_per_bar)
            ET.SubElement(time, "beat-type").text = "4"
            clef = ET.SubElement(attrs, "clef")
            ET.SubElement(clef, "sign").text = "F"
            ET.SubElement(clef, "line").text = "4"
            # 베이스는 적힌 음보다 한 옥타브 낮게 소리난다.
            transpose = ET.SubElement(attrs, "transpose")
            ET.SubElement(transpose, "chromatic").text = "0"
            ET.SubElement(transpose, "octave-change").text = "-1"

            direction = ET.SubElement(measure, "direction", placement="above")
            dtype = ET.SubElement(direction, "direction-type")
            metronome = ET.SubElement(dtype, "metronome")
            ET.SubElement(metronome, "beat-unit").text = "quarter"
            ET.SubElement(metronome, "per-minute").text = str(round(score.median_bpm))
            sound = ET.SubElement(direction, "sound")
            sound.set("tempo", f"{score.median_bpm:.2f}")

        # 슬롯 -> 4분음표 환산. 마디 안 슬롯 수와 박자로 정해진다.
        quarters_per_slot = score.beats_per_bar / bar.slots_per_bar

        # 마디를 넘는 음은 마디 끝에서 자르고 다음 마디 앞머리에 타이로 잇는다
        # (alphatex와 같은 규칙). 자르지 않으면 <measure> 총 길이가 박자표를
        # 넘겨 MuseScore가 마디를 다시 그린다(실측: 예뻤어 10마디 어긋남).
        carry = _emit_bar_notes(
            measure, bar, quarters_per_slot, score.tuning, carry
        )

    # `ET.indent`로 보기 좋게 만든다. **다시 파싱하지 않는다** —
    # `minidom.parseString`을 쓰면 우리가 만든 문자열이라도 XML 파서를 한 번 더
    # 통과시키게 되고, 그 자리가 XXE·엔티티 폭탄의 통로가 된다. 들여쓰기만
    # 하려고 파서를 열 이유가 없다.
    ET.indent(root, space="  ")
    body = ET.tostring(root, encoding="unicode")
    # DOCTYPE이 없으면 일부 프로그램(Sibelius)이 파일 종류를 못 알아본다.
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<!DOCTYPE score-partwise PUBLIC "-//Recordare//DTD MusicXML 4.0 Partwise//EN"'
        ' "http://www.musicxml.org/dtds/partwise.dtd">\n' + body + "\n"
    )


def _emit_bar_notes(
    measure: ET.Element, bar, quarters_per_slot: float, tuning: list[int],
    carry: tuple | None,
) -> tuple | None:
    """마디 하나의 음·쉼표를 적는다. 반환 = 다음 마디로 넘길 (note, 남은 슬롯).

    마디를 넘는 음은 여기서 자르고 tie stop/start로 잇는다 — <measure>의
    duration 합이 정확히 박자표와 같아야 한다."""
    cursor = 0
    if carry is not None:
        note, remain = carry
        # 이 마디에 이미 음이 있으면 그 앞까지만 끈다 — 겹치면 마디가 넘친다.
        first = min((n.slot for n in bar.notes), default=bar.slots_per_bar)
        take = min(remain, bar.slots_per_bar, first)
        if take > 0:
            _note(measure, note, quarters_per_slot, tuning,
                  duration_slots=take, tie_stop=True,
                  tie_start=remain > take and first >= bar.slots_per_bar)
            cursor = take
        carry = ((note, remain - take)
                 if remain > take and first >= bar.slots_per_bar else None)
    for note in sorted(bar.notes, key=lambda n: n.slot):
        if note.slot > cursor:
            _rest(measure, (note.slot - cursor) * quarters_per_slot)
        take = min(note.duration_slots, bar.slots_per_bar - note.slot)
        spills = note.duration_slots > take
        _note(measure, note, quarters_per_slot, tuning, duration_slots=take,
              tie_start=spills)
        cursor = note.slot + take
        if spills:
            carry = (note, note.duration_slots - take)
    if cursor < bar.slots_per_bar:
        _rest(measure, (bar.slots_per_bar - cursor) * quarters_per_slot)
    return carry


def _rest(measure: ET.Element, quarters: float) -> None:
    el = ET.SubElement(measure, "note")
    ET.SubElement(el, "rest")
    ET.SubElement(el, "duration").text = str(max(1, round(quarters * DIVISIONS)))
    name, dots = _type_of(quarters)
    ET.SubElement(el, "type").text = name
    for _ in range(dots):
        ET.SubElement(el, "dot")


def _note(
    measure: ET.Element, note, quarters_per_slot: float, tuning: list[int],
    *, duration_slots: int | None = None,
    tie_start: bool = False, tie_stop: bool = False,
) -> None:
    quarters = (duration_slots if duration_slots is not None
                else note.duration_slots) * quarters_per_slot
    el = ET.SubElement(measure, "note")

    pitch = ET.SubElement(el, "pitch")
    pc = note.pitch % 12
    ET.SubElement(pitch, "step").text = _STEPS[pc]
    if _ALTERS[pc]:
        ET.SubElement(pitch, "alter").text = str(_ALTERS[pc])
    # MusicXML octave는 C4=4 관습. 베이스는 <transpose>로 한 옥타브 내렸으므로
    # 적히는 옥타브는 실제보다 하나 위다.
    ET.SubElement(pitch, "octave").text = str(note.pitch // 12)

    ET.SubElement(el, "duration").text = str(max(1, round(quarters * DIVISIONS)))
    # 타이는 <tie>(소리)와 <notations><tied>(표기) 둘 다 필요하고,
    # DTD 순서상 <tie>는 duration 직후·type 앞이다.
    if tie_stop:
        ET.SubElement(el, "tie", type="stop")
    if tie_start:
        ET.SubElement(el, "tie", type="start")
    name, dots = _type_of(quarters)
    ET.SubElement(el, "type").text = name
    for _ in range(dots):
        ET.SubElement(el, "dot")

    # 현·프렛. **이것이 MusicXML을 쓰는 이유다** — MIDI로는 담을 수 없다.
    notations = ET.SubElement(el, "notations")
    if tie_stop:
        ET.SubElement(notations, "tied", type="stop")
    if tie_start:
        ET.SubElement(notations, "tied", type="start")
    technical = ET.SubElement(notations, "technical")
    ET.SubElement(technical, "string").text = str(note.string + 1)
    ET.SubElement(technical, "fret").text = str(note.fret)


def _fifths(signature: str | None) -> int:
    """조표 이름을 MusicXML `fifths`(샵 개수, 플랫은 음수)로 바꾼다.

    모르는 이름이면 0(다장조)을 쓴다. **추측해서 틀린 조표를 찍는 것보다
    조표 없는 것이 낫다** — 틀린 조표는 임시표를 전부 어긋나게 만든다.
    """
    table = {
        "C": 0, "G": 1, "D": 2, "A": 3, "E": 4, "B": 5, "F#": 6, "C#": 7,
        "F": -1, "Bb": -2, "Eb": -3, "Ab": -4, "Db": -5, "Gb": -6, "Cb": -7,
    }
    return table.get((signature or "").strip(), 0)


def to_midi(score: FrettedScore, *, program: int = 33) -> bytes:
    """FrettedScore를 표준 MIDI 파일(포맷 0)로 만든다.

    **의존성 없이 직접 쓴다.** pretty_midi를 쓰면 numpy·scipy가 따라오고,
    이 프로젝트에서 이미 버전 충돌을 겪었다(`fretting.py` tuttut 절). MIDI
    포맷 0은 단순해서 직접 쓰는 비용이 의존성을 관리하는 비용보다 낮다.

    현·프렛은 담지 않는다 — MIDI에 그런 자리가 없다. 운지가 필요하면
    MusicXML을 쓴다.
    """
    ticks_per_quarter = 480
    events: list[tuple[int, bytes]] = []      # (절대 tick, 이벤트 바이트)

    # 템포. 마디마다 BPM이 흔들리지만 중앙값 하나로 적는다 — 마디별 템포
    # 변화를 넣으면 DAW에서 편집이 어려워지고, 우리 그리드는 이미 균일하다.
    usec_per_quarter = int(60_000_000 / max(1.0, score.median_bpm))
    events.append((0, b"\xff\x51\x03" + usec_per_quarter.to_bytes(3, "big")))
    events.append((0, bytes([0xFF, 0x58, 0x04, score.beats_per_bar, 2, 24, 8])))
    events.append((0, bytes([0xC0, program & 0x7F])))

    tick = 0
    for bar in score.bars:
        quarters_per_slot = score.beats_per_bar / bar.slots_per_bar
        for note in sorted(bar.notes, key=lambda n: n.slot):
            on = tick + round(note.slot * quarters_per_slot * ticks_per_quarter)
            off = on + max(
                1, round(note.duration_slots * quarters_per_slot * ticks_per_quarter)
            )
            velocity = 64 if note.low_confidence else 96
            events.append((on, bytes([0x90, note.pitch & 0x7F, velocity])))
            events.append((off, bytes([0x80, note.pitch & 0x7F, 0])))
        tick += round(score.beats_per_bar * ticks_per_quarter)

    events.append((tick, b"\xff\x2f\x00"))
    # note off가 같은 tick의 note on보다 먼저 와야 한다. 아니면 같은 음을
    # 이어 칠 때 뒤 음이 즉시 꺼진다.
    events.sort(key=lambda e: (e[0], 0 if e[1][0] == 0x80 else 1))

    track = bytearray()
    prev = 0
    for at, payload in events:
        track += _varlen(at - prev)
        track += payload
        prev = at

    header = b"MThd" + (6).to_bytes(4, "big") + b"\x00\x00\x00\x01" + \
        ticks_per_quarter.to_bytes(2, "big")
    return header + b"MTrk" + len(track).to_bytes(4, "big") + bytes(track)


def _varlen(value: int) -> bytes:
    """MIDI 가변길이 수. delta time에 쓴다."""
    value = max(0, value)
    out = [value & 0x7F]
    value >>= 7
    while value:
        out.append((value & 0x7F) | 0x80)
        value >>= 7
    return bytes(reversed(out))
