/**
 * 파싱된 악보 모델에서 표기 요소를 읽는다.
 *
 * 문법이 통과해도 실제로 모델에 반영되는지는 별개다. 파서가 무시하는 지시자면
 * 조용히 기본값으로 남는다(`\clef`가 그랬다). 그래서 모델을 직접 본다.
 *
 * probe_clef.mjs가 음자리표만 보던 것을 조표·트랙·코드 심볼·가사·효과까지
 * 넓힌 것이다. 3단 악보(보컬 오선 + 베이스 오선 + TAB)를 만들려면 이 요소들이
 * 실제로 적용되는지 먼저 확인해야 한다.
 *
 * 사용: node probe_notation.mjs <file.alphatex>
 */

import { readFileSync } from "node:fs";
import * as alphaTab from "@coderline/alphatab";

const path = process.argv[2];
if (!path) {
  console.error("사용법: node probe_notation.mjs <file.alphatex>");
  process.exit(2);
}

const AlphaTexImporter =
  alphaTab?.importer?.AlphaTexImporter ?? alphaTab?.AlphaTexImporter ?? null;
if (!AlphaTexImporter) {
  console.error("AlphaTexImporter를 찾을 수 없습니다.");
  process.exit(3);
}

const model = alphaTab.model ?? alphaTab;
const nameOf = (enumObj, value) =>
  enumObj
    ? (Object.keys(enumObj).find((k) => enumObj[k] === value) ?? String(value))
    : String(value);

let score;
try {
  const importer = new AlphaTexImporter();
  importer.initFromString(readFileSync(path, "utf-8"), new alphaTab.Settings());
  score = importer.readScore();
} catch (e) {
  console.log(`PARSE FAIL: ${e?.message ?? e}`);
  process.exit(1);
}

console.log("PARSE OK");
console.log(`  title   : ${score.title}`);
console.log(`  tracks  : ${score.tracks.length}`);

// 조표는 마디(MasterBar/Bar) 단위로 붙는다. 첫 마디를 본다.
const mb = score.masterBars?.[0];
if (mb) {
  console.log(
    `  keySig  : ${nameOf(model.KeySignature, mb.keySignature)} (raw=${mb.keySignature})` +
      ` type=${nameOf(model.KeySignatureType, mb.keySignatureType)}`
  );
}

for (const track of score.tracks) {
  console.log(`  track "${track.name}" — staff ${track.staves.length}개`);
  track.staves.forEach((staff, si) => {
    const bar = staff.bars[0];
    console.log(
      `    staff${si}: score=${staff.showStandardNotation} tab=${staff.showTablature}` +
        ` clef=${nameOf(model.Clef, bar?.clef)}` +
        ` strings=${staff.tuning?.length ?? 0}` +
        ` tuning=[${staff.tuning?.join(",") ?? "-"}]`
    );
  });

  // 코드 심볼 — 트랙에 정의된 코드와 비트에 붙은 코드 아이디를 본다
  const chordIds = [];
  const chordMap = track.chords;
  if (chordMap && typeof chordMap.forEach === "function") {
    chordMap.forEach((chord, id) => chordIds.push(`${id}:${chord?.name ?? "?"}`));
  }
  console.log(`    chords 정의: ${chordIds.length ? chordIds.join(" ") : "없음"}`);

  const beatChords = [];
  const lyricNotes = [];
  const effects = new Set();
  for (const staff of track.staves) {
    for (const bar of staff.bars) {
      for (const voice of bar.voices) {
        for (const beat of voice.beats) {
          if (beat.chordId) beatChords.push(`bar${bar.index}:${beat.chordId}`);
          if (beat.lyrics && beat.lyrics.length) {
            lyricNotes.push(`bar${bar.index}:${beat.lyrics.join("/")}`);
          }
          for (const note of beat.notes) {
            if (note.slideOutType) {
              effects.add(`slideOut=${nameOf(model.SlideOutType, note.slideOutType)}`);
            }
            if (note.slideInType) {
              effects.add(`slideIn=${nameOf(model.SlideInType, note.slideInType)}`);
            }
            if (note.isHammerPullOrigin) effects.add("hammerPull");
            if (note.isStaccato) effects.add("staccato");
          }
        }
      }
    }
  }
  console.log(`    비트 코드  : ${beatChords.length ? beatChords.slice(0, 6).join(" ") : "없음"}`);
  console.log(`    가사       : ${lyricNotes.length ? lyricNotes.slice(0, 8).join(" ") : "없음"}`);
  console.log(`    효과       : ${effects.size ? [...effects].join(" ") : "없음"}`);
}
