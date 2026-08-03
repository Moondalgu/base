"""FastAPI 워커 (PRD 6.5).

파이프라인을 웹에서 돌리고 진행률을 SSE로 흘린다.
스템·악보 서빙은 Next.js 쪽 라우트가 담당하므로 여기서는 잡만 다룬다.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

import jobs

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
