/**
 * 원장 JSON 프록시 — 편집 UI가 (마디, 슬롯) → 검출 시각(srcStart)을 찾는다.
 * 화면 악보와 같은 변형 인자를 그대로 워커에 넘긴다.
 */

import { NextRequest } from "next/server";

const WORKER = process.env.WORKER_URL ?? "http://localhost:8000";

export async function GET(
  request: NextRequest,
  context: { params: Promise<{ hash: string }> },
) {
  const { hash } = await context.params;
  const params = request.nextUrl.searchParams;
  const query = new URLSearchParams({
    level: params.get("level") ?? "3",
    transpose: params.get("transpose") ?? "0",
  });
  const tuning = params.get("tuning");
  if (tuning) query.set("tuning", tuning);

  try {
    const upstream = await fetch(
      `${WORKER}/api/scores/${hash}/ledger.json?${query}`,
      { cache: "no-store" },
    );
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
