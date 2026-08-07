"""잡 오케스트레이션 (PRD 6.3).

Celery/Redis를 쓰지 않는다. 로컬 단일 사용자에 과하다.
- CPU 바운드 단계는 asyncio.to_thread로 돌린다 (torch가 GIL을 놓으므로
  이벤트 루프가 살아있다)
- 상태는 data/{hash}/manifest.json에 쓴다 — 프로세스가 죽어도 살아남는다
- 진행률은 asyncio.Queue로 SSE에 흘린다

업그레이드 경로: pipeline/은 그대로 두고 이 파일의 실행기만 큐로 교체하면 된다.
"""

from __future__ import annotations

import asyncio
import json
import time
import traceback
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, AsyncGenerator

from pipeline import (
    bassclean, beats, compose, diagnose, encode, fretting, quality, reduce,
    separate, transcribe, transcribe_crepe,
)
from pipeline.ingest import ingest

ROOT = Path(__file__).resolve().parent.parent.parent
DATA = ROOT / "data"

# 웹 경로의 채보 엔진. crepe는 프레임당 피치가 하나라 배음 거짓 음을
# 만들지 않는다(정답 데이터셋 거짓 음 22.8% -> 10.5%).
DEFAULT_ENGINE = "crepe"

STAGES = [
    ("ingest", "오디오 준비"),
    ("separate", "악기 분리"),
    ("encode", "전송용 인코딩"),
    ("beats", "박자 분석"),
    ("transcribe", "음 검출"),
    ("bassclean", "베이스 정리"),
    ("chords", "코드 분석"),
    # 양자화·운지·표기는 한 단계로 묶는다. 셋잇단을 적을 수 없을 때 격자를
    # 되돌려 세 단계를 다시 도는 폴백이 있어서 경계가 원래 없고, 세 단계를
    # 합쳐도 분리(450초)·채보(480초) 옆에서는 1초가 안 된다. 무엇보다
    # "레벨·이조를 바꿔 다시 그려달라"는 요청이 같은 코드를 타야 한다.
    ("score", "악보 생성"),
]


@dataclass
class Job:
    id: str
    source: str
    tuning: str
    content_hash: str | None = None
    status: str = "queued"  # queued | running | done | failed
    error: str | None = None
    events: asyncio.Queue = field(default_factory=asyncio.Queue)
    task: asyncio.Task | None = None


_JOBS: dict[str, Job] = {}


def get_job(job_id: str) -> Job | None:
    return _JOBS.get(job_id)


def find_cached(source: str) -> str | None:
    """이미 처리한 소스인지 확인한다. 있으면 contentHash를 돌려준다."""
    try:
        from pipeline.ingest.base import content_hash_of
        from pipeline.ingest.ytdlp import extract_video_id

        video_id = extract_video_id(source)
        if video_id:
            chash = content_hash_of(f"youtube:{video_id}")
        else:
            path = Path(source)
            if not path.exists():
                return None
            chash = content_hash_of(path.read_bytes())
        manifest = DATA / chash / "manifest.json"
        if manifest.exists():
            data = json.loads(manifest.read_text(encoding="utf-8"))
            if data.get("status") == "done":
                return chash
    except Exception:
        pass
    return None


def _detect_chords(
    cleaned: list, grid, audio_path: Path, workdir: Path
) -> tuple[list[str] | None, dict | None]:
    """마디별 코드를 판정해 chords.json에 남기고 이름 목록을 돌려준다.

    코드 판정에 마디 근음이 필요한데, 근음은 양자화된 마디에서 나온다. 그래서
    여기서 양자화를 한 번 더 돈다 — 밀리초 단위라 비용이 없고, compose 안에서
    코드를 만들면 "오디오 분석"과 "표기 조립"이 섞여 변형 요청마다 오디오를
    다시 읽게 된다.
    """
    from pipeline import chords as chords_mod
    from pipeline import quantize as quantize_mod
    from pipeline import reduce as reduce_mod

    try:
        qscore = quantize_mod.quantize(cleaned, grid)
        bars = [
            (b.index, b.start_sec, b.end_sec, reduce_mod.bar_root(b))
            for b in qscore.bars
        ]
        detected = chords_mod.detect(audio_path, bars)
        # 코드 진행이 나오면 조성은 계산으로 떨어진다. 오디오를 다시 안 본다.
        key = chords_mod.detect_key(detected)
    except Exception as exc:  # noqa: BLE001
        # 코드가 없어도 악보는 나온다. 여기서 잡을 멈추지 않는다.
        print(f"[chords] 실패: {type(exc).__name__}: {exc}")
        return None, None

    (workdir / "chords.json").write_text(
        json.dumps([c.to_dict() for c in detected], ensure_ascii=False),
        encoding="utf-8",
    )
    return [c.name for c in detected], (key.to_dict() if key else None)


class MissingOriginals(FileNotFoundError):
    """악보를 다시 그릴 원본이 없다. schemaVersion 1 산출물이면 이 상태다."""


def build_score_variant(
    content_hash: str,
    *,
    level: int = compose.ORIGINAL_LEVEL,
    transpose: int = 0,
    tuning: str | None = None,
) -> compose.BuiltScore:
    """저장된 원본에서 악보를 다시 그린다. 채보는 다시 돌지 않는다.

    tuning을 주지 않으면 원래 잡이 쓴 튜닝을 manifest에서 읽는다.
    """
    workdir = DATA / content_hash
    notes_path = workdir / "notes.json"
    beats_path = workdir / "beats.json"
    if not notes_path.exists() or not beats_path.exists():
        raise MissingOriginals(
            f"{content_hash}에 notes.json/beats.json이 없습니다. "
            "파이프라인을 다시 돌려야 악보 변형을 만들 수 있습니다."
        )

    title = content_hash
    manifest_path = workdir / "manifest.json"
    if manifest_path.exists():
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
        title = data.get("source", {}).get("title") or title
        if tuning is None:
            tuning = data.get("tuning", {}).get("preset")

    # 코드는 오디오 분석 결과라 레벨·이조와 무관하다. 한 번 구워두고 읽는다.
    # 이조하면 코드 이름도 함께 옮겨야 한다 — 악보가 옮겨졌는데 코드가 그대로면
    # 서로 어긋난다. 조표도 마찬가지다.
    chord_names = _load_chords(workdir / "chords.json", transpose)
    key_signature = _load_key_signature(workdir, transpose)

    return compose.build(
        bassclean.load_notes(notes_path),
        beats.BeatGrid.from_json(beats_path),
        title=title,
        tuning=tuning or "standard",
        level=level,
        transpose=transpose,
        chords=chord_names,
        key_signature=key_signature,
    )


def score_metadata(content_hash: str, *, transpose: int = 0) -> dict:
    """내보내기 파일에 적을 제목·아티스트·조표.

    `build_score_variant`가 이미 manifest를 읽지만 `BuiltScore`에 제목을
    담지 않는다(AlphaTex 안에는 들어간다). 파일 이름과 MusicXML 헤더에
    쓰려면 따로 필요하다. **transpose를 함께 받는 이유**: 이조한 악보를
    원래 조표로 적으면 임시표가 전부 어긋난다.
    """
    workdir = DATA / content_hash
    title, artist = content_hash, ""
    manifest_path = workdir / "manifest.json"
    if manifest_path.exists():
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
        source = data.get("source") or {}
        title = source.get("title") or title
        artist = source.get("uploader") or source.get("artist") or ""
    return {
        "title": title,
        "artist": artist,
        "keySignature": _load_key_signature(workdir, transpose),
    }


def _load_key_signature(workdir: Path, transpose: int) -> str | None:
    """저장된 조성을 읽어 이조만큼 옮긴 조표 이름을 돌려준다. 없으면 None.

    조성을 모르면 조표를 적지 않는다 — C장조로 찍으면 임시표가 엉망이 되어
    악보가 오히려 나빠진다.

    **확신이 없어도 적지 않는다.** `chords.detect_key()`가 `trusted=False`로
    표시한 경우다. 조성 이름은 manifest에 그대로 남으므로 UI에서 참고로 보여줄
    수는 있다 — 악보 조표로만 쓰지 않는 것이다.

    구버전 산출물에는 `trusted` 키가 없다. 그때는 True로 본다 — 없는 정보를
    False로 단정하면 이미 맞게 나온 조표까지 지운다.
    """
    manifest_path = workdir / "manifest.json"
    if not manifest_path.exists():
        return None
    key = json.loads(manifest_path.read_text(encoding="utf-8")).get("key")
    if not key or key.get("tonicPitchClass") is None:
        return None
    if not key.get("trusted", True):
        return None

    from pipeline import chords as chords_mod

    tonic = (int(key["tonicPitchClass"]) + transpose) % 12
    name, _flats = chords_mod.signature_for(tonic, key.get("mode", "major"))
    return name


def _load_chords(path: Path, transpose: int) -> list[str] | None:
    """저장된 코드 이름을 읽고 이조만큼 옮긴다. 없으면 None."""
    if not path.exists():
        return None
    from pipeline import chords as chords_mod

    data = json.loads(path.read_text(encoding="utf-8"))
    out: list[str] = []
    for item in data:
        name = item.get("name") or ""
        if not name or transpose == 0:
            out.append(name)
            continue
        root = item.get("rootPitchClass")
        if root is None:
            out.append("")   # 루트를 모르면 옮길 수 없다. 비운다.
            continue
        # 분수 코드는 루트와 베이스 음을 **둘 다** 옮겨야 한다. 하나만 옮기면
        # C/E가 D/E 같은 존재하지 않는 표기가 된다.
        bass = item.get("bassPitchClass")
        out.append(
            chords_mod.name_of(
                (root + transpose) % 12,
                item.get("quality"),
                (bass + transpose) % 12 if item.get("inverted") and bass is not None else None,
            )
        )
    return out


def create_job(source: str, tuning: str = "standard") -> Job:
    job = Job(id=uuid.uuid4().hex[:12], source=source, tuning=tuning)
    _JOBS[job.id] = job
    job.task = asyncio.create_task(_run(job))
    return job


async def _run(job: Job) -> None:
    job.status = "running"
    stages: dict[str, dict] = {}

    async def emit(**payload: Any) -> None:
        await job.events.put(payload)

    def stage_index(key: str) -> int:
        return next(i for i, (k, _) in enumerate(STAGES) if k == key)

    async def run_stage(key: str, fn, *args, **kwargs):
        label = dict(STAGES)[key]
        await emit(
            stage=key,
            label=label,
            status="start",
            progress=stage_index(key) / len(STAGES),
        )
        start = time.monotonic()
        result = await asyncio.to_thread(fn, *args, **kwargs)
        ms = int((time.monotonic() - start) * 1000)
        stages[key] = {"status": "done", "ms": ms}
        await emit(
            stage=key,
            label=label,
            status="done",
            ms=ms,
            progress=(stage_index(key) + 1) / len(STAGES),
        )
        return result

    try:
        info = await run_stage("ingest", ingest, job.source, DATA)
        job.content_hash = info.content_hash
        workdir = info.wav_path.parent
        await emit(contentHash=info.content_hash, title=info.title,
                   durationSec=round(info.duration_sec, 2))

        stems = await run_stage("separate", separate.separate, info.wav_path, workdir)
        # 파이프라인은 wav를 계속 쓰고, 브라우저는 opus만 받는다 (encode.py 주석)
        await run_stage("encode", encode.encode_stems, stems)
        # 비트는 믹스에서 잡고, 마디 시작 위상은 베이스 스템으로 맞춘다.
        grid = await run_stage(
            "beats", beats.track_beats, info.wav_path, workdir,
            phase_source=stems.get("bass"),
        )
        # 엔진에 따라 뒷단 후처리가 갈린다. crepe 출력에는 배음 거짓 음도
        # 조각도 없어서 배음 제거·단선율 강제·병합이 실제 음만 깎는다.
        monophonic = DEFAULT_ENGINE == "crepe"
        engine_fn = transcribe_crepe.transcribe if monophonic else transcribe.transcribe
        note_events = await run_stage("transcribe", engine_fn, stems["bass"])

        cleaned, clean_report = await run_stage(
            "bassclean",
            bassclean.clean,
            note_events,
            monophonic_source=monophonic,
        )
        # 실제 음량을 재서 두 연주가 섞인 입력을 정리한다. 연습 영상은 원곡
        # 반주 위에 커버 연주가 겹치는데, 크게 녹음된 쪽(커버)만 남기면 리듬이
        # 격자에 돌아온다. 정상 입력에서는 게이트가 스스로 아무것도 버리지 않는다.
        bassclean.measure_loudness(cleaned, stems["bass"])
        # 게이트 **전** 노트도 남긴다. 게이트가 이득인지 판정하려면 전후를 같은
        # 정답으로 채점할 수 있어야 하는데, 후처리 결과만 저장하면 그 비교가
        # 영원히 불가능해진다(실제로 막혔다).
        bassclean.save_notes(cleaned, workdir / "notes_raw.json")
        cleaned, gate_report = bassclean.gate_by_loudness(cleaned, grid.beats)

        # 입력이 연습 영상(베이스 둘)인지 판정한다. 게이트를 **건 뒤**의 정렬로
        # 봐야 한다 — 게이트 전 값으로 보면 게이트가 해결한 곡까지 몰린다.
        diagnosis = diagnose.diagnose(
            gate_applied=gate_report.applied,
            grid_ratio=gate_report.grid_after,
            onsets=[n.start for n in cleaned],
            bass_stem=stems["bass"],
            vocals_stem=stems.get("vocals"),
        )

        # 정리된 노트가 악보의 원본이다. 남겨두면 난이도·이조·튜닝을 바꿀 때
        # 채보(약 480초)를 건너뛰고 여기서부터 다시 돌 수 있다.
        bassclean.save_notes(cleaned, workdir / "notes.json")

        # 코드 심볼 — 화성 악기가 든 other 스템의 크로마를 본다. 베이스 스템에는
        # 근음만 있어 3도가 없다. 마디 근음은 베이스 채보에서 이미 나오므로
        # 남는 판단은 장/단뿐이다.
        chord_names, key = await run_stage(
            "chords", _detect_chords, cleaned, grid,
            stems.get("other") or info.wav_path, workdir,
        )

        built = await run_stage(
            "score", compose.build, cleaned, grid,
            title=info.title, tuning=job.tuning, chords=chord_names,
            key_signature=(key or {}).get("signatureName"),
        )
        qscore, fscore = built.qscore, built.fscore
        # 원곡이 이미 초급 수준인지 본다. 쉬운 곡에는 단계를 만들지 않는다.
        assessment = reduce.assess_original(qscore)
        report = quality.evaluate(cleaned, clean_report, grid, qscore, fscore)
        (workdir / "score.alphatex").write_text(built.tex, encoding="utf-8")

        manifest = {
            "contentHash": info.content_hash,
            # 2: notes.json이 함께 저장되고 악보를 레벨·이조별로 다시 그릴 수 있다.
            #    1은 score.alphatex 하나만 있어서 프론트가 변형을 요청할 수 없다.
            "schemaVersion": 2,
            "source": {
                "type": info.source_type,
                "id": info.source_id,
                "title": info.title,
                "durationSec": round(info.duration_sec, 2),
            },
            "status": "done",
            "stages": stages,
            "stems": sorted(stems),
            # 플레이어가 스템 URL 확장자를 정할 때 읽는다. 없으면 wav로 간주(구버전).
            "stemFormat": "opus",
            "instrument": "bass",
            # 어느 채보 엔진으로 만든 악보인지 남긴다. 엔진마다 거짓 음·누락
            # 성향이 달라서, 나중에 결과를 볼 때 이 값 없이는 해석이 안 된다.
            "engine": DEFAULT_ENGINE,
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
            # 프론트가 요청할 수 있는 악보 변형 범위. 레벨은 하향만 가능하고
            # (원곡이 상한), 이조는 재생 피치와 같은 값을 써야 한다.
            #
            # 원곡이 이미 초급 수준이면 levels에 원본 하나만 담긴다 — 쉬운 곡을
            # 더 깎으면 원곡보다 심심해지기만 한다.
            "scoreVariants": {
                "levels": reduce.available_levels(
                    assessment, practice_video=diagnosis.practice_video
                ),
                "transposeRange": [-compose.TRANSPOSE_LIMIT, compose.TRANSPOSE_LIMIT],
                "tunings": sorted(fretting.TUNING_PRESETS),
            },
            "originalDifficulty": assessment.to_dict(),
            # 입력 종류 판정. 연습 영상이면 하향 단계를 만들지 않는다.
            "inputDiagnosis": diagnosis.to_dict(),
            # 조성. 조표 표기에 쓰고, 조성 밖 코드를 의심하는 안전장치로도 쓴다.
            **({"key": key} if key else {}),
            # 마디 시각 재구성에 필요하다. 없으면 평가 도구가 슬롯 시각을 틀리게 계산한다.
            "phase": qscore.phase,
            "phaseCorrected": qscore.phase_corrected,
            "quality": report.to_dict(),
            # 음량 게이트가 걸렸으면 그 곡은 두 연주가 섞인 입력일 가능성이
            # 높다. 사용자에게 알려야 하고, 나중에 결과를 해석할 때도 필요하다.
            "loudnessGate": gate_report.to_dict(),
        }
        (workdir / "manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
        )

        job.status = "done"
        await emit(status="done", contentHash=info.content_hash,
                   quality=report.to_dict(), progress=1.0)
    except Exception as exc:  # noqa: BLE001
        job.status = "failed"
        job.error = f"{type(exc).__name__}: {exc}"
        traceback.print_exc()
        await emit(status="failed", error=job.error)
    finally:
        await job.events.put(None)  # 스트림 종료 신호


async def stream(job: Job) -> AsyncGenerator[str, None]:
    """SSE 이벤트 스트림."""
    while True:
        item = await job.events.get()
        if item is None:
            yield "data: [DONE]\n\n"
            return
        yield f"data: {json.dumps(item, ensure_ascii=False)}\n\n"
