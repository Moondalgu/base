"""재타현 분리 평가 — IDMT 정답과 실곡 정답 **둘 다**에서 잰다.

## 왜 둘 다인가

이 프로젝트에서 IDMT 하나로 튜닝해 크게 틀린 적이 있다(운지 가중치: IDMT
75.5%까지 올렸더니 실곡에서 모든 음이 E현에 갇혔다). IDMT는 곡당 21초짜리
베이스 단독 리프이고, 실곡은 분리를 거친 5분 곡이다. **둘이 반대를 가리키면
더 나쁜 쪽을 기준으로 고른다.**

## 무엇을 재는가

- IDMT: 음 단위 온셋+피치 F1, 그리고 **같은 피치 재타현만 따로** 본 회복률.
  전체 F1만 보면 재타현 개선이 거짓음 증가에 묻혀 안 보인다.
- 실곡: 반복 구간 47마디(정답 전부 3타)의 마디별 타현 일치. 여기가 재타현
  누락이 드러난 자리다.

사용:
    python eval/eval_reattack.py                 # 현재 기본값으로 둘 다
    python eval/eval_reattack.py --sweep         # peak_ratio 훑기
"""

from __future__ import annotations

import argparse
import glob
import json
import statistics as st
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "apps" / "worker"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from pipeline import (  # noqa: E402
    bassclean, beats as beats_mod, inertia, quantize, reattack,
)

IDMT = ROOT / "data" / "_datasets" / "idmt_single"
SONG = ROOT / "data" / "975e4e588d282666"
TOL = 0.15

# 채보는 느리다(IDMT 17곡에 수 분). 결과를 캐시해 스윕에서 재사용한다.
CACHE = ROOT / "data" / "_cache" / "idmt_raw_events.json"


def idmt_truth(xml: Path) -> list[tuple[float, int]]:
    root = ET.parse(xml).getroot()
    out = []
    for ev in root.iter("event"):
        d = {c.tag: c.text for c in ev}
        if "onsetSec" in d and "pitch" in d:
            out.append((float(d["onsetSec"]), int(d["pitch"])))
    return sorted(out)


def load_idmt_events() -> dict[str, list[list]]:
    """IDMT 오디오에 채보를 돌린 **원본 note_events**를 캐시한다.

    `bassclean`을 거치지 않은 것을 저장한다 — 재타현 분리가 그 앞에 들어가므로
    거기서부터 다시 돌려야 한다.
    """
    if CACHE.exists():
        return json.loads(CACHE.read_text())

    from pipeline.transcribe_crepe import transcribe

    store: dict[str, list[list]] = {}
    for wav in sorted(glob.glob(str(IDMT / "audio" / "*.wav"))):
        stem = Path(wav).stem
        events = transcribe(Path(wav), verbose=False)
        store[stem] = [[float(e[0]), float(e[1]), int(e[2]), float(e[3])] for e in events]
        print(f"  채보 {stem} {len(events)}이벤트", flush=True)
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    CACHE.write_text(json.dumps(store))
    return store


def match(truth: list[tuple[float, int]], det: list[tuple[float, int]]):
    """온셋+피치 그리디 매칭. (맞힌 정답 인덱스 집합, 쓰인 검출 수)."""
    used: set[int] = set()
    hit: set[int] = set()
    for i, (t, p) in enumerate(truth):
        for j, (dt, dp) in enumerate(det):
            if j in used or dp != p or abs(dt - t) > TOL:
                continue
            used.add(j)
            hit.add(i)
            break
    return hit, len(used)


def run_idmt(store: dict, **kw) -> dict:
    """IDMT에서 F1과 재타현 회복률을 잰다."""
    tot = tot_hit = tot_det = 0
    same_tot = same_hit = 0
    for xml in sorted((IDMT / "annotation").glob("*.xml")):
        stem = xml.stem
        if stem not in store:
            continue
        truth = idmt_truth(xml)
        raw = [tuple(e) + (None,) for e in store[stem]]
        wav = IDMT / "audio" / f"{stem}.wav"
        if kw.get("enabled", True):
            raw, _ = reattack.split_reattacks(
                list(raw), wav,
                peak_ratio=kw.get("peak_ratio", reattack.PEAK_RATIO),
                require_rms_rise=kw.get("require_rms_rise", True),
                rms_tolerance=kw.get("rms_tolerance", 1.0),
            )
        notes, _ = bassclean.clean(raw, monophonic_source=True)
        det = [(n.start, n.pitch) for n in notes]

        hit, used = match(truth, det)
        tot += len(truth)
        tot_hit += len(hit)
        tot_det += len(det)

        # 앞 음과 같은 피치인 정답만 따로
        for i in range(1, len(truth)):
            if truth[i - 1][1] == truth[i][1]:
                same_tot += 1
                same_hit += i in hit

    p = tot_hit / tot_det if tot_det else 0.0
    r = tot_hit / tot if tot else 0.0
    return {
        "P": p, "R": r,
        "F": 2 * p * r / (p + r) if p + r else 0.0,
        "false": 1 - p, "miss": 1 - r,
        "sameRecall": same_hit / same_tot if same_tot else 0.0,
        "sameTotal": same_tot,
        "detected": tot_det,
    }


def run_song(**kw) -> dict:
    """실곡 반복 구간(정답 전부 3타)의 마디별 타현 일치."""
    gold: dict[int, int] = {}
    for name in ("champagne_video_bars25_40", "champagne_video_bars41_99"):
        data = json.loads(
            (ROOT / "eval" / "golden" / f"{name}.json").read_text(encoding="utf-8")
        )
        for row in data["bars"]:
            gold[row["ourBar"]] = row["attacks"]
    rep_bars = [b for b, a in gold.items() if a == 3]

    grid = beats_mod.BeatGrid.from_json(SONG / "beats.json")
    raw = json.loads((SONG / "notes_raw_events.json").read_text()) \
        if (SONG / "notes_raw_events.json").exists() else None

    if raw is None:
        # 원본 note_events가 없으면 게이트 전 노트로 근사한다. 재타현 분리는
        # 채보 직후가 제자리이므로 정확히 같지는 않다 — 그 사실을 알고 본다.
        notes = bassclean.load_notes(SONG / "notes_raw.json")
        events = [(n.start, n.end, n.pitch, n.amplitude, None) for n in notes]
    else:
        events = [tuple(e) + (None,) for e in raw]

    stem = SONG / "stems" / "bass.wav"
    if kw.get("enabled", True):
        events, _ = reattack.split_reattacks(
            list(events), stem,
            peak_ratio=kw.get("peak_ratio", reattack.PEAK_RATIO),
            require_rms_rise=kw.get("require_rms_rise", True),
            rms_tolerance=kw.get("rms_tolerance", 1.0),
        )
    notes, _ = bassclean.clean(list(events), monophonic_source=True)
    bassclean.measure_loudness(notes, stem)
    gated, _ = bassclean.gate_by_loudness(
        notes, grid.beats, beats_per_bar=grid.beats_per_bar
    )
    qs = quantize.quantize(gated, grid)
    qs, _ = inertia.apply_inertia(qs)
    counts = {i + 1: len(b.notes) for i, b in enumerate(qs.bars)}

    ok = sum(1 for b in rep_bars if counts.get(b, 0) == gold[b])
    err = st.fmean(abs(counts.get(b, 0) - gold[b]) for b in rep_bars)
    all_ok = sum(1 for b, a in gold.items() if counts.get(b, 0) == a)
    return {
        "repOk": ok, "repTotal": len(rep_bars), "repErr": err,
        "allOk": all_ok, "allTotal": len(gold),
        "notes": len(gated),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="재타현 분리 평가")
    ap.add_argument("--sweep", action="store_true")
    args = ap.parse_args()

    print("IDMT 원본 이벤트 준비...")
    store = load_idmt_events()

    configs: list[tuple[str, dict]] = [("끄기(기준선)", {"enabled": False})]
    if args.sweep:
        # RMS 조건의 **강도**를 훑는다. 앞선 스윕에서 peak_ratio를 0.20~0.60으로
        # 바꿔도 결과가 꿈쩍하지 않았다 — 묶여 있는 것은 peak가 아니라 RMS 조건이다.
        for tol in (1.0, 0.9, 0.8, 0.7, 0.5, 0.3):
            configs.append((f"RMS 허용 {tol:.1f}",
                            {"peak_ratio": 0.35, "rms_tolerance": tol}))
        configs.append(("RMS 조건 없음", {"peak_ratio": 0.35, "require_rms_rise": False}))
    else:
        configs.append((f"켜기(peak {reattack.PEAK_RATIO})", {}))

    print(f"\n{'설정':26} {'IDMT F':>7} {'거짓음':>7} {'누락':>7} {'재타현회복':>10} "
          f"{'실곡 반복':>10} {'실곡 오차':>8} {'실곡 전체':>10}")
    for label, kw in configs:
        i = run_idmt(store, **kw)
        s = run_song(**kw)
        print(f"{label:26} {i['F']:7.3f} {i['false']:7.1%} {i['miss']:7.1%} "
              f"{i['sameRecall']:10.1%} "
              f"{s['repOk']:4}/{s['repTotal']:<5} {s['repErr']:8.2f} "
              f"{s['allOk']:4}/{s['allTotal']:<5}")
    print(f"\n(재타현회복 = 정답에서 앞 음과 같은 피치인 {run_idmt(store, enabled=False)['sameTotal']}음 중 맞힌 비율)")
    print("실곡 반복 = 정답이 3타인 47마디 / 실곡 전체 = 정답 59마디")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
