"""자기 채점 — 정답 악보 없이 녹음 자체를 정답으로 쓴다 (X1 되먹임 고리).

## 원리

채보(notes.json)와 베이스 스템은 **같은 타임라인**에 있다. 채보가 맞다면
채보를 크로마(피치클래스×시간)로 펼친 것과 오디오의 크로마가 겹쳐야 한다.
프레임 단위 코사인 유사도의 평균이 그 겹침이다 — 정답 악보가 없는 곡도
이 값으로 "악보가 녹음을 얼마나 설명하는가"를 잴 수 있다.

DTW(synctoolbox)는 타임라인이 다를 때 필요한 도구다. 우리는 같은 타임라인이라
정렬 자체가 필요 없다 — 유사도만 재면 된다.

## 유효성 검증

이 지표가 쓸모 있으려면 **골든셋 점수(사람 채보 대조)와 같은 방향**이어야
한다. 6곡에서 상관을 재서 판정한다. 상관이 없으면 quality.py에 넣지 않는다 —
채점할 수 없는 지표를 넣으면 품질이 올랐는지 알 수 없다(13.5 원칙).

사용:
    .venv/Scripts/python.exe eval/eval_selfscore.py            # 골든셋 6곡
    .venv/Scripts/python.exe eval/eval_selfscore.py data/<hash>
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import librosa
import numpy as np

ROOT = Path(__file__).resolve().parent.parent

SR = 16000
HOP = 1024          # 64ms 프레임 — 8분음표(75BPM 0.4s)보다 충분히 촘촘
# 크로마는 저역에서 뭉개진다. 베이스 기음(E1~)을 옥타브 위 배음까지 포함해
# 잡기 위해 CQT 크로마를 쓴다.


def symbolic_chroma(notes: list[dict], n_frames: int) -> np.ndarray:
    """notes.json을 (12, n_frames) 크로마로 펼친다."""
    C = np.zeros((12, n_frames), dtype=float)
    fps = SR / HOP
    for n in notes:
        a = int(n["start"] * fps)
        b = max(a + 1, int(n["end"] * fps))
        C[n["pitch"] % 12, a:min(b, n_frames)] = 1.0
    return C


def self_score(workdir: Path) -> dict | None:
    notes_path = workdir / "notes.json"
    wav = workdir / "stems" / "bass.wav"
    if not notes_path.exists() or not wav.exists():
        return None
    notes = json.loads(notes_path.read_text(encoding="utf-8"))
    y, _ = librosa.load(str(wav), sr=SR, mono=True)
    audio_c = librosa.feature.chroma_cqt(y=y, sr=SR, hop_length=HOP)
    sym_c = symbolic_chroma(notes, audio_c.shape[1])

    # 둘 다 소리가 있는 프레임만 비교한다. 무음 구간은 채보가 없어도 맞는
    # 것이므로 넣으면 점수가 공짜로 오른다.
    active = (sym_c.sum(axis=0) > 0) | (audio_c.sum(axis=0) > audio_c.sum(axis=0).mean() * 0.5)
    a = audio_c[:, active]
    s = sym_c[:, active]
    denom = np.linalg.norm(a, axis=0) * np.linalg.norm(s, axis=0)
    ok = denom > 0
    cos = (a[:, ok] * s[:, ok]).sum(axis=0) / denom[ok]
    # 채보가 있는 프레임 비율(커버리지)과 그 프레임의 일치(정밀) — 곱이 아니라
    # 따로 본다. 합쳐 하나로 만들면 어느 쪽이 문제인지 안 보인다.
    covered = (s.sum(axis=0) > 0).mean()
    return {
        "agreement": float(np.mean(cos)) if cos.size else 0.0,
        "coverage": float(covered),
        "frames": int(active.sum()),
    }


SONGS = [
    ("Champagne", "975e4e588d282666", 94),
    ("Queen", "528aa2e6986aa42a", 62),
    ("Come Together", "78d6e3fc12388629", 65),
    ("Virtual Insanity", "d4fd7b689b9db1bb", 25),
    ("Drowning", "65ef1cf020561a5c", 81),
    ("예뻤어", "8181e1aa7d7a0be1", 98),
]


def main() -> int:
    if len(sys.argv) > 1:
        r = self_score(Path(sys.argv[1]))
        print(r)
        return 0

    rows = []
    print(f"{'곡':<18} {'일치':>6} {'커버리지':>8} {'골든셋 피치':>10}")
    for name, h, golden_pc in SONGS:
        r = self_score(ROOT / "data" / h)
        if r is None:
            print(f"{name:<18} 데이터 없음")
            continue
        rows.append((r["agreement"], golden_pc))
        print(f"{name:<18} {r['agreement']:>6.3f} {r['coverage']:>8.1%} {golden_pc:>9}%")

    if len(rows) >= 3:
        a = np.array([x for x, _ in rows])
        g = np.array([y for _, y in rows])
        corr = np.corrcoef(a, g)[0, 1]
        print(f"\n골든셋 피치클래스와 상관: {corr:.3f}")
        print("(0.7 이상이면 quality.py 편입 후보, 아니면 편입하지 않는다)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
