/**
 * 번들러를 타면 안 되는 라이브러리를 public/vendor/로 복사한다.
 *
 * signalsmith-stretch는 워크릿 코드를 함수 toString()으로 직렬화하기 때문에
 * 번들러가 손대면 깨진다. 원본 그대로 서빙해야 한다. 자세한 내용은
 * lib/player/engine.ts 상단 주석 참조.
 *
 * postinstall과 predev/prebuild에서 실행된다.
 */
import { copyFileSync, mkdirSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const root = resolve(here, "..");

const FILES = [
  {
    from: resolve(root, "node_modules/signalsmith-stretch/SignalsmithStretch.mjs"),
    to: resolve(root, "public/vendor/SignalsmithStretch.mjs"),
  },
];

for (const { from, to } of FILES) {
  mkdirSync(dirname(to), { recursive: true });
  copyFileSync(from, to);
  console.log(`[sync-vendor] ${from.replace(root, ".")} -> ${to.replace(root, ".")}`);
}
