"""연습 영상(베이스 두 대)을 인위로 합성해 통제 실험을 만든다.

**왜 필요한가.** 실제 연습 영상과 원곡을 나란히 놓고 비교하려 했더니, 그
영상이 참조한 원곡 녹음을 특정할 수 없었다(백예린 Champagne Supernova는
라이브 버전이 여럿이고, 실측상 길이 320초 대 336초·템포 76 대 71.8로
서로 다른 녹음이었다). 마디가 1:1로 안 맞으면 "두 베이스가 섞여서 틀린
것"과 "애초에 다른 연주라서 다른 것"을 가릴 수 없다.

그래서 **깨끗한 베이스 스템 하나에서 두 번째 연주를 합성**한다. 원본과
합성본의 차이는 오직 "베이스가 겹쳤다" 하나뿐이므로, 채보가 어디서
망가지는지가 그대로 드러난다. 같은 곡의 Songsterr 정답도 그대로 쓸 수 있다.

두 번째 연주를 만드는 방법(실제 연습 영상의 성질을 흉내낸다):
- 시간을 조금 밀어 타점을 어긋나게 한다(사람은 원곡과 정확히 같이 못 친다)
- 음량을 낮춘다(원곡 반주는 스피커를 거쳐 작게 녹음된다)
- 고역을 깎는다(스피커→마이크 경로에서 실제로 일어나는 일)

사용:
    python tools/diag/make_overlay_take.py data/<hash> --shift-ms 40 --gain 0.55
    → data/_overlay/<hash>_overlay.wav (원본은 data/_overlay/<hash>_clean.wav)
"""

from __future__ import annotations

import argparse
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "data" / "_overlay"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("workdir", type=Path, help="data/<hash> (stems/bass.wav 필요)")
    ap.add_argument("--shift-ms", type=float, default=40.0,
                    help="두 번째 연주를 뒤로 미는 양(ms). 사람이 원곡과 어긋나는 정도")
    ap.add_argument("--gain", type=float, default=0.55,
                    help="두 번째 연주의 음량 배율(스피커를 거친 원곡 쪽)")
    ap.add_argument("--lowpass", type=float, default=3000.0,
                    help="두 번째 연주에 걸 저역통과 차단(Hz). 스피커 경로 재현")
    args = ap.parse_args()

    import numpy as np
    import librosa
    import scipy.signal as sg
    import soundfile as sf

    src = args.workdir / "stems" / "bass.wav"
    if not src.exists():
        print(f"베이스 스템이 없다: {src}")
        return 1

    y, sr = librosa.load(str(src), sr=None, mono=True)
    OUT.mkdir(parents=True, exist_ok=True)
    tag = args.workdir.name

    # 두 번째 연주 — 밀고, 깎고, 줄인다
    shift = int(sr * args.shift_ms / 1000.0)
    second = np.concatenate([np.zeros(shift, dtype=y.dtype), y])[: len(y)]
    sos = sg.butter(4, args.lowpass / (sr / 2), btype="low", output="sos")
    second = sg.sosfilt(sos, second).astype(np.float32) * args.gain

    mixed = y + second
    peak = float(np.max(np.abs(mixed))) or 1.0
    if peak > 1.0:                      # 클리핑 방지 — 두 트랙을 같은 비율로 줄인다
        mixed = mixed / peak * 0.99

    clean_path = OUT / f"{tag}_clean.wav"
    over_path = OUT / f"{tag}_overlay.wav"
    sf.write(clean_path, y, sr)
    sf.write(over_path, mixed, sr)
    print(f"원본  → {clean_path}")
    print(f"합성  → {over_path}  (지연 {args.shift_ms:.0f}ms · 음량 {args.gain} · "
          f"저역통과 {args.lowpass:.0f}Hz)")
    print("\n다음: 두 파일을 같은 인자로 채보해 비교한다")
    print(f"  scripts/run_pipeline.py {clean_path} --skip-separate "
          f"--beat-source {args.workdir}/source.wav --no-vocal")
    print(f"  scripts/run_pipeline.py {over_path} --skip-separate "
          f"--beat-source {args.workdir}/source.wav --no-vocal")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
