"""Gemini REST로 이미지를 분석한다. base64는 여기서 만들어 보내므로
호출자(Claude) 컨텍스트에 이미지 데이터가 들어가지 않는다.

사용: python gemini_vision.py <이미지경로> <프롬프트파일경로> [모델]
"""
import base64
import json
import mimetypes
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

MODELS = ["gemini-3.1-pro-preview", "gemini-2.5-pro", "gemini-flash-latest"]


def load_key() -> str:
    for var in ("GEMINI_API_KEY", "GOOGLE_API_KEY"):
        if os.environ.get(var):
            return os.environ[var]
    env = Path(r"C:\Users\admin\Desktop\bz\.env")
    if env.exists():
        for line in env.read_text(encoding="utf-8", errors="ignore").splitlines():
            line = line.strip()
            if line.startswith("GEMINI_API_KEY") and "=" in line:
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    raise SystemExit("GEMINI_API_KEY를 찾지 못했습니다")


def analyze(img_path: Path, prompt: str, model: str, key: str) -> str:
    mime = mimetypes.guess_type(str(img_path))[0] or "image/jpeg"
    payload = {
        "contents": [{
            "parts": [
                {"text": prompt},
                {"inline_data": {
                    "mime_type": mime,
                    "data": base64.b64encode(img_path.read_bytes()).decode("ascii"),
                }},
            ]
        }],
        "generationConfig": {"temperature": 0.0, "maxOutputTokens": 40000},
    }
    url = (f"https://generativelanguage.googleapis.com/v1beta/models/"
           f"{model}:generateContent?key={key}")
    req = urllib.request.Request(
        url, data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=300) as resp:
        body = json.loads(resp.read().decode("utf-8"))
    cands = body.get("candidates") or []
    if not cands:
        return "[응답 없음] " + json.dumps(body, ensure_ascii=False)[:500]
    parts = cands[0].get("content", {}).get("parts", [])
    text = "\n".join(p.get("text", "") for p in parts if "text" in p)
    finish = cands[0].get("finishReason", "?")
    usage = body.get("usageMetadata", {})
    meta = (f"\n\n[finishReason={finish} "
            f"prompt={usage.get('promptTokenCount')} "
            f"thoughts={usage.get('thoughtsTokenCount')} "
            f"output={usage.get('candidatesTokenCount')}]")
    return text + meta


def main() -> int:
    img = Path(sys.argv[1])
    prompt = Path(sys.argv[2]).read_text(encoding="utf-8")
    key = load_key()
    models = [sys.argv[3]] if len(sys.argv) > 3 else MODELS
    last = ""
    for model in models:
        try:
            out = analyze(img, prompt, model, key)
            print(f"### 모델: {model} / 이미지: {img.name}\n")
            print(out)
            return 0
        except urllib.error.HTTPError as e:
            last = f"{model}: HTTP {e.code} {e.read().decode('utf-8', 'ignore')[:300]}"
            continue
        except Exception as e:  # noqa: BLE001
            last = f"{model}: {e}"
            continue
    print("[전부 실패] " + last)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
