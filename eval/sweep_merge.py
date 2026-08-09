"""같은 피치 조각 병합 임계를 정답으로 채점한다.

AC/DC "Highway to Hell"에서 한 번 뜯은 4분음표가 16분 두 조각으로 갈려
마디마다 타현이 하나씩 늘었다(정답 4타 → 우리 5타, 20마디). 병합 조건인
`MERGE_MAX_AMPLITUDE_RATIO`(0.8)는 "조각은 앞보다 약하다"는 전제인데,
이 곡의 실측 진폭비 중앙값은 1.007이라 걸리지 않는다.

임계를 추측으로 올리면 진짜 재타현을 뭉갠다. 그래서 **골든셋 전곡을 동시에
채점**한다 — 대상 곡이 좋아지고 나머지가 나빠지지 않는 값만 채택한다.

사용: .venv/Scripts/python.exe eval/sweep_merge.py [--ratios 0.8,1.0,1.2]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps" / "worker"))
sys.path.insert(0, str(ROOT / "eval"))

from pipeline import bassclean, beats as beats_mod, compose  # noqa: E402
from eval_songsterr import find_transpose, score_at, OFFSET_RANGE  # noqa: E402
from eval_video_bars import our_bars  # noqa: E402
from run_goldenset import SONGS  # noqa: E402


def rebuild(workdir: Path, ratio: float, gap: float,
            short_beats: float | None = None) -> str | None:
    """병합 임계를 바꿔 다시 조립한 alphaTex. 원본 파일은 건드리지 않는다.

    `notes_raw.json`은 **clean을 이미 거친**(게이트 전) 산출물이라 채보
    원본이 아니다. 우리가 고치려는 것은 "병합이 덜 됐다"이므로 그 위에 병합
    단계만 더 세게 다시 적용하면 된다 — 재채보(곡당 8분)가 필요 없다.
    """
    raw = workdir / "notes_raw.json"
    if not raw.exists():
        return None
    notes = bassclean.load_notes(raw)
    manifest = json.loads((workdir / "manifest.json").read_text(encoding="utf-8"))
    grid = beats_mod.BeatGrid.from_json(workdir / "beats.json")
    # 짧은 앞음 임계는 박 길이에 비례한다 — 느린 곡의 16분과 빠른 곡의 16분은
    # 절대 시간이 다르다. 곡의 BPM으로 환산해서 넘긴다.
    short_sec = None
    # 프로덕션과 같은 조건: 짧은 앞음 판별자는 CREPE(단선율) 출력에만 건다.
    engine = manifest.get("engine") or (manifest.get("transcription") or {}).get("engine")
    if short_beats is not None and grid.median_bpm > 0 and engine == "crepe":
        short_sec = short_beats * 60.0 / grid.median_bpm
    notes, _ = bassclean.merge_same_pitch(
        notes, ratio=ratio, gap=gap, short_prev_sec=short_sec
    )
    built = compose.build(
        notes, grid, level=compose.ORIGINAL_LEVEL,
        tuning=(manifest.get("tuning") or {}).get("preset") or "standard",
    )
    return built.tex


def score(workdir: Path, golden_path: Path, tex: str) -> tuple[float, float]:
    """(피치클래스 일치율, 타현 일치율)."""
    manifest = json.loads((workdir / "manifest.json").read_text(encoding="utf-8"))
    bars = json.loads(golden_path.read_text(encoding="utf-8"))["bars"]
    ours = our_bars(tex, manifest.get("subdivision", 4))
    transpose, _ = find_transpose(ours, bars)
    # score_at → (자리 일치, 피치클래스 일치, 타현 일치, 비교 마디 수)
    best = max(
        (score_at(ours, bars, off, transpose) for off in OFFSET_RANGE),
        key=lambda r: r[1] / max(r[3], 1),
    )
    _place, pc, attack, compared = best
    return pc / max(compared, 1), attack / max(compared, 1)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ratios", default="0.8")
    ap.add_argument("--gaps", default="0.04")
    ap.add_argument("--short", default="none",
                    help="짧은 앞음 임계(박). none이면 이 판별자를 끈다")
    args = ap.parse_args()

    ratios = [float(x) for x in args.ratios.split(",")]
    gaps = [float(x) for x in args.gaps.split(",")]
    shorts = [None if x.strip() == "none" else float(x)
              for x in args.short.split(",")]

    rows = []
    for short in shorts:
      for gap in gaps:
        for ratio in ratios:
            line = {"ratio": ratio, "gap": gap, "short": short, "songs": {}}
            for name, h, golden in SONGS:
                wd = ROOT / "data" / h
                gp = ROOT / "eval" / "golden" / golden
                if not (wd / "notes_raw.json").exists() or not gp.exists():
                    continue
                try:
                    tex = rebuild(wd, ratio, gap, short)
                    if tex is None:
                        continue
                    line["songs"][name] = score(wd, gp, tex)
                except Exception as exc:  # 곡 하나가 죽어도 스윕은 계속
                    import traceback
                    line["songs"][name] = ("ERR", str(exc)[:60])
                    if not rows:  # 첫 조합에서만 원인을 자세히 찍는다
                        traceback.print_exc()
            rows.append(line)
            cells = " | ".join(
                f"{n[:12]} {v[0]:.0%}/{v[1]:.0%}" if isinstance(v[0], float)
                else f"{n[:12]} ERR"
                for n, v in line["songs"].items()
            )
            print(f"ratio={ratio} short={short}: {cells}", flush=True)


if __name__ == "__main__":
    main()
