/**
 * 파이프라인 산출물 서빙 (개발용).
 *
 * data/{contentHash}/ 아래 파일을 그대로 내보낸다.
 * 경로 탈출을 막기 위해 해석된 절대경로가 DATA_ROOT 안에 있는지 확인한다.
 *
 * TODO(M3): 스템을 wav 대신 opus로 인코딩해 전송량을 줄인다.
 *   5분 곡 스템 하나가 wav로는 50MB인데 opus면 5MB 수준이다.
 */

import { createReadStream, existsSync, statSync } from "node:fs";
import path from "node:path";
import { Readable } from "node:stream";
import { NextRequest } from "next/server";

// apps/web/app/api/artifacts/[hash]/[...file] -> 저장소 루트의 data/
const DATA_ROOT = path.resolve(process.cwd(), "..", "..", "data");

const CONTENT_TYPES: Record<string, string> = {
  ".wav": "audio/wav",
  ".opus": "audio/ogg",
  ".ogg": "audio/ogg",
  ".json": "application/json",
  ".alphatex": "text/plain; charset=utf-8",
};

export async function GET(
  request: NextRequest,
  context: { params: Promise<{ hash: string; file: string[] }> },
) {
  const { hash, file } = await context.params;

  const target = path.resolve(DATA_ROOT, hash, ...file);
  if (!target.startsWith(DATA_ROOT + path.sep)) {
    return new Response("잘못된 경로입니다", { status: 400 });
  }
  if (!existsSync(target) || !statSync(target).isFile()) {
    return new Response("파일이 없습니다", { status: 404 });
  }

  const stat = statSync(target);
  const contentType = CONTENT_TYPES[path.extname(target)] ?? "application/octet-stream";
  const range = request.headers.get("range");

  if (range) {
    const match = /bytes=(\d*)-(\d*)/.exec(range);
    if (match) {
      const start = match[1] ? parseInt(match[1], 10) : 0;
      const end = match[2] ? parseInt(match[2], 10) : stat.size - 1;
      const stream = createReadStream(target, { start, end });
      return new Response(Readable.toWeb(stream) as ReadableStream, {
        status: 206,
        headers: {
          "Content-Type": contentType,
          "Content-Length": String(end - start + 1),
          "Content-Range": `bytes ${start}-${end}/${stat.size}`,
          "Accept-Ranges": "bytes",
        },
      });
    }
  }

  const stream = createReadStream(target);
  return new Response(Readable.toWeb(stream) as ReadableStream, {
    headers: {
      "Content-Type": contentType,
      "Content-Length": String(stat.size),
      "Accept-Ranges": "bytes",
      "Cache-Control": "no-store",
    },
  });
}
