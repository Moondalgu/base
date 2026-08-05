/**
 * 파싱된 악보 모델에서 음자리표를 읽는다.
 *
 * 문법이 통과해도 실제로 낮은음자리표로 그려지는지는 별개다. 파서가 무시하는
 * 지시자면 조용히 기본값(높은음자리표)으로 남는다. 그래서 모델을 직접 본다.
 *
 * 사용: node probe_clef.mjs <file.alphatex>
 */

import { readFileSync } from "node:fs";
import * as alphaTab from "@coderline/alphatab";

const path = process.argv[2];
if (!path) {
  console.error("사용법: node probe_clef.mjs <file.alphatex>");
  process.exit(2);
}

const AlphaTexImporter =
  alphaTab?.importer?.AlphaTexImporter ?? alphaTab?.AlphaTexImporter ?? null;
if (!AlphaTexImporter) {
  console.error("AlphaTexImporter를 찾을 수 없습니다.");
  process.exit(3);
}

const importer = new AlphaTexImporter();
importer.initFromString(readFileSync(path, "utf-8"), new alphaTab.Settings());
const score = importer.readScore();

const clefNames = alphaTab.model?.Clef ?? alphaTab.Clef ?? {};
const nameOf = (v) =>
  Object.keys(clefNames).find((k) => clefNames[k] === v) ?? String(v);

for (const track of score.tracks) {
  console.log(`track "${track.name}" — staff ${track.staves.length}개`);
  track.staves.forEach((staff, si) => {
    const bar = staff.bars[0];
    console.log(
      `  staff${si}: showStandardNotation=${staff.showStandardNotation}` +
        ` showTablature=${staff.showTablature}` +
        ` clef=${nameOf(bar?.clef)}` +
        ` clefOttava=${bar?.clefOttava ?? "-"}` +
        ` tuning=[${staff.tuning?.join(", ") ?? "-"}]`
    );
  });
}
