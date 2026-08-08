/**
 * 음표 배치 원장 프록시 — 화면 악보와 같은 변형(레벨·이조·튜닝)의 모든 음을
 * CSV로 내려준다. 각 음이 어느 마디·슬롯·박에, 어떤 검출 시각에서 스냅되어,
 * 어떤 피치 출처와 운지로 들어갔는지가 전부 담긴다(pipeline/ledger.py 머리말).
 *
 * 정적 폴백을 두지 않는다 — 요청한 변형과 다른 원장을 주면 조용한 거짓말이
 * 된다(/api/exports와 같은 원칙).
 */

import { NextRequest } from "next/server";

const WORKER = process.env.WORKER_URL ?? "http://localhost:8000";

export async function GET(
  request: NextRequest,
  context: { params: Promise<{ hash: string }> },
) {
  const { hash } = await context.params;
  const search = request.nextUrl.searchParams.toString();
  const url = `${WORKER}/api/scores/${hash}/ledger.csv${search ? `?${search}` : ""}`;

  try {
    const res = await fetch(url, { cache: "no-store" });
    return new Response(res.body, {
      status: res.status,
      headers: {
        "Content-Type": res.headers.get("Content-Type") ?? "text/csv; charset=utf-8",
        "Content-Disposition":
          res.headers.get("Content-Disposition") ?? "attachment",
        "Cache-Control": "no-store",
      },
    });
  } catch {
    return Response.json(
      { error: "워커에 연결할 수 없습니다. apps/worker를 먼저 켜세요." },
      { status: 502 },
    );
  }
}
