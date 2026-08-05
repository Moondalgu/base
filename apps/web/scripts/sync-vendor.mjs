/**
 * 번들러를 타면 안 되는 라이브러리를 public/vendor/로 복사한다.
 *
 * - signalsmith-stretch: 워크릿 코드를 함수 toString()으로 직렬화하기 때문에
 *   번들러가 손대면 워크릿 스코프에서 조용히 깨진다.
 *   (lib/player/engine.ts 상단 주석 참조)
 * - @coderline/alphatab: 자체 Worker/AudioWorklet을 생성하고 폰트를 상대경로로
 *   찾는다. 공식 번들러 플러그인은 webpack/vite용만 있고 Turbopack용이 없다.
 *   원본을 그대로 서빙하면 alphaTab이 자기 스크립트 경로를 스스로 찾아낸다.
 *
 * postinstall / predev / prebuild에서 실행된다.
 */
import { cpSync, copyFileSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const root = resolve(here, "..");
const rel = (p) => p.replace(root, ".");

/**
 * signalsmith-stretch 1.3.2 처리기 버그 패치.
 *
 * process()의 비활성(inactive) 분기가 inputs를 무조건 읽는다:
 *   let channelBuffer = inputs[c%inputs.length];
 * numberOfInputs: 0이면 inputs가 undefined라 첫 쿼텀에서 TypeError로
 * 프로세서가 영구 사망한다(processorerror). 실시간 AudioContext는 노드가
 * 스케줄되기 전(비활성)에도 process()를 돌리므로 재생이 무조건 죽고,
 * OfflineAudioContext는 startRendering 시점에 이미 활성이라 안 걸린다.
 * 읽기만 하고 쓰지 않는 죽은 코드라서 지워도 동작이 변하지 않는다.
 *
 * 업스트림이 바뀌어 패턴이 사라지면(수정됐거나 코드가 달라졌거나) 빌드를
 * 실패시켜 이 패치가 아직 필요한지 사람이 다시 판단하게 한다.
 */
function patchSignalsmith(path) {
  const src = readFileSync(path, "utf-8");
  const broken = "let channelBuffer = inputs[c%inputs.length];";
  const first = src.indexOf(broken);
  if (first === -1) {
    throw new Error(
      `[sync-vendor] ${rel(path)}에서 패치 대상 패턴을 찾지 못했습니다. ` +
        "signalsmith-stretch가 업데이트된 듯합니다 — inactive 분기 버그가 " +
        "고쳐졌는지 확인하고 이 패치를 갱신/삭제하세요.",
    );
  }
  // 비활성 분기(첫 번째 등장)의 죽은 코드만 제거한다.
  // 활성 분기(두 번째 등장)는 channelBuffer를 실제로 사용하므로 남긴다.
  const patched =
    src.slice(0, first) +
    "/* patched by sync-vendor: inputs가 undefined일 때(numberOfInputs 0) 죽는 미사용 코드 제거 */" +
    src.slice(first + broken.length);
  writeFileSync(path, patched);
  console.log(`[sync-vendor] inactive 분기 버그 패치 적용 -> ${rel(path)}`);
}

const FILES = [
  {
    from: resolve(root, "node_modules/signalsmith-stretch/SignalsmithStretch.mjs"),
    to: resolve(root, "public/vendor/SignalsmithStretch.mjs"),
    patch: patchSignalsmith,
  },
];

const DIRS = [
  {
    from: resolve(root, "node_modules/@coderline/alphatab/dist"),
    to: resolve(root, "public/vendor/alphatab"),
  },
];

for (const { from, to, patch } of FILES) {
  mkdirSync(dirname(to), { recursive: true });
  copyFileSync(from, to);
  console.log(`[sync-vendor] ${rel(from)} -> ${rel(to)}`);
  patch?.(to);
}

for (const { from, to } of DIRS) {
  mkdirSync(to, { recursive: true });
  cpSync(from, to, { recursive: true });
  console.log(`[sync-vendor] ${rel(from)}/ -> ${rel(to)}/`);
}
