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
    alphatex, bassclean, beats, encode, fretting, quality, quantize, separate,
    transcribe, transcribe_crepe,
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
    ("quantize", "리듬 정리"),
    ("fretting", "운지 배정"),
    ("alphatex", "악보 생성"),
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
        qscore = await run_stage("quantize", quantize.quantize, cleaned, grid)
        fscore = await run_stage("fretting", fretting.assign, qscore, job.tuning)

        report = quality.evaluate(cleaned, clean_report, grid, qscore, fscore)

        def build_tex() -> str:
            nonlocal qscore, fscore, report
            try:
                return alphatex.build(fscore, title=info.title)
            except alphatex.UnsupportedSubdivision:
                # 예상 못 한 subdivision이면 스트레이트 16분으로 재양자화한다.
                # 리듬은 덜 정확해지지만 악보가 아예 안 나오는 것보다 낫다.
                qscore = quantize.quantize(cleaned, grid, force_subdivision=4)
                fscore = fretting.assign(qscore, job.tuning)
                report = quality.evaluate(cleaned, clean_report, grid, qscore, fscore)
                return alphatex.build(fscore, title=info.title)

        tex = await run_stage("alphatex", build_tex)
        (workdir / "score.alphatex").write_text(tex, encoding="utf-8")

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
            # 마디 시각 재구성에 필요하다. 없으면 평가 도구가 슬롯 시각을 틀리게 계산한다.
            "phase": qscore.phase,
            "phaseCorrected": qscore.phase_corrected,
            "quality": report.to_dict(),
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
