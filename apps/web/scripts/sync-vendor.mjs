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
import { cpSync, copyFileSync, mkdirSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const root = resolve(here, "..");
const rel = (p) => p.replace(root, ".");

const FILES = [
  {
    from: resolve(root, "node_modules/signalsmith-stretch/SignalsmithStretch.mjs"),
    to: resolve(root, "public/vendor/SignalsmithStretch.mjs"),
  },
];

const DIRS = [
  {
    from: resolve(root, "node_modules/@coderline/alphatab/dist"),
    to: resolve(root, "public/vendor/alphatab"),
  },
];

for (const { from, to } of FILES) {
  mkdirSync(dirname(to), { recursive: true });
  copyFileSync(from, to);
  console.log(`[sync-vendor] ${rel(from)} -> ${rel(to)}`);
}

for (const { from, to } of DIRS) {
  mkdirSync(to, { recursive: true });
  cpSync(from, to, { recursive: true });
  console.log(`[sync-vendor] ${rel(from)}/ -> ${rel(to)}/`);
}
