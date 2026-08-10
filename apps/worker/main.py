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

from fastapi import FastAPI, File, HTTPException, Request, UploadFile
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
    # 원곡을 틀어놓고 그 위에 연주한 커버 영상인가. True일 때만 음량 게이트가
    # 걸린다 — 오디오만으로는 가려낼 수 없어서 사용자에게 묻는다(jobs.py 주석).
    coverOverlay: bool = False


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "dataRoot": str(jobs.DATA)}


@app.post("/api/jobs")
async def create_job(req: JobRequest) -> dict:
    cached = jobs.find_cached(req.source)
    if cached:
        return {"jobId": None, "contentHash": cached, "cached": True}

    job = jobs.create_job(req.source, req.tuning, req.coverOverlay)
    return {"jobId": job.id, "contentHash": None, "cached": False}


@app.post("/api/upload")
async def upload(file: UploadFile = File(...), tuning: str = "standard",
                 coverOverlay: bool = False) -> dict:
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

    job = jobs.create_job(str(target), tuning, coverOverlay)
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


@app.get("/api/scores/{content_hash}/ledger.json")
async def score_ledger_json(
    content_hash: str,
    level: int = compose.ORIGINAL_LEVEL,
    transpose: int = 0,
    tuning: str | None = None,
) -> Response:
    """원장을 JSON으로 — 편집 UI가 (마디, 슬롯) → 검출 시각(srcStart)을
    찾는 데 쓴다. `/api/scores`와 같은 인자·같은 빌드를 탄다."""
    import json as json_mod

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
        content=json_mod.dumps({
            "rows": built.ledger or [],
            # 클릭 좌표(마디 안 비율) → 슬롯 환산에 필요하다.
            "subdivision": built.fscore.subdivision,
            "beatsPerBar": built.fscore.beats_per_bar,
            # **양자화 좌표계의** 마디 시작 시각. beats.json 다운비트와
            # 위상 보정만큼(실측 ~0.5초) 어긋난다 — 음 추가가 다운비트로
            # 시각을 계산하면 옆 슬롯에 앉는다(실측). 반드시 이걸 쓴다.
            "barStarts": [round(b.start_sec, 4) for b in built.qscore.bars],
            "barEnds": [round(b.end_sec, 4) for b in built.qscore.bars],
        }, ensure_ascii=False),
        media_type="application/json",
        headers={"Cache-Control": "no-store"},
    )


@app.get("/api/scores/{content_hash}/edits")
async def get_edits(content_hash: str) -> Response:
    """사용자 채보 보정 목록 (pipeline/edits.py)."""
    import json as json_mod

    from pipeline import edits as edits_mod

    workdir = jobs.DATA / content_hash
    if not workdir.exists():
        raise HTTPException(status_code=404, detail="곡이 없습니다")
    return Response(
        content=json_mod.dumps({"edits": edits_mod.load(workdir)}),
        media_type="application/json",
        headers={"Cache-Control": "no-store"},
    )


@app.put("/api/scores/{content_hash}/edits")
async def put_edits(content_hash: str, body: dict) -> Response:
    """보정 목록 전체 교체 — 멱등. 형식이 틀리면 통째로 거부한다."""
    import json as json_mod

    from pipeline import edits as edits_mod

    workdir = jobs.DATA / content_hash
    if not workdir.exists():
        raise HTTPException(status_code=404, detail="곡이 없습니다")
    try:
        validated = edits_mod.validate(body.get("edits"))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    edits_mod.save(workdir, validated)
    return Response(
        content=json_mod.dumps({"edits": validated}),
        media_type="application/json",
    )


@app.get("/api/scores/{content_hash}/reference-tex")
async def reference_tex(content_hash: str, transpose: int = 0) -> Response:
    """사용자 악보(reference.json)를 오디오 마디 순서로 펼친 alphaTex.

    마디 수가 자동 채보와 같아지므로(근음 DP 매핑, pipeline/reference.py
    머리말) 웹의 커서·시크·자동넘김이 수정 없이 작동한다. 악보가 없으면 404.
    """
    from pipeline import reduce as reduce_mod
    from pipeline import reference as ref_mod

    workdir = jobs.DATA / content_hash
    ref = ref_mod.load(workdir)
    if ref is None:
        raise HTTPException(status_code=404, detail="적재된 악보가 없습니다")
    try:
        built = await asyncio.to_thread(
            jobs.build_score_variant, content_hash, level=compose.ORIGINAL_LEVEL,
        )
    except jobs.MissingOriginals as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    our_roots = []
    for b in built.qscore.bars:
        r = reduce_mod.bar_root(b)
        our_roots.append(r % 12 if r is not None else None)
    mapping = ref_mod.align_bars(ref, our_roots)
    meta = jobs.score_metadata(content_hash)
    tex = ref_mod.build_tex(ref, built.qscore, mapping, meta["title"], transpose=transpose)
    matched = sum(1 for m in mapping if m is not None)
    return Response(
        content=tex,
        media_type="text/plain; charset=utf-8",
        headers={
            "X-Reference-Matched": str(matched),
            "X-Reference-Bars": str(len(ref.get("bars", []))),
            "Cache-Control": "no-store",
        },
    )


@app.post("/api/scores/{content_hash}/reference")
async def upload_reference(content_hash: str, request: Request) -> Response:
    """악보 이미지 업로드 → Gemini 판독 → reference.json 적재.

    본문은 multipart/form-data(files). 이미지 원본은 data/<hash>/
    reference_pages/에만 저장한다(data는 저장소 밖 — 악보는 저작물이다).
    페이지당 ~40초 걸린다 — 프론트가 안내한다.
    """
    import json as json_mod

    from pipeline import reference as ref_mod

    workdir = jobs.DATA / content_hash
    if not workdir.exists():
        raise HTTPException(status_code=404, detail="곡이 없습니다")
    form = await request.form()
    files = [v for v in form.getlist("files") if hasattr(v, "filename")]
    if not files:
        raise HTTPException(status_code=400, detail="이미지 파일이 없습니다")
    if len(files) > 20:
        raise HTTPException(status_code=400, detail="페이지가 너무 많습니다(최대 20)")
    pages_dir = workdir / "reference_pages"
    pages_dir.mkdir(exist_ok=True)
    saved: list = []
    for i, f in enumerate(files):
        suffix = Path(f.filename or "page.png").suffix.lower() or ".png"
        if suffix not in (".png", ".jpg", ".jpeg", ".webp"):
            raise HTTPException(status_code=400, detail=f"지원 않는 형식: {suffix}")
        dest = pages_dir / f"page_{i + 1:02d}{suffix}"
        dest.write_bytes(await f.read())
        saved.append(dest)
    try:
        out = await asyncio.to_thread(
            ref_mod.ingest_images, saved, workdir, verbose=True
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return Response(
        content=json_mod.dumps({
            "bars": len(out.get("bars", [])),
            "keySignature": out.get("keySignature"),
            "failedPages": out.get("failedPages", []),
        }),
        media_type="application/json",
    )


@app.put("/api/scores/{content_hash}/lyrics")
async def put_lyric(content_hash: str, body: dict) -> Response:
    """가사 음절 하나 교정 — {index, text}. 시각·개수는 불변(텍스트만).

    ASR·Gemini 교정을 거쳐도 오인이 남는 것이 실증됐다(드라우닝 "미치도록").
    마지막 통로는 사람이다 — 에디터의 가사 보정이 여기를 부른다.
    """
    import json as json_mod

    workdir = jobs.DATA / content_hash
    path = workdir / "lyrics.json"
    if not path.exists():
        raise HTTPException(status_code=404, detail="가사가 없는 곡입니다")
    index = body.get("index")
    text = body.get("text")
    if not isinstance(index, int) or not isinstance(text, str):
        raise HTTPException(status_code=400, detail="index(정수)·text(문자열)가 필요합니다")
    text = text.strip()
    if not (0 < len(text) <= 8):
        raise HTTPException(status_code=400, detail="음절 텍스트는 1~8자여야 합니다")
    sylls = json_mod.loads(path.read_text(encoding="utf-8"))
    if not (0 <= index < len(sylls)):
        raise HTTPException(status_code=400, detail=f"index 범위 밖: {index}")
    sylls[index]["text"] = text
    path.write_text(json_mod.dumps(sylls, ensure_ascii=False, indent=1), encoding="utf-8")
    return Response(
        content=json_mod.dumps({"index": index, "text": text}),
        media_type="application/json",
    )


@app.get("/api/scores/{content_hash}/synth-notes")
async def score_synth_notes(
    content_hash: str,
    level: int = compose.ORIGINAL_LEVEL,
    transpose: int = 0,
    tuning: str | None = None,
    source: str = "auto",
) -> Response:
    """악보 연주 이벤트 — 화면 악보와 같은 변형의 음표 타임라인(JSON).

    웹 베이스 샘플러가 원곡 반주 위에 악보를 연주할 때 쓴다. `/api/scores`와
    같은 인자·같은 `compose.build()`를 탄다 — 보이는 TAB과 들리는 소리가
    달라지면 안 된다. source=reference면 사용자 악보(내 악보)의 음을 낸다.
    """
    import json as json_mod

    from pipeline import perform

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

    if source == "reference":
        from pipeline import reduce as reduce_mod
        from pipeline import reference as ref_mod

        ref = ref_mod.load(jobs.DATA / content_hash)
        if ref is None:
            raise HTTPException(status_code=404, detail="적재된 악보가 없습니다")
        our_roots = [
            (reduce_mod.bar_root(b) % 12 if reduce_mod.bar_root(b) is not None else None)
            for b in built.qscore.bars
        ]
        mapping = ref_mod.align_bars(ref, our_roots)
        notes = ref_mod.events(ref, built.qscore, mapping, transpose=transpose)
    else:
        notes = perform.events(built.qscore, built.fscore)

    # 드럼 타임라인 — 악보의 드럼 트랙과 같은 격자(drums.json)에서.
    # 이조·난이도와 무관한 리듬 정보라 always 동봉, 없으면 빈 목록.
    from pipeline import drums as drums_mod

    drum_grid = drums_mod.load(jobs.DATA / content_hash) or []
    drum_hits = drums_mod.events(drum_grid, built.qscore.bars)

    return Response(
        content=json_mod.dumps(
            {"level": built.level, "transpose": built.transpose,
             "notes": notes, "drums": drum_hits}
        ),
        media_type="application/json",
        headers={"Cache-Control": "no-store"},
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
