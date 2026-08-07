/**
 * 악보 변형 서빙 — 난이도 레벨·이조·튜닝을 받아 AlphaTex를 돌려준다.
 *
 * 워커가 저장된 노트에서 양자화부터 다시 돌려 만든다(채보는 다시 하지 않는다).
 * 프론트가 워커를 직접 부르지 않고 여기를 거치는 이유는 두 가지다.
 *   - 같은 오리진이라 CORS와 커스텀 헤더 노출 설정이 필요 없다
 *   - 변형을 만들 수 없는 구버전 산출물을 여기서 정적 파일로 메꿔줄 수 있다
 */

import { readFileSync, existsSync } from "node:fs";
import path from "node:path";
import { NextRequest } from "next/server";

const WORKER = process.env.WORKER_URL ?? "http://localhost:8000";

// apps/web/app/api/scores/[hash] -> 저장소 루트의 data/
const DATA_ROOT = path.resolve(process.cwd(), "..", "..", "data");

/**
 * 원곡 그대로. 워커의 `compose.ORIGINAL_LEVEL`과 **같은 값이어야 한다.**
 *
 * 난이도를 5단계에서 3단계로 줄일 때 이 상수가 5로 남아 있었다. 그러면
 * 원곡 요청(level=3)이 `canFallBack` 조건을 통과하지 못해, 워커가 꺼져 있을 때
 * 이미 구워둔 악보가 있는데도 502를 냈다. 같은 종류의 낡은 상수가
 * `ScoreView.tsx`에도 있었고 거기서는 "쉬운 버전" 배지를 원곡에 붙였다.
 */
const ORIGINAL_LEVEL = 3;

const SCORE_HEADERS = [
  "x-score-level",
  "x-score-transpose",
  "x-score-octave-folded",
  "x-score-subdivision-forced",
];

export async function GET(
  request: NextRequest,
  context: { params: Promise<{ hash: string }> },
) {
  const { hash } = await context.params;
  const params = request.nextUrl.searchParams;
  const level = Number(params.get("level") ?? ORIGINAL_LEVEL);
  const transpose = Number(params.get("transpose") ?? 0);
  const tuning = params.get("tuning");

  const query = new URLSearchParams({
    level: String(level),
    transpose: String(transpose),
  });
  if (tuning) query.set("tuning", tuning);

  let upstream: Response | null = null;
  try {
    upstream = await fetch(`${WORKER}/api/scores/${hash}?${query}`, {
      cache: "no-store",
    });
  } catch {
    // 워커가 꺼져 있다. 원곡·무이조라면 정적 파일로 메꾼다.
    upstream = null;
  }

  if (upstream?.ok) {
    const tex = await upstream.text();
    const headers = new Headers({
      "Content-Type": "text/plain; charset=utf-8",
      "Cache-Control": "no-store",
    });
    for (const key of SCORE_HEADERS) {
      const value = upstream.headers.get(key);
      if (value !== null) headers.set(key, value);
    }
    return new Response(tex, { headers });
  }

  // 변형을 만들 수 없는 경우. 요청이 원곡·무이조·튜닝 무지정일 때만
  // 파이프라인이 이미 구워둔 악보로 대신할 수 있다. 그 밖의 요청은
  // 다른 악보를 달라는 것이므로 정적 파일을 주면 거짓말이 된다.
  const canFallBack = level === ORIGINAL_LEVEL && transpose === 0 && !tuning;
  if (canFallBack) {
    const target = path.resolve(DATA_ROOT, hash, "score.alphatex");
    if (target.startsWith(DATA_ROOT + path.sep) && existsSync(target)) {
      return new Response(readFileSync(target, "utf-8"), {
        headers: {
          "Content-Type": "text/plain; charset=utf-8",
          "Cache-Control": "no-store",
          "x-score-level": String(ORIGINAL_LEVEL),
          "x-score-transpose": "0",
          // 정적 파일은 생성 당시 값을 알 수 없다. 모르는 것을 0으로 단정하지 않는다.
          "x-score-source": "static",
        },
      });
    }
  }

  if (upstream) {
    return new Response(await upstream.text(), { status: upstream.status });
  }
  return new Response("워커에 연결할 수 없고 저장된 악보도 없습니다", { status: 502 });
}
