"""킥드럼이 베이스 스템에 얼마나 새어 들어왔는지 잰다 (PRD DIAG-04).

베이스 분리에서 가장 어려운 과제는 **같은 저음역을 쓰는 킥드럼과 베이스를
가르는 것**이다. 우리는 그 판단을 Demucs에 전적으로 맡기고 한 번도 검증하지
않았다. `drums` 스템은 채보 로직에서 참조되지 않는다.

## 재는 것

1) 저역(<120Hz) 에너지의 상관 — 두 스템이 같은 소리를 나눠 갖고 있나
2) 킥 온셋 시각에 베이스 스템 저역이 튀는가 — 누출의 직접 신호
3) **우리가 검출한 음이 킥 위에 얹혀 있나** — 킥 온셋 근처(±50ms)에 있는
   음의 비율을 무작위 기대치와 비교한다. 기대치보다 크게 높으면 킥을 음으로
   잘못 채보하고 있다는 뜻이다.

무작위 기대치를 함께 내는 것이 중요하다. 비율만 보면 "높다/낮다"를 판정할
기준이 없다.

사용:
    python tools/diag/diag_kick_leak.py data/<hash>
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "apps" / "worker"))

from pipeline import bassclean  # noqa: E402

SR = 22050
# 킥의 기음 대역. 베이스 기음도 여기 있어서 둘을 가르는 것이 어렵다.
LOW_HZ = 120.0
# 음이 킥 위에 얹혔다고 볼 시간 여유
COINCIDE_SEC = 0.05


def main() -> int:
    import librosa
    import numpy as np
    import scipy.signal as sig

    parser = argparse.ArgumentParser(description="킥드럼 누출 진단")
    parser.add_argument("workdir", type=Path)
    args = parser.parse_args()

    drums_path = args.workdir / "stems" / "drums.wav"
    bass_path = args.workdir / "stems" / "bass.wav"
    if not drums_path.exists() or not bass_path.exists():
        print(f"[오류] 스템이 없습니다: {drums_path} / {bass_path}")
        return 1

    drums, _ = librosa.load(str(drums_path), sr=SR, mono=True)
    bass, _ = librosa.load(str(bass_path), sr=SR, mono=True)
    n = min(len(drums), len(bass))
    drums, bass = drums[:n], bass[:n]

    # 저역만 남긴다. 4차 버터워스 저역통과.
    b, a = sig.butter(4, LOW_HZ / (SR / 2), btype="low")
    drums_low = sig.lfilter(b, a, drums)
    bass_low = sig.lfilter(b, a, bass)

    hop = 256
    def env(x):
        return librosa.feature.rms(y=x, frame_length=1024, hop_length=hop)[0]

    d_env, b_env = env(drums_low), env(bass_low)
    m = min(len(d_env), len(b_env))
    d_env, b_env = d_env[:m], b_env[:m]

    print(f"=== {args.workdir.name} — 킥드럼 누출 진단 ===")
    print()
    print(f"[1] 저역(<{LOW_HZ:.0f}Hz) 에너지 상관")
    corr = float(np.corrcoef(d_env, b_env)[0, 1])
    print(f"    drums 저역 RMS 평균 {float(d_env.mean()):.5f}")
    print(f"    bass  저역 RMS 평균 {float(b_env.mean()):.5f}")
    print(f"    상관계수 {corr:.4f}")
    print("    → 높으면 두 스템이 같은 저역을 나눠 갖고 있다는 뜻이다")

    print()
    print("[2] 킥 온셋 시각에 베이스 저역이 튀는가")
    kick_onsets = librosa.onset.onset_detect(
        y=drums_low, sr=SR, hop_length=hop, units="time", backtrack=False
    )
    frame_of = lambda t: min(m - 1, max(0, int(t * SR / hop)))
    if len(kick_onsets) == 0:
        print("    킥 온셋을 찾지 못했습니다.")
    else:
        at_kick = float(np.mean([b_env[frame_of(t)] for t in kick_onsets]))
        overall = float(b_env.mean())
        print(f"    킥 온셋 {len(kick_onsets)}개")
        print(f"    킥 시점 베이스 저역 {at_kick:.5f} 대 전체 평균 {overall:.5f} "
              f"= {at_kick / max(overall, 1e-9):.2f}배")
        print("    → 1.0에 가까우면 킥과 베이스가 무관하게 울린다는 뜻이다")

    print()
    print("[3] 우리가 검출한 음이 킥 위에 얹혀 있나")
    notes_path = args.workdir / "notes.json"
    if not notes_path.exists() or len(kick_onsets) == 0:
        print("    notes.json 또는 킥 온셋이 없어 판정 불가")
        return 0

    notes = bassclean.load_notes(notes_path)
    duration = n / SR
    kicks = np.asarray(kick_onsets)
    hits = sum(
        1 for note in notes
        if np.min(np.abs(kicks - note.start)) <= COINCIDE_SEC
    )
    ratio = hits / len(notes) if notes else 0.0

    # 무작위 기대치: 킥마다 ±COINCIDE_SEC 창을 두면 전체 시간의 몇 %가 덮이는가.
    covered = min(1.0, len(kicks) * 2 * COINCIDE_SEC / duration)
    print(f"    검출 {len(notes)}음 중 킥 근처(±{COINCIDE_SEC * 1000:.0f}ms) {hits}음 = {100 * ratio:.1f}%")
    print(f"    무작위 기대치 {100 * covered:.1f}% (킥 창이 덮는 시간 비율)")
    if covered > 0:
        print(f"    배수 {ratio / covered:.2f}")
    print()
    print("    ※ 이 배수만으로는 누출을 판정할 수 없다. **베이시스트는 킥과 같은")
    print("      타이밍에 연주한다** — 록·팝에서 베이스와 킥은 리듬적으로 정렬되므로")
    print("      우리 음이 킥 근처에 몰리는 것은 음악적으로 정상이다.")
    print()
    print("[4] 결정적 판별 — 베이스가 쉬는 구간에서 킥에 반응했나")
    # 베이스 스템이 조용한데 킥은 울리는 시점을 찾는다. 그 구간에 우리가 음을
    # 찍었다면 그것은 킥(또는 다른 누출)이다. 베이스-킥 정렬과 섞이지 않는
    # 유일한 판별이다.
    quiet = float(np.percentile(b_env, 20))
    silent_kicks = [t for t in kick_onsets if b_env[frame_of(t)] <= quiet]
    if not silent_kicks:
        print("    베이스가 조용한데 킥이 울리는 시점이 없어 판정 불가")
        return 0
    sk = np.asarray(silent_kicks)
    caught = sum(
        1 for note in notes if np.min(np.abs(sk - note.start)) <= COINCIDE_SEC
    )
    print(f"    베이스가 조용한 킥 {len(silent_kicks)}개 (베이스 저역 하위 20% 시점)")
    print(f"    그중 우리가 음을 찍은 것 {caught}개")
    print("    → 0에 가까우면 킥을 음으로 잡지 않는다는 뜻이다")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
