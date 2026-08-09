/**
 * 사용자 악보 프록시.
 * GET  — 오디오 마디 순서로 펼친 alphaTex(없으면 404).
 * POST — 악보 이미지 업로드(multipart) → 워커가 Gemini 판독 후 적재.
 *        페이지당 ~40초 걸리므로 타임아웃을 길게 둔다.
 */

import { NextRequest } from "next/server";

const WORKER = process.env.WORKER_URL ?? "http://localhost:8000";

export async function GET(
  request: NextRequest,
  context: { params: Promise<{ hash: string }> },
) {
  const { hash } = await context.params;
  const transpose = request.nextUrl.searchParams.get("transpose") ?? "0";
  try {
    const upstream = await fetch(
      `${WORKER}/api/scores/${hash}/reference-tex?transpose=${transpose}`,
      { cache: "no-store" },
    );
    const headers = new Headers({
      "Content-Type": "text/plain; charset=utf-8",
      "Cache-Control": "no-store",
    });
    for (const key of ["x-reference-matched", "x-reference-bars"]) {
      const v = upstream.headers.get(key);
      if (v !== null) headers.set(key, v);
    }
    return new Response(await upstream.text(), { status: upstream.status, headers });
  } catch {
    return new Response("워커에 연결할 수 없습니다", { status: 502 });
  }
}

export async function POST(
  request: NextRequest,
  context: { params: Promise<{ hash: string }> },
) {
  const { hash } = await context.params;
  try {
    const upstream = await fetch(`${WORKER}/api/scores/${hash}/reference`, {
      method: "POST",
      body: request.body,
      headers: {
        "Content-Type": request.headers.get("content-type") ?? "",
      },
      // Node fetch로 스트림 본문을 넘기려면 duplex가 필요하다.
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      ...({ duplex: "half" } as any),
      cache: "no-store",
    });
    return new Response(await upstream.text(), {
      status: upstream.status,
      headers: { "Content-Type": "application/json" },
    });
  } catch {
    return new Response(JSON.stringify({ error: "워커에 연결할 수 없습니다" }), {
      status: 502,
      headers: { "Content-Type": "application/json" },
    });
  }
}
