"""내보내기 검증 — MusicXML·MIDI가 원본 악보와 같은 것을 담고 있는가.

내보내기는 조용히 틀리기 쉽다. 파일이 열리기만 하면 맞아 보이는데, 마디 길이가
어긋나거나 현·프렛이 뒤집혀도 프로그램이 알아서 보정해 버린다. 그래서 **파일을
다시 읽어 원본과 대조**한다.

검사 항목:
1. 마디 수·음 수가 원본과 같다
2. **마디마다 duration 합이 정확히 한 마디다** — 이것이 어긋나면 MuseScore가
   마디를 늘리고 그 뒤 전체가 밀린다
3. 현·프렛이 원본과 같다 (규약이 세 군데에서 다르므로 뒤집히기 쉽다)
4. MIDI 헤더가 유효하고 note on/off 짝이 맞는다
5. **같은 tick에서 note off가 note on보다 먼저 온다** — 아니면 같은 음을
   이어 칠 때 뒤 음이 즉시 꺼진다

사용:
    python tools/diag/test_export.py data/<hash>
"""

from __future__ import annotations

import argparse
import json
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "apps" / "worker"))

from pipeline import (  # noqa: E402
    bassclean, beats as beats_mod, compose, export,
)

failures = 0


def check(label: str, ok: bool, detail: str = "") -> None:
    global failures
    failures += not ok
    print(f"  [{'OK  ' if ok else 'FAIL'}] {label}" + (f" — {detail}" if detail else ""))


def main() -> int:
    ap = argparse.ArgumentParser(description="내보내기 검증")
    ap.add_argument("workdir", type=Path)
    args = ap.parse_args()

    grid = beats_mod.BeatGrid.from_json(args.workdir / "beats.json")
    notes = bassclean.load_notes(args.workdir / "notes.json")
    manifest = json.loads((args.workdir / "manifest.json").read_text(encoding="utf-8"))
    key = (manifest.get("key") or {}).get("signatureName")
    built = compose.build(notes, grid, title="Test", key_signature=key)
    fscore = built.fscore

    src_bars = len(fscore.bars)
    src_notes = sum(len(b.notes) for b in fscore.bars)
    print(f"원본: {src_bars}마디 {src_notes}음, subdiv={fscore.subdivision}, "
          f"{fscore.beats_per_bar}/4, {fscore.median_bpm:.1f}bpm")

    # --- MusicXML ---
    print("\nMusicXML")
    xml = export.to_musicxml(fscore, title="Test", key_signature=key)
    root = ET.fromstring(xml.split("?>", 1)[1].split(">", 1)[1] if "DOCTYPE" in xml else xml)
    measures = root.findall("./part/measure")
    check("마디 수 일치", len(measures) == src_bars, f"{len(measures)} vs {src_bars}")

    # 타이 stop(마디 이월 연속분)은 별도 <note>지만 새 음이 아니다 — 뺀다.
    xml_notes = [
        n for n in root.iter("note")
        if n.find("rest") is None
        and not any(t.get("type") == "stop" for t in n.findall("tie"))
    ]
    check("음 수 일치", len(xml_notes) == src_notes, f"{len(xml_notes)} vs {src_notes}")

    # 마디마다 duration 합이 한 마디여야 한다.
    per_bar = export.DIVISIONS * fscore.beats_per_bar
    bad = []
    for i, m in enumerate(measures, start=1):
        total = sum(int(d.text) for d in m.iter("duration"))
        if total != per_bar:
            bad.append((i, total))
    check("마디 길이 정확", not bad,
          f"어긋난 마디 {len(bad)}개 (기대 {per_bar}) 예: {bad[:3]}" if bad else "")

    # 현·프렛 대조
    src_places = [
        (n.string + 1, n.fret)
        for b in fscore.bars for n in sorted(b.notes, key=lambda x: x.slot)
    ]
    xml_places = []
    for n in xml_notes:
        s, f = n.find(".//string"), n.find(".//fret")
        if s is not None and f is not None:
            xml_places.append((int(s.text), int(f.text)))
    check("현·프렛 일치", xml_places == src_places,
          f"{sum(1 for a, b in zip(xml_places, src_places) if a != b)}개 불일치")

    # **`elem or 기본값`을 쓰면 안 된다.** 자식이 없는 Element는 falsy라서
    # 유효한 요소를 찾았는데도 기본값으로 넘어간다(파이썬 3.12는 여기에
    # DeprecationWarning을 낸다). `is not None`으로 봐야 한다.
    check("조표 기록", root.find(".//key/fifths") is not None)
    check("낮은음자리표", _text(root, ".//clef/sign") == "F", _text(root, ".//clef/sign"))
    check("옥타브 이조(-1)", _text(root, ".//transpose/octave-change") == "-1",
          _text(root, ".//transpose/octave-change"))

    # --- MIDI ---
    print("\nMIDI")
    mid = export.to_midi(fscore)
    check("MThd 헤더", mid[:4] == b"MThd")
    check("MTrk 트랙", mid[14:18] == b"MTrk")
    declared = int.from_bytes(mid[18:22], "big")
    check("트랙 길이 선언 일치", declared == len(mid) - 22,
          f"{declared} vs {len(mid) - 22}")

    on, off, order_bad = _scan_midi(mid[22:])
    check("note on 수 일치", on == src_notes, f"{on} vs {src_notes}")
    check("note on/off 짝", on == off, f"on {on} / off {off}")
    check("같은 tick에서 off가 먼저", not order_bad,
          f"{order_bad}건 위반" if order_bad else "")

    print(f"\n실패 {failures}건")
    return 1 if failures else 0


def _text(root: ET.Element, path: str) -> str | None:
    el = root.find(path)
    return None if el is None else el.text


def _scan_midi(track: bytes) -> tuple[int, int, int]:
    """트랙을 훑어 note on/off 수와 순서 위반을 센다."""
    i = 0
    on = off = order_bad = 0
    at = 0
    last_on_tick = -1
    while i < len(track):
        delta, i = _read_varlen(track, i)
        at += delta
        status = track[i]
        if status == 0xFF:
            i += 1
            meta = track[i]; i += 1
            length, i = _read_varlen(track, i)
            i += length
            if meta == 0x2F:
                break
            continue
        if status == 0xC0:
            i += 2
            continue
        if status == 0x90:
            on += 1
            last_on_tick = at
            i += 3
            continue
        if status == 0x80:
            off += 1
            if at == last_on_tick:
                order_bad += 1
            i += 3
            continue
        i += 1
    return on, off, order_bad


def _read_varlen(data: bytes, i: int) -> tuple[int, int]:
    value = 0
    while True:
        byte = data[i]; i += 1
        value = (value << 7) | (byte & 0x7F)
        if not byte & 0x80:
            return value, i


if __name__ == "__main__":
    raise SystemExit(main())
