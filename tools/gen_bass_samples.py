"""베이스 단음 샘플 생성 — 악보 연주(신스 재생)용 웹 에셋.

alphaTab이 동봉한 sonivox.sf2(MIT)에서 GM Electric Bass(finger, program 33)
단음을 MIDI 피치별로 렌더해 apps/web/public/synth/bass/{midi}.wav 로 저장한다.
웹 플레이어(BassSampler)가 이걸 받아 악보 음표를 실시간 스케줄로 연주한다.

왜 사운드폰트를 브라우저에서 직접 안 쓰나 — sf2 파서+신스 런타임을 통째로
들여오는 것보다, 필요한 피치의 단음 PCM만 미리 구워 AudioBufferSourceNode로
트는 쪽이 코드가 10분의 1이고 결정적이다(같은 입력 → 같은 소리).

실행: .venv/Scripts/python.exe tools/gen_bass_samples.py
"""

from __future__ import annotations

import json
import struct
import wave
from pathlib import Path

import tinysoundfont

ROOT = Path(__file__).resolve().parents[1]
SF2 = ROOT / "apps" / "web" / "node_modules" / "@coderline" / "alphatab" / "dist" / "soundfont" / "sonivox.sf2"
OUT = ROOT / "apps" / "web" / "public" / "synth" / "bass"

SAMPLE_RATE = 44100
# 4현 베이스 E1(28)~G3(55) + 이조 ±6 여유. 22 밑은 어차피 악기 음역 밖.
MIDI_LO, MIDI_HI = 22, 62
# 노트온 유지 시간 + 릴리스 꼬리. 플레이어가 듀레이션에 맞춰 엔벨로프로 자른다.
HOLD_SEC, TAIL_SEC = 1.6, 0.4
PROGRAM = 33  # GM 34번(0-기준 33) Electric Bass (finger)
VELOCITY = 112  # "부스트 있게" — 세게 뜯은 샘플을 기준으로 굽는다


def render_note(midi: int) -> bytes:
    synth = tinysoundfont.Synth(samplerate=SAMPLE_RATE)
    sfid = synth.sfload(str(SF2))
    synth.program_select(0, sfid, 0, PROGRAM)
    hold = int(SAMPLE_RATE * HOLD_SEC)
    tail = int(SAMPLE_RATE * TAIL_SEC)
    synth.noteon(0, midi, VELOCITY)
    a = bytes(synth.generate(hold))  # float32 스테레오 interleaved
    synth.noteoff(0, midi)
    b = bytes(synth.generate(tail))
    return a + b


def to_mono16(raw: bytes) -> tuple[bytes, float]:
    n = len(raw) // 8  # 프레임 수 (f32 × 2ch)
    floats = struct.unpack(f"<{n * 2}f", raw)
    mono = [(floats[i * 2] + floats[i * 2 + 1]) * 0.5 for i in range(n)]
    peak = max(1e-9, max(abs(v) for v in mono))
    # 피치마다 사운드폰트 음량이 다르다 — 피크 -1dB로 통일해야 저음이 안 묻힌다.
    scale = 0.891 / peak
    pcm = struct.pack(
        f"<{n}h", *(max(-32768, min(32767, int(v * scale * 32767))) for v in mono)
    )
    return pcm, peak


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    manifest = {"sampleRate": SAMPLE_RATE, "holdSec": HOLD_SEC, "tailSec": TAIL_SEC,
                "program": PROGRAM, "midi": []}
    for midi in range(MIDI_LO, MIDI_HI + 1):
        pcm, peak = to_mono16(render_note(midi))
        path = OUT / f"{midi}.wav"
        with wave.open(str(path), "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(SAMPLE_RATE)
            w.writeframes(pcm)
        manifest["midi"].append(midi)
        print(f"{midi:>3} peak={peak:.3f} -> {path.name}")
    (OUT / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    print(f"[완료] {len(manifest['midi'])}개 샘플, {OUT}")


if __name__ == "__main__":
    main()
