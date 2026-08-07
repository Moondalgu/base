"""Songsterr의 사람 채보를 정답 참조로 받아온다.

## 왜 이것이 값어치가 있는가

우리 정답(유튜브 화면 TAB)은 **커버 연주자 본인의 채보**라서 원곡과 다를 수 있다.
"우리가 틀렸는가, 연주자가 단순화했는가"를 가릴 제3의 자료가 필요했다.

Songsterr는 사람이 만든 베이스 탭을 리듬·타이·섹션 마커까지 갖춰 제공하고,
튜닝이 [43,38,33,28]로 **우리 standard와 동일**하다. 즉 현·프렛을 그대로 비교할 수
있다.

## 어떻게 받는가

Songsterr 페이지는 탭을 CDN의 트랙별 JSON으로 받는다. 브라우저 네트워크에서
확인한 경로 형식:

    https://dqsljvtekg760.cloudfront.net/{songId}/{revisionId}/{token}/{trackIndex}.json

`token`은 리비전마다 바뀐다. **`--auto`를 쓰면 songId만으로 전부 알아낸다** —
`/api/meta/{songId}/revisions`에서 최신 리비전을, `/api/meta/{songId}/{revisionId}`에서
토큰을 뽑는다. 처음에는 playwright로 페이지를 열고 네트워크 요청을 뒤졌는데
그럴 필요가 없었다.

곡을 찾는 것도 API로 된다:
    https://www.songsterr.com/api/search?pattern=<제목>&inst=bass&size=8&from=0
응답의 `records[].tracks`에서 `tuning`이 4개인 것이 베이스 트랙이다.

## 주의 — 이 자료의 한계

**같은 곡의 다른 녹음이다.** Oasis 원곡이고 우리가 채보하는 것은 백예린 커버다.
마디 번호가 1:1로 맞지 않고 편곡도 다르다. 쓸 수 있는 것은 **화성 진행의 상대
관계**이고, 마디별 타현 수를 정답으로 그대로 쓰면 안 된다.

사용:
    python tools/fetch_songsterr.py 49284 6960683 v0-3-2-ywhg9FJzgAWQkCku 8 \
        --out eval/golden/songsterr_champagne_bass.json
"""

from __future__ import annotations

import argparse
import json
import re
import urllib.request
from collections import Counter
from pathlib import Path

CDN = "https://dqsljvtekg760.cloudfront.net/{song}/{rev}/{token}/{track}.json"
META = "https://www.songsterr.com/api/meta/{song}"
UA = {"User-Agent": "Mozilla/5.0", "Accept-Encoding": "gzip, deflate"}

# gzip 파일 시그니처(0x1F 0x8B). CDN·API가 압축해 내려주므로 응답 헤더가
# 없어도 이것으로 판별한다. 바이트 리터럴 대신 숫자로 만든 이유: 소스에
# 제어문자를 직접 넣으면 편집 도구를 거치며 깨진다.
GZIP_MAGIC = bytes((0x1F, 0x8B))



def fetch(song: int, rev: int, token: str, track: int) -> dict:
    """CDN에서 트랙 JSON을 받는다.

    **CDN이 gzip으로 내려준다.** `Content-Encoding`을 보지 않고 그대로
    `json.loads`에 넣으면 `UnicodeDecodeError: byte 0x8b`가 난다 —
    0x8b는 gzip 매직의 두 번째 바이트다.
    """
    import gzip
    import zlib

    url = CDN.format(song=song, rev=rev, token=token, track=track)
    req = urllib.request.Request(
        url, headers={"User-Agent": "Mozilla/5.0", "Accept-Encoding": "gzip, deflate"}
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        raw = resp.read()
        encoding = (resp.headers.get("Content-Encoding") or "").lower()
    if encoding == "gzip" or raw[:2] == b"\x1f\x8b":
        raw = gzip.decompress(raw)
    elif encoding == "deflate":
        raw = zlib.decompress(raw)
    return json.loads(raw)


def _get(url: str) -> bytes:
    """gzip을 풀어서 본문을 돌려준다."""
    import gzip
    import zlib

    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=60) as resp:
        raw = resp.read()
        enc = (resp.headers.get("Content-Encoding") or "").lower()
    if enc == "gzip" or raw[:2] == GZIP_MAGIC:
        return gzip.decompress(raw)
    if enc == "deflate":
        return zlib.decompress(raw)
    return raw


def resolve(song: int) -> tuple[int, str, int]:
    """songId만으로 (최신 revisionId, CDN 토큰, 베이스 트랙 인덱스)를 찾는다.

    베이스 트랙은 **튜닝 길이가 4인 것**으로 고른다. 이름(`| Bass`)으로 찾으면
    "Moog Bass"·"Synth Bass"처럼 이름이 다른 것을 놓치고, instrumentId로 찾으면
    신스 베이스(38·39)를 빼먹는다. 4현이라는 사실이 가장 안전한 신호다.

    베이스 트랙이 여러 개면(예: Billie Jean은 신스 2개 + 일렉 1개) **일렉
    베이스를 우선**한다. 우리 파이프라인이 4현 일렉 기준이기 때문이다.
    """
    revs = json.loads(_get(META.format(song=song) + "/revisions"))
    if not revs:
        raise SystemExit(f"리비전이 없습니다: songId={song}")
    revision = int(revs[0]["revisionId"])

    body = _get(f"{META.format(song=song)}/{revision}").decode("utf-8", "replace")
    match = re.search(r"v\d+-\d+-\d+-[A-Za-z0-9_-]{10,}", body)
    if not match:
        raise SystemExit(f"CDN 토큰을 찾지 못했습니다: songId={song} rev={revision}")
    token = match.group(0)

    meta = json.loads(body)
    tracks = meta.get("tracks") or meta.get("revision", {}).get("tracks") or []
    candidates = [
        (i, t) for i, t in enumerate(tracks) if len(t.get("tuning") or []) == 4
    ]
    if not candidates:
        raise SystemExit(f"4현 트랙이 없습니다: songId={song}")
    electric = [c for c in candidates if "Electric Bass" in (c[1].get("instrument") or "")]
    index = (electric or candidates)[0][0]
    return revision, token, index


def summarize(data: dict) -> list[dict]:
    """마디별로 (섹션 마커, 타현 수, 적힌 수, 타이 수, 주된 자리)를 뽑는다.

    **타이는 타현이 아니다.** 화면 TAB 판독과 같은 규칙을 쓴다
    (`harmony.json` articulation.comparisonRule).
    """
    tuning = data["tuning"]          # [1현, 2현, 3현, 4현]
    rows: list[dict] = []
    for i, measure in enumerate(data["measures"], start=1):
        attacks = written = ties = 0
        places: list[tuple[int, int]] = []
        for voice in measure.get("voices") or []:
            for beat in voice.get("beats") or []:
                for note in beat.get("notes") or []:
                    if note.get("rest"):
                        continue
                    written += 1
                    if note.get("tie"):
                        ties += 1
                        continue
                    attacks += 1
                    if "fret" in note and "string" in note:
                        places.append((note["string"] + 1, note["fret"]))
        main = Counter(places).most_common(1)
        string, fret = main[0][0] if main else (None, None)
        rows.append({
            "bar": i,
            "marker": (measure.get("marker") or {}).get("text"),
            "attacks": attacks,
            "writtenNotes": written,
            "ties": ties,
            "string": string,
            "fret": fret,
            "pitch": tuning[string - 1] + fret if string else None,
        })
    return rows


def sections(rows: list[dict]) -> list[dict]:
    """섹션 마커를 [(이름, 시작마디, 길이)]로 정리한다.

    구조 분할(`pipeline/sections.py`)을 검증할 정답이다. 우리가 스스로 만든
    경계와 대조할 수 있는 유일한 사람 표기다.
    """
    marks = [(r["bar"], r["marker"]) for r in rows if r["marker"]]
    out = []
    for (bar, name), nxt in zip(marks, marks[1:] + [(len(rows) + 1, None)]):
        out.append({"name": name, "startBar": bar, "bars": nxt[0] - bar})
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="Songsterr 사람 채보를 정답 참조로 받는다")
    ap.add_argument("song", type=int)
    ap.add_argument("rev", type=int, nargs="?")
    ap.add_argument("token", nargs="?")
    ap.add_argument("track", type=int, nargs="?", help="베이스 트랙 인덱스")
    ap.add_argument("--auto", action="store_true",
                    help="songId만으로 리비전·토큰·베이스 트랙을 알아낸다")
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()

    if args.auto or args.rev is None:
        rev, token, track = resolve(args.song)
        print(f"  자동 해석: rev={rev} token={token} 베이스 트랙={track}")
    else:
        rev, token, track = args.rev, args.token, args.track
    args.rev, args.token, args.track = rev, token, track

    data = fetch(args.song, args.rev, args.token, args.track)
    rows = summarize(data)
    secs = sections(rows)
    payload = {
        "_readme": [
            "Songsterr의 **사람이 만든** 베이스 탭. 자동 채보가 아니다.",
            "",
            "**같은 곡의 다른 녹음이다.** 우리가 채보하는 것은 백예린 커버 영상이고",
            "이것은 Oasis 원곡이다. 마디 번호가 1:1로 맞지 않고 편곡도 다르다.",
            "마디별 타현 수를 우리 정답으로 그대로 쓰면 안 된다.",
            "",
            "쓸 수 있는 것:",
            "1. **화성 진행의 상대 관계** — 이조 상수가 일정하면 우리 피치 검출이",
            "   맞다는 독립 증거가 된다.",
            "2. **섹션 마커** — 사람이 표기한 곡 구조. `pipeline/sections.py`가 낸",
            "   경계와 대조할 수 있는 유일한 정답이다.",
            "3. **타현 밀도의 구간별 패턴** — 어느 구간이 2타이고 어디가 8타인지.",
            "",
            "튜닝이 [43,38,33,28]로 우리 standard와 같아서 현·프렛을 그대로 비교한다.",
            "타이는 타현으로 세지 않았다 (harmony.json articulation.comparisonRule).",
            "",
            "받는 방법은 tools/fetch_songsterr.py 문서 참조.",
        ],
        "source": f"songsterr s{args.song} rev {args.rev} track {args.track}",
        "track": data.get("name"),
        "tuning": data["tuning"],
        "sections": secs,
        "bars": rows,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"=== {data.get('name')} ===")
    print(f"  {len(rows)}마디, 튜닝 {data['tuning']}")
    print(f"  섹션 {len(secs)}개:")
    for s in secs:
        print(f"    {s['name']:16} {s['startBar']:>4}마디부터 {s['bars']:>3}마디")
    print(f"  -> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
