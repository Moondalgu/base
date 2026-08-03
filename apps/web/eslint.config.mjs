import { defineConfig, globalIgnores } from "eslint/config";
import nextVitals from "eslint-config-next/core-web-vitals";
import nextTs from "eslint-config-next/typescript";

const eslintConfig = defineConfig([
  ...nextVitals,
  ...nextTs,
  // Override default ignores of eslint-config-next.
  globalIgnores([
    // Default ignores of eslint-config-next:
    ".next/**",
    "out/**",
    "build/**",
    "next-env.d.ts",
    // scripts/sync-vendor.mjs가 node_modules에서 복사해온 원본 라이브러리.
    // 우리 코드가 아니고 손대서도 안 된다(번들러가 손대면 깨지는 것들이라
    // 일부러 원본 그대로 서빙한다). lib/player/engine.ts 주석 참조.
    "public/vendor/**",
  ]),
]);

export default eslintConfig;
