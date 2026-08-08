---
version: anydesign-1
name: Songscription 결과 화면 (전사 플레이어)
source: eval/bench/songscription/drowning_16-44s_sheet.png, drowning_16-44s_tab.png
captured_at: 2026-08-09
description: |
  악보가 주인공인 백지 위에 깊은 틸 그린 한 색만 무겁게 쓰는 실용주의 연습 도구.
  본문은 종이(흰 배경 + 검은 잉크)이고, 조작할 수 있는 모든 것은 틸이다 —
  색이 곧 "여기를 누르라"는 신호로 기능한다. 장식은 없고, 상태(재생 하이라이트·
  베타 배지·컷 안내)만 색으로 구분한다.

colors:
  primary: "#22877B"
  primary-deep: "#0F5C53"
  surface: "#FFFFFF"
  surface-sidebar: "#F9F9F9"
  surface-toolbar: "#FBF9F8"
  badge-beta: "#DBEAFE"
  highlight-playing: "#FFFCBF"
  on-primary: "#FFFFFF"

typography:
  display-title:
    fontFamily: "serif 디스플레이 (Playfair/DM Serif 계열 추정)"
    fontSize: 40px
    fontWeight: 700
  control-label:
    fontFamily: "sans-serif (Inter/system 계열 추정)"
    fontSize: 11px
    fontWeight: 500
  body:
    fontFamily: "sans-serif (Inter/system 계열 추정)"
    fontSize: 14px
    fontWeight: 400

spacing:
  base: 4px
  scale: [4, 8, 12, 16, 24, 32, 48]

rounded:
  md: 8px
  lg: 12px
  pill: 9999px

components:
  bottom-player-bar:
    backgroundColor: "{colors.primary-deep}"
    textColor: "{colors.on-primary}"
    rounded: "0"
    padding: 12px 24px
  segmented-pill:
    backgroundColor: "{colors.primary-deep}"
    textColor: "{colors.on-primary}"
    rounded: "{rounded.pill}"
    padding: 4px
  button-primary:
    backgroundColor: "{colors.primary}"
    textColor: "{colors.on-primary}"
    typography: "{typography.body}"
    rounded: "{rounded.md}"
    padding: 8px 16px
  difficulty-pill:
    backgroundColor: "{colors.surface}"
    border: "1px solid #E5E5E5"
    rounded: "{rounded.lg}"
    padding: 6px 12px
  view-tab-group:
    backgroundColor: "{colors.surface-toolbar}"
    rounded: "{rounded.lg}"
    padding: 4px
  beta-badge:
    backgroundColor: "{colors.badge-beta}"
    textColor: "#1D4ED8"
    rounded: "{rounded.pill}"
    padding: 2px 8px
  icon-label-control:
    backgroundColor: "transparent"
    textColor: "{colors.on-primary}"
    typography: "{typography.control-label}"
    rounded: "{rounded.md}"
    padding: 4px 8px
---

# Design Analysis — Songscription 결과 화면 (전사 플레이어)

> Analysis generated with the `anydesign` skill.
> Date: 2026-08-09
> Analysis emphasis: reconstruction — Lowend 플레이어 이식 요소 선별

---

## Source

- **Source type**: local image ×2 (악보 뷰 / TAB 뷰, 로그인 상태 데스크톱 캡처)
- **Path / URL**: `eval/bench/songscription/drowning_16-44s_sheet.png`, `drowning_16-44s_tab.png`
- **Capture method**: direct vision + PIL 픽셀·영역 최빈값 샘플링(색은 실측)
- **Detected limitations**: 데스크톱 1455×875 한 뷰포트뿐 — 반응형·다크모드·호버 상태 관측 불가.
  첫 캡처에는 온보딩 딤이 깔려 있어 색 추출은 두 번째 캡처만 사용.

---

## TL;DR

악보(종이)가 화면의 90%를 차지하고, 브랜드는 **깊은 틸 그린 단색**으로만 말하는 절제된
연습 도구다. Beta 배지 색이 Tailwind `blue-100`(#DBEAFE)과 정확히 일치 — Tailwind 스택.
Lowend가 가져갈 실질 가치는 색이 아니라 **배치 문법**: 모드 전환(전사/원곡)을 하단
재생바의 세그먼트 필로, 난이도를 악보 우상단의 상시 노출 pill로 승격한 것.

---

## 1. Visual identity

### 1.1 Surface description

**Personality**: 실용적, 절제됨, 도구적, 신뢰 지향, 조용함

**Mood**: "악보 보면대 앞에 선 연습실" — 소프트웨어가 아니라 문방구처럼 느껴지게 한다.

**Detectable stylistic references**: Notion류 화이트 SaaS + 음악 앱(Moises)의 하단 트랜스포트 바 문법.

**Information density**: minimalist (본문) / dense (하단 바 — 컨트롤 8종 집약)

**Implicit positioning**: 독학 연주자·학생. 전문 DAW 사용자 흉내를 내지 않는다.

**Confidence**: ✅ high

### 1.2 Brand voice / Atmosphere

이 화면은 "채보 결과는 종이 악보다"라고 믿는다. 그래서 본문에는 UI를 거의 두지 않고
(제목·별점·난이도 pill이 전부), 소프트웨어임을 드러내는 모든 조작부를 화면 가장자리
(상단 툴바·하단 바·사이드바)로 밀어냈다. 종이 위에는 재생 하이라이트(#FFFCBF)라는
최소한의 소프트웨어 흔적만 허락된다.

두 번째 믿음은 "사용자는 언제나 소리와 악보를 오간다"이다. Transcribed/Original 토글이
재생 버튼 바로 옆, 화면에서 가장 진한 색 블록 위에 있다 — 이 전환이 이 제품의 존재
이유(내 귀로 검증)라는 선언이다. Lowend의 "악보 연주" 토글이 접이식 패널 안에 있는 것과
정확히 반대의 위계다.

### 1.3 The "ONE brand thing"

- **The thing**: 깊은 틸 그린(#0F5C53) **풀블리드 하단 재생바** — 흰 종이 위에 단 하나의
  진한 색 블록.
- **Why it carries the brand**: 이것을 빼면 화면 전체가 무채색 문서 뷰어가 된다. 색이
  "조작 가능한 것"과 "읽는 것"의 경계를 긋는다.
- **How everything else supports it**: 본문·사이드바·툴바가 전부 흰색~#FBF9F8 사이에
  머물러서 틸이 유일한 채도가 된다.
- **Where it appears (and where it deliberately doesn't)**: CTA·재생바·링크에만. 악보
  영역 안에는 절대 들어오지 않는다(하이라이트는 노랑으로 분리).

*Confidence*: ✅ high

---

## 2. Design System (tokens)

### 2.1 Colors

| Token | Hex | Role | Where it appears | Confidence |
|---|---|---|---|---|
| `primary` | `#22877B` | 주 액션 | CTA·Download·링크 | ✅ 실측 |
| `primary-deep` | `#0F5C53` | 조작 영역 그라운드 | 하단 재생바·세그먼트 필 배경 | ✅ 실측 |
| `surface` | `#FFFFFF` | 종이 | 악보 본문 | ✅ 실측 |
| `surface-sidebar` | `#F9F9F9` | 보조 영역 | 좌측 사이드바 | ✅ 실측 |
| `surface-toolbar` | `#FBF9F8` | 툴바 컨테이너 | 상단 뷰 탭 그룹 | ✅ 실측 |
| `badge-beta` | `#DBEAFE` | 상태 배지 | Beta 태그 (= Tailwind blue-100) | ✅ 실측 |
| `highlight-playing` | `#FFFCBF` | 재생 위치 | 연주 중 마디 배경 | ✅ 실측 |

다크모드: 관측 불가 ❓.

### 2.2 Typography

- **Detected family**: 본문 sans(Inter/system 계열), 곡 제목만 **serif 디스플레이**
  *(confidence: ⚠️ medium — 시각 추정, 웹폰트 미확인)*
- **Suggested fallback**: `system-ui, sans-serif` / 제목 `Georgia, serif`

| Token | Size | Weight | Use |
|---|---|---|---|
| `display-title` | ~40px | 700 | 곡 제목 (serif — 종이 악보 표제 은유) |
| `body` | ~14px | 400 | 링크·안내문 |
| `control-label` | ~11px | 500 | 하단 바 아이콘 밑 라벨 (Edit/Speed/Loop…) |

### 2.3 Spacing / Rounded

4px 베이스 추정 ⚠️. 버튼 radius ~8px, pill류 9999px, 툴바 컨테이너 ~12px.

---

## 3. Components

- `bottom-player-bar` ✅: 풀블리드 #0F5C53. 좌→우: 모드 세그먼트, 처음으로·재생(흰 원형
  44px)·시간, 우측에 아이콘+라벨 스택 컨트롤(Edit, −/1x/+, Loop, Practice, Metronome,
  Settings). 비활성 컨트롤은 저대비로 남겨둔다(숨기지 않음).
- `segmented-pill` ✅: "Transcribed | Original" — 활성 쪽이 흰 필, 나머지는 딥 틸 위 흰 글자.
  모드 전환의 1급 지위.
- `button-primary` ✅: #22877B 솔리드, 흰 글자, radius 8px (Download·New Transcription).
- `difficulty-pill` ✅: 악보 우상단 상시 노출 "Difficulty: ⚙ Original ▾" — 흰 배경·회색
  테두리 pill 드롭다운. 접힌 설정 패널이 아니라 악보에 붙어 있다.
- `view-tab-group` ✅: 상단 중앙 "Sheet Music / Piano Roll / Guitar Tabs" — 연회색 컨테이너
  안 탭, 활성 탭 흰 배경.
- `beta-badge` ✅: #DBEAFE 파랑 pill — 기능 성숙도를 숨기지 않고 표기.
- `icon-label-control` ✅: 아이콘 위·11px 라벨 아래 스택. 라벨 덕에 아이콘 학습 비용 0.

관측 못 한 변형(호버·포커스·비활성 세부): ❓.

---

## 4. Layout

- 3열: 고정 사이드바(#F9F9F9, ~250px) / 본문(흰색, 악보 중앙 정렬 max-width ~1100px) /
  없음. 상단 툴바는 본문 폭 기준 중앙 탭 + 우측 액션.
- 하단 바는 뷰포트 고정(fixed), 본문 스크롤과 독립.
- 반응형 동작: 관측 불가 ❓.

---

## 5. Reconstruction notes (Lowend 이식 판정)

**이식 가치 높음 (배치 문법):**
- **모드 세그먼트를 하단 바로** — 우리 "악보 연주" 토글은 접이식 스템 패널 안에 있어
   발견성이 낮다. `원곡 | 악보 연주` 세그먼트를 TransportBar에 승격.
- **난이도 상시 노출 pill** — 우리 난이도는 접힌 "악보 설정" 안 range 슬라이더. 악보
   헤더 줄(보기 토글 옆)에 세그먼트 칩(원본/초급)으로 승격.
- **비활성 컨트롤 저대비 유지** — 우리도 이미 유사(메트로놈 비활성) ✓ 유지.

**이식 불필요/보류:**
- 틸 팔레트 채택 ✗ — 우리는 주황 재생 버튼이 이미 브랜드 앵커. 색을 베끼면 클론 티만 남.
- serif 제목 ✗ — 우리 3단 악보 안에 이미 alphaTab 표제가 있어 중복.
- 별점 피드백 ⏸ — 로컬 프로토 단계에서 수집처가 없음.

**Tricky bits**: 세그먼트를 하단 바에 넣을 때 모바일 폭에서 줄바꿈 — 우리 TransportBar는
이미 2~3줄 접힘 설계라 세그먼트가 첫 줄을 독점하지 않게 폭 제한 필요.

**Confidence map**: 색 ✅ / 배치 ✅ / 타이포 ⚠️ / 반응형·다크 ❓

---

## 6. Do's and Don'ts (Songscription 문법 기준)

### Do

- 조작 가능한 것에만 채도를 쓴다 — 본문(악보)은 무채색으로 지킨다.
- 모드 전환(소리의 정체)을 재생 버튼 옆 1급 자리에 둔다.
- 미성숙 기능은 Beta 배지로 정직하게 표기한다.
- 아이콘에는 항상 11px 라벨을 붙인다.

### Don't

- 악보 영역 안에 브랜드색 UI를 넣지 않는다(하이라이트는 노랑 계열로 분리).
- 비활성 컨트롤을 숨기지 않는다 — 저대비로 남겨 기능의 존재를 알린다.
- 설정류(난이도·모드)를 접이식 패널에만 숨기지 않는다 — 연습 중 바꾸는 값은 상시 노출.

---

## 7. Open Questions

- 다크모드 팔레트 — 관측 자료 없음. Lowend는 자체 다크모드 유지.
- serif 제목의 실제 폰트 — 웹폰트 요청 로그 미확보.
- 호버·포커스 상태와 모바일 레이아웃 — 단일 데스크톱 캡처의 한계.
- Difficulty 드롭다운의 실제 옵션 목록 — 클릭이 자동화에서 열리지 않아 미확인(유료 게이트 가능성).
