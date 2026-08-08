"""이미 처리한 곡의 채보를 제자리에서 다시 하고 악보까지 재조립한다.

쓰는 경우 두 가지:
- schemaVersion 1 산출물에 `notes.json`이 없어 변형(레벨·이조·튜닝)을 못 만들 때
- 채보 엔진을 갈아끼울 때 (예: CREPE가 붕괴한 곡을 basic-pitch로 —
  `pipeline/engine_select.py` 머리말 근거)

분리(약 450초)는 다시 돌지 않는다. 채보 이후의 재조립(게이트→코드→악보→품질)은
`regen_beats.rebuild_from_raw()` 하나로 통일돼 있다 — 웹·CLI와 같은 경로.

사용:
    python tools/diag/regen_notes.py data/<hash>                  # auto (폴백 게이트)
    python tools/diag/regen_notes.py data/<hash> --engine basic-pitch
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "apps" / "worker"))

from pipeline import bassclean, engine_select, transcribe, transcribe_crepe  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
from regen_beats import rebuild_from_raw  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="채보 제자리 재생성 + 악보 재조립")
    parser.add_argument("workdir", type=Path, help="data/<hash> 디렉토리")
    parser.add_argument("--engine", choices=("auto", "crepe", "basic-pitch"), default="auto")
    args = parser.parse_args()

    workdir: Path = args.workdir
    stem = workdir / "stems" / "bass.wav"
    if not stem.exists():
        print(f"[오류] 베이스 스템이 없습니다: {stem}")
        return 1
    if not (workdir / "beats.json").exists():
        print("[오류] beats.json이 없습니다. tools/diag/regen_beats.py를 먼저 돌리세요.")
        return 1

    t = time.monotonic()
    if args.engine == "auto":
        events, engine_used, coverage = engine_select.transcribe_auto(stem, verbose=True)
    else:
        engine_used = args.engine
        fn = transcribe_crepe.transcribe if args.engine == "crepe" else transcribe.transcribe
        events = fn(stem)
        coverage = engine_select.note_coverage(events, stem)
    monophonic = engine_used == "crepe"

    notes, report = bassclean.clean(events, verbose=True, monophonic_source=monophonic)
    bassclean.measure_loudness(notes, stem)
    bassclean.save_notes(notes, workdir / "notes_raw.json")
    print(f"[regen] {engine_used} {len(notes)}음 (커버리지 {coverage:.2f}, "
          f"{time.monotonic() - t:.1f}s)")

    manifest_path = workdir / "manifest.json"
    if manifest_path.exists():
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
        data["schemaVersion"] = 2
        data["engine"] = engine_used
        data["engineCoverage"] = round(coverage, 3)
        manifest_path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    # 게이트부터 품질까지 — regen_beats와 같은 재조립 경로 (비트는 유지)
    rebuild_from_raw(workdir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
