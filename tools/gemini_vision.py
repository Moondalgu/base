"""Gemini 비전 호출 — MCP `gemini_analyze_image`를 우회하는 직통 경로.

## 왜 필요한가

MCP의 이미지 도구가 어떤 이미지를 줘도 `400 Bad Request: Unable to process
input image`를 낸다(jpg·png·리사이즈·크롭 모두 실패). 같은 키로 REST에 직접
붙이면 정상 응답한다. 즉 이미지 인코딩 단계의 MCP 버그이고 우리가 고칠 수
없는 쪽이다. 이 스크립트가 그 자리를 대신한다.

텍스트 대화는 MCP가 정상이므로 그쪽은 계속 MCP를 쓴다. 이 파일은 **이미지가
들어갈 때만** 쓴다.

## 모델 이름 함정

`gemini-3.1-pro`는 없는 이름이고 404가 난다. 실제 이름은
`gemini-3.1-pro-preview`다. 모델 목록은 이렇게 확인한다:

    curl -s "https://generativelanguage.googleapis.com/v1beta/models?key=$KEY"

사용:
    python tools/gemini_vision.py --prompt-file p.txt img1.png img2.png
    python tools/gemini_vision.py --prompt "이 악보를 읽어줘" frame.jpg
"""

from __future__ import annotations

import argparse
import base64
import json
import mimetypes
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
DEFAULT_MODEL = "gemini-3.1-pro-preview"

# 키는 환경변수를 먼저 보고, 없으면 Claude Code MCP 설정에서 꺼낸다.
# MCP는 `env GEMINI_API_KEY=... npx ...` 형태로 args에 키를 박아둔다.
CLAUDE_CONFIG = Path.home() / ".claude.json"


def api_key() -> str:
    for name in ("GEMINI_API_KEY", "GOOGLE_API_KEY"):
        if os.environ.get(name):
            return os.environ[name]
    if CLAUDE_CONFIG.exists():
        cfg = json.loads(CLAUDE_CONFIG.read_text(encoding="utf-8"))
        for server in (cfg.get("mcpServers") or {}).values():
            for arg in server.get("args") or []:
                if isinstance(arg, str) and arg.startswith("GEMINI_API_KEY="):
                    return arg.split("=", 1)[1]
            key = (server.get("env") or {}).get("GEMINI_API_KEY")
            if key:
                return key
    raise SystemExit("GEMINI_API_KEY를 찾을 수 없습니다.")


def ask(prompt: str, images: list[Path], *, model: str = DEFAULT_MODEL) -> str:
    parts: list[dict] = [{"text": prompt}]
    for path in images:
        mime = mimetypes.guess_type(path.name)[0] or "image/jpeg"
        parts.append({
            "inline_data": {
                "mime_type": mime,
                "data": base64.b64encode(path.read_bytes()).decode("ascii"),
            }
        })

    body = json.dumps({"contents": [{"parts": parts}]}).encode("utf-8")
    req = urllib.request.Request(
        ENDPOINT.format(model=model) + f"?key={api_key()}",
        data=body,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=300) as resp:
            data = json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:1200]
        raise SystemExit(f"[{exc.code}] {detail}") from exc

    chunks: list[str] = []
    for cand in data.get("candidates", []):
        for part in cand.get("content", {}).get("parts", []):
            if "text" in part:
                chunks.append(part["text"])
    if not chunks:
        return f"(빈 응답) {json.dumps(data, ensure_ascii=False)[:800]}"
    return "".join(chunks)


def main() -> int:
    ap = argparse.ArgumentParser(description="Gemini 비전 직통 호출")
    ap.add_argument("images", nargs="+", type=Path)
    ap.add_argument("--prompt", default="")
    ap.add_argument("--prompt-file", type=Path)
    ap.add_argument("--model", default=DEFAULT_MODEL)
    args = ap.parse_args()

    prompt = args.prompt
    if args.prompt_file:
        prompt = args.prompt_file.read_text(encoding="utf-8")
    if not prompt:
        ap.error("--prompt 또는 --prompt-file 이 필요합니다")

    missing = [p for p in args.images if not p.exists()]
    if missing:
        ap.error(f"없는 이미지: {missing}")

    sys.stdout.reconfigure(encoding="utf-8")
    print(ask(prompt, args.images, model=args.model))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
