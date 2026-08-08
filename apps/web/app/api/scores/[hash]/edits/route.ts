/**
 * 사용자 채보 보정(edits) 프록시 — GET 목록 / PUT 전체 교체(멱등).
 * 보정은 검출 원본 위 오버레이라 워커가 소유한다(pipeline/edits.py).
 */

import { NextRequest } from "next/server";

const WORKER = process.env.WORKER_URL ?? "http://localhost:8000";

export async function GET(
  _request: NextRequest,
  context: { params: Promise<{ hash: string }> },
) {
  const { hash } = await context.params;
  try {
    const upstream = await fetch(`${WORKER}/api/scores/${hash}/edits`, {
      cache: "no-store",
    });
    return new Response(await upstream.text(), {
      status: upstream.status,
      headers: { "Content-Type": "application/json", "Cache-Control": "no-store" },
    });
  } catch {
    return new Response(JSON.stringify({ error: "워커에 연결할 수 없습니다" }), {
      status: 502,
      headers: { "Content-Type": "application/json" },
    });
  }
}

export async function PUT(
  request: NextRequest,
  context: { params: Promise<{ hash: string }> },
) {
  const { hash } = await context.params;
  try {
    const upstream = await fetch(`${WORKER}/api/scores/${hash}/edits`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: await request.text(),
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
