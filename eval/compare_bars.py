"""마디 단위 대조 — 정답 TAB(사람이 읽은 실제 악보)과 파이프라인 산출물을
마디·슬롯 단위로 나란히 비교한다.

run_eval.py의 노트 F1은 온셋+피치를 통째로 그리디 매칭해서 "이 마디가
왜 틀렸는지"를 보여주지 못한다. 이 도구는 같은 alphatex 파싱 규칙을 재사용해
마디별로 (슬롯, 피치, 길이슬롯)을 정답과 나란히 놓고 어긋난 지점을 정확히
짚는다.

사용:
    python eval/compare_bars.py <data/{hash}> <정답json>

정답json 형식은 eval/golden/*.json 참고. `_`로 시작하는 키는 메타 설명이라
파싱에서 무시한다.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "apps" / "worker"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

# 토큰 분리 로직은 eval/run_eval.py 것을 그대로 재사용한다 ({tu 3} 안의
# 공백을 보존해야 하는 규칙이 이미 검증돼 있다).
from run_eval import _tokens  # noqa: E402

NOTE_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]


def midi_name(pitch: int) -> str:
    """MIDI 번호 -> 음이름. C4=60 관습 (fretting.TUNING_PRESETS와 일치 확인됨)."""
    octave = pitch // 12 - 1
    return f"{NOTE_NAMES[pitch % 12]}{octave}"


def _notes_by_bar(tex: str, manifest: dict) -> dict[int, dict]:
    """AlphaTex를 마디별 {slot: (pitch, durSlots)} + 마디 전체 슬롯 합으로 복원한다.

    시각 재구성이 필요 없으므로(마디 내 상대 위치만 비교) BeatGrid 없이
    슬롯 산술만으로 충분하다. 파싱 규칙(토큰 분리, 튜닝 변환, 음길이 표)은
    eval/run_eval.py._notes_from_alphatex와 동일하게 맞춘다.
    """
    from pipeline.fretting import TUNING_PRESETS
    from pipeline.alphatex import slots_of

    tuning = TUNING_PRESETS[manifest["tuning"]["preset"]]
    subdivision = manifest.get("subdivision", 4)

    body_lines = [
        ln for ln in tex.splitlines()
        if ln and not ln.startswith("\\") and not ln.startswith("//") and not ln == "."
    ]
    body = " ".join(body_lines)

    out: dict[int, dict] = {}
    # 직전 어택의 위치 (마디번호, 슬롯). 타이(-.현.길이)를 만나면 이 어택의 길이에
    # 더한다. 마디 넘김 타이는 마디 첫 토큰으로 오고 **앞 마디 마지막 어택**의
    # 연장이므로, 마디마다 초기화하면 그 길이가 사라져 durSlots가 짧게 나온다.
    last_ref: tuple[int, int] | None = None
    for bar_idx, bar_text in enumerate(body.split("|")):
        if not bar_text.strip():
            continue
        bar_num = bar_idx + 1  # 정답 파일과 맞춰 1부터
        slot = 0
        out[bar_num] = {"attacks": {}, "total_slots": 0}
        attacks: dict[int, tuple[int, int]] = out[bar_num]["attacks"]
        for token in _tokens(bar_text):
            parts = token.split(".")
            if parts[0] == "r":
                slot += slots_of(parts[1], subdivision)
                last_ref = None  # 쉼표 뒤에는 이어줄 음이 없다
                continue
            if len(parts) != 3:
                continue
            dur = slots_of(parts[2], subdivision)
            if parts[0] == "-":
                # 타이는 새 어택이 아니다. 앞 음이 그만큼 길게 울린다는 표기이므로
                # 어택 수를 늘리지 않고 durSlots에만 더한다. 마디를 넘어온 타이는
                # 앞 마디에 기록된 어택을 찾아 더한다.
                if last_ref is not None:
                    ref_bar, ref_slot = last_ref
                    prev_pitch, prev_dur = out[ref_bar]["attacks"][ref_slot]
                    out[ref_bar]["attacks"][ref_slot] = (prev_pitch, prev_dur + dur)
                slot += dur
                continue
            fret, string = int(parts[0]), int(parts[1])
            pitch = tuning[string - 1] + fret
            attacks[slot] = (pitch, dur)
            last_ref = (bar_num, slot)
            slot += dur
        out[bar_num]["total_slots"] = slot
    return out


def _load_golden(path: Path) -> dict:
    raw = json.loads(path.read_text(encoding="utf-8"))
    # `_`로 시작하는 키는 메타 설명 — 파싱에서 무시
    return {k: v for k, v in raw.items() if not k.startswith("_")}


def main() -> int:
    parser = argparse.ArgumentParser(description="마디 단위 정답 대조")
    parser.add_argument("workdir", type=Path, help="data/{contentHash} 디렉토리")
    parser.add_argument("golden", type=Path, help="정답 json (eval/golden/*.json)")
    parser.add_argument(
        "--bar-offset",
        type=int,
        default=None,
        help=(
            "정답의 악보 기준 마디 번호에 더해 우리 마디 번호로 변환할 값. "
            "기본값은 정답 파일의 ourBarOffset(없으면 0). 격자 방식이 바뀌면 이 값으로 즉시 재확인 가능."
        ),
    )
    args = parser.parse_args()

    manifest = json.loads((args.workdir / "manifest.json").read_text(encoding="utf-8"))
    tex = (args.workdir / "score.alphatex").read_text(encoding="utf-8")
    golden = _load_golden(args.golden)

    bar_offset = args.bar_offset if args.bar_offset is not None else golden.get("ourBarOffset", 0)

    subdivision = manifest.get("subdivision", golden.get("subdivision", 4))
    bpb = manifest["timeSignature"][0]
    slots_per_bar = bpb * subdivision

    ours = _notes_by_bar(tex, manifest)

    totals = {"일치": 0, "길이오류": 0, "피치오류": 0, "누락": 0, "추가": 0}
    total_ref_attacks = 0
    total_ref_dur = 0
    total_our_dur_at_ref_slots = 0

    for bar in golden["bars"]:
        bar_num = bar["bar"]
        our_bar_num = bar_num + bar_offset
        bar_pitch = bar["pitch"]
        ref_map: dict[int, tuple[int, int]] = {
            a["slot"]: (a.get("pitch", bar_pitch), a["durSlots"])
            for a in bar["attacks"]
        }
        our_bar = ours.get(our_bar_num, {"attacks": {}, "total_slots": 0})
        our_map: dict[int, tuple[int, int]] = our_bar["attacks"]

        pitch_label = midi_name(bar_pitch)
        print(f"=== 악보 {bar_num}마디 (우리 {our_bar_num}마디) (정답 피치 {bar_pitch}, {pitch_label}) ===")
        print(f"  슬롯  정답                우리 출력            판정")

        bar_counts = {"일치": 0, "길이오류": 0, "피치오류": 0, "누락": 0, "추가": 0}

        for slot in sorted(set(ref_map) | set(our_map)):
            ref = ref_map.get(slot)
            our = our_map.get(slot)

            ref_col = f"어택 dur={ref[1]}" if ref else "-"
            our_col = f"어택 dur={our[1]} pitch={our[0]}" if our else "-"

            if ref and our:
                ref_pitch, ref_dur = ref
                our_pitch, our_dur = our
                if our_pitch == ref_pitch and our_dur == ref_dur:
                    verdict = "일치"
                elif our_pitch == ref_pitch:
                    verdict = f"길이오류({ref_dur}→{our_dur})"
                else:
                    verdict = f"피치오류({ref_pitch}→{our_pitch})"
            elif ref and not our:
                verdict = "누락"
            else:
                verdict = "추가"

            print(f"   {slot:<4} {ref_col:<19} {our_col:<19} {verdict}")

            # 집계 (판정 문자열이 아니라 원래 분류값으로 정확히 카운트한다)
            if ref and our:
                ref_pitch, ref_dur = ref
                our_pitch, our_dur = our
                if our_pitch == ref_pitch and our_dur == ref_dur:
                    bar_counts["일치"] += 1
                elif our_pitch == ref_pitch:
                    bar_counts["길이오류"] += 1
                else:
                    bar_counts["피치오류"] += 1
            elif ref and not our:
                bar_counts["누락"] += 1
            else:
                bar_counts["추가"] += 1

        ref_count = len(ref_map)
        our_count = len(our_map)
        print("  (우리 출력에만 있는 슬롯은 \"추가\"로 표시)")
        print(
            f"  마디 요약: 정답 {ref_count}타 / 우리 {our_count}타 / "
            f"일치 {bar_counts['일치']} / 길이오류 {bar_counts['길이오류']} / "
            f"누락 {bar_counts['누락']} / 추가 {bar_counts['추가']} / "
            f"피치오류 {bar_counts['피치오류']}"
        )
        print()

        for k in totals:
            totals[k] += bar_counts[k]
        total_ref_attacks += ref_count

        for slot, (ref_pitch, ref_dur) in ref_map.items():
            total_ref_dur += ref_dur
            if slot in our_map:
                total_our_dur_at_ref_slots += our_map[slot][1]

    # 마디 길이 검산 — 곡 전체 마디 대상 (정답 유무와 무관하게 산출물 자체의 정합성)
    length_mismatches = [
        (bar_num, data["total_slots"])
        for bar_num, data in sorted(ours.items())
        if data["total_slots"] != slots_per_bar
    ]

    recall = (
        (totals["일치"] + totals["길이오류"] + totals["피치오류"]) / total_ref_attacks
        if total_ref_attacks else 0.0
    )

    print("=== 전체 요약 ===")
    print(f"  마디 오프셋 : {bar_offset:+d} (악보 기준 → 우리 기준)")
    print(
        f"  어택 재현율 : {recall * 100:.1f}%  "
        f"({totals['일치'] + totals['길이오류'] + totals['피치오류']}/{total_ref_attacks})"
    )
    print(
        f"  유형별 합계 : 일치 {totals['일치']} / 길이오류 {totals['길이오류']} / "
        f"피치오류 {totals['피치오류']} / 누락 {totals['누락']} / 추가 {totals['추가']}"
    )

    if length_mismatches:
        print(f"  마디 길이 검산 : 불일치 {len(length_mismatches)}건 (기대 {slots_per_bar}슬롯)")
        for bar_num, total in length_mismatches:
            print(f"    {bar_num}마디: {total}슬롯 (차이 {total - slots_per_bar:+d})")
    else:
        print(f"  마디 길이 검산 : 전 마디 정상 ({slots_per_bar}슬롯)")

    notation_loss = total_ref_dur - total_our_dur_at_ref_slots
    print(
        f"  표기 손실 : 정답 durSlots 합 {total_ref_dur} 대비 "
        f"우리 {total_our_dur_at_ref_slots} (손실 {notation_loss}슬롯)"
    )

    target = 0.8
    ok = recall >= target
    print(f"\n  어택 재현율 목표 {target * 100:.0f}%: {'통과' if ok else '미달'}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
