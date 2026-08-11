"""운지 배정을 정답으로 채점한다.

IDMT-SMT-BASS 어노테이션에는 **실제 연주자가 짚은 현·프렛**이 들어 있다
(`stringNumber`, `fretNumber`). 우리 Viterbi DP가 같은 음높이에 대해 같은 자리를
고르는지 채점할 수 있다.

**한 번도 채점한 적이 없다.** 비용 가중치(개방현 보너스·고프렛 기피·현 이동)는
전부 감으로 정한 값이고, 실곡에서 정답과 어긋나는 것이 확인됐다 — 영상 악보는
D를 A현 5프렛으로 짚는데 우리는 개방 D현을 골랐다.

## 주의 — 현 번호가 반대다

IDMT는 **1=E(가장 두꺼운 현), 4=G**. 우리 내부 표현은 **0=G(가장 얇은 현), 3=E**.
이 변환을 놓치면 일치율이 엉터리로 나온다(이 프로젝트에서 이미 한 번 겪었다).

    IDMT string 1(E) -> 우리 index 3
    IDMT string 4(G) -> 우리 index 0
    즉 our_index = 4 - idmt_string

## 무엇을 재는가

음높이가 맞는 음에 한해 자리를 비교한다. 음이 틀렸으면 자리를 따질 의미가 없다.

사용:
    python eval/eval_fretting.py
    python eval/eval_fretting.py --sweep      # 가중치 조합을 훑는다
"""

from __future__ import annotations

import argparse
import itertools
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "apps" / "worker"))

try:
    import defusedxml.ElementTree as ET
except ImportError:  # pragma: no cover
    import xml.etree.ElementTree as ET  # type: ignore[no-redef]

from pipeline import fretting  # noqa: E402

IDMT = ROOT / "data" / "_datasets" / "idmt_single"


def truth_positions(xml_path: Path) -> list[tuple[int, int, int]]:
    """정답 (피치, 우리 표현 현 index, 프렛). IDMT 현 번호를 변환해서 돌려준다."""
    root = ET.parse(xml_path).getroot()
    out: list[tuple[int, int, int]] = []
    for ev in root.iter("event"):
        pitch = ev.findtext("pitch")
        string = ev.findtext("stringNumber")
        fret = ev.findtext("fretNumber")
        if pitch is None or string is None or fret is None:
            continue
        # IDMT 1=E(두꺼움) -> 우리 3, IDMT 4=G -> 우리 0
        out.append((int(pitch), 4 - int(string), int(fret)))
    return out


def score_weights(
    tracks: list[list[tuple[int, int, int]]],
    *,
    w_move: float,
    w_string: float,
    w_position: float,
    w_open: float,
    w_thin_string: float | None = None,
) -> dict:
    """가중치 한 조합으로 전 곡의 운지를 채점한다.

    정답 피치 열을 그대로 DP에 넣는다 — 채보 오차를 섞지 않고 **운지 로직만**
    재기 위해서다.

    `w_thin_string`을 받는 이유: 이 가중치가 뒤에 추가됐는데 여기 빠져 있어서
    스윕이 그 축을 못 봤다. 고정된 축을 최적이라고 보고하면 없는 최적을 만든다.
    """
    saved = (
        fretting.W_MOVE, fretting.W_STRING_CHANGE,
        fretting.W_POSITION, fretting.W_OPEN_PENALTY, fretting.W_THIN_STRING,
    )
    fretting.W_MOVE = w_move
    fretting.W_STRING_CHANGE = w_string
    fretting.W_POSITION = w_position
    fretting.W_OPEN_PENALTY = w_open
    if w_thin_string is not None:
        fretting.W_THIN_STRING = w_thin_string
    try:
        exact = string_ok = total = 0
        fret_err = 0
        for events in tracks:
            pitches = [p for p, _s, _f in events]
            positions = fretting._viterbi(pitches, fretting.TUNING_PRESETS["standard"])
            for (pitch, ts, tf), pos in zip(events, positions):
                if pos is None:
                    continue
                total += 1
                s, f = pos
                if s == ts:
                    string_ok += 1
                    if f == tf:
                        exact += 1
                fret_err += abs(f - tf)
        return {
            "total": total,
            "exact": exact,
            "stringOk": string_ok,
            "exactRatio": exact / total if total else 0.0,
            "stringRatio": string_ok / total if total else 0.0,
            "meanFretErr": fret_err / total if total else 0.0,
        }
    finally:
        (
            fretting.W_MOVE, fretting.W_STRING_CHANGE,
            fretting.W_POSITION, fretting.W_OPEN_PENALTY, fretting.W_THIN_STRING,
        ) = saved


def load_video_truth() -> list[list[tuple[int, int, int]]]:
    """커버 영상 화면 악보에서 읽은 운지 정답.

    **IDMT만으로 튜닝하면 안 된다.** IDMT는 곡당 21초짜리 짧은 리프라 한 현에
    머무는 경향이 강하다. IDMT 점수를 최대로 만든 가중치를 실곡에 걸었더니
    모든 음이 E현에 갇혀(10·9·7프렛) 자리 일치가 5/8에서 1/8로 떨어졌다.

    이 정답은 코드 진행이 도는 실제 곡이라 성격이 다르다. 둘 다 봐야 한다.
    """
    import json

    path = ROOT / "eval" / "golden" / "champagne_video_bars25_32.json"
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    seq: list[tuple[int, int, int]] = []
    for bar in data["bars"]:
        # 화면 표기 현 번호(1=G)를 우리 내부 index(0=G)로 바꾼다.
        entry = (bar["pitch"], bar["string"] - 1, bar["fret"])
        seq.extend([entry] * bar["attacks"])
    return [seq]


def load_tracks(limit: int = 0) -> list[list[tuple[int, int, int]]]:
    xmls = sorted((IDMT / "annotation").glob("*.xml"))
    if limit:
        xmls = xmls[:limit]
    tracks = []
    for xml in xmls:
        events = truth_positions(xml)
        if len(events) >= 8:
            tracks.append(events)
    return tracks


def main() -> int:
    parser = argparse.ArgumentParser(description="운지 배정 채점")
    parser.add_argument("--sweep", action="store_true", help="가중치 조합을 훑는다")
    parser.add_argument("--limit", type=int, default=0)
    args = parser.parse_args()

    tracks = load_tracks(args.limit)
    if not tracks:
        print(f"[오류] IDMT 어노테이션이 없습니다: {IDMT / 'annotation'}")
        return 1
    total_notes = sum(len(t) for t in tracks)
    print(f"=== 운지 채점 (IDMT {len(tracks)}곡, {total_notes}음) ===")
    print("  IDMT 현 번호(1=E)를 우리 표현(0=G)으로 변환해 비교한다")
    print()

    current = dict(
        w_move=fretting.W_MOVE, w_string=fretting.W_STRING_CHANGE,
        w_position=fretting.W_POSITION, w_open=fretting.W_OPEN_PENALTY,
    )
    base = score_weights(tracks, **current)
    print(f"현재 가중치 move={current['w_move']} string={current['w_string']} "
          f"position={current['w_position']} open={current['w_open']}")
    print(f"  정확 일치(현+프렛) {100 * base['exactRatio']:.1f}%  "
          f"현만 일치 {100 * base['stringRatio']:.1f}%  "
          f"평균 프렛 오차 {base['meanFretErr']:.2f}")

    if not args.sweep:
        return 0

    print()
    print("=== 가중치 스윕 ===")
    # 1차 스윕에서 최선값이 경계(w_string 1.2, w_position 0.0, w_open 0.0)에
    # 붙었다. 경계에 붙은 값은 "범위가 좁았다"는 뜻일 수 있으므로 넓혀서 다시
    # 훑는다. w_open은 양수(개방현 기피)까지 열어둔다 — 개방현은 뮤트가 안 되고
    # 음색이 달라 연주자가 피하는 맥락이 있다.
    grid = {
        "w_move": [0.2, 0.35, 0.5, 0.75, 1.0],
        "w_string": [0.8, 1.2, 2.0, 3.0, 5.0],
        "w_position": [0.0, 0.02, 0.05],
        "w_open": [0.4, 0.2, 0.0, -0.2],
    }
    # **홀드아웃으로 검증한다.** 조합을 수백 개 훑고 최댓값을 고르면 17곡에
    # 과적합할 수 있다. 곡을 둘로 나눠 한쪽에서 고르고 **다른 쪽에서 채점**한다.
    # 두 값이 크게 벌어지면 그 가중치는 못 믿는다.
    tune = [t for i, t in enumerate(tracks) if i % 2 == 0]
    test = [t for i, t in enumerate(tracks) if i % 2 == 1]
    print(f"  튜닝 {len(tune)}곡 / 검증 {len(test)}곡으로 나눠 홀드아웃한다")
    print()

    results = []
    for combo in itertools.product(*grid.values()):
        params = dict(zip(grid.keys(), combo))
        r_all = score_weights(tracks, **params)
        r_tune = score_weights(tune, **params)
        results.append((r_tune["exactRatio"], params, r_all, r_tune))
    results.sort(reverse=True, key=lambda x: x[0])

    print(f"  {'튜닝':>6} {'검증':>6} {'전체':>6} | move string position open")
    for _ratio, params, r_all, r_tune in results[:8]:
        r_test = score_weights(test, **params)
        print(f"  {100 * r_tune['exactRatio']:5.1f}% {100 * r_test['exactRatio']:5.1f}% "
              f"{100 * r_all['exactRatio']:5.1f}% | {params['w_move']:4} "
              f"{params['w_string']:6} {params['w_position']:8} {params['w_open']:5}")

    best_params = results[0][1]
    best_test = score_weights(test, **best_params)
    base_test = score_weights(test, **current)
    print()
    print(f"튜닝셋 최선: {best_params}")
    print(f"  **검증셋** {100 * base_test['exactRatio']:.1f}% -> "
          f"{100 * best_test['exactRatio']:.1f}% "
          f"({100 * (best_test['exactRatio'] - base_test['exactRatio']):+.1f}pp)")
    print("  검증셋에서도 오르면 과적합이 아니다. 튜닝셋만 오르면 못 믿는다.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
