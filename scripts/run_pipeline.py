"""M0 — 파이프라인 전체 관통 CLI.

사용:
    python scripts/run_pipeline.py <오디오파일|유튜브URL>
    python scripts/run_pipeline.py song.wav --skip-separate   # 이미 베이스만 있는 파일
    python scripts/run_pipeline.py song.wav --tuning dropD

산출물: data/{contentHash}/score.alphatex, manifest.json
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "apps" / "worker"))

from pipeline import (  # noqa: E402
    alphatex, bassclean, beats, fretting, quality, quantize, separate, transcribe,
)
from pipeline.ingest import ingest  # noqa: E402

DATA = ROOT / "data"


def main() -> int:
    parser = argparse.ArgumentParser(description="베이스 자동 채보 파이프라인")
    parser.add_argument("source", help="오디오 파일 경로 또는 유튜브 URL")
    parser.add_argument("--tuning", default="standard", choices=["standard", "dropD"])
    parser.add_argument(
        "--skip-separate",
        action="store_true",
        help="입력이 이미 베이스 단독 음원일 때 Demucs를 건너뛴다",
    )
    parser.add_argument("--no-sync", action="store_true", help="sync 포인트 생략")
    parser.add_argument(
        "--beat-source",
        help="비트 추적에 쓸 별도 오디오. --skip-separate로 베이스 단독 파일을 넣을 때 "
             "드럼이 있는 믹스를 여기로 준다 (드럼 없으면 비트가 잡히지 않는다)",
    )
    args = parser.parse_args()

    stages: dict[str, dict] = {}
    t_all = time.monotonic()

    # 1) 수집
    t = time.monotonic()
    info = ingest(args.source, DATA)
    workdir = info.wav_path.parent
    stages["ingest"] = _done(t)
    print(f"[ingest] {info.source_type} '{info.title}' {info.duration_sec:.1f}s -> {workdir.name}")

    # 2) 스템 분리
    if args.skip_separate:
        bass_stem = info.wav_path
        stages["separate"] = {"status": "skipped", "ms": 0}
        print("[separate] 건너뜀 (입력을 베이스 스템으로 취급)")
    else:
        t = time.monotonic()
        stems = separate.separate(info.wav_path, workdir)
        bass_stem = stems["bass"]
        stages["separate"] = _done(t)

    # 3) 비트 추적 — 원본 믹스에 적용한다 (드럼이 있어야 비트가 잡힌다)
    t = time.monotonic()
    beat_input = Path(args.beat_source) if args.beat_source else info.wav_path
    if args.beat_source:
        print(f"[beats] 별도 소스 사용: {beat_input.name}")
    grid = beats.track_beats(beat_input, workdir)
    stages["beats"] = _done(t)

    # 4) 채보
    t = time.monotonic()
    note_events = transcribe.transcribe(bass_stem, verbose=True)
    stages["transcribe"] = _done(t)

    # 5) 베이스 후처리
    t = time.monotonic()
    cleaned, clean_report = bassclean.clean(note_events, verbose=True)
    stages["bassclean"] = _done(t)

    # 6) 양자화
    t = time.monotonic()
    qscore = quantize.quantize(cleaned, grid, verbose=True)
    stages["quantize"] = _done(t)

    # 7) 운지 배정
    t = time.monotonic()
    fscore = fretting.assign(qscore, args.tuning, verbose=True)
    stages["fretting"] = _done(t)

    # 품질 게이트
    report = quality.evaluate(cleaned, clean_report, grid, qscore, fscore)
    print(f"[quality] {report.score}점 ({report.level})"
          + (f" — {report.reason}" if report.reason else ""))
    for key, value in report.components.items():
        print(f"           {key:26s} {value:.3f}")

    # 8) AlphaTex
    t = time.monotonic()
    try:
        tex = alphatex.build(
            fscore,
            title=info.title,
            include_sync=not args.no_sync,
        )
    except alphatex.UnsupportedSubdivision as exc:
        print(f"[alphatex] {exc}")
        print("[alphatex] 스윙 셋잇단은 아직 미지원. subdivision 4로 재양자화합니다.")
        quantize.DEFAULT_SUBDIVISION = 4
        qscore = quantize.quantize(cleaned, grid, verbose=True)
        qscore.subdivision = 4
        fscore = fretting.assign(qscore, args.tuning, verbose=True)
        tex = alphatex.build(fscore, title=info.title, include_sync=not args.no_sync)
    tex_path = workdir / "score.alphatex"
    tex_path.write_text(tex, encoding="utf-8")
    stages["alphatex"] = _done(t)

    # ASCII 미리보기
    print("\n[ASCII 탭 미리보기 — 앞 4마디]")
    preview = fretting.FrettedScore(
        bars=fscore.bars[:4],
        tuning=fscore.tuning,
        tuning_name=fscore.tuning_name,
        subdivision=fscore.subdivision,
        beats_per_bar=fscore.beats_per_bar,
        median_bpm=fscore.median_bpm,
        unplayable=0,
    )
    for line in fretting.to_ascii(preview):
        print("  " + line)

    # manifest
    manifest = {
        "contentHash": info.content_hash,
        "schemaVersion": 1,
        "source": {
            "type": info.source_type,
            "id": info.source_id,
            "title": info.title,
            "durationSec": round(info.duration_sec, 2),
        },
        "status": "done",
        "stages": stages,
        "instrument": "bass",
        "tuning": {
            "preset": fscore.tuning_name,
            "midi": fscore.tuning,
            "strings": len(fscore.tuning),
        },
        "tempo": {
            "medianBpm": round(grid.median_bpm, 1),
            "variance": round(grid.bpm_variance, 4),
        },
        "timeSignature": [fscore.beats_per_bar, 4],
        "barCount": len(fscore.bars),
        "noteCount": sum(len(b.notes) for b in fscore.bars),
        "subdivision": fscore.subdivision,
        "swing": qscore.swing,
        # 마디 시각 재구성에 필요하다 (eval/run_eval.py)
        "phase": qscore.phase,
        "phaseCorrected": qscore.phase_corrected,
        "quality": report.to_dict(),
    }
    (workdir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    total = time.monotonic() - t_all
    print(f"\n[완료] {total:.1f}s  ->  {tex_path}")
    print(f"        마디 {manifest['barCount']}, 음표 {manifest['noteCount']}, "
          f"{manifest['tempo']['medianBpm']}BPM")
    print(f"\n검증:  node tools/validate_alphatex.mjs \"{tex_path}\"")
    return 0


def _done(t: float) -> dict:
    return {"status": "done", "ms": int((time.monotonic() - t) * 1000)}


if __name__ == "__main__":
    raise SystemExit(main())
