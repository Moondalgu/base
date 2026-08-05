# 이미지·PDF 판독 (Gemini)

**이미지·PDF 분석은 Gemini로 한다.** 시각 추론이 더 정확하고, 무엇보다 base64가 호출자 컨텍스트에 들어가지 않는다(스크립트가 파일을 직접 읽어 보낸다).

```bash
cd C:\Users\admin\Desktop\lowend
.venv/Scripts/python.exe tools/vision/gemini_vision.py <이미지|PDF> <프롬프트파일> [모델]
```

API 키는 `GEMINI_API_KEY` / `GOOGLE_API_KEY` 환경변수 또는 `C:\Users\admin\Desktop\bz\.env`에서 읽는다.
모델은 `gemini-3.1-pro-preview` → `gemini-2.5-pro` → `gemini-flash-latest` 순으로 폴백한다.

## 프롬프트

**`prompt_score.txt`** — 악보 판독. 조표·박자·템포, 마디 번호, 음표 전수(박 위치·음길이·현·프렛·타이), 다중쉼표 숫자, 마디 길이 검산, 그리고 "사람이 만든 정식 악보인가 자동 생성처럼 지저분한가" 판단까지 요구한다.

**`prompt_pdf.txt`** — 악보 PDF의 성격 판독. 몇 현 TAB인가(6현=기타, 4현=베이스), 오선은 보컬 멜로디인가 악기 파트인가, 코드 진행, TAB 숫자가 몇 번째 줄인가, 출처 표기.

## 반드시 지킬 것

**한 번 판독한 결과를 그대로 믿지 마라.** 같은 이미지에서 TAB 줄 위치를 처음엔 D현으로, 다시 물으니 A현으로 답한 사례가 있다(한 옥타브 차이). 중요한 값은 **판단 근거를 요구하는 방식으로 재질문**해라 — "줄 위에 몇 개, 아래에 몇 개가 지나가는지 세어서 답하라", "TAB을 보지 말고 오선보만 보고 답하라" 같은 형태다. 교차검증이 되면 신뢰할 수 있다.

`maxOutputTokens`는 40000으로 잡아뒀다. Gemini 3.x는 thinking 토큰이 이 예산을 먹으므로 8192로는 답이 중간에 끊긴다(`finishReason`을 출력에 찍으니 확인 가능하다).
