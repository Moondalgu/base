/** AlphaTex 문법 요소를 하나씩 켜보며 무엇이 거부되는지 찾는다. */
import * as alphaTab from "@coderline/alphatab";

const HEAD = `\\title "t"
\\tempo 120
.

\\track "Bass"
\\staff{tabs} \\tuning E1 A1 D2 G2
\\ts 4 4

`;

const CASES = {
  "r.8 두개": `0.4.4 r.8 r.8 0.4.4 0.4.4`,
  "r.16 네개": `0.4.4 r.16 r.16 r.16 r.16 0.4.4 0.4.4`,
  "타이 -.8 (쉼표없음)": `0.4.4 -.8 -.8 0.4.4 0.4.4`,
  "타이 -.8 짧은음뒤": `0.4.8 -.8 0.4.4 0.4.4 0.4.4`,
  "타이 -.16": `0.4.8 -.16 -.16 0.4.4 0.4.4 0.4.4`,
  "타이 -.2": `0.4.2 -.2`,
  "타이 두번 -.4": `0.4.4 -.4 -.4 -.4`,
  "점음표 0.4.4{d}": `0.4.4{d} 0.4.8 0.4.4 0.4.4`,
  "타이없이 쉼표패딩": `0.4.8 r.16 r.16 0.4.4 0.4.4 0.4.4`,
};

const AlphaTexImporter = alphaTab.importer.AlphaTexImporter;

for (const [name, body] of Object.entries(CASES)) {
  const tex = HEAD + body;
  try {
    const imp = new AlphaTexImporter();
    imp.initFromString(tex, new alphaTab.Settings());
    const score = imp.readScore();
    const bars = score.tracks[0].staves[0].bars;
    let notes = 0;
    for (const bar of bars)
      for (const v of bar.voices) for (const b of v.beats) notes += b.notes.length;
    console.log(`OK    ${name.padEnd(24)} bars=${bars.length} notes=${notes}`);
  } catch (e) {
    console.log(`FAIL  ${name.padEnd(24)} ${e?.message ?? e}`);
  }
}
