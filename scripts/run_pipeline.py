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
    bassclean, beats, compose, diagnose, encode, fretting, quality, reduce,
    separate, transcribe, transcribe_crepe,
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
        "--engine", default="crepe", choices=["crepe", "basic-pitch"],
        help="채보 엔진. crepe가 기본(거짓 음 22.8%%→10.5%%)",
    )
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
        stems = None
        bass_stem = info.wav_path
        stages["separate"] = {"status": "skipped", "ms": 0}
        print("[separate] 건너뜀 (입력을 베이스 스템으로 취급)")
    else:
        t = time.monotonic()
        stems = separate.separate(info.wav_path, workdir)
        bass_stem = stems["bass"]
        stages["separate"] = _done(t)

        # 브라우저 전송용 opus. 파이프라인 내부는 계속 wav를 쓴다 (encode.py 주석)
        t = time.monotonic()
        encode.encode_stems(stems)
        stages["encode"] = _done(t)

    # 3) 비트 추적 — 원본 믹스에 적용한다 (드럼이 있어야 비트가 잡힌다)
    t = time.monotonic()
    beat_input = Path(args.beat_source) if args.beat_source else info.wav_path
    if args.beat_source:
        print(f"[beats] 별도 소스 사용: {beat_input.name}")
    # 위상 피팅은 베이스로 한다. --skip-separate면 입력 자체가 베이스 스템이다.
    grid = beats.track_beats(beat_input, workdir, phase_source=bass_stem)
    stages["beats"] = _done(t)

    # 4) 채보 — 엔진에 따라 뒷단 후처리 방식이 달라진다.
    #    crepe는 프레임당 피치가 하나라 배음 거짓 음을 만들지 않는다.
    t = time.monotonic()
    monophonic = args.engine == "crepe"
    engine_fn = transcribe_crepe.transcribe if monophonic else transcribe.transcribe
    note_events = engine_fn(bass_stem, verbose=True)
    stages["transcribe"] = _done(t)

    # 5) 베이스 후처리
    t = time.monotonic()
    cleaned, clean_report = bassclean.clean(
        note_events,
        verbose=True,
        monophonic_source=monophonic,
    )
    stages["bassclean"] = _done(t)

    # 실제 음량을 재서 두 연주가 섞인 입력을 정리한다(연습 영상: 원곡 반주 +
    # 커버 연주). 정상 입력에서는 게이트가 스스로 아무것도 버리지 않는다.
    bassclean.measure_loudness(cleaned, bass_stem)
    # 게이트 전 노트도 남긴다 — 게이트 전후를 같은 정답으로 채점하기 위해서다.
    bassclean.save_notes(cleaned, workdir / "notes_raw.json")
    # beats_per_bar를 넘긴다. 게이트는 마디마다 같은 비율로 깎는데(한 마디를
    # 통째로 비우지 않기 위해) 기본값 4로 두면 4/4가 아닌 곡에서 마디 경계가
    # 어긋난다.
    cleaned, gate_report = bassclean.gate_by_loudness(
        cleaned, grid.beats, beats_per_bar=grid.beats_per_bar, verbose=True
    )

    # 입력이 연습 영상(베이스 둘)인지 판정한다. 게이트를 건 뒤의 정렬로 본다.
    input_diagnosis = diagnose.diagnose(
        gate_applied=gate_report.applied,
        # 필드 이름이 `grid_*`다. 게이트 판정을 8분 격자에서 16분·셋잇단 격자로
        # 바꿀 때 함께 바뀌었다. 옛 이름을 쓰면 AttributeError로 잡 전체가
        # 죽는다 — 실제로 골든셋 3곡이 분리·채보를 다 끝낸 뒤 여기서 죽었다.
        grid_ratio=gate_report.grid_after,
        onsets=[n.start for n in cleaned],
        bass_stem=bass_stem,
        vocals_stem=(stems or {}).get("vocals"),
        verbose=True,
    )

    # 정리된 노트가 악보의 원본이다. 남겨두면 난이도·이조·튜닝을 바꿀 때
    # 채보를 건너뛰고 여기서부터 다시 돌 수 있다.
    bassclean.save_notes(cleaned, workdir / "notes.json")

    # 6) 악보 — 양자화 -> 운지 -> AlphaTex. 웹 경로(jobs.py)와 같은 함수를 쓴다.
    t = time.monotonic()
    built = compose.build(
        cleaned, grid,
        title=info.title,
        tuning=args.tuning,
        include_sync=not args.no_sync,
        verbose=True,
    )
    qscore, fscore = built.qscore, built.fscore
    if built.subdivision_forced:
        print("[score] 셋잇단을 적을 수 없어 subdivision 4로 재양자화했습니다.")
    tex_path = workdir / "score.alphatex"
    tex_path.write_text(built.tex, encoding="utf-8")
    stages["score"] = _done(t)

    # 품질 게이트
    report = quality.evaluate(cleaned, clean_report, grid, qscore, fscore)
    print(f"[quality] {report.score}점 ({report.level})"
          + (f" — {report.reason}" if report.reason else ""))
    for key, value in report.components.items():
        print(f"           {key:26s} {value:.3f}")

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
        # 2: notes.json이 함께 저장되고 악보를 레벨·이조별로 다시 그릴 수 있다.
        "schemaVersion": 2,
        "source": {
            "type": info.source_type,
            "id": info.source_id,
            "title": info.title,
            "durationSec": round(info.duration_sec, 2),
        },
        "status": "done",
        "stages": stages,
        "instrument": "bass",
        # 어느 채보 엔진으로 만든 악보인지 남긴다. 엔진마다 거짓 음·누락
        # 성향이 달라서, 나중에 결과를 볼 때 이 값 없이는 해석이 안 된다.
        "engine": args.engine,
        # --skip-separate면 스템이 없어 플레이어를 못 쓴다. 키 자체를 빼서 표시한다.
        **({"stems": sorted(stems), "stemFormat": "opus"} if stems else {}),
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
        "loudnessGate": gate_report.to_dict(),
        "inputDiagnosis": input_diagnosis.to_dict(),
        # 프론트가 요청할 수 있는 악보 변형 범위 (apps/worker/main.py의 /api/scores)
        "scoreVariants": {
            "levels": reduce.available_levels(
                reduce.assess_original(qscore),
                practice_video=input_diagnosis.practice_video,
            ),
            "transposeRange": [-compose.TRANSPOSE_LIMIT, compose.TRANSPOSE_LIMIT],
            "tunings": sorted(fretting.TUNING_PRESETS),
        },
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
