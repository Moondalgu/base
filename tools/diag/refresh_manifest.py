"""저장된 원본에서 manifest를 다시 만든다 (채보 없이).

파이프라인을 전부 돌리지 않고 뒷단만 고치면 manifest가 낡는다. 실제로 그랬다 —
음량 게이트를 넣어 노트가 479에서 272로 줄었는데 `noteCount`는 450으로 남아
있었고, 튜닝 프리셋을 추가했는데 `scoreVariants.tunings`에 반영되지 않았다.

`notes.json` + `beats.json` + `chords.json`이 있으면 채보(9~14분) 없이
양자화부터 다시 돌려 manifest를 정확히 맞출 수 있다.

**품질 점수는 다시 계산하지 않는다.** `quality.evaluate`가 `CleanReport`를
요구하는데 그것은 저장되지 않는다(후처리 단계에서만 존재한다). 없는 값을
0으로 채워 넣으면 "음역 이탈 0건"이라는 거짓 보고가 된다. 대신 그 점수가
언제 것인지 표시해 둔다.

사용:
    python tools/diag/refresh_manifest.py data/<hash>
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "apps" / "worker"))

from pipeline import (  # noqa: E402
    bassclean, beats as beats_mod, chords as chords_mod, compose, fretting,
    quantize as quantize_mod, reduce as reduce_mod,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="manifest 재생성 (채보 없이)")
    parser.add_argument("workdir", type=Path, help="data/<hash>")
    args = parser.parse_args()

    workdir: Path = args.workdir
    manifest_path = workdir / "manifest.json"
    notes_path = workdir / "notes.json"
    beats_path = workdir / "beats.json"
    if not manifest_path.exists() or not notes_path.exists():
        print(f"[오류] manifest.json 또는 notes.json이 없습니다: {workdir}")
        return 1

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    grid = beats_mod.BeatGrid.from_json(beats_path)

    # 게이트 전 노트가 있으면 **게이트부터 다시 돌린다.** 게이트 규칙을 고쳤을 때
    # 채보(14분)를 다시 하지 않고 반영하려면 이 경로가 필요하다.
    raw_path = workdir / "notes_raw.json"
    if raw_path.exists():
        raw = bassclean.load_notes(raw_path)
        stem_for_loudness = workdir / "stems" / "bass.wav"
        if stem_for_loudness.exists() and all(n.loudness <= 0 for n in raw):
            bassclean.measure_loudness(raw, stem_for_loudness)
        notes, gate_report = bassclean.gate_by_loudness(
            raw, grid.beats, beats_per_bar=grid.beats_per_bar
        )
        bassclean.save_notes(notes, notes_path)
        manifest["loudnessGate"] = gate_report.to_dict()
        print(f"  게이트 재실행 {len(raw)} -> {len(notes)}음 "
              f"(격자정렬 {100 * gate_report.grid_before:.1f}% -> "
              f"{100 * gate_report.grid_after:.1f}%)")
    else:
        notes = bassclean.load_notes(notes_path)

    qscore = quantize_mod.quantize(notes, grid)
    fscore = fretting.assign(qscore, manifest.get("tuning", {}).get("preset", "standard"))
    assessment = reduce_mod.assess_original(qscore)

    before = {
        "noteCount": manifest.get("noteCount"),
        "subdivision": manifest.get("subdivision"),
        "tunings": manifest.get("scoreVariants", {}).get("tunings"),
        "levels": manifest.get("scoreVariants", {}).get("levels"),
    }

    manifest["schemaVersion"] = 2
    manifest["barCount"] = len(fscore.bars)
    manifest["noteCount"] = sum(len(b.notes) for b in fscore.bars)
    manifest["subdivision"] = fscore.subdivision
    manifest["swing"] = qscore.swing
    manifest["phase"] = qscore.phase
    manifest["phaseCorrected"] = qscore.phase_corrected
    manifest["timeSignature"] = [fscore.beats_per_bar, 4]
    # 입력 종류 판정. 게이트 결과는 manifest에 남아 있으므로 오디오에서
    # 어택 편차만 다시 재면 된다.
    gate = manifest.get("loudnessGate") or {}
    stem = workdir / "stems" / "bass.wav"
    diagnosis = None
    if stem.exists():
        from pipeline import diagnose as diagnose_mod

        diagnosis = diagnose_mod.diagnose(
            gate_applied=bool(gate.get("applied")),
            grid_ratio=float(gate.get("gridAfter", 1.0)),
            onsets=[n.start for n in notes],
            bass_stem=stem,
            vocals_stem=workdir / "stems" / "vocals.wav",
        )
        manifest["inputDiagnosis"] = diagnosis.to_dict()

    manifest["scoreVariants"] = {
        "levels": reduce_mod.available_levels(
            assessment,
            practice_video=bool(diagnosis and diagnosis.practice_video),
        ),
        "transposeRange": [-compose.TRANSPOSE_LIMIT, compose.TRANSPOSE_LIMIT],
        "tunings": sorted(fretting.TUNING_PRESETS),
    }
    manifest["originalDifficulty"] = assessment.to_dict()

    # 조성은 코드에서 다시 계산한다(오디오를 보지 않는다).
    chords_path = workdir / "chords.json"
    if chords_path.exists():
        data = json.loads(chords_path.read_text(encoding="utf-8"))
        bar_chords = [
            chords_mod.BarChord(
                x["bar"], x["bassPitchClass"], x["rootPitchClass"],
                x["name"], x["quality"], x["inverted"], x["confidence"],
            )
            for x in data
        ]
        key = chords_mod.detect_key(bar_chords)
        if key:
            manifest["key"] = key.to_dict()

    # 품질 점수는 CleanReport 없이 다시 낼 수 없다. 언제 것인지만 표시한다.
    if "quality" in manifest:
        manifest["quality"]["stale"] = True

    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print(f"=== {workdir.name} manifest 갱신 ===")
    print(f"  noteCount    {before['noteCount']} -> {manifest['noteCount']}")
    print(f"  subdivision  {before['subdivision']} -> {manifest['subdivision']}")
    print(f"  levels       {before['levels']} -> {manifest['scoreVariants']['levels']}")
    print(f"  tunings      {before['tunings']} -> {manifest['scoreVariants']['tunings']}")
    if manifest.get("key"):
        k = manifest["key"]
        print(f"  key          {k['name']} (조표 {k['signatureName']}, 확신도 {k['confidence']})")
    print(f"  원곡 난이도   {assessment.reason}")
    print("  ※ 품질 점수는 CleanReport가 없어 다시 내지 않았다 (stale 표시)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
