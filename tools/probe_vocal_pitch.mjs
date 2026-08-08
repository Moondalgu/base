/**
 * 오선 전용(보컬) 트랙의 음이름 표기 실측.
 *
 * `c4.4`가 "C4 음의 4분음표"로 모델에 들어가는지 — 피치(realValue)와
 * duration을 트랙별로 직접 읽는다. P5에서 "파싱은 통과했지만 무엇을
 * 뜻하는지 확인 안 됨"으로 남겨둔 항목.
 *
 * 사용: cd apps/web && node ../../tools/probe_vocal_pitch.mjs <file.alphatex>
 */

import { readFileSync } from "node:fs";
import * as alphaTab from "@coderline/alphatab";

const path = process.argv[2];
const tex = readFileSync(path, "utf8");

const importer = new alphaTab.importer.AlphaTexImporter();
importer.initFromString(tex, new alphaTab.Settings());
const score = importer.readScore();

console.log(`트랙 ${score.tracks.length}개`);
for (const track of score.tracks) {
  const staff = track.staves[0];
  console.log(
    `- ${track.name}: staves=${track.staves.length} ` +
    `showStd=${staff.showStandardNotation} showTab=${staff.showTablature} ` +
    `tuning=${staff.tuning?.length ?? 0}현`
  );
  let printed = 0;
  for (const bar of staff.bars) {
    for (const voice of bar.voices) {
      for (const beat of voice.beats) {
        if (printed >= 8) break;
        const notes = beat.notes.map((n) =>
          `rv=${n.realValue}(str=${n.string},fret=${n.fret},oct=${n.octave},tone=${n.tone})`
        );
        const lyr = beat.lyrics && beat.lyrics.length
          ? ` lyrics=[${beat.lyrics.join(",")}]` : "";
        console.log(
          `    bar${bar.index} beat dur=${beat.duration} ` +
          (beat.isRest ? "rest" : notes.join(" ")) + lyr
        );
        printed++;
      }
    }
    if (printed >= 8) break;
  }
}
