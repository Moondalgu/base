/**
 * 가사 음절 보정 프록시 — PUT {index, text}. 시각·개수 불변, 텍스트만.
 * ASR·Gemini를 거쳐도 오인이 남는 것이 실증돼(드라우닝 "미치도록")
 * 마지막 통로는 사람이다 — 에디터 가사 보정이 여기를 부른다.
 */

import { NextRequest } from "next/server";

const WORKER = process.env.WORKER_URL ?? "http://localhost:8000";

export async function PUT(
  request: NextRequest,
  context: { params: Promise<{ hash: string }> },
) {
  const { hash } = await context.params;
  try {
    const upstream = await fetch(`${WORKER}/api/scores/${hash}/lyrics`, {
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
