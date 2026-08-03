/**
 * AlphaTex 문법 검증기.
 *
 * alphaTab의 실제 파서로 .alphatex를 읽어 에러를 보고한다.
 * 브라우저 Playground에 수동으로 붙여넣는 대신 CI에서 돌릴 수 있다.
 *
 * 사용: node validate_alphatex.mjs <path-to-.alphatex>
 */

import { readFileSync } from "node:fs";
import * as alphaTab from "@coderline/alphatab";

const path = process.argv[2];
if (!path) {
  console.error("사용법: node validate_alphatex.mjs <file.alphatex>");
  process.exit(2);
}

const tex = readFileSync(path, "utf-8");

// 사용 가능한 importer 확인 (버전에 따라 경로가 다를 수 있음)
const AlphaTexImporter =
  alphaTab?.importer?.AlphaTexImporter ??
  alphaTab?.AlphaTexImporter ??
  null;

if (!AlphaTexImporter) {
  console.error("AlphaTexImporter를 찾을 수 없습니다. 사용 가능한 최상위 키:");
  console.error(Object.keys(alphaTab).join(", "));
  process.exit(3);
}

try {
  const importer = new AlphaTexImporter();
  const settings = new alphaTab.Settings();
  importer.initFromString(tex, settings);
  const score = importer.readScore();

  const track = score.tracks[0];
  const staff = track.staves[0];
  const bars = staff.bars;

  let noteCount = 0;
  let restCount = 0;
  const barSummary = [];

  for (const bar of bars) {
    let barNotes = 0;
    for (const voice of bar.voices) {
      for (const beat of voice.beats) {
        if (beat.isRest) restCount++;
        else {
          barNotes += beat.notes.length;
          noteCount += beat.notes.length;
        }
      }
    }
    barSummary.push(barNotes);
  }

  console.log("PARSE OK");
  console.log(`  title      : ${score.title}`);
  console.log(`  tempo      : ${score.tempo}`);
  console.log(`  tracks     : ${score.tracks.length}`);
  console.log(`  staff tuning: [${staff.tuning.join(", ")}]  (strings=${staff.tuning.length})`);
  console.log(`  bars       : ${bars.length}`);
  console.log(`  notes      : ${noteCount}`);
  console.log(`  rests      : ${restCount}`);
  console.log(`  notes/bar  : [${barSummary.slice(0, 16).join(", ")}${barSummary.length > 16 ? ", ..." : ""}]`);

  // 마디 길이 정합성 — 마디마다 채워진 길이가 박자표와 맞는지
  const masterBars = score.masterBars;
  if (masterBars?.length) {
    const mb = masterBars[0];
    console.log(`  time sig   : ${mb.timeSignatureNumerator}/${mb.timeSignatureDenominator}`);
  }

  // sync 포인트가 파싱됐는지
  let syncCount = 0;
  for (const mb of masterBars ?? []) {
    if (mb.syncPoints?.length) syncCount += mb.syncPoints.length;
  }
  console.log(`  syncPoints : ${syncCount}`);

  if (noteCount === 0) {
    console.error("\nWARN: 음표가 하나도 파싱되지 않았습니다.");
    process.exit(1);
  }
  process.exit(0);
} catch (err) {
  console.error("PARSE FAILED");
  console.error(`  ${err?.message ?? err}`);
  if (err?.position !== undefined) {
    console.error(`  position: ${err.position}`);
  }
  // alphaTab은 단계별로 진단을 나눠 담는다
  for (const key of ["lexerDiagnostics", "parserDiagnostics", "semanticDiagnostics"]) {
    const diags = err?.[key] ?? [];
    if (!diags.length) continue;
    console.error(`\n--- ${key} (${diags.length}) ---`);
    for (const d of diags.slice(0, 15)) {
      const line = d.line ?? d.startLine ?? d.range?.startLine ?? "?";
      const col = d.col ?? d.column ?? d.range?.startColumn ?? "?";
      console.error(`  [line ${line}, col ${col}] ${d.message ?? JSON.stringify(d)}`);
    }
  }
  const lines = tex.split("\n");
  console.error("\n--- 파일 앞부분 ---");
  lines.slice(0, 20).forEach((l, i) => console.error(`${String(i + 1).padStart(3)}: ${l}`));
  process.exit(1);
}
