"""FastAPI 워커 (PRD 6.5).

파이프라인을 웹에서 돌리고 진행률을 SSE로 흘린다.
스템·악보 서빙은 Next.js 쪽 라우트가 담당하므로 여기서는 잡만 다룬다.
"""

from __future__ import annotations

import asyncio
import json
import shutil
from pathlib import Path
from urllib.parse import quote

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel

import jobs
from pipeline import compose, export

app = FastAPI(title="Lowend Worker")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

UPLOADS = jobs.DATA / "_uploads"


class JobRequest(BaseModel):
    source: str
    tuning: str = "standard"


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "dataRoot": str(jobs.DATA)}


@app.post("/api/jobs")
async def create_job(req: JobRequest) -> dict:
    cached = jobs.find_cached(req.source)
    if cached:
        return {"jobId": None, "contentHash": cached, "cached": True}

    job = jobs.create_job(req.source, req.tuning)
    return {"jobId": job.id, "contentHash": None, "cached": False}


@app.post("/api/upload")
async def upload(file: UploadFile = File(...), tuning: str = "standard") -> dict:
    """파일을 받아 저장하고 잡을 만든다."""
    if not file.filename:
        raise HTTPException(status_code=400, detail="파일 이름이 없습니다")

    UPLOADS.mkdir(parents=True, exist_ok=True)
    target = UPLOADS / file.filename
    with target.open("wb") as out:
        shutil.copyfileobj(file.file, out)

    cached = jobs.find_cached(str(target))
    if cached:
        return {"jobId": None, "contentHash": cached, "cached": True}

    job = jobs.create_job(str(target), tuning)
    return {"jobId": job.id, "contentHash": None, "cached": False}


@app.get("/api/jobs/{job_id}")
async def job_status(job_id: str) -> dict:
    job = jobs.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="잡을 찾을 수 없습니다")

    payload = {
        "jobId": job.id,
        "status": job.status,
        "contentHash": job.content_hash,
        "error": job.error,
    }
    if job.content_hash:
        manifest = jobs.DATA / job.content_hash / "manifest.json"
        if manifest.exists():
            payload["manifest"] = json.loads(manifest.read_text(encoding="utf-8"))
    return payload


@app.get("/api/jobs/{job_id}/events")
async def job_events(job_id: str) -> StreamingResponse:
    job = jobs.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="잡을 찾을 수 없습니다")

    return StreamingResponse(
        jobs.stream(job),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.get("/api/scores/{content_hash}")
async def score_variant(
    content_hash: str,
    level: int = compose.ORIGINAL_LEVEL,
    transpose: int = 0,
    tuning: str | None = None,
) -> Response:
    """악보를 난이도·이조·튜닝별로 다시 그려 AlphaTex로 돌려준다.

    저장된 노트에서 양자화부터 다시 도는 것이므로 채보(약 480초)가 없다.
    프론트는 피치를 바꿀 때마다 같은 transpose 값으로 여기를 다시 부른다 —
    들리는 음과 악보가 어긋나면 안 되기 때문이다.
    """
    try:
        built = await asyncio.to_thread(
            jobs.build_score_variant,
            content_hash,
            level=level,
            transpose=transpose,
            tuning=tuning,
        )
    except jobs.MissingOriginals as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except compose.UnsupportedLevel as exc:
        raise HTTPException(status_code=501, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return Response(
        content=built.tex,
        media_type="text/plain; charset=utf-8",
        headers={
            # 프론트가 옥타브 접힘·표기 폴백을 사용자에게 알릴 수 있게 함께 넘긴다.
            # 본문은 alphaTab에 그대로 먹여야 하므로 여기에 섞을 수 없다.
            "X-Score-Level": str(built.level),
            "X-Score-Transpose": str(built.transpose),
            "X-Score-Octave-Folded": str(built.octave_folded),
            "X-Score-Subdivision-Forced": "1" if built.subdivision_forced else "0",
            "Cache-Control": "no-store",
        },
    )


@app.get("/api/scores/{content_hash}/ledger.csv")
async def score_ledger(
    content_hash: str,
    level: int = compose.ORIGINAL_LEVEL,
    transpose: int = 0,
    tuning: str | None = None,
) -> Response:
    """음표 배치 원장 — 화면 악보와 같은 변형의 모든 음을 CSV로.

    각 음이 어느 마디·슬롯·박에, 어떤 검출 시각에서 스냅되어, 어떤 피치
    출처(검출/템플릿)와 운지로 들어갔는지 전부 담는다. `/api/scores`와 같은
    인자·같은 `compose.build()`를 탄다 — 화면과 다른 원장을 주면 거짓말이 된다.
    """
    from pipeline import ledger as ledger_mod

    try:
        built = await asyncio.to_thread(
            jobs.build_score_variant,
            content_hash, level=level, transpose=transpose, tuning=tuning,
        )
    except jobs.MissingOriginals as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except compose.UnsupportedLevel as exc:
        raise HTTPException(status_code=501, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return Response(
        content=ledger_mod.to_csv(built.ledger or []),
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition":
                f'attachment; filename="{content_hash}_lv{built.level}_ledger.csv"',
            "Cache-Control": "no-store",
        },
    )


@app.get("/api/exports/{content_hash}.{fmt}")
async def score_export(
    content_hash: str,
    fmt: str,
    level: int = compose.ORIGINAL_LEVEL,
    transpose: int = 0,
    tuning: str | None = None,
) -> Response:
    """악보를 MusicXML 또는 MIDI로 내보낸다.

    **난이도·이조·튜닝을 그대로 받는다.** 화면에서 보고 있는 것과 다른 것이
    내려가면 사용자가 알 방법이 없다. `/api/scores`와 같은 인자를 같은 순서로
    받아 같은 `compose.build()`를 타게 한 이유가 그것이다.

    MusicXML은 현·프렛을 담으므로 Guitar Pro·MuseScore에서 TAB이 살아 있다.
    MIDI는 음정·리듬만 남는다(포맷에 운지 자리가 없다).
    """
    if fmt not in ("musicxml", "mid"):
        raise HTTPException(
            status_code=404,
            detail=f"지원하지 않는 형식: {fmt} (musicxml 또는 mid)",
        )
    try:
        built = await asyncio.to_thread(
            jobs.build_score_variant,
            content_hash,
            level=level,
            transpose=transpose,
            tuning=tuning,
        )
        meta = await asyncio.to_thread(
            jobs.score_metadata, content_hash, transpose=transpose
        )
    except jobs.MissingOriginals as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except compose.UnsupportedLevel as exc:
        raise HTTPException(status_code=501, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    stem = _safe_filename(meta["title"]) or content_hash
    suffix = "" if level == compose.ORIGINAL_LEVEL else f"_Lv{level}"
    if transpose:
        suffix += f"_{transpose:+d}st"
    name = f"{stem}{suffix}.{fmt}"

    if fmt == "musicxml":
        body: bytes = export.to_musicxml(
            built.fscore,
            title=meta["title"],
            artist=meta["artist"],
            key_signature=meta["keySignature"],
        ).encode("utf-8")
        media = "application/vnd.recordare.musicxml+xml"
    else:
        body = export.to_midi(built.fscore)
        media = "audio/midi"

    return Response(
        content=body,
        media_type=media,
        headers={
            # RFC 5987 형식으로 한글 제목을 담는다. filename= 만 쓰면 비ASCII가
            # 깨지고, filename*= 만 쓰면 옛 브라우저가 못 읽는다.
            "Content-Disposition": (
                f'attachment; filename="{content_hash}.{fmt}"; '
                f"filename*=UTF-8''{quote(name)}"
            ),
            "Cache-Control": "no-store",
        },
    )


def _safe_filename(text: str) -> str:
    """파일명에 쓸 수 없는 문자를 뺀다. 경로 구분자와 제어문자가 대상이다."""
    cleaned = "".join(
        c for c in (text or "") if c not in '\\/:*?"<>|' and c.isprintable()
    ).strip()
    return cleaned[:80]


@app.get("/api/library")
async def library() -> list[dict]:
    """처리 완료된 곡 목록."""
    out: list[dict] = []
    if not jobs.DATA.exists():
        return out
    for child in sorted(jobs.DATA.iterdir()):
        manifest = child / "manifest.json"
        if not manifest.exists():
            continue
        try:
            data = json.loads(manifest.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        out.append({
            "contentHash": data.get("contentHash", child.name),
            "title": data.get("source", {}).get("title", child.name),
            "durationSec": data.get("source", {}).get("durationSec"),
            "bpm": data.get("tempo", {}).get("medianBpm"),
            "barCount": data.get("barCount"),
            "noteCount": data.get("noteCount"),
            "quality": data.get("quality", {}),
        })
    return out
