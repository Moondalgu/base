"""이미 처리한 곡의 비트 격자를 제자리에서 다시 만들고 악보를 재조립한다.

박자표 추론(`beats._infer_beats_per_bar`)이 틀렸던 곡을 고칠 때 쓴다.
채보(CREPE, 곡당 ~5분)는 다시 하지 않는다 — 검출은 비트와 무관하므로
`notes_raw.json`(게이트 전 노트)을 그대로 쓰고, 비트에 의존하는 단계
(음량 게이트 → 진단 → 코드 → 양자화 → 운지 → AlphaTex → 품질)만 다시 돈다.

`rebuild_from_raw()`는 regen_notes.py도 재사용한다 — 엔진을 갈아끼운 뒤의
재조립이 이 함수 하나로 통일된다. 갈라지면 도구마다 다른 악보가 나온다.

사용:
    python tools/diag/regen_beats.py data/<hash>
    python tools/diag/regen_beats.py data/<hash> --keep-beats   # 비트는 유지, 재조립만
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "apps" / "worker"))

from pipeline import (  # noqa: E402
    bassclean, beats, chords, compose, diagnose, fretting, quality, reduce,
)


def rebuild_from_raw(
    workdir: Path,
    *,
    grid: "beats.BeatGrid | None" = None,
    tuning: str = "standard",
    cover_overlay: bool | None = None,
) -> dict:
    """notes_raw.json에서 게이트→코드→악보→품질→manifest까지 재조립한다.

    grid를 주지 않으면 기존 beats.json을 읽는다. manifest를 갱신해 저장하고
    그 dict를 돌려준다.

    cover_overlay를 주지 않으면 manifest에 적힌 값을 따른다. 이 도구가 웹과
    다른 악보를 만들지 않게 하려는 것이다 — 여기서 게이트를 강제하면 같은 곡을
    재조립할 때마다 사용자가 끈 게이트가 되살아난다.
    """
    raw_path = workdir / "notes_raw.json"
    bass_stem = workdir / "stems" / "bass.wav"
    manifest_path = workdir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    if grid is None:
        grid = beats.BeatGrid.from_json(workdir / "beats.json")

    # 1) 게이트부터 다시 (게이트는 grid.beats_per_bar에 의존한다)
    if cover_overlay is None:
        cover_overlay = bool(manifest.get("coverOverlay", False))
    cleaned = bassclean.load_notes(raw_path)
    cleaned, gate_report = bassclean.apply_gate(
        cleaned, grid.beats,
        enabled=cover_overlay, beats_per_bar=grid.beats_per_bar, verbose=True,
    )
    input_diagnosis = diagnose.diagnose(
        gate_applied=gate_report.applied,
        grid_ratio=gate_report.grid_after,
        onsets=[n.start for n in cleaned],
        bass_stem=bass_stem,
        vocals_stem=workdir / "stems" / "vocals.wav",
        verbose=True,
    )
    bassclean.save_notes(cleaned, workdir / "notes.json")

    # 2) 코드 + 조성 — 웹·CLI와 같은 공용 함수
    other = workdir / "stems" / "other.wav"
    try:
        chord_names, key = chords.detect_and_save(
            cleaned, grid, other if other.exists() else workdir / "source.wav", workdir
        )
    except Exception as exc:  # noqa: BLE001
        print(f"[chords] 실패: {type(exc).__name__}: {exc} — 코드 없이 진행")
        chord_names, key = None, None

    # 3) 악보 재조립 — 웹·CLI와 같은 compose.build. 보컬 채보가 있으면 3단,
    #    가사(ASR 음절)가 있으면 \lyrics까지.
    from pipeline import lyrics as lyrics_mod

    vocal_path = workdir / "vocal_notes.json"
    vocal_notes = bassclean.load_notes(vocal_path) if vocal_path.exists() else None
    lyrics_path = workdir / "lyrics.json"
    vocal_syllables = (
        lyrics_mod.load_lyrics(lyrics_path)
        if vocal_notes and lyrics_path.exists() else None
    )
    title = manifest.get("source", {}).get("title", workdir.name)
    built = compose.build(
        cleaned, grid, title=title, tuning=tuning, include_sync=True,
        chords=chord_names,
        key_signature=(key or {}).get("signatureName"),
        vocal_notes=vocal_notes,
        vocal_syllables=vocal_syllables,
        chord_tones=chords.load_tones(workdir / "chords.json"),
        diatonic_pcs=(
            chords.diatonic_pcs(key["tonicPitchClass"], key.get("mode", "major"))
            if key and key.get("tonicPitchClass") is not None else None
        ),
        verbose=True,
    )
    qscore, fscore = built.qscore, built.fscore
    (workdir / "score.alphatex").write_text(built.tex, encoding="utf-8")
    from pipeline import ledger as ledger_mod

    ledger_mod.write(built.ledger or [], workdir / "ledger.csv")

    # 4) 품질 재계산 — clean_report(정리 단계 통계)는 이 시점에 없다.
    #    evaluate가 쓰는 것은 out_of_range_ratio 하나뿐이므로 기존 manifest의
    #    rangeIntegrity에서 역산한다 (rangeIntegrity = 1 − ratio×4). 정리
    #    단계는 다시 돌지 않았으므로 이 값은 실제로 변하지 않았다.
    prev_range = (
        manifest.get("quality", {}).get("components", {}).get("rangeIntegrity", 1.0)
    )
    shim = type("CleanReportShim", (), {
        "out_of_range_ratio": max(0.0, (1.0 - float(prev_range)) / 4.0)
    })()
    report = quality.evaluate(cleaned, shim, grid, qscore, fscore)
    print(f"[quality] {report.score}점 ({report.level})")

    assessment = reduce.assess_original(qscore)
    manifest.update({
        "tempo": {"medianBpm": round(grid.median_bpm, 1), "variance": round(grid.bpm_variance, 4)},
        "timeSignature": [fscore.beats_per_bar, 4],
        "barCount": len(fscore.bars),
        "noteCount": sum(len(b.notes) for b in fscore.bars),
        "subdivision": fscore.subdivision,
        "swing": qscore.swing,
        "loudnessGate": gate_report.to_dict(),
        "inputDiagnosis": input_diagnosis.to_dict(),
        "originalDifficulty": assessment.to_dict(),
        "scoreVariants": {
            "levels": reduce.available_levels(
                assessment, rhythm_confident=input_diagnosis.rhythm_confident
            ),
            "transposeRange": [-compose.TRANSPOSE_LIMIT, compose.TRANSPOSE_LIMIT],
            "tunings": sorted(fretting.TUNING_PRESETS),
        },
        "phase": qscore.phase,
        "phaseCorrected": qscore.phase_corrected,
        "quality": report.to_dict(),
    })
    if key:
        manifest["key"] = key
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[완료] 마디 {manifest['barCount']}, 음표 {manifest['noteCount']}, "
          f"{manifest['timeSignature'][0]}/4, {manifest['tempo']['medianBpm']}BPM")
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description="비트 격자 제자리 재생성 + 악보 재조립")
    parser.add_argument("workdir", type=Path, help="data/<hash> 디렉토리")
    parser.add_argument("--tuning", default="standard", choices=sorted(fretting.TUNING_PRESETS))
    parser.add_argument(
        "--keep-beats", action="store_true",
        help="비트를 다시 추적하지 않고 기존 beats.json으로 재조립만 한다",
    )
    args = parser.parse_args()

    workdir: Path = args.workdir
    source = workdir / "source.wav"
    bass_stem = workdir / "stems" / "bass.wav"
    raw_path = workdir / "notes_raw.json"
    for p, why in ((source, "원본"), (bass_stem, "베이스 스템"), (raw_path, "게이트 전 노트")):
        if not p.exists():
            print(f"[오류] {why}이 없습니다: {p}")
            return 1

    grid = None
    if not args.keep_beats:
        cache = workdir / "beats.json"
        if cache.exists():
            cache.unlink()
        t = time.monotonic()
        grid = beats.track_beats(source, workdir, phase_source=bass_stem)
        print(f"[regen] 비트 {time.monotonic() - t:.1f}s: {grid.beats_per_bar}/4, "
              f"{grid.median_bpm:.1f} BPM, var={grid.bpm_variance:.3f}")

    rebuild_from_raw(workdir, grid=grid, tuning=args.tuning)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
