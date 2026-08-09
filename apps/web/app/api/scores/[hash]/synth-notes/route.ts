/**
 * 악보 연주 이벤트 프록시 — 화면 악보와 같은 변형의 음표 타임라인(JSON).
 *
 * 베이스 샘플러("악보 연주" 모드)가 쓴다. `/api/scores/[hash]`와 같은
 * 이유로 워커를 직접 부르지 않고 여기를 거친다(CORS·오리진 통일).
 * 정적 폴백은 없다 — 워커가 없으면 연주 모드도 없는 것이 맞다.
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
  const source = params.get("source");
  if (source) query.set("source", source);

  try {
    const upstream = await fetch(
      `${WORKER}/api/scores/${hash}/synth-notes?${query}`,
      { cache: "no-store" },
    );
    return new Response(await upstream.text(), {
      status: upstream.status,
      headers: {
        "Content-Type": "application/json",
        "Cache-Control": "no-store",
      },
    });
  } catch {
    return new Response(
      JSON.stringify({ error: "워커에 연결할 수 없습니다" }),
      { status: 502, headers: { "Content-Type": "application/json" } },
    );
  }
}
