"""골든셋 평가 — 노트 F1과 비트 F-measure.

정답(truth.json)과 파이프라인 산출물(manifest + 양자화 결과)을 비교한다.
PRD 9의 지표를 실제로 측정하는 도구.

사용:
    python eval/run_eval.py <data/{hash}> <truth.json>
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "apps" / "worker"))

ONSET_TOLERANCE = 0.05   # 50ms — PRD 9의 기준


def note_f1(
    ref: list[tuple[float, int]],
    est: list[tuple[float, int]],
    tolerance: float = ONSET_TOLERANCE,
) -> dict:
    """온셋+피치가 모두 맞아야 정답으로 치는 그리디 매칭."""
    unmatched = list(est)
    tp = 0
    matched_pairs: list[tuple[tuple[float, int], tuple[float, int]]] = []

    for r_time, r_pitch in ref:
        best = None
        best_delta = tolerance
        for cand in unmatched:
            e_time, e_pitch = cand
            if e_pitch != r_pitch:
                continue
            delta = abs(e_time - r_time)
            if delta <= best_delta:
                best, best_delta = cand, delta
        if best is not None:
            unmatched.remove(best)
            tp += 1
            matched_pairs.append(((r_time, r_pitch), best))

    fp = len(est) - tp
    fn = len(ref) - tp
    precision = tp / len(est) if est else 0.0
    recall = tp / len(ref) if ref else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
    mean_offset = (
        sum(abs(e[0] - r[0]) for r, e in matched_pairs) / len(matched_pairs)
        if matched_pairs else 0.0
    )
    return {
        "tp": tp, "fp": fp, "fn": fn,
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(f1, 4),
        "meanOnsetOffsetMs": round(mean_offset * 1000, 1),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("workdir", type=Path, help="data/{contentHash} 디렉토리")
    parser.add_argument("truth", type=Path, help="truth.json 경로")
    args = parser.parse_args()

    manifest = json.loads((args.workdir / "manifest.json").read_text(encoding="utf-8"))
    truth = json.loads(args.truth.read_text(encoding="utf-8"))

    ref = [(n["start"], n["pitch"]) for n in truth["notes"]]

    # 산출물에서 추정 노트를 복원한다: 마디 시작 + 슬롯 위치 -> 초
    from pipeline.beats import BeatGrid
    from pipeline.quantize import DEFAULT_SUBDIVISION

    grid = BeatGrid.from_json(args.workdir / "beats.json")
    tex = (args.workdir / "score.alphatex").read_text(encoding="utf-8")

    est = _notes_from_alphatex(tex, manifest, grid)

    metrics = note_f1(ref, est)
    beat_metrics = _beat_f_measure(grid.beats, truth)

    print(f"=== 평가: {args.workdir.name} ===")
    print(f"  정답 {len(ref)}음 / 추정 {len(est)}음")
    print(f"  노트 F1        : {metrics['f1']:.3f}  "
          f"(P={metrics['precision']:.3f} R={metrics['recall']:.3f})")
    print(f"  TP/FP/FN       : {metrics['tp']}/{metrics['fp']}/{metrics['fn']}")
    print(f"  평균 온셋 오차 : {metrics['meanOnsetOffsetMs']}ms")
    print(f"  비트 F-measure : {beat_metrics['f']:.3f}")
    print(f"  BPM            : 정답 {truth['bpm']} / 추정 {manifest['tempo']['medianBpm']}")
    print(f"  마디            : 정답 {truth['bars']} / 추정 {manifest['barCount']}")

    quality = manifest.get("quality", {})
    if "score" in quality:
        # components는 0~1로 정규화된 점수다(높을수록 좋음). 원시 잔차가 아니다.
        print(f"  품질 점수       : {quality['score']} ({quality.get('level')})")
        for key, value in quality.get("components", {}).items():
            print(f"    {key:26s} {value}")

    target = 0.75
    ok = metrics["f1"] >= target
    print(f"\n  MVP 목표 F1 {target}: {'통과' if ok else '미달'}")
    return 0 if ok else 1


def _notes_from_alphatex(tex: str, manifest: dict, grid) -> list[tuple[float, int]]:
    """AlphaTex를 되읽어 (시각, MIDI) 목록으로 복원한다.

    산출물 자체를 검증 대상으로 삼는다. 중간 객체가 아니라 최종 파일을 보는 게
    회귀 테스트로서 의미가 있다.
    """
    from pipeline.fretting import TUNING_PRESETS
    from pipeline.quantize import _bar_beat_spans

    tuning = TUNING_PRESETS[manifest["tuning"]["preset"]]
    subdivision = manifest.get("subdivision", 4)
    bpb = manifest["timeSignature"][0]
    slots_per_bar = bpb * subdivision

    # 마디별 슬롯 시각 재구성
    spans = _bar_beat_spans(grid, _phase_from_manifest(manifest, grid))
    slot_times: list[list[float]] = []
    for span in spans:
        times = []
        for b0, b1 in zip(span, span[1:]):
            step = (b1 - b0) / subdivision
            times.extend(b0 + step * k for k in range(subdivision))
        slot_times.append(times)

    body_lines = [
        ln for ln in tex.splitlines()
        if ln and not ln.startswith("\\") and not ln.startswith("//") and not ln == "."
    ]
    body = " ".join(body_lines)

    from pipeline.alphatex import slots_of

    out: list[tuple[float, int]] = []
    for bar_idx, bar_text in enumerate(body.split("|")):
        if bar_idx >= len(slot_times):
            break
        slot = 0
        # 토큰은 공백으로 나뉘지만 셋잇단 표기 {tu 3} 안에도 공백이 있다.
        # 중괄호가 닫힐 때까지 이어붙인다.
        for token in _tokens(bar_text):
            parts = token.split(".")
            if parts[0] == "r":
                slot += slots_of(parts[1], subdivision)
                continue
            if len(parts) != 3:
                continue
            if parts[0] == "-":
                # 타이(-.현.길이)는 앞 음의 연장이다. 새 온셋이 아니므로 세지 않고
                # 슬롯 커서만 밀어 뒤 음의 시각을 맞춘다.
                slot += slots_of(parts[2], subdivision)
                continue
            fret, string = int(parts[0]), int(parts[1])
            pitch = tuning[string - 1] + fret
            if slot < len(slot_times[bar_idx]):
                out.append((slot_times[bar_idx][slot], pitch))
            slot += slots_of(parts[2], subdivision)
    return out


def _tokens(bar_text: str) -> list[str]:
    """공백으로 나누되 중괄호 안의 공백은 유지한다 ({tu 3} 때문)."""
    out: list[str] = []
    current = ""
    depth = 0
    for ch in bar_text:
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
        if ch.isspace() and depth == 0:
            if current:
                out.append(current)
                current = ""
            continue
        current += ch
    if current:
        out.append(current)
    return out


def _phase_from_manifest(manifest: dict, grid) -> int:
    """파이프라인이 실제로 쓴 위상을 manifest에서 읽는다.

    이 값을 추측하면 안 된다. 파이프라인은 첫 음 기준으로 다운비트 위상을
    교정하는데(quantize.choose_phase), 여기서 0으로 가정하면 마디 시각이
    통째로 밀려서 평가 결과가 실제보다 나쁘게 나온다.
    """
    if "phase" in manifest:
        return int(manifest["phase"])
    # 구버전 manifest 호환 — 다운비트에서 근사한다
    beats = grid.beats
    if not grid.downbeats or not beats:
        return 0
    first = grid.downbeats[0]
    idx = min(range(len(beats)), key=lambda i: abs(beats[i] - first))
    return idx % grid.beats_per_bar


def _beat_f_measure(beats: list[float], truth: dict, tolerance: float = 0.07) -> dict:
    """정답 BPM에서 기대 비트를 만들어 비교한다."""
    expected_interval = 60.0 / truth["bpm"]
    n = int(truth["durationSec"] / expected_interval) + 1
    ref = [i * expected_interval for i in range(n)]

    unmatched = list(beats)
    tp = 0
    for r in ref:
        best, best_delta = None, tolerance
        for b in unmatched:
            d = abs(b - r)
            if d <= best_delta:
                best, best_delta = b, d
        if best is not None:
            unmatched.remove(best)
            tp += 1
    precision = tp / len(beats) if beats else 0.0
    recall = tp / len(ref) if ref else 0.0
    f = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
    return {"f": round(f, 4), "precision": round(precision, 4), "recall": round(recall, 4)}


if __name__ == "__main__":
    raise SystemExit(main())
