"""스모크 테스트: 합성 베이스 라인 -> basic-pitch -> tuttut.

Demucs 없이 채보/운지 체인만 빠르게 검증한다.
정답을 아는 신호를 넣으므로 파이프라인 상한을 측정할 수 있다.
"""

from __future__ import annotations

import warnings
from pathlib import Path

import numpy as np
import soundfile as sf

warnings.filterwarnings("ignore")

SR = 44100
OUT = Path(__file__).resolve().parent.parent / "data" / "_smoke"
OUT.mkdir(parents=True, exist_ok=True)

# 4현 베이스 개방현 + 몇 프렛. (이름, MIDI)
LINE = [
    ("E1", 28), ("G1", 31), ("A1", 33), ("B1", 35),
    ("E1", 28), ("G1", 31), ("A1", 33), ("E1", 28),
]
NOTE_SEC = 0.5


def midi_to_hz(m: int) -> float:
    return 440.0 * 2 ** ((m - 69) / 12)


def synth_bass(path: Path) -> list[tuple[float, float, int]]:
    """배음이 있는 톱니 비슷한 신호로 베이스 라인을 합성한다.

    순수 사인파는 basic-pitch가 옥타브를 헷갈리기 쉬워서 배음을 섞는다.
    """
    truth: list[tuple[float, float, int]] = []
    chunks = []
    for i, (_, midi) in enumerate(LINE):
        f0 = midi_to_hz(midi)
        t = np.linspace(0, NOTE_SEC, int(SR * NOTE_SEC), endpoint=False)
        sig = np.zeros_like(t)
        for h, amp in [(1, 1.0), (2, 0.5), (3, 0.3), (4, 0.15)]:
            sig += amp * np.sin(2 * np.pi * f0 * h * t)
        # 어택/릴리즈 엔벨로프
        env = np.ones_like(t)
        a = int(SR * 0.01)
        r = int(SR * 0.05)
        env[:a] = np.linspace(0, 1, a)
        env[-r:] = np.linspace(1, 0, r)
        sig *= env * 0.3
        chunks.append(sig)
        start = i * NOTE_SEC
        truth.append((start, start + NOTE_SEC, midi))

    audio = np.concatenate(chunks).astype(np.float32)
    sf.write(path, np.stack([audio, audio], axis=1), SR)
    return truth


def main() -> None:
    wav = OUT / "bassline.wav"
    truth = synth_bass(wav)
    print(f"[synth] {wav}  {len(truth)} notes, {len(truth) * NOTE_SEC:.1f}s")

    from basic_pitch.inference import predict

    # 베이스 전용 파라미터.
    # minimum_note_length 기본값 127.7ms는 빠른 베이스 라인을 잘라먹으므로 60ms로 낮춘다.
    _, midi_data, note_events = predict(
        str(wav),
        minimum_frequency=35,
        maximum_frequency=450,
        minimum_note_length=60,
        onset_threshold=0.5,
        frame_threshold=0.3,
    )

    print(f"\n[basic-pitch] {len(note_events)} note events")
    print("  (start, end, midi, amplitude, bends)")
    for ev in note_events[:12]:
        start, end, pitch, amp, bends = ev
        print(f"  {start:6.3f} {end:6.3f}  midi={pitch:3d}  amp={amp:.3f}  bends={'y' if bends else 'n'}")

    detected = sorted(note_events, key=lambda e: e[0])
    print(f"\n[정답 대조] 기대 {len(truth)}개")
    for i, (ts, te, tp) in enumerate(truth):
        match = [e for e in detected if abs(e[0] - ts) < 0.15]
        got = match[0][2] if match else None
        mark = "OK " if got == tp else "MISS"
        print(f"  {mark} t={ts:4.1f}s  기대 midi={tp}  검출={got}")

    # ---- 베이스 후처리 ----
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "apps" / "worker"))
    from pipeline.bassclean import clean, to_pretty_midi

    cleaned, report = clean(note_events, verbose=True)
    print("[bassclean] 정리 결과")
    for n in cleaned:
        print(f"   {n.start:6.3f} {n.end:6.3f}  midi={n.pitch:3d}  amp={n.amplitude:.3f}")
    midi_data = to_pretty_midi(cleaned)

    # ---- tuttut 운지 배정 ----
    from tuttut.logic.tab import Tab
    from tuttut.logic.theory import Tuning

    # 4현 베이스, thin -> thick
    bass_tuning = Tuning(strings=["G2", "D2", "A1", "E1"])
    print(f"\n[tuttut] tuning={[str(s) for s in bass_tuning.strings]} nstrings={bass_tuning.nstrings}")

    weights = {"b": 1, "height": 1, "length": 1, "n_changed_strings": 1}
    tab = Tab("smoke", bass_tuning, midi_data, output_dir=OUT, weights=weights)

    # to_ascii()는 파일로 쓰고 None을 반환한다. 구조화 데이터는 tab.tab에 있다.
    print("\n[탭 구조 데이터]")
    print("  tuning(pitch):", tab.tab["tuning"])
    print("  measures:", len(tab.tab["measures"]))
    for mi, measure in enumerate(tab.tab["measures"][:3]):
        print(f"  -- measure {mi}: {len(measure['events'])} events")
        for ev in measure["events"][:6]:
            print(f"     {ev}")

    print("\n[ASCII 탭]")
    for line in tab.to_string():
        print("  " + line)


if __name__ == "__main__":
    main()
