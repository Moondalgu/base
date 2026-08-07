/**
 * 내보내기 프록시 — MusicXML · MIDI 다운로드.
 *
 * 워커가 저장된 노트에서 악보를 다시 조립해 파일로 만든다(채보는 다시 하지 않는다).
 * 프론트가 워커를 직접 부르지 않고 여기를 거치는 이유는 `api/scores`와 같다:
 * 같은 오리진이라 CORS와 `Content-Disposition` 노출 설정이 필요 없다.
 *
 * **정적 폴백을 두지 않는다.** 악보 요청은 워커가 없으면 이미 구워둔
 * `score.alphatex`로 메꿀 수 있지만, 내보내기는 그럴 대상이 없다. 그리고
 * 난이도·이조를 반영하지 않은 파일을 대신 주면 사용자가 알 방법이 없다 —
 * 화면에서 보는 것과 다른 것이 내려가는 것이 조용한 실패다.
 */

import { NextRequest } from "next/server";

const WORKER = process.env.WORKER_URL ?? "http://localhost:8000";

/** 워커가 받는 형식. 그 밖의 것은 워커에 묻지 않고 여기서 막는다. */
const FORMATS = new Set(["musicxml", "mid"]);

export async function GET(
  request: NextRequest,
  context: { params: Promise<{ hash: string; file: string }> },
) {
  const { hash, file } = await context.params;

  // `<hash>.musicxml` 형태를 기대한다. 확장자만 떼어 쓴다 — 파일 이름은
  // 워커가 곡 제목으로 다시 정한다.
  const fmt = file.split(".").pop() ?? "";
  if (!FORMATS.has(fmt)) {
    return new Response(
      `지원하지 않는 형식입니다: ${fmt} (musicxml 또는 mid)`,
      { status: 404 },
    );
  }

  const params = request.nextUrl.searchParams;
  const query = new URLSearchParams({
    level: params.get("level") ?? "",
    transpose: params.get("transpose") ?? "0",
  });
  // 빈 값을 보내면 워커의 기본값(원곡)이 아니라 파싱 오류가 된다.
  if (!query.get("level")) query.delete("level");
  const tuning = params.get("tuning");
  if (tuning) query.set("tuning", tuning);

  let upstream: Response;
  try {
    upstream = await fetch(`${WORKER}/api/exports/${hash}.${fmt}?${query}`, {
      cache: "no-store",
    });
  } catch {
    return new Response(
      "워커에 연결할 수 없습니다. 내보내기는 저장된 파일로 대신할 수 없습니다.",
      { status: 502 },
    );
  }

  if (!upstream.ok) {
    return new Response(await upstream.text(), { status: upstream.status });
  }

  const headers = new Headers({
    "Content-Type":
      upstream.headers.get("content-type") ?? "application/octet-stream",
    "Cache-Control": "no-store",
  });
  // 파일 이름은 워커가 정한다(곡 제목 + 레벨 + 이조). 그대로 넘긴다.
  const disposition = upstream.headers.get("content-disposition");
  if (disposition) headers.set("Content-Disposition", disposition);

  return new Response(await upstream.arrayBuffer(), { headers });
}
